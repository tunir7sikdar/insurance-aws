import json
import logging
import os
from datetime import datetime
from typing import Dict, Any

import boto3
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.utilities.data_classes.s3_event import S3Event

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
glue = boto3.client("glue")

logger = Logger()
tracer = Tracer()
metrics = Metrics()

AUDIT_TABLE_NAME = os.getenv("DYNAMODB_AUDIT_TABLE", "file_ingestion_audit")
DECRYPT_JOB_NAME = os.getenv("DECRYPT_JOB_NAME", "decrypt-and-convert-csv-dev")


class FileIngestionAuditor:
    def __init__(self, table_name: str):
        self.table = dynamodb.Table(table_name)

    def create_audit_entry(
        self,
        bucket: str,
        key: str,
        file_type: str,
        cycle_date: str,
    ) -> Dict[str, Any]:
        try:
            timestamp = datetime.utcnow().isoformat()
            audit_entry = {
                "file_key": f"{bucket}#{key}",
                "cycle_date": cycle_date,
                "bucket": bucket,
                "object_key": key,
                "file_type": file_type,
                "file_name": key.split("/")[-1],
                "ingestion_timestamp": timestamp,
                "status": "RECEIVED",
                "file_size": self._get_file_size(bucket, key),
                "created_at": timestamp,
                "updated_at": timestamp,
            }

            self.table.put_item(Item=audit_entry)

            logger.info(f"Audit entry created for {file_type} file: {key} (cycle: {cycle_date})")

            return audit_entry

        except Exception as e:
            logger.error(f"Failed to create audit entry: {str(e)}")
            raise

    def _get_file_size(self, bucket: str, key: str) -> int:
        try:
            response = s3.head_object(Bucket=bucket, Key=key)
            return response["ContentLength"]
        except Exception as e:
            logger.warning(f"Could not get file size: {str(e)}")
            return 0

    def check_cycle_complete(self, cycle_date: str, expected_files: list) -> bool:
        try:
            response = self.table.query(
                KeyConditionExpression="cycle_date = :cd",
                ExpressionAttributeValues={":cd": cycle_date},
            )

            received_files = {item["file_type"] for item in response["Items"]}
            expected_set = set(expected_files)

            is_complete = expected_set.issubset(received_files)

            logger.info(f"Cycle {cycle_date}: complete={is_complete}, received={len(received_files)}/{len(expected_set)}")
            return is_complete

        except Exception as e:
            logger.error(f"Failed checking cycle completion: {str(e)}")
            raise

    def trigger_glue_job(self, cycle_date: str, **job_args) -> str:
        try:
            run_args = {
                "--cycle_date": cycle_date,
                **job_args,
            }

            response = glue.start_job_run(
                JobName=DECRYPT_JOB_NAME,
                Arguments=run_args,
            )

            job_run_id = response["JobRunId"]
            logger.info(f"Glue job triggered: {DECRYPT_JOB_NAME} (run: {job_run_id}, cycle: {cycle_date})")
            return job_run_id

        except Exception as e:
            logger.error(f"Failed to trigger Glue job: {str(e)}")
            raise

    def update_audit_status(
        self,
        bucket: str,
        key: str,
        cycle_date: str,
        status: str,
    ) -> None:
        try:
            self.table.update_item(
                Key={
                    "file_key": f"{bucket}#{key}",
                    "cycle_date": cycle_date,
                },
                UpdateExpression="SET #status = :s, updated_at = :ts",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":s": status,
                    ":ts": datetime.utcnow().isoformat(),
                },
            )
            logger.debug(f"Updated {key} status to {status}")

        except Exception as e:
            logger.error(f"Failed to update audit status: {str(e)}")
            raise


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        # Parse S3 event
        s3_event = S3Event(event)

        auditor = FileIngestionAuditor(AUDIT_TABLE_NAME)
        processed_files = []

        for record in s3_event.records:
            bucket = record.s3.bucket.name
            key = record.s3.object.key

            # Extract cycle date and file type from S3 path
            # Assuming path like: raw/transactions/cycle_20240101/transactions.csv
            path_parts = key.split("/")
            if len(path_parts) >= 3:
                file_type = path_parts[1]
                cycle_info = path_parts[2]  # e.g., cycle_20240101
                cycle_date = cycle_info.replace("cycle_", "")

                # Create audit entry
                audit_entry = auditor.create_audit_entry(
                    bucket=bucket,
                    key=key,
                    file_type=file_type,
                    cycle_date=cycle_date,
                )

                processed_files.append(
                    {
                        "file": key,
                        "type": file_type,
                        "cycle_date": cycle_date,
                        "status": "AUDITED",
                    }
                )

                # Check if cycle is complete
                expected_files = ["transactions", "policy", "coverage", 
                                "feature", "exchange", "rider"]
                if auditor.check_cycle_complete(cycle_date, expected_files):
                    job_run_id = auditor.trigger_glue_job(cycle_date)
                    logger.info(f"Glue job triggered: {job_run_id}")

        metrics.add_metadata("processed_files", len(processed_files))

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "File ingestion audit completed",
                "files_processed": len(processed_files),
                "details": processed_files,
            }),
        }

    except Exception as e:
        logger.exception(f"Error processing S3 event: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


if __name__ == "__main__":
    # For local testing
    test_event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {
                        "key": "raw/transactions/cycle_20240101/transactions.csv"
                    },
                }
            }
        ]
    }

    print(lambda_handler(test_event, None))

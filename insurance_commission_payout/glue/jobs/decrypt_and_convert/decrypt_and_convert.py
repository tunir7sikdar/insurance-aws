"""Glue Job 1: Decrypt PGP files and convert CSV to Parquet format."""

import sys
import logging
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.dynamicframe import DynamicFrame
import boto3
import os
from datetime import datetime

# Add shared utilities to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from utils.pgp_decryption import PGPDecryptor
from utils.kms_handler import KMSHandler
from config.config import (
    S3_RAW_PATH,
    S3_PARQUET_PATH,
    KMS_KEY_ID,
    GLUE_DATABASE,
    EXPECTED_FILES,
    PGP_PRIVATE_KEY_SECRET,
    PGP_PASSPHRASE_SECRET,
)

# Initialize logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize AWS services
s3_client = boto3.client("s3")
secretsmanager = boto3.client("secretsmanager")

# Get Glue arguments
args = getResolvedOptions(sys.argv, ["JOB_NAME", "cycle_date"])

# Initialize Glue context
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

cycle_date = args["cycle_date"]

logger.info(f"Starting decrypt_and_convert job for cycle_date: {cycle_date}")


class CSVDecryptor:
    """Handle CSV file decryption and conversion."""

    def __init__(self, kms_key_id: str):
        """Initialize decryptor."""
        self.kms_handler = KMSHandler(kms_key_id)
        self.s3_client = s3_client

    def get_pgp_credentials(self) -> tuple:
        """
        Retrieve PGP credentials from Secrets Manager.

        Returns:
            tuple: (private_key_pem, passphrase)
        """
        try:
            # Get private key from Secrets Manager
            private_key_response = secretsmanager.get_secret_value(
                SecretId=PGP_PRIVATE_KEY_SECRET
            )
            private_key = private_key_response.get(
                "SecretString", private_key_response.get("SecretBinary")
            )

            # Get passphrase from Secrets Manager
            passphrase_response = secretsmanager.get_secret_value(
                SecretId=PGP_PASSPHRASE_SECRET
            )
            passphrase = passphrase_response.get(
                "SecretString", passphrase_response.get("SecretBinary")
            )

            logger.info("Successfully retrieved PGP credentials from Secrets Manager")
            return private_key, passphrase

        except Exception as e:
            logger.error(f"Failed to retrieve PGP credentials: {str(e)}")
            raise

    def decrypt_and_convert_csv(
        self, bucket: str, encrypted_key: str, file_type: str, output_path: str
    ) -> bool:
        """
        Decrypt PGP file and convert CSV to Parquet.

        Args:
            bucket: S3 bucket
            encrypted_key: S3 key of encrypted file
            file_type: Type of file (transactions, policy, etc.)
            output_path: S3 path for output Parquet file

        Returns:
            bool: Success status
        """
        try:
            logger.info(f"Processing {file_type} file: {encrypted_key}")

            # Get PGP credentials
            private_key, passphrase = self.get_pgp_credentials()

            # Download encrypted file from S3
            local_encrypted_file = f"/tmp/{file_type}_encrypted.pgp"
            self.s3_client.download_file(bucket, encrypted_key, local_encrypted_file)

            logger.info(f"Downloaded encrypted file to {local_encrypted_file}")

            # Decrypt file
            pgp_decryptor = PGPDecryptor(local_encrypted_file, passphrase)
            decrypted_csv_path = f"/tmp/{file_type}_decrypted.csv"

            # Read decrypted content and convert to Parquet
            decrypted_content = pgp_decryptor.decrypt_content(
                open(local_encrypted_file, "rb").read()
            )

            # Write decrypted CSV
            with open(decrypted_csv_path, "w") as f:
                f.write(decrypted_content)

            logger.info(f"Decrypted file to {decrypted_csv_path}")

            # Read CSV using Spark
            df = spark.read.option("header", "true").option("inferSchema", "true").csv(
                decrypted_csv_path
            )

            # Add metadata columns
            df = df.withColumn("ingestion_date", 
                             F.lit(datetime.now())) \
                   .withColumn("cycle_date", F.lit(cycle_date)) \
                   .withColumn("file_type", F.lit(file_type))

            # Write to Parquet
            df.coalesce(1).write.mode("overwrite").parquet(output_path)

            logger.info(f"Successfully converted {file_type} CSV to Parquet at {output_path}")

            # Clean up local files
            os.remove(local_encrypted_file)
            os.remove(decrypted_csv_path)

            return True

        except Exception as e:
            logger.error(f"Failed to decrypt and convert {file_type}: {str(e)}")
            raise

    def process_cycle_files(self) -> list:
        """
        Process all files for a cycle.

        Returns:
            list: List of processed file types
        """
        try:
            processed_files = []

            # List all files in cycle folder
            cycle_prefix = f"raw/{cycle_date}/"
            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=S3_RAW_PATH.replace("s3://", ""), 
                                      Prefix=cycle_prefix)

            for page in pages:
                if "Contents" not in page:
                    continue

                for obj in page["Contents"]:
                    key = obj["Key"]

                    # Skip directories
                    if key.endswith("/"):
                        continue

                    # Determine file type
                    for file_type in EXPECTED_FILES:
                        if file_type in key.lower():
                            output_path = f"{S3_PARQUET_PATH}{file_type}/{cycle_date}/"

                            self.decrypt_and_convert_csv(
                                bucket=S3_RAW_PATH.replace("s3://", ""),
                                encrypted_key=key,
                                file_type=file_type,
                                output_path=output_path,
                            )

                            processed_files.append(file_type)
                            break

            logger.info(f"Processed files: {processed_files}")
            return processed_files

        except Exception as e:
            logger.error(f"Failed to process cycle files: {str(e)}")
            raise


# Main execution
try:
    decryptor = CSVDecryptor(KMS_KEY_ID)
    processed_files = decryptor.process_cycle_files()

    logger.info(
        f"Decrypt and convert job completed successfully. "
        f"Processed {len(processed_files)} files"
    )

    job.commit()

except Exception as e:
    logger.error(f"Glue job failed: {str(e)}")
    job.commit()
    sys.exit(1)

"""Glue Job 1b: Data quality checks on Parquet files before transformation."""

import json
import logging
import os
import sys
from datetime import datetime

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from config.config import DQ_RULES, EXPECTED_FILES, S3_BUCKET, S3_PARQUET_PATH, ENV
from utils.dq_checks import DataQualityChecker, DQException, DQResult

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

args = getResolvedOptions(sys.argv, ["JOB_NAME", "cycle_date"])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

cycle_date: str = args["cycle_date"]
s3_client = boto3.client("s3")

logger.info("Starting dq_check job for cycle_date: %s", cycle_date)


def _write_report(report: dict, cycle_date: str) -> None:
    key = f"dq_reports/{ENV}/{cycle_date}/report.json"
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(report, indent=2, default=str),
        ContentType="application/json",
    )
    logger.info("DQ report written to s3://%s/%s", S3_BUCKET, key)


def run_dq_checks(cycle_date: str) -> None:
    all_results: list[DQResult] = []

    for table in EXPECTED_FILES:
        path = f"{S3_PARQUET_PATH}{table}/{cycle_date}/"
        try:
            df = spark.read.parquet(path)
        except Exception as exc:
            logger.error("Could not load parquet for table '%s': %s", table, exc)
            raise

        rules = DQ_RULES.get(table, {})
        if not rules:
            logger.warning("No DQ rules defined for table '%s' — skipping", table)
            continue

        results = DataQualityChecker.run_all_checks(df, table, rules)
        all_results.extend(results)

    report = DataQualityChecker.to_report(all_results)
    report["cycle_date"] = cycle_date
    report["generated_at"] = datetime.utcnow().isoformat()

    _write_report(report, cycle_date)
    DataQualityChecker.assert_no_failures(all_results)


try:
    run_dq_checks(cycle_date)
    logger.info("DQ checks passed for cycle_date: %s", cycle_date)
except DQException as exc:
    logger.error("DQ checks FAILED: %s", exc)
    raise
finally:
    job.commit()

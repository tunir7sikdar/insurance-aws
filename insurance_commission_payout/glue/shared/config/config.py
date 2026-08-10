"""Configuration management for commission payout pipeline."""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass

import yaml

_CONFIG_PATH = Path(__file__).parent / "config.yaml"

with _CONFIG_PATH.open() as _f:
    _cfg: Dict[str, Any] = yaml.safe_load(_f)

# Runtime environment — env vars take precedence over YAML defaults
ENV = os.getenv("ENV", "dev")
REGION = os.getenv("AWS_REGION", _cfg["aws"]["region"])

S3_BUCKET = os.getenv("S3_BUCKET_NAME", _cfg["s3"]["bucket"])
S3_RAW_PATH = f"s3://{S3_BUCKET}/raw/{ENV}/"
S3_PARQUET_PATH = f"s3://{S3_BUCKET}/parquet/{ENV}/"
S3_ICEBERG_PATH = f"s3://{S3_BUCKET}/iceberg/{ENV}/"

LAMBDA_ROLE_ARN = os.getenv("LAMBDA_ROLE_ARN")
GLUE_ROLE_ARN = os.getenv("GLUE_ROLE_ARN")
KMS_KEY_ID = os.getenv("KMS_KEY_ID")
DYNAMODB_AUDIT_TABLE = os.getenv("DYNAMODB_AUDIT_TABLE", _cfg["dynamodb"]["audit_table"])

PGP_PRIVATE_KEY_SECRET = os.getenv("PGP_PRIVATE_KEY_SECRET", _cfg["secrets"]["pgp_private_key"])
PGP_PASSPHRASE_SECRET = os.getenv("PGP_PASSPHRASE_SECRET", _cfg["secrets"]["pgp_passphrase"])

GLUE_CATALOG = _cfg["glue"]["catalog"]
GLUE_DATABASE = os.getenv("GLUE_DATABASE", f"{_cfg['glue']['database_prefix']}_{ENV}")

EXPECTED_FILES: list = _cfg["expected_files"]
PRIMARY_KEYS: Dict[str, list] = _cfg["primary_keys"]


@dataclass
class GlueJobConfig:
    """Configuration for Glue jobs."""

    name: str
    role: str
    timeout: int = 2880  # 48 hours
    max_retries: int = 1
    worker_type: str = "G.2X"
    num_workers: int = 10
    glue_version: str = "4.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Name": self.name,
            "Role": self.role,
            "Timeout": self.timeout,
            "MaxRetries": self.max_retries,
            "WorkerType": self.worker_type,
            "NumberOfWorkers": self.num_workers,
            "GlueVersion": self.glue_version,
        }


def _make_job_config(job_key: str) -> GlueJobConfig:
    jcfg = _cfg["glue_jobs"][job_key]
    return GlueJobConfig(
        name=f"{jcfg['name_suffix']}-{ENV}",
        role=GLUE_ROLE_ARN,
        timeout=jcfg["timeout"],
        max_retries=jcfg["max_retries"],
        worker_type=jcfg["worker_type"],
        num_workers=jcfg["num_workers"],
        glue_version=jcfg["glue_version"],
    )


DECRYPT_AND_CONVERT_JOB_CONFIG = _make_job_config("decrypt_and_convert")
DQ_CHECK_JOB_CONFIG = _make_job_config("dq_check")
TRANSFORM_AND_MERGE_JOB_CONFIG = _make_job_config("transform_and_merge")

DQ_RULES: Dict[str, Any] = _cfg["dq_rules"]


def get_config(key: str, default: Optional[str] = None) -> str:
    return os.getenv(key, default)

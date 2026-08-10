"""AWS KMS utilities."""

import logging
import base64
from typing import Optional
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class KMSHandler:
    def __init__(self, kms_key_id: str, region: str = "us-east-1"):
        self.kms_key_id = kms_key_id
        self.kms = boto3.client("kms", region_name=region)

    def encrypt(self, plaintext: str) -> str:
        try:
            response = self.kms.encrypt(
                KeyId=self.kms_key_id, Plaintext=plaintext.encode()
            )
            return base64.b64encode(response["CiphertextBlob"]).decode()
        except ClientError as e:
            logger.error(f"KMS encryption failed: {str(e)}")
            raise

    def decrypt(self, encrypted_data: str) -> str:
        try:
            response = self.kms.decrypt(CiphertextBlob=base64.b64decode(encrypted_data))
            return response["Plaintext"].decode()
        except ClientError as e:
            logger.error(f"KMS decryption failed: {str(e)}")
            raise

    def get_secret(self, secret_name: str) -> str:
        try:
            sm = boto3.client("secretsmanager")
            response = sm.get_secret_value(SecretId=secret_name)

            if "SecretString" in response:
                return response["SecretString"]
            else:
                return base64.b64decode(response["SecretBinary"]).decode()

        except ClientError as e:
            logger.error(f"Failed retrieving secret {secret_name}: {str(e)}")
            raise

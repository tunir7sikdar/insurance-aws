"""PGP decryption utilities."""

import logging
from pathlib import Path
from typing import Optional
import pgpy

logger = logging.getLogger(__name__)


class PGPDecryptor:
    def __init__(self, private_key_path: str, passphrase: Optional[str] = None):
        self.private_key_path = Path(private_key_path)
        self.passphrase = passphrase
        self.private_key = self._load_private_key()

    def _load_private_key(self):
        try:
            with open(self.private_key_path, "r") as f:
                key = pgpy.PGPKey()
                key.parse(f.read())

            if self.passphrase:
                with key.unlock(self.passphrase):
                    logger.info("Private key loaded")
            else:
                logger.info("Private key loaded (no passphrase)")

            return key
        except FileNotFoundError as e:
            logger.error(f"Private key not found: {self.private_key_path}")
            raise
        except Exception as e:
            logger.error(f"Failed loading private key: {str(e)}")
            raise

    def decrypt_file(self, encrypted_file_path: str, output_file_path: str) -> bool:
        try:
            with open(encrypted_file_path, "rb") as f:
                encrypted_message = pgpy.PGPMessage.from_blob(f.read())

            with self.private_key.unlock(self.passphrase):
                decrypted_message = self.private_key.decrypt(encrypted_message)

            with open(output_file_path, "wb") as f:
                f.write(bytes(decrypted_message))

            logger.info(f"Decrypted: {encrypted_file_path} -> {output_file_path}")
            return True

        except Exception as e:
            logger.error(f"Decryption failed: {encrypted_file_path} ({str(e)})")
            raise

    def decrypt_content(self, encrypted_content: bytes) -> str:
        try:
            encrypted_message = pgpy.PGPMessage.from_blob(encrypted_content)

            with self.private_key.unlock(self.passphrase):
                decrypted_message = self.private_key.decrypt(encrypted_message)

            return str(decrypted_message)

        except Exception as e:
            logger.error(f"Content decryption failed: {str(e)}")
            raise

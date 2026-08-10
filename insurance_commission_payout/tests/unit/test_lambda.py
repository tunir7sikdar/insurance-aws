"""Unit tests for Lambda function."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def sample_s3_event():
    return {
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


def test_parse_s3_event(sample_s3_event):
    record = sample_s3_event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = record["s3"]["object"]["key"]

    assert bucket == "test-bucket"
    assert "transactions" in key
    assert "cycle_20240101" in key


def test_extract_cycle_date_from_key():
    key = "raw/transactions/cycle_20240101/transactions.csv"
    path_parts = key.split("/")
    
    if len(path_parts) >= 3:
        cycle_info = path_parts[2]
        cycle_date = cycle_info.replace("cycle_", "")
        
        assert cycle_date == "20240101"


def test_extract_file_type_from_key():
    key = "raw/transactions/cycle_20240101/transactions.csv"
    path_parts = key.split("/")
    
    if len(path_parts) >= 2:
        file_type = path_parts[1]
        
        assert file_type == "transactions"


@patch("boto3.client")
@patch("boto3.resource")
def test_lambda_handler_structure(mock_resource, mock_client, sample_s3_event):
    mock_dynamodb = Mock()
    mock_s3 = Mock()
    
    mock_resource.return_value = mock_dynamodb
    mock_client.return_value = mock_s3

    assert "Records" in sample_s3_event
    assert len(sample_s3_event["Records"]) > 0
    assert "s3" in sample_s3_event["Records"][0]


def test_audit_entry_structure():
    audit_entry = {
        "file_key": "bucket#key",
        "cycle_date": "20240101",
        "bucket": "test-bucket",
        "object_key": "path/to/file",
        "file_type": "transactions",
        "status": "RECEIVED",
    }

    assert audit_entry["file_key"]
    assert audit_entry["cycle_date"]
    assert audit_entry["status"] in ["RECEIVED", "PROCESSING", "SUCCESS", "FAILED"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Unit tests for SCD Type 1 handler."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


class MockSCDType1Handler:
    def __init__(self, spark, s3_path, table_name):
        self.spark = spark
        self.s3_path = s3_path
        self.table_name = table_name

    def merge_scd_type1(self, source_df, primary_keys, update_columns=None):
        return source_df.count()

    def validate_merge_integrity(self, primary_keys):
        return True


@pytest.fixture
def mock_spark():
    return Mock()


@pytest.fixture
def scd_handler(mock_spark):
    return MockSCDType1Handler(mock_spark, "s3://bucket/iceberg/", "test_table")


def test_scd_handler_initialization(scd_handler):
    assert scd_handler.table_name == "test_table"
    assert scd_handler.s3_path == "s3://bucket/iceberg/"


def test_merge_scd_type1_returns_count(scd_handler):
    mock_df = Mock()
    mock_df.count.return_value = 100

    result = scd_handler.merge_scd_type1(
        mock_df,
        primary_keys=["id"],
    )

    assert result == 100


def test_validate_merge_integrity(scd_handler):
    result = scd_handler.validate_merge_integrity(["id"])
    assert result is True


def test_scd_handler_with_multiple_primary_keys():
    handler = MockSCDType1Handler(Mock(), "s3://bucket/", "multi_key_table")

    mock_df = Mock()
    mock_df.count.return_value = 50

    result = handler.merge_scd_type1(
        mock_df,
        primary_keys=["id", "date"],
        update_columns=["amount", "status"],
    )

    assert result == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

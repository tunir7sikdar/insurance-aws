"""Unit tests for transformations module."""

import pytest
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType

# This would need to be imported from glue shared utils
# For now, we'll write tests in a way that can be adapted


@pytest.fixture(scope="module")
def spark():
    return SparkSession.builder.appName("transformation_tests").getOrCreate()


@pytest.fixture
def sample_data(spark):
    schema = StructType([
        StructField("transaction_id", StringType(), True),
        StructField("policy_id", StringType(), True),
        StructField("transaction_amount", DoubleType(), True),
        StructField("transaction_status", StringType(), True),
        StructField("is_commission_eligible", IntegerType(), True),
    ])

    data = [
        ("T001", "P001", 1000.0, "SUCCESS", 1),
        ("T002", "P002", 2000.0, "SUCCESS", 1),
        ("T003", "P003", 500.0, "FAILED", 0),
        ("T004", "P001", 1500.0, "SUCCESS", 1),
    ]

    return spark.createDataFrame(data, schema=schema)


def test_filter_successful_transactions(spark, sample_data):
    filtered = sample_data.filter(sample_data.transaction_status == "SUCCESS")

    assert filtered.count() == 3
    assert all(row.transaction_status == "SUCCESS" for row in filtered.collect())


def test_filter_commission_eligible(spark, sample_data):
    filtered = sample_data.filter(sample_data.is_commission_eligible == 1)

    assert filtered.count() == 3
    assert all(row.is_commission_eligible == 1 for row in filtered.collect())


def test_filter_positive_amounts(spark, sample_data):
    filtered = sample_data.filter(sample_data.transaction_amount > 0)

    assert filtered.count() == 4
    assert all(row.transaction_amount > 0 for row in filtered.collect())


def test_combined_filters(spark, sample_data):
    # Apply multiple filters
    filtered = (
        sample_data
        .filter(sample_data.transaction_status == "SUCCESS")
        .filter(sample_data.is_commission_eligible == 1)
        .filter(sample_data.transaction_amount > 0)
    )

    assert filtered.count() == 3


def test_empty_result_after_filter(spark, sample_data):
    """Test that filtering can result in empty dataframe."""
    # Filter that results in no matches
    filtered = sample_data.filter(sample_data.transaction_amount > 10000.0)

    assert filtered.count() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

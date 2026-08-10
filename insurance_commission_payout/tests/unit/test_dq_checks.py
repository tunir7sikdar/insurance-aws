"""Unit tests for DataQualityChecker."""

import pytest
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    DoubleType,
    StringType,
    StructField,
    StructType,
)

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "glue" / "shared"))

from utils.dq_checks import DataQualityChecker, DQException


@pytest.fixture(scope="module")
def spark():
    return SparkSession.builder.master("local").appName("dq_tests").getOrCreate()


@pytest.fixture
def transactions_df(spark):
    schema = StructType([
        StructField("transaction_id", StringType(), True),
        StructField("cycle_date", StringType(), True),
        StructField("transaction_amount", DoubleType(), True),
        StructField("transaction_status", StringType(), True),
    ])
    data = [
        ("T001", "2024-01-01", 1000.0, "SUCCESS"),
        ("T002", "2024-01-01", 2000.0, "FAILED"),
        ("T003", "2024-01-01", 500.0, "SUCCESS"),
    ]
    return spark.createDataFrame(data, schema=schema)


# --- not_null ---

def test_not_null_passes(spark, transactions_df):
    result = DataQualityChecker.check_not_null(transactions_df, "transactions", "transaction_id")
    assert result.passed
    assert result.failing_count == 0


def test_not_null_fails_when_null_present(spark):
    df = spark.createDataFrame([("T1", None), ("T2", "2024-01-01")], ["transaction_id", "cycle_date"])
    result = DataQualityChecker.check_not_null(df, "transactions", "cycle_date")
    assert not result.passed
    assert result.failing_count == 1


# --- no_duplicates ---

def test_no_duplicates_passes(spark, transactions_df):
    result = DataQualityChecker.check_no_duplicates(transactions_df, "transactions", ["transaction_id", "cycle_date"])
    assert result.passed
    assert result.failing_count == 0


def test_no_duplicates_fails_on_duplicate_keys(spark):
    df = spark.createDataFrame(
        [("T001", "2024-01-01"), ("T001", "2024-01-01"), ("T002", "2024-01-01")],
        ["transaction_id", "cycle_date"],
    )
    result = DataQualityChecker.check_no_duplicates(df, "transactions", ["transaction_id", "cycle_date"])
    assert not result.passed
    assert result.failing_count == 1


# --- positive_values ---

def test_positive_values_passes(spark, transactions_df):
    result = DataQualityChecker.check_positive_values(transactions_df, "transactions", "transaction_amount")
    assert result.passed


def test_positive_values_fails_on_zero_or_negative(spark):
    df = spark.createDataFrame([(100.0,), (0.0,), (-50.0,)], ["amount"])
    result = DataQualityChecker.check_positive_values(df, "transactions", "amount")
    assert not result.passed
    assert result.failing_count == 2


# --- allowed_values ---

def test_allowed_values_passes(spark, transactions_df):
    result = DataQualityChecker.check_allowed_values(
        transactions_df, "transactions", "transaction_status", ["SUCCESS", "FAILED", "PENDING"]
    )
    assert result.passed


def test_allowed_values_fails_on_unexpected_value(spark):
    df = spark.createDataFrame([("SUCCESS",), ("UNKNOWN",)], ["status"])
    result = DataQualityChecker.check_allowed_values(df, "transactions", "status", ["SUCCESS", "FAILED"])
    assert not result.passed
    assert result.failing_count == 1


# --- min_row_count ---

def test_min_row_count_passes(spark, transactions_df):
    result = DataQualityChecker.check_min_row_count(transactions_df, "transactions", 1)
    assert result.passed


def test_min_row_count_fails_on_empty_df(spark):
    df = spark.createDataFrame([], StructType([StructField("id", StringType(), True)]))
    result = DataQualityChecker.check_min_row_count(df, "transactions", 1)
    assert not result.passed
    assert result.failing_count == 1


# --- run_all_checks ---

def test_run_all_checks_all_pass(spark, transactions_df):
    rules = {
        "not_null": ["transaction_id", "cycle_date"],
        "no_duplicates": ["transaction_id", "cycle_date"],
        "positive_values": ["transaction_amount"],
        "allowed_values": {"transaction_status": ["SUCCESS", "FAILED", "PENDING"]},
        "min_row_count": 1,
    }
    results = DataQualityChecker.run_all_checks(transactions_df, "transactions", rules)
    assert all(r.passed for r in results)


def test_run_all_checks_detects_failures(spark):
    df = spark.createDataFrame(
        [(None, "2024-01-01", -10.0, "BAD_STATUS")],
        ["transaction_id", "cycle_date", "transaction_amount", "transaction_status"],
    )
    rules = {
        "not_null": ["transaction_id"],
        "positive_values": ["transaction_amount"],
        "allowed_values": {"transaction_status": ["SUCCESS", "FAILED"]},
    }
    results = DataQualityChecker.run_all_checks(df, "transactions", rules)
    failures = [r for r in results if not r.passed]
    assert len(failures) == 3


# --- assert_no_failures ---

def test_assert_no_failures_raises_on_failure(spark, transactions_df):
    results = DataQualityChecker.run_all_checks(
        transactions_df,
        "transactions",
        {"not_null": ["transaction_id"], "positive_values": ["transaction_amount"]},
    )
    # All pass — should not raise
    DataQualityChecker.assert_no_failures(results)


def test_assert_no_failures_raises_dq_exception(spark):
    df = spark.createDataFrame([(None,)], ["transaction_id"])
    results = DataQualityChecker.run_all_checks(df, "transactions", {"not_null": ["transaction_id"]})
    with pytest.raises(DQException):
        DataQualityChecker.assert_no_failures(results)


# --- to_report ---

def test_to_report_structure(spark, transactions_df):
    results = DataQualityChecker.run_all_checks(
        transactions_df, "transactions", {"not_null": ["transaction_id"], "min_row_count": 1}
    )
    report = DataQualityChecker.to_report(results)
    assert "total_checks" in report
    assert "passed" in report
    assert "failed" in report
    assert "results" in report
    assert report["total_checks"] == len(results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

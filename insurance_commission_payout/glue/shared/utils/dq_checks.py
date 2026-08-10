"""Data quality checks for commission payout pipeline."""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import pyspark.sql.functions as F
from pyspark.sql import DataFrame

logger = logging.getLogger(__name__)


class DQException(Exception):
    """Raised when one or more critical DQ checks fail."""


@dataclass
class DQResult:
    table: str
    rule: str
    column: Optional[str]
    passed: bool
    failing_count: int
    details: str


class DataQualityChecker:

    @staticmethod
    def check_not_null(df: DataFrame, table: str, column: str) -> DQResult:
        failing = df.filter(F.col(column).isNull()).count()
        passed = failing == 0
        return DQResult(
            table=table,
            rule="not_null",
            column=column,
            passed=passed,
            failing_count=failing,
            details=f"{failing} null(s) found in '{column}'" if not passed else "OK",
        )

    @staticmethod
    def check_no_duplicates(df: DataFrame, table: str, keys: List[str]) -> DQResult:
        total = df.count()
        distinct = df.select(*keys).distinct().count()
        failing = total - distinct
        passed = failing == 0
        return DQResult(
            table=table,
            rule="no_duplicates",
            column=",".join(keys),
            passed=passed,
            failing_count=failing,
            details=f"{failing} duplicate row(s) on {keys}" if not passed else "OK",
        )

    @staticmethod
    def check_positive_values(df: DataFrame, table: str, column: str) -> DQResult:
        failing = df.filter(F.col(column) <= 0).count()
        passed = failing == 0
        return DQResult(
            table=table,
            rule="positive_values",
            column=column,
            passed=passed,
            failing_count=failing,
            details=f"{failing} non-positive value(s) in '{column}'" if not passed else "OK",
        )

    @staticmethod
    def check_allowed_values(
        df: DataFrame, table: str, column: str, allowed: List[str]
    ) -> DQResult:
        failing = df.filter(~F.col(column).isin(allowed)).count()
        passed = failing == 0
        return DQResult(
            table=table,
            rule="allowed_values",
            column=column,
            passed=passed,
            failing_count=failing,
            details=f"{failing} value(s) outside {allowed} in '{column}'" if not passed else "OK",
        )

    @staticmethod
    def check_min_row_count(df: DataFrame, table: str, min_count: int) -> DQResult:
        total = df.count()
        passed = total >= min_count
        return DQResult(
            table=table,
            rule="min_row_count",
            column=None,
            passed=passed,
            failing_count=0 if passed else min_count - total,
            details=f"Row count {total} < minimum {min_count}" if not passed else f"Row count {total} OK",
        )

    @staticmethod
    def run_all_checks(
        df: DataFrame, table: str, rules: Dict[str, Any]
    ) -> List[DQResult]:
        results: List[DQResult] = []

        for column in rules.get("not_null", []):
            results.append(DataQualityChecker.check_not_null(df, table, column))

        keys = rules.get("no_duplicates")
        if keys:
            results.append(DataQualityChecker.check_no_duplicates(df, table, keys))

        for column in rules.get("positive_values", []):
            results.append(DataQualityChecker.check_positive_values(df, table, column))

        for column, allowed in rules.get("allowed_values", {}).items():
            results.append(DataQualityChecker.check_allowed_values(df, table, column, allowed))

        min_count = rules.get("min_row_count")
        if min_count is not None:
            results.append(DataQualityChecker.check_min_row_count(df, table, min_count))

        for r in results:
            level = logging.INFO if r.passed else logging.WARNING
            logger.log(level, "[DQ] table=%s rule=%s col=%s passed=%s details=%s",
                       r.table, r.rule, r.column, r.passed, r.details)

        return results

    @staticmethod
    def to_report(all_results: List[DQResult]) -> Dict[str, Any]:
        failures = [r for r in all_results if not r.passed]
        return {
            "total_checks": len(all_results),
            "passed": len(all_results) - len(failures),
            "failed": len(failures),
            "results": [asdict(r) for r in all_results],
        }

    @staticmethod
    def assert_no_failures(all_results: List[DQResult]) -> None:
        failures = [r for r in all_results if not r.passed]
        if failures:
            summary = "; ".join(f"{r.table}/{r.rule}/{r.column}: {r.details}" for r in failures)
            raise DQException(f"{len(failures)} DQ check(s) failed: {summary}")

"""Data transformation utilities."""

import logging
from typing import List, Optional, Dict, Any
import pyspark.sql.functions as F
from pyspark.sql import DataFrame, Window

logger = logging.getLogger(__name__)


class DataTransformer:
    @staticmethod
    def apply_filters(df: DataFrame, filters: Dict[str, Any]) -> DataFrame:
        try:
            for column, value in filters.items():
                if isinstance(value, list):
                    df = df.filter(F.col(column).isin(*value))
                else:
                    df = df.filter(F.col(column) == value)

            logger.info(f"Applied {len(filters)} filters")
            return df

        except Exception as e:
            logger.error(f"Filtering failed: {str(e)}")
            raise

    @staticmethod
    def broadcast_join(
        left_df: DataFrame, right_df: DataFrame, join_key: str, join_type: str = "inner"
    ) -> DataFrame:
        try:
            result = left_df.join(F.broadcast(right_df), on=join_key, how=join_type)
            logger.info(f"Broadcast join on {join_key}")
            return result

        except Exception as e:
            logger.error(f"Broadcast join failed: {str(e)}")
            raise

    @staticmethod
    def sort_merge_join(
        left_df: DataFrame, right_df: DataFrame, join_keys: List[str], join_type: str = "inner"
    ) -> DataFrame:
        try:
            left_repartitioned = left_df.repartition(*join_keys)
            right_repartitioned = right_df.repartition(*join_keys)

            result = left_repartitioned.join(
                right_repartitioned, on=join_keys, how=join_type
            )

            logger.info(f"Sort-merge join on {join_keys}")
            return result

        except Exception as e:
            logger.error(f"Sort-merge join failed: {str(e)}")
            raise

    @staticmethod
    def add_audit_columns(df: DataFrame, cycle_date: str) -> DataFrame:
        try:
            from datetime import datetime

            now = datetime.now()
            return df.withColumn(
                "dw_inserted_date", F.lit(now)
            ).withColumn(
                "dw_updated_date", F.lit(now)
            ).withColumn(
                "dw_cycle_date", F.lit(cycle_date)
            ).withColumn(
                "dw_is_active", F.lit(True)
            )

        except Exception as e:
            logger.error(f"Failed adding audit columns: {str(e)}")
            raise

    @staticmethod
    def deduplicate(
        df: DataFrame, partition_keys: List[str], order_by_key: str, ascending: bool = False
    ) -> DataFrame:
        try:
            window = Window.partitionBy(*partition_keys).orderBy(
                F.col(order_by_key).desc() if not ascending else F.col(order_by_key).asc()
            )

            result = df.withColumn("row_num", F.row_number().over(window)).filter(
                F.col("row_num") == 1
            ).drop("row_num")

            logger.info(f"Deduplicated on {partition_keys}")
            return result

        except Exception as e:
            logger.error(f"Deduplication failed: {str(e)}")
            raise

"""SCD Type 1 merge operations for Iceberg tables."""

import logging
from typing import List, Optional
import pyspark.sql.functions as F
from pyspark.sql import DataFrame, SparkSession
from datetime import datetime

logger = logging.getLogger(__name__)


class SCDType1Handler:
    def __init__(self, spark: SparkSession, s3_path: str, table_name: str):
        self.spark = spark
        self.s3_path = s3_path
        self.table_name = table_name

    def merge_scd_type1(
        self,
        source_df: DataFrame,
        primary_keys: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> int:
        try:
            if update_columns is None:
                update_columns = [
                    col for col in source_df.columns if col not in primary_keys
                ]

            source_with_audit = source_df.withColumn(
                "dw_updated_date", F.lit(datetime.now())
            ).withColumn(
                "dw_updated_by", F.lit("glue_job")
            )

            merge_condition = " AND ".join(
                [f"target.{key} = source.{key}" for key in primary_keys]
            )

            update_set = ", ".join(
                [f"target.{col} = source.{col}" for col in update_columns]
            )
            update_set += ", target.dw_updated_date = source.dw_updated_date"
            update_set += ", target.dw_updated_by = source.dw_updated_by"

            insert_columns = ", ".join(source_with_audit.columns)
            insert_values = ", ".join([f"source.{col}" for col in source_with_audit.columns])

            merge_sql = f"""
            MERGE INTO iceberg.{self.table_name} target
            USING {self.table_name}_source source
            ON {merge_condition}
            WHEN MATCHED THEN
                UPDATE SET {update_set}
            WHEN NOT MATCHED THEN
                INSERT ({insert_columns})
                VALUES ({insert_values})
            """

            source_with_audit.createOrReplaceTempView(f"{self.table_name}_source")
            self.spark.sql(merge_sql)

            logger.info(f"SCD Type 1 merge completed: {self.table_name} (keys: {primary_keys})")
            return source_df.count()

        except Exception as e:
            logger.error(f"SCD Type 1 merge failed: {self.table_name} - {str(e)}")
            raise

    def initialize_scd_table(self, initial_data: DataFrame) -> None:
        try:
            df_with_audit = initial_data.withColumn(
                "dw_inserted_date", F.lit(datetime.now())
            ).withColumn(
                "dw_updated_date", F.lit(datetime.now())
            ).withColumn(
                "dw_updated_by", F.lit("initial_load")
            ).withColumn(
                "dw_is_active", F.lit(True)
            )

            df_with_audit.write.format("iceberg").mode("overwrite").save(self.s3_path)
            logger.info(f"Initialized Iceberg table {self.table_name}")

        except Exception as e:
            logger.error(f"Failed to initialize SCD table {self.table_name}: {str(e)}")
            raise

    def validate_merge_integrity(
        self, primary_keys: List[str]
    ) -> bool:
        try:
            duplicates = self.spark.sql(
                f"""
                SELECT {", ".join(primary_keys)}, COUNT(*) as cnt
                FROM iceberg.{self.table_name}
                GROUP BY {", ".join(primary_keys)}
                HAVING cnt > 1
                """
            )

            duplicate_count = duplicates.count()

            if duplicate_count > 0:
                logger.warning(f"Found {duplicate_count} duplicate primary keys")
                return False

            logger.info("Merge integrity validation passed")
            return True

        except Exception as e:
            logger.error(f"Merge integrity validation failed: {str(e)}")
            return False

"""Glue Job 2: Transform, filter, join, and apply SCD Type 1 MERGE to Iceberg tables."""

import sys
import logging
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
import pyspark.sql.functions as F

# Add shared utilities to path
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from utils.transformations import DataTransformer
from utils.scd_handler import SCDType1Handler
from config.config import (
    S3_PARQUET_PATH,
    S3_ICEBERG_PATH,
    GLUE_DATABASE,
    PRIMARY_KEYS,
    GLUE_CATALOG,
)

# Initialize logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Get Glue arguments
args = getResolvedOptions(sys.argv, ["JOB_NAME", "cycle_date"])

# Initialize Glue context
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

cycle_date = args["cycle_date"]

logger.info(f"Starting transform_and_merge job for cycle_date: {cycle_date}")


class CommissionPayoutTransformer:
    """Handle transformation and merging of commission payout data."""

    def __init__(self, spark_session, cycle_date: str):
        """Initialize transformer."""
        self.spark = spark_session
        self.cycle_date = cycle_date
        self.transformer = DataTransformer()

    def load_parquet_files(self) -> dict:
        """
        Load all Parquet files for the cycle.

        Returns:
            dict: Dictionary of DataFrames by file type
        """
        try:
            dataframes = {}
            file_types = ["transactions", "policy", "coverage", "feature", "exchange", "rider"]

            for file_type in file_types:
                path = f"{S3_PARQUET_PATH}{file_type}/{self.cycle_date}/"
                try:
                    df = self.spark.read.parquet(path)
                    dataframes[file_type] = df
                    logger.info(f"Loaded {file_type} parquet with {df.count()} rows")
                except Exception as e:
                    logger.warning(f"Could not load {file_type}: {str(e)}")

            return dataframes

        except Exception as e:
            logger.error(f"Failed to load parquet files: {str(e)}")
            raise

    def apply_business_filters(self, dataframes: dict) -> dict:
        """
        Apply business logic filters to each dataset.

        Args:
            dataframes: Dictionary of DataFrames

        Returns:
            dict: Filtered DataFrames
        """
        try:
            filtered_dfs = {}

            # Filter transactions: only successful, commission-eligible transactions
            if "transactions" in dataframes:
                df = dataframes["transactions"]
                df = df.filter(F.col("transaction_status") == "SUCCESS") \
                       .filter(F.col("is_commission_eligible") == True) \
                       .filter(F.col("transaction_amount") > 0)
                filtered_dfs["transactions"] = df
                logger.info(f"Filtered transactions to {df.count()} rows")

            # Filter policies: active policies only
            if "policy" in dataframes:
                df = dataframes["policy"]
                df = df.filter(F.col("policy_status").isin("ACTIVE", "RENEWAL"))
                filtered_dfs["policy"] = df
                logger.info(f"Filtered policies to {df.count()} rows")

            # Copy other tables as-is
            for key in ["coverage", "feature", "exchange", "rider"]:
                if key in dataframes:
                    filtered_dfs[key] = dataframes[key]

            return filtered_dfs

        except Exception as e:
            logger.error(f"Business filter application failed: {str(e)}")
            raise

    def apply_joins(self, dataframes: dict) -> any:
        """
        Apply broadcast and sort-merge joins.

        Args:
            dataframes: Dictionary of DataFrames

        Returns:
            DataFrame: Joined result
        """
        try:
            # Start with transactions
            result = dataframes.get("transactions")

            if result is None:
                raise ValueError("Transactions dataframe is required")

            # Broadcast join with policy (dimension table)
            if "policy" in dataframes:
                result = self.transformer.broadcast_join(
                    result,
                    dataframes["policy"],
                    join_key="policy_id",
                    join_type="inner",
                )

            # Broadcast join with coverage
            if "coverage" in dataframes:
                result = self.transformer.broadcast_join(
                    result,
                    dataframes["coverage"],
                    join_key="policy_id",
                    join_type="left",
                )

            # Broadcast join with feature
            if "feature" in dataframes:
                result = self.transformer.broadcast_join(
                    result,
                    dataframes["feature"],
                    join_key="feature_id",
                    join_type="left",
                )

            # Sort-merge join with exchange (larger table)
            if "exchange" in dataframes:
                result = self.transformer.sort_merge_join(
                    result,
                    dataframes["exchange"],
                    join_keys=["exchange_code"],
                    join_type="left",
                )

            # Broadcast join with rider
            if "rider" in dataframes:
                result = self.transformer.broadcast_join(
                    result,
                    dataframes["rider"],
                    join_key="policy_id",
                    join_type="left",
                )

            logger.info(f"Joins completed. Result has {result.count()} rows")

            return result

        except Exception as e:
            logger.error(f"Join operations failed: {str(e)}")
            raise

    def apply_transformations(self, df) -> any:
        """
        Apply business logic transformations.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame: Transformed DataFrame
        """
        try:
            # Calculate commission payout
            df = df.withColumn(
                "commission_amount",
                F.col("transaction_amount") * F.col("commission_rate")
            )

            # Aggregate commissions by agent and policy
            df = df.withColumn(
                "agent_id", F.col("agent_id")
            ).withColumn(
                "policy_id", F.col("policy_id")
            )

            # Add audit columns
            df = self.transformer.add_audit_columns(df, self.cycle_date)

            logger.info(f"Transformations applied. Result has {df.count()} rows")

            return df

        except Exception as e:
            logger.error(f"Transformations failed: {str(e)}")
            raise

    def merge_to_iceberg(self, df, table_name: str) -> None:
        """
        Merge transformed data to Iceberg table using SCD Type 1.

        Args:
            df: Input DataFrame
            table_name: Target Iceberg table name
        """
        try:
            iceberg_path = f"{S3_ICEBERG_PATH}{table_name}/"
            scd_handler = SCDType1Handler(self.spark, iceberg_path, table_name)

            # Get primary keys for this table
            primary_keys = PRIMARY_KEYS.get(table_name, ["id"])

            # Check if table exists, if not initialize
            try:
                self.spark.sql(f"SELECT COUNT(*) FROM iceberg.{GLUE_DATABASE}.{table_name}")
                logger.info(f"Table {table_name} exists, proceeding with MERGE")
            except:
                logger.info(f"Table {table_name} does not exist, initializing")
                scd_handler.initialize_scd_table(df)
                return

            # Perform SCD Type 1 MERGE
            rows_affected = scd_handler.merge_scd_type1(
                df,
                primary_keys=primary_keys,
            )

            # Validate merge integrity
            is_valid = scd_handler.validate_merge_integrity(primary_keys)

            if not is_valid:
                logger.warning(f"Merge integrity issues detected for {table_name}")

            logger.info(
                f"Merged {rows_affected} rows to {table_name} Iceberg table"
            )

        except Exception as e:
            logger.error(f"Failed to merge to Iceberg for {table_name}: {str(e)}")
            raise


# Main execution
try:
    transformer = CommissionPayoutTransformer(spark, cycle_date)

    # Load parquet files
    logger.info("Loading parquet files...")
    dataframes = transformer.load_parquet_files()

    # Apply business filters
    logger.info("Applying business filters...")
    filtered_dfs = transformer.apply_business_filters(dataframes)

    # Apply joins
    logger.info("Applying joins...")
    joined_df = transformer.apply_joins(filtered_dfs)

    # Apply transformations
    logger.info("Applying transformations...")
    transformed_df = transformer.apply_transformations(joined_df)

    # Merge to Iceberg with SCD Type 1
    logger.info("Merging to Iceberg tables...")
    transformer.merge_to_iceberg(transformed_df, "commission_transactions")

    logger.info("Transform and merge job completed successfully")

    job.commit()

except Exception as e:
    logger.error(f"Glue job failed: {str(e)}")
    job.commit()
    sys.exit(1)

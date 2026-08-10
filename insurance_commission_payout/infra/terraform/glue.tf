resource "aws_glue_catalog_database" "commission_payout" {
  name        = "${var.glue_database_name}_${var.environment}"
  description = "Commission Payout Data Lake - ${var.environment}"

  catalog_id = local.account_id
}

resource "aws_glue_job" "decrypt_and_convert" {
  name              = local.glue_decrypt_job
  role_arn          = aws_iam_role.glue_role.arn
  glue_version      = "4.0"
  worker_type       = "G.2X"
  number_of_workers = 5
  timeout           = var.glue_job_timeout
  max_retries       = 1

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "${var.glue_job_script_location}decrypt_and_convert.py"
  }

  default_arguments = {
    "--job-bookmark-option"        = "job-bookmark-enable"
    "--enable-spark-ui"            = "false"
    "--enable-glue-datacatalog"    = "true"
    "--job-language"               = "python"
    "--TempDir"                    = "s3://${var.s3_bucket_name}/temp/"
    "--S3_RAW_PATH"                = "s3://${var.s3_bucket_name}/raw/"
    "--S3_PARQUET_PATH"            = "s3://${var.s3_bucket_name}/parquet/"
    "--KMS_KEY_ID"                 = var.kms_key_id
    "--GLUE_DATABASE"              = aws_glue_catalog_database.commission_payout.name
  }

  tags = var.tags

  depends_on = [
    aws_iam_role_policy.glue_s3_policy,
    aws_iam_role_policy.glue_secrets_policy,
  ]
}

resource "aws_glue_job" "transform_and_merge" {
  name              = local.glue_transform_job
  role_arn          = aws_iam_role.glue_role.arn
  glue_version      = "4.0"
  worker_type       = "G.2X"
  number_of_workers = var.glue_job_max_workers
  timeout           = var.glue_job_timeout
  max_retries       = 1

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "${var.glue_job_script_location}transform_and_merge.py"
  }

  default_arguments = {
    "--job-bookmark-option"        = "job-bookmark-enable"
    "--enable-spark-ui"            = "false"
    "--enable-glue-datacatalog"    = "true"
    "--job-language"               = "python"
    "--TempDir"                    = "s3://${var.s3_bucket_name}/temp/"
    "--S3_PARQUET_PATH"            = "s3://${var.s3_bucket_name}/parquet/"
    "--S3_ICEBERG_PATH"            = "s3://${var.s3_bucket_name}/iceberg/"
    "--GLUE_DATABASE"              = aws_glue_catalog_database.commission_payout.name
  }

  tags = var.tags

  depends_on = [
    aws_iam_role_policy.glue_s3_policy,
    aws_iam_role_policy.glue_kms_policy,
  ]
}

# CloudWatch Log Group for Glue
resource "aws_cloudwatch_log_group" "glue" {
  name              = "/aws-glue/commission-payout-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

data "archive_file" "lambda_function" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambda/file_ingestion_audit"
  output_path = "${path.module}/lambda_function.zip"
}

resource "aws_lambda_function" "file_ingestion" {
  filename      = data.archive_file.lambda_function.output_path
  function_name = local.lambda_function_name
  role          = aws_iam_role.lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory

  source_code_hash = data.archive_file.lambda_function.output_base64sha256

  environment {
    variables = {
      DYNAMODB_AUDIT_TABLE = aws_dynamodb_table.audit.name
      DECRYPT_JOB_NAME     = aws_glue_job.decrypt_and_convert.name
      AWS_REGION           = local.region
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda_dynamodb_policy,
    aws_iam_role_policy.lambda_glue_policy,
  ]

  tags = var.tags
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.file_ingestion.function_name}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.file_ingestion.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = "arn:aws:s3:::${var.s3_bucket_name}"
}

resource "aws_s3_bucket_notification" "lambda_trigger" {
  bucket = var.s3_bucket_name

  lambda_function {
    lambda_function_arn = aws_lambda_function.file_ingestion.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw/"
    filter_suffix       = ".pgp"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}

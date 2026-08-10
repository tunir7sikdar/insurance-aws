output "lambda_function_arn" {
  description = "ARN of file ingestion Lambda function"
  value       = aws_lambda_function.file_ingestion.arn
}

output "lambda_function_name" {
  description = "Name of file ingestion Lambda function"
  value       = aws_lambda_function.file_ingestion.function_name
}

output "glue_decrypt_job_name" {
  description = "Name of decrypt and convert Glue job"
  value       = aws_glue_job.decrypt_and_convert.name
}

output "glue_transform_job_name" {
  description = "Name of transform and merge Glue job"
  value       = aws_glue_job.transform_and_merge.name
}

output "dynamodb_table_name" {
  description = "Name of DynamoDB audit table"
  value       = aws_dynamodb_table.audit.name
}

output "dynamodb_table_arn" {
  description = "ARN of DynamoDB audit table"
  value       = aws_dynamodb_table.audit.arn
}

output "s3_bucket_name" {
  description = "Name of S3 data lake bucket"
  value       = var.s3_bucket_name
}

output "glue_catalog_database" {
  description = "Glue Catalog database name"
  value       = aws_glue_catalog_database.commission_payout.name
}

output "cloudwatch_log_group_lambda" {
  description = "CloudWatch log group for Lambda"
  value       = aws_cloudwatch_log_group.lambda.name
}

output "cloudwatch_log_group_glue" {
  description = "CloudWatch log group for Glue"
  value       = aws_cloudwatch_log_group.glue.name
}

output "lambda_role_arn" {
  description = "ARN of Lambda execution role"
  value       = aws_iam_role.lambda_role.arn
}

output "glue_role_arn" {
  description = "ARN of Glue job execution role"
  value       = aws_iam_role.glue_role.arn
}

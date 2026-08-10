variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "s3_bucket_name" {
  description = "Name of S3 bucket for data lake"
  type        = string
}

variable "kms_key_id" {
  description = "ARN of KMS key for encryption"
  type        = string
}

variable "dynamodb_table_name" {
  description = "Name of DynamoDB audit table"
  type        = string
  default     = "file_ingestion_audit"
}

variable "glue_database_name" {
  description = "Name of Glue Catalog database"
  type        = string
  default     = "commission_payout"
}

variable "glue_job_max_workers" {
  description = "Maximum number of workers for Glue jobs"
  type        = number
  default     = 10
  validation {
    condition     = var.glue_job_max_workers >= 2 && var.glue_job_max_workers <= 100
    error_message = "Glue job workers must be between 2 and 100."
  }
}

variable "glue_job_timeout" {
  description = "Timeout in minutes for Glue jobs"
  type        = number
  default     = 2880  # 48 hours
}

variable "glue_job_script_location" {
  description = "S3 location of Glue job scripts"
  type        = string
  default     = "s3://commission-payout-scripts/jobs/"
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 60
}

variable "lambda_memory" {
  description = "Lambda function memory in MB"
  type        = number
  default     = 256
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Project = "CommissionPayout"
    Owner   = "DataEngineering"
  }
}

# Locals for derived values
locals {
  environment_name = "${var.environment}-commission-payout"
}

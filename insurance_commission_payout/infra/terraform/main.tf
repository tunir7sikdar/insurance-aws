terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment to use remote state (S3 backend)
  # backend "s3" {
  #   bucket         = "commission-payout-terraform-state"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "terraform-locks"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(
      var.tags,
      {
        ManagedBy   = "Terraform"
        Environment = var.environment
      }
    )
  }
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}

# Data source for current AWS region
data "aws_region" "current" {}

# Local variables
locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
  
  s3_bucket_arn = "arn:aws:s3:::${var.s3_bucket_name}"
  
  lambda_function_name = "file-ingestion-audit-${var.environment}"
  glue_decrypt_job     = "decrypt-and-convert-csv-${var.environment}"
  glue_transform_job   = "transform-and-merge-${var.environment}"
}

# Deployment Guide

Complete step-by-step guide for deploying the Commission Payout Pipeline.

## Prerequisites

### AWS Account Setup
1. AWS account with appropriate permissions
2. IAM user/role with AdministratorAccess (for setup)
3. AWS CLI configured
4. Terraform >= 1.0

### Local Setup
1. Python 3.9+ installed
2. Git installed
3. PGP key pair generated
4. SSH key for EC2 (if needed)

### Generate PGP Key Pair

```bash
# Generate key pair
gpg --gen-key

# Export public key
gpg --export-armor "Key ID" > public.key

# Export private key (protected with passphrase)
gpg --export-secret-keys-armor "Key ID" > private.key

# Store private.key securely - you'll need it for AWS Secrets Manager
```

## Step 1: AWS Infrastructure Setup

### 1.1 Create S3 Buckets

```bash
# Variables
BUCKET_NAME="commission-payout-data-dev"
AWS_REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create main bucket
aws s3api create-bucket \
  --bucket $BUCKET_NAME \
  --region $AWS_REGION

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket $BUCKET_NAME \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket $BUCKET_NAME \
  --server-side-encryption-configuration '{
    "Rules": [
      {
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "aws:kms",
          "KMSMasterKeyID": "arn:aws:kms:'$AWS_REGION':'$ACCOUNT_ID':alias/commission-payout"
        }
      }
    ]
  }'

# Create lifecycle policy
aws s3api put-bucket-lifecycle-configuration \
  --bucket $BUCKET_NAME \
  --lifecycle-configuration file://- <<EOF
{
  "Rules": [
    {
      "Id": "DeleteOldTemp",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "temp/"
      },
      "ExpirationInDays": 7
    }
  ]
}
EOF
```

### 1.2 Create KMS Key

```bash
# Create KMS key
KEY_ID=$(aws kms create-key \
  --description "Commission Payout Pipeline Key" \
  --region $AWS_REGION \
  --query 'KeyMetadata.KeyId' \
  --output text)

# Create alias
aws kms create-alias \
  --alias-name alias/commission-payout \
  --target-key-id $KEY_ID \
  --region $AWS_REGION

echo "KMS Key ID: $KEY_ID"
```

### 1.3 Store Secrets in Secrets Manager

```bash
# Store PGP private key
aws secretsmanager create-secret \
  --name pgp-private-key-dev \
  --description "PGP private key for file decryption" \
  --secret-string file://private.key \
  --region $AWS_REGION

# Store PGP passphrase
aws secretsmanager create-secret \
  --name pgp-passphrase-dev \
  --description "Passphrase for PGP key" \
  --secret-string "your-passphrase-here" \
  --region $AWS_REGION

# Verify secrets created
aws secretsmanager list-secrets --region $AWS_REGION
```

### 1.4 Create DynamoDB Audit Table

```bash
aws dynamodb create-table \
  --table-name file_ingestion_audit_dev \
  --attribute-definitions \
    AttributeName=file_key,AttributeType=S \
    AttributeName=cycle_date,AttributeType=S \
  --key-schema \
    AttributeName=file_key,KeyType=HASH \
    AttributeName=cycle_date,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region $AWS_REGION

# Enable TTL (optional - delete old entries after 90 days)
aws dynamodb update-time-to-live \
  --table-name file_ingestion_audit_dev \
  --time-to-live-specification "Enabled=true, AttributeName=ttl" \
  --region $AWS_REGION
```

## Step 2: Terraform Deployment

### 2.1 Configure Terraform Variables

```bash
cd infra/terraform

# Copy example variables
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
cat > terraform.tfvars <<EOF
aws_region              = "us-east-1"
environment             = "dev"
s3_bucket_name          = "commission-payout-data-dev"
kms_key_id              = "arn:aws:kms:us-east-1:$ACCOUNT_ID:key/$KEY_ID"
glue_job_max_workers    = 10
glue_job_timeout        = 2880
lambda_timeout          = 60
dynamodb_table_name     = "file_ingestion_audit_dev"

tags = {
  Project     = "CommissionPayout"
  Environment = "dev"
  ManagedBy   = "Terraform"
}
EOF
```

### 2.2 Initialize and Deploy

```bash
# Initialize Terraform
terraform init

# Plan deployment
terraform plan -out=tfplan

# Review plan output

# Apply configuration
terraform apply tfplan

# Save outputs
terraform output > terraform-outputs.json
```

### 2.3 Verify Resources Created

```bash
# Check Lambda function
aws lambda list-functions --query "Functions[?contains(FunctionName, 'file-ingestion')].FunctionName"

# Check Glue jobs
aws glue list-jobs --query "JobList[?contains(Name, 'commission')].Name"

# Check DynamoDB table
aws dynamodb list-tables | grep "file_ingestion"

# Check IAM roles
aws iam list-roles --query "Roles[?contains(RoleName, 'commission')].RoleName"
```

## Step 3: Configure Lambda Function

### 3.1 Build Lambda Deployment Package

```bash
# From project root
make lambda-build

# Output: build/lambda_function.zip
```

### 3.2 Deploy Lambda Function

```bash
# Get Lambda function name from Terraform outputs
LAMBDA_FUNCTION=$(terraform output -raw lambda_function_name)

# Update function code
aws lambda update-function-code \
  --function-name $LAMBDA_FUNCTION \
  --zip-file fileb://../../build/lambda_function.zip

# Verify deployment
aws lambda get-function-configuration --function-name $LAMBDA_FUNCTION
```

### 3.3 Configure Lambda Environment Variables

```bash
aws lambda update-function-configuration \
  --function-name $LAMBDA_FUNCTION \
  --environment Variables='{
    "DYNAMODB_AUDIT_TABLE": "file_ingestion_audit_dev",
    "DECRYPT_JOB_NAME": "decrypt-and-convert-csv-dev",
    "AWS_REGION": "us-east-1"
  }'
```

## Step 4: Configure Glue Jobs

### 4.1 Upload Job Scripts to S3

```bash
# Create scripts bucket
SCRIPTS_BUCKET="commission-payout-scripts-dev"

aws s3api create-bucket \
  --bucket $SCRIPTS_BUCKET \
  --region $AWS_REGION

# Upload Glue job scripts
aws s3 cp glue/jobs/decrypt_and_convert/decrypt_and_convert.py \
  s3://$SCRIPTS_BUCKET/jobs/

aws s3 cp glue/jobs/transform_and_merge/transform_and_merge.py \
  s3://$SCRIPTS_BUCKET/jobs/

# Upload shared utilities
aws s3 sync glue/shared/ s3://$SCRIPTS_BUCKET/libs/
```

### 4.2 Create Glue Jobs via Terraform

Terraform templates already include Glue job creation. Verify:

```bash
# List Glue jobs
aws glue list-jobs --query "JobList[].Name"

# Get job details
aws glue get-job --name decrypt-and-convert-csv-dev
```

### 4.3 Configure Job Parameters

Update job parameters in `infra/terraform/glue.tf`:

```hcl
resource "aws_glue_job" "decrypt_and_convert" {
  # ... existing config ...

  default_arguments = {
    "--job-bookmark-option"        = "job-bookmark-enable"
    "--enable-spark-ui"            = "false"
    "--enable-glue-datacatalog"    = "true"
    "--job-language"               = "python"
  }

  # Additional arguments
  command {
    python_version = "3"
  }
}
```

## Step 5: Setup S3 Event Triggers

### 5.1 Configure S3 to Lambda

```bash
# Add S3 event notification
aws s3api put-bucket-notification-configuration \
  --bucket $BUCKET_NAME \
  --notification-configuration file://- <<EOF
{
  "LambdaFunctionConfigurations": [
    {
      "LambdaFunctionArn": "arn:aws:lambda:$AWS_REGION:$ACCOUNT_ID:function:file-ingestion-audit",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "raw/"
            },
            {
              "Name": "suffix",
              "Value": ".pgp"
            }
          ]
        }
      }
    }
  ]
}
EOF
```

### 5.2 Grant Lambda S3 Permission

```bash
aws lambda add-permission \
  --function-name $LAMBDA_FUNCTION \
  --statement-id AllowS3Invoke \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::$BUCKET_NAME
```

## Step 6: Monitoring and Logging

### 6.1 Create CloudWatch Log Groups

```bash
# Lambda logs (created automatically)
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/file-ingestion"

# Glue logs
aws logs create-log-group \
  --log-group-name /aws-glue/commission-payout-dev

# Configure retention
aws logs put-retention-policy \
  --log-group-name /aws-glue/commission-payout-dev \
  --retention-in-days 30
```

### 6.2 Setup CloudWatch Alarms

```bash
# Lambda error alarm
aws cloudwatch put-metric-alarm \
  --alarm-name lambda-file-ingestion-errors \
  --alarm-description "Alert on Lambda errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=$LAMBDA_FUNCTION

# Glue job failure alarm
aws cloudwatch put-metric-alarm \
  --alarm-name glue-decrypt-job-failures \
  --alarm-description "Alert on Glue job failures" \
  --metric-name glue_job_run_failure \
  --namespace AWS/Glue \
  --statistic Sum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold
```

## Step 7: Testing

### 7.1 Unit Tests

```bash
# Run all unit tests
make test

# Run with coverage
make test-cov

# Expected: >= 80% coverage
```

### 7.2 Integration Test

```bash
# Upload test file
aws s3 cp test-data/transactions.csv.pgp \
  s3://$BUCKET_NAME/raw/transactions/cycle_20240101/

# Monitor Lambda execution
aws logs tail /aws/lambda/file-ingestion-audit --follow

# Check DynamoDB audit table
aws dynamodb get-item \
  --table-name file_ingestion_audit_dev \
  --key '{"file_key": {"S": "BUCKET#raw/transactions/..."}}'

# Verify Glue job triggered
aws glue list-job-runs \
  --job-name decrypt-and-convert-csv-dev \
  --query "JobRuns | sort_by(@, &StartedOn) | [-1]"
```

### 7.3 End-to-End Test

```bash
# 1. Upload all test files
aws s3 sync test-data/cycle_20240101/ \
  s3://$BUCKET_NAME/raw/

# 2. Monitor pipeline
watch -n 5 "aws glue get-job-runs --job-name decrypt-and-convert-csv-dev"

# 3. Verify output in Iceberg
aws glue get-table-versions \
  --catalog-id $ACCOUNT_ID \
  --database-name commission_payout_dev \
  --table-name commission_transactions
```

## Troubleshooting

### Lambda Not Triggering

```bash
# Check S3 event notification
aws s3api get-bucket-notification-configuration \
  --bucket $BUCKET_NAME

# Check Lambda permission
aws lambda get-policy \
  --function-name $LAMBDA_FUNCTION

# Check CloudTrail logs
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=$LAMBDA_FUNCTION
```

### Glue Job Failures

```bash
# Get job run details
aws glue get-job-run \
  --job-name decrypt-and-convert-csv-dev \
  --run-id <run-id>

# View job logs
aws logs tail /aws-glue/commission-payout-dev --follow

# Check IAM permissions
aws iam get-role-policy \
  --role-name GlueJobRole \
  --policy-name GlueJobPolicy
```

### DynamoDB Issues

```bash
# Check table metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedWriteCapacityUnits \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum

# Query audit table
aws dynamodb scan \
  --table-name file_ingestion_audit_dev \
  --limit 10
```

## Cleanup

```bash
# Destroy Terraform infrastructure (if needed)
cd infra/terraform
terraform destroy

# Delete manually created resources
aws s3 rm s3://$BUCKET_NAME --recursive
aws dynamodb delete-table --table-name file_ingestion_audit_dev
aws kms schedule-key-deletion --key-id $KEY_ID --pending-window-in-days 7
aws secretsmanager delete-secret --secret-id pgp-private-key-dev --force-delete-without-recovery
```

## Post-Deployment

1. ✅ Verify all resources created
2. ✅ Run unit tests (80%+ coverage)
3. ✅ Run integration tests
4. ✅ Configure monitoring and alerts
5. ✅ Document any customizations
6. ✅ Setup backup strategy
7. ✅ Schedule security audit

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues.

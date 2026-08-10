# Troubleshooting Guide

Common issues and solutions for the Commission Payout Pipeline.

## Lambda Function Issues

### Issue: Lambda Not Triggered by S3

**Symptoms**: Files uploaded to S3 but Lambda doesn't execute

**Solutions**:

1. **Check S3 Event Configuration**
```bash
aws s3api get-bucket-notification-configuration --bucket your-bucket
```
- Verify the notification is configured for the correct prefix (`raw/`)
- Verify the suffix filter (`.pgp`)
- Ensure Lambda function ARN is correct

2. **Check Lambda Permissions**
```bash
aws lambda get-policy --function-name file-ingestion-audit
```
- Ensure `s3.amazonaws.com` has `lambda:InvokeFunction` permission
- Re-add permission if missing:
```bash
aws lambda add-permission \
  --function-name file-ingestion-audit \
  --statement-id AllowS3Invoke \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::your-bucket
```

3. **Check Lambda Execution Logs**
```bash
aws logs tail /aws/lambda/file-ingestion-audit --follow
```

4. **Test Lambda Manually**
```bash
# Create test event
cat > test-event.json <<EOF
{
  "Records": [
    {
      "s3": {
        "bucket": {"name": "your-bucket"},
        "object": {"key": "raw/transactions/cycle_20240101/test.csv.pgp"}
      }
    }
  ]
}
EOF

# Invoke Lambda
aws lambda invoke \
  --function-name file-ingestion-audit \
  --payload file://test-event.json \
  --cli-binary-format raw-in-base64-out \
  response.json

# Check response
cat response.json
```

---

### Issue: Lambda Timeout

**Symptoms**: Lambda function times out (signal: SIGKILL)

**Causes**:
- DynamoDB write is slow
- Glue job triggering is slow
- Network connectivity issues

**Solutions**:

1. **Increase Lambda Timeout**
```bash
aws lambda update-function-configuration \
  --function-name file-ingestion-audit \
  --timeout 60  # Increase from default 30
```

2. **Check DynamoDB Performance**
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedWriteCapacityUnits \
  --table-name file_ingestion_audit_dev \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

3. **Check VPC Configuration** (if Lambda in VPC)
   - Ensure NAT gateway is available
   - Check security group rules

---

### Issue: Lambda Cannot Access DynamoDB

**Symptoms**: Error like "User: arn:aws:iam::123456789012:role/lambda-role is not authorized..."

**Solutions**:

1. **Check IAM Role Policy**
```bash
aws iam get-role-policy \
  --role-name lambda-execution-role \
  --policy-name lambda-dynamodb-policy
```

2. **Add Missing Permissions**
```bash
cat > policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:UpdateItem"
      ],
      "Resource": "arn:aws:dynamodb:region:account:table/file_ingestion_audit*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name lambda-execution-role \
  --policy-name lambda-dynamodb-policy \
  --policy-document file://policy.json
```

3. **Check DynamoDB Encryption**
   - Ensure Lambda role has KMS decrypt permission if table is encrypted

---

## Glue Job Issues

### Issue: Glue Job Fails with "PGP Decryption Failed"

**Symptoms**: Glue job fails with error about PGP key or passphrase

**Solutions**:

1. **Verify Secrets Manager Access**
```bash
# Check if Glue role can access secrets
aws secretsmanager get-secret-value --secret-id pgp-private-key-dev
```

2. **Verify Secret Format**
```bash
# Get secret to inspect
aws secretsmanager get-secret-value \
  --secret-id pgp-private-key-dev \
  --query SecretString --output text | head -5
```
Expected output: `-----BEGIN PGP PRIVATE KEY BLOCK-----`

3. **Re-upload Secret if Corrupted**
```bash
# Delete old secret
aws secretsmanager delete-secret \
  --secret-id pgp-private-key-dev \
  --force-delete-without-recovery

# Upload new secret
aws secretsmanager create-secret \
  --name pgp-private-key-dev \
  --secret-string file://private.key
```

4. **Check Glue Job IAM Role**
```bash
# Verify SecretsManager permissions
aws iam get-role-policy --role-name glue-job-role --policy-name glue-secrets-policy

# Should include:
# "secretsmanager:GetSecretValue"
# "kms:Decrypt"
```

---

### Issue: Glue Job Out of Memory

**Symptoms**: Glue job fails with Java heap space error or OOM killer

**Solutions**:

1. **Increase Worker Count**
```bash
aws glue update-job \
  --name decrypt-and-convert-csv-dev \
  --job-update '{
    "NumberOfWorkers": 10,
    "WorkerType": "G.2X"
  }'
```

2. **Use Broadcast Join for Dimension Tables**
```python
# In transform_and_merge.py
# Ensure small tables are broadcast
from pyspark.sql.functions import broadcast

result = fact_df.join(
    broadcast(dimension_df),
    on="key",
    how="inner"
)
```

3. **Increase Shuffle Partitions**
```bash
# In Glue job configuration
spark.sql.shuffle.partitions=200  # Default is 200, increase if needed
```

4. **Check S3 File Sizes**
```bash
aws s3 ls s3://bucket/parquet/transactions/ --recursive --summarize
```
If files are large, may need more workers

---

### Issue: Glue Job Takes Too Long

**Symptoms**: Glue job duration exceeds expected time

**Solutions**:

1. **Analyze Spark UI**
   - Enable Spark UI in Glue job configuration
   - Check for shuffle/skew operations
   - Identify slow stages

2. **Optimize Join Strategy**
```python
# Use sort-merge join instead of shuffle
df1.repartition("key").join(
    df2.repartition("key"),
    on="key",
    how="inner"
)
```

3. **Partition Pruning**
```python
# Filter on partition columns early
df = df.filter(F.col("cycle_date") == "20240101")
```

4. **Check for Cartesian Products**
```python
# Bad: Can cause Cartesian product
result = df1.join(df2)  # No join condition!

# Good:
result = df1.join(df2, on="id", how="inner")
```

---

## DynamoDB Issues

### Issue: DynamoDB Throughput Exceeded

**Symptoms**: `ProvisionedThroughputExceededException` or high write throttling

**Solutions**:

1. **Switch to On-Demand Billing**
```bash
aws dynamodb update-billing-mode \
  --table-name file_ingestion_audit_dev \
  --billing-mode PAY_PER_REQUEST
```

2. **Increase Provisioned Capacity**
```bash
aws dynamodb update-table \
  --table-name file_ingestion_audit_dev \
  --provisioned-throughput ReadCapacityUnits=100,WriteCapacityUnits=100
```

3. **Check Write Pattern**
   - Avoid hot partition keys
   - Batch writes if possible
   - Distribute cycle_date values evenly

---

### Issue: DynamoDB Item Size Exceeds Limit

**Symptoms**: "Item size has exceeded the maximum allowed size" error

**Cause**: DynamoDB max item size is 400 KB

**Solutions**:

1. **Reduce Stored Data**
```python
# Store only essential fields in audit table
audit_entry = {
    "file_key": key,
    "cycle_date": cycle_date,
    "status": "RECEIVED",
    "timestamp": now,
    # Remove large fields
}
```

2. **Use S3 for Large Data**
```python
# Store metadata in DynamoDB, large data in S3
audit_entry = {
    "s3_location": "s3://bucket/audit/...",
    "status": "RECEIVED",
}
```

---

## Data Quality Issues

### Issue: Missing Data in Iceberg Table

**Symptoms**: Expected records not appearing in Iceberg table

**Solutions**:

1. **Check Glue Job Output**
```bash
# Get latest job run
aws glue list-job-runs \
  --job-name transform-and-merge-dev \
  --query "JobRuns | sort_by(@, &StartedOn) | [-1]"

# Check logs
aws logs tail /aws-glue/commission-payout-dev --follow
```

2. **Verify Filters Are Not Too Restrictive**
```python
# Check filter logic in transformations.py
# Example: May be filtering out all records if status doesn't match
df = df.filter(F.col("transaction_status") == "SUCCESS")
print(f"After filter: {df.count()} rows")  # Add logging
```

3. **Check Primary Key Conflicts**
```sql
-- In Iceberg table
SELECT transaction_id, COUNT(*) as cnt
FROM commission_transactions
GROUP BY transaction_id
HAVING cnt > 1
```

4. **Verify MERGE Condition**
   - Ensure MERGE condition correctly identifies matching records
   - Check if updating correct columns

---

### Issue: Duplicate Records in Iceberg

**Symptoms**: Same primary key appears multiple times

**Solutions**:

1. **Validate Merge Integrity**
```python
# In scd_handler.py
is_valid = scd.validate_merge_integrity(primary_keys)
if not is_valid:
    logger.error("Duplicates detected!")
    # Handle error
```

2. **Check Primary Key Definition**
```python
# Ensure primary key uniquely identifies records
PRIMARY_KEYS = {
    "transactions": ["transaction_id", "cycle_date"],  # Must be unique!
}
```

3. **Clean Up Duplicates** (if already exists)
```sql
-- Find duplicates
SELECT transaction_id, COUNT(*) as cnt
FROM commission_transactions
GROUP BY transaction_id
HAVING cnt > 1

-- Manual cleanup (use with caution)
DELETE FROM commission_transactions
WHERE transaction_id IN (
    SELECT transaction_id
    FROM (
        SELECT transaction_id, ROW_NUMBER() OVER (PARTITION BY transaction_id ORDER BY dw_updated_date DESC) as rn
        FROM commission_transactions
    ) WHERE rn > 1
)
```

---

## Performance Tuning

### Optimize Glue Job Shuffle

```python
# Set appropriate shuffle partitions
spark.conf.set("spark.sql.shuffle.partitions", "400")  # For large datasets

# Enable adaptive query execution (Spark 3.0+)
spark.conf.set("spark.sql.adaptive.enabled", "true")
```

### Optimize S3 Access Pattern

```python
# Use partitioned reads
df = spark.read.parquet(
    "s3://bucket/parquet/transactions/",
    basePath="s3://bucket/parquet/"
)

# Filter on partition columns early
df = df.filter(F.col("cycle_date") == "20240101")
```

### Monitor Glue Job Metrics

```bash
# Custom metrics
aws cloudwatch put-metric-data \
  --namespace CommissionPayout \
  --metric-name GlueJobDuration \
  --value 1500  # seconds \
  --unit Seconds

# Query custom metrics
aws cloudwatch get-metric-statistics \
  --namespace CommissionPayout \
  --metric-name GlueJobDuration \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum
```

---

## Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `InvalidSignatureException` | PGP signature invalid | Verify encrypted file format, re-encrypt with correct key |
| `FileNotFoundException` | S3 file not found | Check S3 path, verify file uploaded, check prefix/suffix filters |
| `AccessDeniedException` | IAM permission issue | Check role policy, ensure action is allowed on resource |
| `ThrottlingException` | DynamoDB/Glue throttled | Use on-demand billing or increase capacity |
| `OutOfMemoryError` | Heap space exhausted | Increase workers, optimize shuffles, reduce data size |
| `SchemaInferenceException` | CSV schema inference failed | Verify CSV format, specify schema explicitly |
| `KMSInvalidStateException` | KMS key disabled | Check KMS key status, re-enable if needed |

---

## Support and Escalation

### Gather Diagnostic Information

```bash
# Collect logs
aws logs get-log-events \
  --log-group-name /aws/lambda/file-ingestion-audit \
  --log-stream-name <stream-name> \
  > lambda-logs.json

aws logs get-log-events \
  --log-group-name /aws-glue/commission-payout-dev \
  --log-stream-name <stream-name> \
  > glue-logs.json

# Export CloudTrail logs
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=file-ingestion-audit \
  > cloudtrail.json
```

### Create Support Ticket with

- Log files from above
- CloudFormation/Terraform template used
- Steps to reproduce
- Expected vs actual behavior
- AWS account ID and region

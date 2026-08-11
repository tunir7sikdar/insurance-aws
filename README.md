# Commission Payout Pipeline

AWS-based data pipeline for processing insurance commission payouts using Lambda, Glue, and Iceberg tables.

## Overview

This project implements a comprehensive, production-ready pipeline for calculating and managing insurance agent commissions. It processes encrypted CSV files, applies business logic transformations, and stores results in Apache Iceberg tables.

### Architecture

```
S3 (Raw CSV) 
    ↓
Lambda (Audit) → DynamoDB (Audit Log)
    ↓
Glue Job 1 (Decrypt & Convert CSV → Parquet)
    ↓
S3 (Parquet)
    ↓
Glue Job 1b (DQ Check → S3 DQ Report)
    ↓
Glue Job 2 (Transform, Filter, Join, SCD Type 1 Merge → Iceberg)
    ↓
S3 (Iceberg Tables)
```

### Key Features

- PGP Encryption: Decrypt encrypted CSV files using private keys stored in AWS Secrets Manager
- Data Quality: Automated DQ checks (nulls, duplicates, value ranges, allowed values) with S3 report
- Data Transformation: Filtering, broadcasting joins, and sort-merge joins
- SCD Type 1: Slowly Changing Dimension Type 1 implementation for fact table updates
- Iceberg Tables: Apache Iceberg for ACID transactions and time-travel queries
- Audit Trail: DynamoDB audit table tracking all file ingestions
- Comprehensive Tests: Unit tests with 80%+ coverage requirement
- Infrastructure as Code: Terraform templates for AWS resource provisioning

## Quick Start

### Prerequisites

- Python 3.9+
- AWS Account with appropriate permissions
- Terraform (for infrastructure deployment)
- Git

### Installation

1. Clone the repository
   ```bash
   git clone https://github.com/tunir7sikdar/insurance-aws.git
   cd insurance-aws
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   make install
   # or: pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your AWS account details
   ```

### Running Tests

```bash
# Run all unit tests
make test

# Run with coverage report
make test-cov

# Run specific test file
pytest tests/unit/test_transformations.py -v
```

### Code Quality

```bash
# Format code
make format

# Run linting checks
make lint
```

## 📁 Project Structure

```
insurance-aws/
├── lambda/
│   └── file_ingestion_audit/
│       ├── lambda_function.py       # S3 event handler
│       └── __init__.py
├── glue/
│   ├── jobs/
│   │   ├── decrypt_and_convert/
│   │   │   └── decrypt_and_convert.py
│   │   ├── dq_check/
│   │   │   └── dq_check.py
│   │   └── transform_and_merge/
│   │       └── transform_and_merge.py
│   └── shared/
│       ├── utils/
│       │   ├── pgp_decryption.py    # PGP decryption utilities
│       │   ├── kms_handler.py       # AWS KMS operations
│       │   ├── transformations.py   # Data transformations
│       │   ├── scd_handler.py       # SCD Type 1 logic
│       │   ├── dq_checks.py         # Data quality checks
│       │   └── __init__.py
│       └── config/
│           ├── config.py             # Configuration management
│           └── __init__.py
├── tests/
│   ├── unit/
│   │   ├── test_transformations.py
│   │   ├── test_scd_handler.py
│   │   ├── test_lambda.py
│   │   ├── test_dq_checks.py
│   │   └── __init__.py
│   ├── integration/
│   │   └── test_placeholder.py
│   └── conftest.py
├── infra/
│   ├── terraform/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── terraform.tfvars.example
│   └── scripts/
│       └── setup_secrets.sh
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   └── TROUBLESHOOTING.md
├── requirements.txt
├── pytest.ini
├── setup.py
├── Makefile
├── .gitignore
├── .env.example
└── README.md
```

## 🔧 Configuration

### Environment Variables

Key environment variables (see `.env.example`):

| Variable | Description | Required |
|----------|-------------|----------|
| `AWS_REGION` | AWS region | Yes |
| `S3_BUCKET_NAME` | S3 bucket for data | Yes |
| `GLUE_DATABASE` | Glue Catalog database | Yes |
| `DYNAMODB_AUDIT_TABLE` | DynamoDB audit table | Yes |
| `KMS_KEY_ID` | KMS key for encryption | Yes |
| `ENV` | Environment (dev/staging/prod) | Yes |

### AWS Secrets Manager

Required secrets:

1. **pgp-private-key**: PGP private key in PEM format
2. **pgp-passphrase**: Passphrase for PGP key

## 🏗️ Components

### 1. Lambda Function: File Ingestion Audit

**Purpose**: Triggered by S3 events to audit incoming files and trigger Glue jobs

**Location**: `lambda/file_ingestion_audit/lambda_function.py`

**Features**:
- S3 event parsing
- DynamoDB audit entry creation
- Cycle completion detection
- Glue job triggering

**Invocation**:
```python
# Triggered by S3 PUT events
# Path format: s3://bucket/raw/{file_type}/cycle_{cycle_date}/{filename}
```

### 2. Glue Job 1: Decrypt and Convert

**Purpose**: Decrypt PGP-encrypted CSV files and convert to Parquet format

**Location**: `glue/jobs/decrypt_and_convert/decrypt_and_convert.py`

**Key Operations**:
1. Retrieve PGP credentials from Secrets Manager
2. Download encrypted file from S3
3. Decrypt using PGP private key
4. Read CSV and infer schema
5. Write to Parquet with metadata columns
6. Clean up temporary files

**Execution**:
```bash
glue_client.start_job_run(
    JobName='decrypt-and-convert-csv-dev',
    Arguments={
        '--cycle_date': '20240101',
    }
)
```

### 3. Glue Job 1b: Data Quality Check

**Purpose**: Validate Parquet data quality before downstream transformation; fails the pipeline early on violations

**Location**: `glue/jobs/dq_check/dq_check.py`

**Checks performed per table**:
- `not_null` — critical columns must contain no nulls
- `no_duplicates` — composite primary keys must be unique
- `positive_values` — numeric columns must be > 0
- `allowed_values` — enum columns must match a known set
- `min_row_count` — table must meet a minimum row threshold

**Output**: JSON report written to `s3://{bucket}/dq_reports/{env}/{cycle_date}/report.json`

**Execution**:
```bash
glue_client.start_job_run(
    JobName='dq-check-dev',
    Arguments={
        '--cycle_date': '20240101',
    }
)
```

### 4. Glue Job 2: Transform and Merge

**Purpose**: Apply business logic transformations and merge to Iceberg tables using SCD Type 1

**Location**: `glue/jobs/transform_and_merge/transform_and_merge.py`

**Transformations**:
1. **Filtering**: Successful transactions, active policies, etc.
2. **Broadcast Joins**: Dimension tables (Policy, Coverage, Feature, Rider)
3. **Sort-Merge Joins**: Large tables (Exchange rates)
4. **Business Calculations**: Commission amount, aggregations
5. **SCD Type 1 Merge**: Update existing records, insert new ones

### 5. Shared Utilities

#### PGP Decryption (`glue/shared/utils/pgp_decryption.py`)
```python
pgp = PGPDecryptor(private_key_path, passphrase)
decrypted = pgp.decrypt_file(encrypted_file_path, output_path)
```

#### KMS Handler (`glue/shared/utils/kms_handler.py`)
```python
kms = KMSHandler(kms_key_id)
encrypted = kms.encrypt(plaintext)
decrypted = kms.decrypt(encrypted_data)
```

#### Data Transformations (`glue/shared/utils/transformations.py`)
```python
transformer = DataTransformer()

# Broadcast join for small tables
result = transformer.broadcast_join(left_df, right_df, join_key='id')

# Sort-merge join for large tables
result = transformer.sort_merge_join(left_df, right_df, join_keys=['id', 'date'])

# Apply multiple filters
filtered = transformer.apply_filters(df, {'status': 'SUCCESS', 'amount': [100, 500]})

# Add audit columns
df = transformer.add_audit_columns(df, cycle_date='20240101')
```

#### Data Quality Checker (`glue/shared/utils/dq_checks.py`)
```python
from utils.dq_checks import DataQualityChecker, DQException

results = DataQualityChecker.run_all_checks(df, table="transactions", rules=DQ_RULES["transactions"])
report = DataQualityChecker.to_report(results)
DataQualityChecker.assert_no_failures(results)  # raises DQException on failure
```

#### SCD Type 1 Handler (`glue/shared/utils/scd_handler.py`)
```python
scd = SCDType1Handler(spark, s3_path, table_name)

# Merge with SCD Type 1 logic
rows_affected = scd.merge_scd_type1(
    source_df,
    primary_keys=['id'],
    update_columns=['amount', 'status']
)

# Validate merge integrity
is_valid = scd.validate_merge_integrity(['id'])
```

## 📊 Data Flow

### Example: Transaction Processing for Cycle 20240101

1. **File Arrives**: S3 receives encrypted CSV
   ```
   s3://bucket/raw/transactions/cycle_20240101/transactions.csv.pgp
   ```

2. **Lambda Audit**: 
   - Creates DynamoDB audit entry
   - Marks file status as RECEIVED
   - Checks if cycle is complete

3. **Cycle Complete**: When all expected files arrive
   - Lambda triggers `decrypt-and-convert-csv` Glue job

4. **Decryption & Conversion**:
   - Glue Job 1 decrypts all cycle files
   - Converts CSV to Parquet
   - Writes to S3: `s3://bucket/parquet/{file_type}/cycle_20240101/`

5. **Transformation & Merge**:
   - Glue Job 2 loads all Parquet files
   - Applies business filters
   - Joins transactions with dimensions
   - Calculates commissions
   - Merges to Iceberg table with SCD Type 1

6. **Final Output**: Iceberg table ready for analytics
   ```
   s3://bucket/iceberg/commission_transactions/
   ```

## 🧪 Testing

### Unit Tests

Coverage requirements: **≥80%** on all changed code

```bash
# Run tests with coverage
pytest tests/unit/ --cov=glue/shared --cov=lambda --cov-report=html

# Run specific test class
pytest tests/unit/test_transformations.py::test_filter_successful_transactions -v
```

### Test Categories

- **Transformations**: Filtering, joining, deduplication
- **SCD Handler**: Merge operations, integrity validation
- **Lambda**: S3 event parsing, DynamoDB operations
- **Integration**: End-to-end Glue job execution (in progress)

## Deployment

### Prerequisites

1. AWS credentials configured
2. Terraform installed
3. S3 bucket created
4. KMS key created
5. PGP key pair generated

### Deployment Steps

```bash
# 1. Plan infrastructure
make deploy-dry

# 2. Review and approve changes
# 3. Deploy
make deploy

# 4. Upload Lambda function
make lambda-build
aws lambda update-function-code \
  --function-name file-ingestion-audit \
  --zip-file fileb://build/lambda_function.zip
```

### Terraform Resources

- Lambda function with S3 trigger
- IAM roles and policies
- DynamoDB audit table
- Glue jobs
- S3 buckets and lifecycle policies
- KMS key policies
- CloudWatch log groups

## 📝 Documentation

See `docs/` directory for detailed documentation:

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design and data flow
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) - Detailed deployment guide
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - Common issues and solutions

## 🔐 Security

### Best Practices Implemented

- Encryption: PGP for data, KMS for keys
- Secrets Management: AWS Secrets Manager for credentials
- IAM: Least privilege roles and policies
- Audit Trail: DynamoDB audit table tracking
- Input Validation: Data validation in transformations
- Error Handling: Graceful error handling without exposing sensitive data

### Secret Management

```bash
# Store PGP private key
aws secretsmanager create-secret \
  --name pgp-private-key-dev \
  --secret-string file://private.key

# Store passphrase
aws secretsmanager create-secret \
  --name pgp-passphrase-dev \
  --secret-string "your-passphrase"
```

## 🐛 Troubleshooting

Common issues and solutions:

### PGP Decryption Fails
- Verify private key format (PEM expected)
- Check passphrase in Secrets Manager
- Ensure file is actually PGP encrypted

### Glue Job Out of Memory
- Increase number of workers in config
- Use broadcast joins for dimension tables
- Partition large joins by key

### SCD Merge Takes Too Long
- Verify indexes on primary keys
- Check for skewed data distribution
- Consider partitioning strategy

See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for more details.

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/your-feature`
2. Write tests for new functionality
3. Ensure 80%+ coverage
4. Format code: `make format`
5. Run linting: `make lint`
6. Submit pull request

## 📄 License

MIT

## 📧 Support

For questions or issues, open a GitHub issue or reach out at sikdartunir@gmail.com

## 🔄 Change Log

### v1.0.0 (2026-08-10)
- Initial release
- Lambda file ingestion audit
- Glue jobs for decrypt and transform
- SCD Type 1 merge to Iceberg
- Comprehensive test suite

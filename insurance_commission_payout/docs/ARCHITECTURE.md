# Architecture Documentation

## System Overview

The Commission Payout Pipeline is a cloud-native data processing system built on AWS services. It implements a modern data lakehouse architecture combining Lambda, Glue, S3, and Iceberg.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     AWS Services                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────┐         ┌──────────────┐                    │
│  │  S3 Input  │         │   AWS KMS    │                    │
│  │  (Raw CSV) │         │   (Encrypt)  │                    │
│  └─────┬──────┘         └──────────────┘                    │
│        │                                                    │
│        │ S3 PUT Event                                       │
│        ▼                                                    │
│  ┌────────────────────────────────────────────┐          │
│  │  Lambda: File Ingestion Audit              │          │
│  │  ├─ Parse S3 event                         │          │
│  │  ├─ Create audit entry                     │          │
│  │  ├─ Check cycle completion                 │          │
│  │  └─ Trigger Glue Job if complete          │          │
│  └────────────────────────────────────────────┘          │
│        │                                                  │
│        ├──────────────────────────────────┬──────────┐   │
│        │                                  │          │   │
│        ▼                                  ▼          ▼   │
│  ┌──────────────────┐          ┌──────────────────┐     │
│  │  DynamoDB Audit  │          │ AWS Secrets Mgr  │     │
│  │  Table           │          │ (PGP Secrets)    │     │
│  └──────────────────┘          └──────────────────┘     │
│                                                          │
│        │ Trigger Job 1                                  │
│        ▼                                                  │
│  ┌────────────────────────────────────────────┐          │
│  │  Glue Job 1: Decrypt & Convert             │          │
│  │  ├─ Retrieve PGP credentials               │          │
│  │  ├─ Decrypt PGP files                      │          │
│  │  ├─ Read CSV with schema inference         │          │
│  │  └─ Write Parquet to S3                    │          │
│  └────────────────────────────────────────────┘          │
│        │                                                │
│        ▼                                                │
│  ┌──────────────────────────────────────┐               │
│  │  S3: Parquet Staging                 │               │
│  │  ├─ transactions/                    │               │
│  │  ├─ policy/                          │               │
│  │  ├─ coverage/                        │               │
│  │  └─ ...                              │               │
│  └──────────────────────────────────────┘               │
│        │ Trigger Job 1b                                 │
│        ▼                                                │
│  ┌────────────────────────────────────────────┐         │
│  │  Glue Job 1b: DQ Check                     │         │
│  │  ├─ Load Parquet files                     │         │
│  │  ├─ Run null / duplicate / range checks    │         │
│  │  ├─ Write DQ report JSON to S3             │         │
│  │  └─ Fail pipeline on any violation         │         │
│  └────────────────────────────────────────────┘         │
│        │ Trigger Job 2                                  │
│        ▼                                                │
│  ┌────────────────────────────────────────────┐         │
│  │  Glue Job 2: Transform & Merge             │         │
│  │  ├─ Load Parquet files                     │         │
│  │  ├─ Apply business filters                 │         │
│  │  ├─ Broadcast joins (dimensions)           │         │
│  │  ├─ Sort-merge joins (large tables)        │         │
│  │  ├─ Calculate commissions                  │         │
│  │  └─ SCD Type 1 MERGE to Iceberg            │         │
│  └────────────────────────────────────────────┘         │
│        │                                                │
│        ▼                                                │
│  ┌──────────────────────────────────────┐               │
│  │  S3: Iceberg Tables (Apache Iceberg) │               │
│  │  ├─ commission_transactions/         │               │
│  │  ├─ policy_dimensions/               │               │
│  │  └─ ...                              │               │
│  └──────────────────────────────────────┘               │
│                                                         │
│  ┌──────────────────────────────────────┐               │
│  │  Glue Catalog Metadata               │               │
│  │  └─ Tables, schemas, partitions      │               │
│  └──────────────────────────────────────┘               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Lambda: File Ingestion Audit

**Purpose**: Track file arrivals and orchestrate pipeline

**Trigger**: S3 PUT events

**Key Responsibilities**:
- Parse S3 events (bucket, key, timestamp)
- Extract cycle date and file type from path
- Create audit entries in DynamoDB
- Detect cycle completion (all files received)
- Trigger Glue Job 1 when cycle complete

**Error Handling**:
- DynamoDB write failures → Log and retry with exponential backoff
- Missing metadata → Skip file, log warning
- Glue job trigger failures → Mark as FAILED in audit

### 2. Glue Job 1: Decrypt & Convert

**Purpose**: Transform encrypted raw data to standardized Parquet format

**Input**: PGP-encrypted CSV files in S3

**Process**:
```
1. Get credentials from Secrets Manager
   ├─ PGP private key
   └─ PGP passphrase

2. For each file in cycle:
   ├─ Download from S3
   ├─ Decrypt using PGP
   ├─ Read CSV with Spark
   ├─ Infer schema
   ├─ Add metadata columns:
   │  ├─ ingestion_date
   │  ├─ cycle_date
   │  └─ file_type
   └─ Write Parquet to S3

3. Clean up temporary files
```

**Metadata Columns Added**:
```
- ingestion_date: Timestamp of file processing
- cycle_date: Processing cycle identifier
- file_type: Type of data (transactions, policy, etc.)
```

### 3. Glue Job 1b: DQ Check

**Purpose**: Gate between raw Parquet and transformation; surface data issues before they corrupt Iceberg tables

**Input**: Parquet files written by Job 1

**Rules** (defined in `config.yaml` under `dq_rules`):

| Check | Description |
|---|---|
| `not_null` | Fails if any row has a null in a critical column |
| `no_duplicates` | Fails if composite primary key has duplicates |
| `positive_values` | Fails if a numeric column has a zero or negative value |
| `allowed_values` | Fails if an enum column contains unexpected values |
| `min_row_count` | Fails if the table has fewer rows than the threshold |

**Output**: `s3://{bucket}/dq_reports/{env}/{cycle_date}/report.json`

**Failure behaviour**: Raises `DQException`; Glue marks the job `FAILED` and downstream Job 2 is not triggered.

**Resource config**: G.1X × 5 workers, no retries (fail fast)

### 4. Glue Job 2: Transform & Merge

**Purpose**: Apply business logic and persist to Iceberg

**Input**: Parquet files from Job 1

**Three-Phase Process**:

#### Phase 1: Filtering
Apply business rules to each dataset:
```
Transactions:
  ├─ transaction_status = 'SUCCESS'
  ├─ is_commission_eligible = True
  └─ transaction_amount > 0

Policies:
  └─ policy_status IN ('ACTIVE', 'RENEWAL')

Other tables:
  └─ No filtering (use as-is)
```

#### Phase 2: Joins
Combine datasets using optimized join strategies:

**Broadcast Joins** (small dimension → large fact):
```
transactions 
  ◀─── broadcast(policy)       [~100KB-100MB]
  ◀─── broadcast(coverage)
  ◀─── broadcast(feature)
  ◀─── broadcast(rider)
```

**Sort-Merge Joins** (large table → large table):
```
transactions 
  ◄─► sort_merge(exchange)     [>100MB]
```

Benefits:
- Broadcast: Avoids network shuffle for small tables
- Sort-Merge: Efficient for large tables with pre-sorting

#### Phase 3: SCD Type 1 Merge
Implement Slowly Changing Dimension Type 1:

```sql
MERGE INTO commission_transactions target
USING source
ON target.transaction_id = source.transaction_id
  AND target.cycle_date = source.cycle_date
WHEN MATCHED THEN
  UPDATE SET
    amount = source.amount,
    status = source.status,
    dw_updated_date = now(),
    dw_updated_by = 'glue_job'
WHEN NOT MATCHED THEN
  INSERT (transaction_id, cycle_date, ..., dw_inserted_date)
  VALUES (...)
```

## Data Models

### Audit Table (DynamoDB)

```
Table: file_ingestion_audit

Partition Key: file_key = "bucket#s3_key"
Sort Key: cycle_date = "20240101"

Attributes:
├─ file_key: PK
├─ cycle_date: SK
├─ bucket: String
├─ object_key: String
├─ file_type: String (transactions, policy, etc.)
├─ file_name: String
├─ ingestion_timestamp: ISO8601
├─ status: String (RECEIVED | PROCESSING | SUCCESS | FAILED)
├─ file_size: Number
├─ created_at: ISO8601
└─ updated_at: ISO8601
```

### Iceberg Table Schema (Example: commission_transactions)

```
commission_transactions/
├─ transaction_id: STRING (PK)
├─ cycle_date: STRING (PK)
├─ policy_id: STRING (FK)
├─ agent_id: STRING
├─ transaction_amount: DOUBLE
├─ commission_rate: DOUBLE
├─ commission_amount: DOUBLE (calculated)
├─ transaction_status: STRING
├─ coverage_id: STRING
├─ exchange_code: STRING
├─ exchange_rate: DOUBLE
├─ dw_inserted_date: TIMESTAMP
├─ dw_updated_date: TIMESTAMP
├─ dw_updated_by: STRING
└─ dw_cycle_date: STRING
```

## Data Flow Sequence

### Normal Path: Cycle Complete

```
Timeline: 20240101

12:00 - File: transactions.csv → S3
        ├─ Lambda triggered
        ├─ Audit entry created (status: RECEIVED)
        └─ Glue Job NOT triggered (other files pending)

13:30 - File: policy.csv → S3
        ├─ Lambda triggered
        ├─ Audit entry created
        └─ Glue Job NOT triggered (other files pending)

... (continue for coverage, feature, exchange, rider)

17:45 - File: rider.csv → S3
        ├─ Lambda triggered
        ├─ Audit entry created
        ├─ Cycle completion check
        ├─ ALL FILES RECEIVED ✓
        └─ Trigger decrypt-and-convert Glue Job

18:00 - Glue Job 1 Starts
        ├─ Load PGP credentials
        ├─ Decrypt 6 files
        ├─ Convert to Parquet
        ├─ Write to S3
        └─ Complete (~10 mins)

18:15 - Trigger dq-check Glue Job

18:20 - Glue Job 1b Starts
        ├─ Run DQ checks on all 6 Parquet tables
        ├─ Write DQ report to S3
        └─ Complete (~5 mins) — fails here if violations found

18:25 - Trigger transform-and-merge Glue Job

18:30 - Glue Job 2 Starts
        ├─ Load Parquet files
        ├─ Apply filters
        ├─ Join tables (broadcast + sort-merge)
        ├─ Calculate commissions
        ├─ Merge to Iceberg (SCD Type 1)
        └─ Complete (~15 mins)

18:45 - Pipeline Complete
        ├─ All data in Iceberg
        ├─ Available for analytics
        └─ Audit trail complete
```

## Performance Considerations

### Broadcast Join Thresholds
- **Small tables** (< 100 MB): Always broadcast
- **Medium tables** (100 MB - 1 GB): Broadcast with care
- **Large tables** (> 1 GB): Use sort-merge join

### Partitioning Strategy
- **Fact tables**: Partition by `cycle_date` for efficient queries
- **Dimension tables**: Partition by `updated_date` or keep unpartitioned
- **Iceberg advantages**: Time travel queries, fast snapshots

### Resource Scaling
- **Glue Job 1**: 5 workers (DPU-based) - high network I/O
- **Glue Job 1b**: 5 workers (G.1X) - light validation workload
- **Glue Job 2**: 10 workers - high CPU/memory for transformations

## Security Architecture

### Data Encryption

**In Transit**:
- S3: HTTPS/TLS (enforced)
- KMS: Encrypted keys stored in AWS

**At Rest**:
- S3: SSE-KMS with customer-managed keys
- DynamoDB: SSE-KMS encryption
- Iceberg tables: Encrypted in S3

### Access Control

**IAM Policies**:
- Lambda: Read S3, Write DynamoDB, Trigger Glue
- Glue: Read S3, Write S3, Read Secrets Manager, Read KMS
- Users: Glue Catalog access with row-level filters

**Secrets Management**:
- PGP keys: AWS Secrets Manager with KMS encryption
- Passphrases: AWS Secrets Manager with rotation policy

### Audit Trail

**Lambda Events**:
- CloudWatch Logs: All invocations
- X-Ray: Distributed tracing (optional)

**Glue Jobs**:
- Glue Logs: Job execution details
- CloudWatch: Performance metrics

**Data**:
- DynamoDB: File audit table
- Iceberg: dw_updated_date, dw_updated_by columns

## Scalability

### Horizontal Scaling

| Component | Scaling Method | Limit |
|-----------|----------------|-------|
| Lambda | Concurrency | AWS account default (1000) |
| Glue | Workers | Depends on DPU quota |
| S3 | Partitions | Unlimited |
| DynamoDB | RCU/WCU | Can be increased on demand |
| Iceberg | Partitions | Best practice: by date |

### Vertical Scaling

- **Glue Job 1**: Increase workers for large file sets
- **Glue Job 2**: Increase workers for complex transformations
- **DynamoDB**: Use on-demand billing for variable load

## Disaster Recovery

### Backup Strategy
- **S3**: Versioning enabled on all buckets
- **DynamoDB**: Point-in-time recovery enabled
- **Iceberg**: Snapshot history available

### Recovery Procedures
1. DynamoDB table: Restore from snapshot
2. S3 data: Restore from previous version
3. Glue Catalog: Rebuild from metadata

## Monitoring and Alerts

### Key Metrics
- Lambda invocation count, duration, errors
- Glue job success rate, duration
- S3 upload rate, storage consumption
- DynamoDB read/write capacity

### CloudWatch Alarms
- Glue job failures
- Lambda errors
- DynamoDB throttling
- S3 bucket size

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed setup.

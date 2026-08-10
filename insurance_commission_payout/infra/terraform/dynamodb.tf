resource "aws_dynamodb_table" "audit" {
  name           = "${var.dynamodb_table_name}_${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "file_key"
  range_key      = "cycle_date"

  attribute {
    name = "file_key"
    type = "S"
  }

  attribute {
    name = "cycle_date"
    type = "S"
  }

  global_secondary_index {
    name            = "CycleDateIndex"
    hash_key        = "cycle_date"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_id
  }

  stream_specification {
    stream_view_type = "NEW_AND_OLD_IMAGES"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(
    var.tags,
    {
      Name = "Commission Payout Audit Table"
    }
  )
}

resource "aws_cloudwatch_metric_alarm" "dynamodb_write_throttle" {
  alarm_name          = "commission-payout-dynamodb-write-throttle-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ConsumedWriteCapacityUnits"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 50
  alarm_description   = "Alert when DynamoDB write capacity is throttled"
  dimensions = {
    TableName = aws_dynamodb_table.audit.name
  }

  tags = var.tags
}

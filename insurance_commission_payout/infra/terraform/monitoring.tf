resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "commission-payout-lambda-errors-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Alert when Lambda errors exceed threshold"
  dimensions = {
    FunctionName = aws_lambda_function.file_ingestion.function_name
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  alarm_name          = "commission-payout-lambda-duration-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Average"
  threshold           = 45000
  alarm_description   = "Alert when Lambda duration is high"
  dimensions = {
    FunctionName = aws_lambda_function.file_ingestion.function_name
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "glue_job_failures" {
  alarm_name          = "commission-payout-glue-failures-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "glue_job_run_failure"
  namespace           = "AWS/Glue"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Alert on Glue job failures"

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "glue_errors" {
  name              = "/aws-glue/commission-payout-errors-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

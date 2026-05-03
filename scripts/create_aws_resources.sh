#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
TEAM_ID="${TEAM_ID:-team07}"
CHALLENGE_CODE="${CHALLENGE_CODE:-cloud07}"

GRADES_TABLE="${DYNAMODB_GRADES_TABLE:-GradeRelease-Grades-team07}"
COURSES_TABLE="${DYNAMODB_COURSES_TABLE:-GradeRelease-Courses-team07}"
IDEMPOTENCY_TABLE="${DYNAMODB_IDEMPOTENCY_TABLE:-GradeRelease-Idempotency-team07}"
SNS_TOPIC_NAME="${SNS_TOPIC_NAME:-GradeRelease-Notifications-team07}"

TAGS=(
  Key=Project,Value=GradeRelease
  Key=Team,Value="$TEAM_ID"
  Key=Benchmark,Value=official
)

create_table_if_missing() {
  local table_name="$1"
  shift
  if aws dynamodb describe-table --region "$REGION" --table-name "$table_name" >/dev/null 2>&1; then
    echo "DynamoDB table already exists: $table_name"
  else
    echo "Creating DynamoDB table: $table_name"
    aws dynamodb create-table --region "$REGION" --table-name "$table_name" "$@"
    aws dynamodb wait table-exists --region "$REGION" --table-name "$table_name"
  fi
}

create_table_if_missing "$GRADES_TABLE" \
  --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --tags "${TAGS[@]}" Key=Stage,Value=shared Key=Challenge,Value="$CHALLENGE_CODE"

create_table_if_missing "$COURSES_TABLE" \
  --attribute-definitions AttributeName=course_code,AttributeType=S \
  --key-schema AttributeName=course_code,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --tags "${TAGS[@]}" Key=Stage,Value=shared Key=Challenge,Value="$CHALLENGE_CODE"

create_table_if_missing "$IDEMPOTENCY_TABLE" \
  --attribute-definitions AttributeName=idempotency_key,AttributeType=S \
  --key-schema AttributeName=idempotency_key,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --tags "${TAGS[@]}" Key=Stage,Value=shared Key=Challenge,Value="$CHALLENGE_CODE"

TOPIC_ARN=$(aws sns create-topic \
  --region "$REGION" \
  --name "$SNS_TOPIC_NAME" \
  --tags "${TAGS[@]}" Key=Stage,Value=shared Key=Challenge,Value="$CHALLENGE_CODE" \
  --query TopicArn \
  --output text)

echo "SNS_TOPIC_ARN=$TOPIC_ARN"
echo "Done. Put this SNS_TOPIC_ARN into your .env or deployment environment variables."

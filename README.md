# Grade Release System - team07 / cloud07

University grade release backend for the Cloud Engineering AWS term project.

## Shared identity

```env
TEAM_ID=team07
CHALLENGE_CODE=cloud07
TEAM_MEMBERS=albayrakk,atilgano,oncut
```

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `AWS_REGION`, DynamoDB table names, and `SNS_TOPIC_ARN` in `.env`.

## Create shared AWS resources

Requires AWS CLI credentials with DynamoDB and SNS permissions.

```bash
export AWS_REGION=us-east-1
export TEAM_ID=team07
export CHALLENGE_CODE=cloud07
./scripts/create_aws_resources.sh
```

Copy the printed `SNS_TOPIC_ARN` into `.env` and deployment environment variables.

## Run locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Smoke test

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/grades \
  -H 'Content-Type: application/json' \
  -d '{"course_code":"CLOUD101","grade_item":"midterm","student_id":"S-100045","student_username":"jdoe","score":85,"request_id":"req-001"}'

curl 'http://localhost:8000/students/S-100045/grades?course_code=CLOUD101'

curl -X POST http://localhost:8000/courses/CLOUD101/finalize \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"finalize-001","notify":true}'
```

## Seed benchmark data

Official benchmark requires at least 1,000 seeded students for `CLOUD101`.

```bash
python scripts/seed_students.py
```

This writes `benchmark/students.csv`.

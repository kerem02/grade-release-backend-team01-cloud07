import os
from functools import lru_cache
from typing import List

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv is optional in AWS deployments; environment variables are enough.
    pass


class Settings:
    def __init__(self) -> None:
        self.team_id = os.getenv("TEAM_ID", "team07")
        self.challenge_code = os.getenv("CHALLENGE_CODE", "cloud07")
        self.team_members: List[str] = [
            member.strip()
            for member in os.getenv("TEAM_MEMBERS", "albayrakk,atilgano,oncut").split(",")
            if member.strip()
        ]
        self.stage = os.getenv("STAGE", "stage1")
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        self.grades_table = os.getenv("DYNAMODB_GRADES_TABLE", "GradeRelease-Grades-team07")
        self.courses_table = os.getenv("DYNAMODB_COURSES_TABLE", "GradeRelease-Courses-team07")
        self.idempotency_table = os.getenv("DYNAMODB_IDEMPOTENCY_TABLE", "GradeRelease-Idempotency-team07")
        self.sns_topic_arn = os.getenv("SNS_TOPIC_ARN", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()

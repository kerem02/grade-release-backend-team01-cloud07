import boto3
from .config import get_settings

settings = get_settings()

dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
sns = boto3.client("sns", region_name=settings.aws_region)

grades_table = dynamodb.Table(settings.grades_table)
courses_table = dynamodb.Table(settings.courses_table)
idempotency_table = dynamodb.Table(settings.idempotency_table)

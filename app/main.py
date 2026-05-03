from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from mangum import Mangum
from pydantic import BaseModel, Field, ValidationError, field_validator

from .aws_clients import courses_table, grades_table, idempotency_table, sns
from .config import get_settings

settings = get_settings()
app = FastAPI(title="Grade Release System", version="1.0.0")


# ---------- Helpers ----------

def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def identity() -> Dict[str, str]:
    return {
        "team_id": settings.team_id,
        "challenge_code": settings.challenge_code,
    }


def grade_pk(course_code: str, student_id: str) -> str:
    return f"COURSE#{course_code}#STUDENT#{student_id}"


def grade_sk(grade_item: str) -> str:
    return f"ITEM#{grade_item}"


def json_safe(value: Any) -> Any:
    """DynamoDB stores maps cleanly, but this keeps response payloads JSON-compatible."""
    return json.loads(json.dumps(value, default=str))


def get_idempotent_response(idempotency_key: str) -> Optional[Dict[str, Any]]:
    item = idempotency_table.get_item(Key={"idempotency_key": idempotency_key}).get("Item")
    if not item:
        return None
    return item.get("response")


def save_idempotent_response(idempotency_key: str, request_id: str, response: Dict[str, Any]) -> None:
    idempotency_table.put_item(
        Item={
            "idempotency_key": idempotency_key,
            "request_id": request_id,
            "response": json_safe(response),
            "created_at": now_utc(),
        },
        ConditionExpression="attribute_not_exists(idempotency_key)",
    )


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": code,
            "message": message,
            **identity(),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
    return error_response(exc.status_code, "http_error", detail)


@app.exception_handler(ValidationError)
async def validation_exception_handler(_: Request, exc: ValidationError) -> JSONResponse:
    return error_response(400, "validation_error", exc.errors()[0].get("msg", "Invalid request"))


# ---------- Models ----------

class GradeRequest(BaseModel):
    course_code: str = Field(min_length=1)
    grade_item: str = Field(min_length=1)
    student_id: str = Field(min_length=1)
    student_username: Optional[str] = None
    score: int = Field(ge=0, le=100)
    request_id: str = Field(min_length=1)

    @field_validator("course_code", "grade_item", "student_id", "request_id")
    @classmethod
    def no_blank_strings(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field cannot be blank")
        return value


class FinalizeRequest(BaseModel):
    request_id: str = Field(min_length=1)
    notify: bool = True

    @field_validator("request_id")
    @classmethod
    def no_blank_request_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("request_id cannot be blank")
        return value


# ---------- Routes ----------

@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "stage": settings.stage,
        "team_id": settings.team_id,
        "team_members": settings.team_members,
        "challenge_code": settings.challenge_code,
        "ts_utc": now_utc(),
    }


@app.post("/grades")
def enter_grade(payload: GradeRequest) -> Dict[str, Any]:
    idempotency_key = f"POST_GRADES#{payload.request_id}"
    previous = get_idempotent_response(idempotency_key)
    if previous:
        return previous

    course = courses_table.get_item(Key={"course_code": payload.course_code}).get("Item")
    if course and course.get("finalized") is True:
        raise HTTPException(status_code=409, detail="Course is already finalized; grades are locked")

    pk = grade_pk(payload.course_code, payload.student_id)
    sk = grade_sk(payload.grade_item)
    existing_grade = grades_table.get_item(Key={"pk": pk, "sk": sk}).get("Item")
    status = "updated" if existing_grade else "stored"

    response = {
        "status": status,
        "course_code": payload.course_code,
        "grade_item": payload.grade_item,
        "student_id": payload.student_id,
        "student_username": payload.student_username,
        "request_id": payload.request_id,
        **identity(),
    }

    grade_item = {
        "pk": pk,
        "sk": sk,
        "course_code": payload.course_code,
        "grade_item": payload.grade_item,
        "student_id": payload.student_id,
        "student_username": payload.student_username or "",
        "score": payload.score,
        "request_id": payload.request_id,
        "updated_at": now_utc(),
    }

    try:
        # Keep idempotency and grade mutation atomic enough for duplicate request protection.
        grades_table.put_item(Item=grade_item)
        save_idempotent_response(idempotency_key, payload.request_id, response)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code == "ConditionalCheckFailedException":
            previous = get_idempotent_response(idempotency_key)
            if previous:
                return previous
        raise HTTPException(status_code=500, detail="Could not store grade") from exc

    return response


@app.get("/students/{student_id}/grades")
def view_student_grades(
    student_id: str,
    course_code: str = Query(..., min_length=1),
) -> Dict[str, Any]:
    pk = grade_pk(course_code, student_id)
    result = grades_table.query(KeyConditionExpression=Key("pk").eq(pk))
    items: List[Dict[str, Any]] = result.get("Items", [])

    grades = [
        {"grade_item": item["grade_item"], "score": int(item["score"])}
        for item in sorted(items, key=lambda x: x.get("grade_item", ""))
    ]
    usernames = [item.get("student_username") for item in items if item.get("student_username")]

    return {
        "student_id": student_id,
        "student_username": usernames[0] if usernames else None,
        "course_code": course_code,
        "grades": grades,
        **identity(),
    }


@app.post("/courses/{course_code}/finalize")
def finalize_course(course_code: str, payload: FinalizeRequest) -> Dict[str, Any]:
    idempotency_key = f"POST_FINALIZE#{course_code}#{payload.request_id}"
    previous = get_idempotent_response(idempotency_key)
    if previous:
        return previous

    course = courses_table.get_item(Key={"course_code": course_code}).get("Item")
    if course and course.get("finalized") is True:
        return {
            "status": "already_finalized",
            "course_code": course_code,
            "request_id": payload.request_id,
            "notification_mode": "sns-publish-only",
            **identity(),
        }

    response = {
        "status": "finalized",
        "course_code": course_code,
        "request_id": payload.request_id,
        "notification_mode": "sns-publish-only",
        **identity(),
    }

    try:
        courses_table.put_item(
            Item={
                "course_code": course_code,
                "finalized": True,
                "finalized_request_id": payload.request_id,
                "finalized_at": now_utc(),
            },
            ConditionExpression="attribute_not_exists(course_code) OR finalized = :false",
            ExpressionAttributeValues={":false": False},
        )
        save_idempotent_response(idempotency_key, payload.request_id, response)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code == "ConditionalCheckFailedException":
            previous = get_idempotent_response(idempotency_key)
            if previous:
                return previous
            return {
                "status": "already_finalized",
                "course_code": course_code,
                "request_id": payload.request_id,
                "notification_mode": "sns-publish-only",
                **identity(),
            }
        raise HTTPException(status_code=500, detail="Could not finalize course") from exc

    if payload.notify and settings.sns_topic_arn:
        try:
            publish_result = sns.publish(
                TopicArn=settings.sns_topic_arn,
                Subject=f"Grades finalized for {course_code}",
                Message=json.dumps(
                    {
                        "event_type": "course_grades_finalized",
                        "course_code": course_code,
                        "team_id": settings.team_id,
                        "challenge_code": settings.challenge_code,
                        "ts_utc": now_utc(),
                    }
                ),
            )
            courses_table.update_item(
                Key={"course_code": course_code},
                UpdateExpression="SET sns_message_id = :mid",
                ExpressionAttributeValues={":mid": publish_result.get("MessageId", "")},
            )
        except ClientError as exc:
            # The course is already finalized. We return success because the API contract focuses on
            # finalize idempotency and at-most-once notification, not guaranteed email delivery.
            print(f"SNS publish failed: {exc}")

    return response


# AWS Lambda entry point for Stage 3.
handler = Mangum(app)

import os
import uuid
from datetime import datetime, timezone

import boto3

REGION = os.getenv("AWS_REGION", "us-east-1")
TABLE_NAME = os.getenv("DYNAMODB_GRADES_TABLE", "GradeRelease-Grades-team07")
COURSE_CODE = os.getenv("COURSE_CODE", "CLOUD101")
COUNT = int(os.getenv("SEED_COUNT", "1000"))
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "benchmark/students.csv")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> None:
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("student_id,student_username\n")
        with table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
            for i in range(1, COUNT + 1):
                student_id = f"S-{100000 + i}"
                username = f"student{i:04d}"
                f.write(f"{student_id},{username}\n")
                pk = f"COURSE#{COURSE_CODE}#STUDENT#{student_id}"
                for grade_item, score in [("midterm", 70 + (i % 20)), ("final", 75 + (i % 20))]:
                    batch.put_item(
                        Item={
                            "pk": pk,
                            "sk": f"ITEM#{grade_item}",
                            "course_code": COURSE_CODE,
                            "grade_item": grade_item,
                            "student_id": student_id,
                            "student_username": username,
                            "score": score,
                            "request_id": f"seed-{uuid.uuid4()}",
                            "updated_at": now_utc(),
                        }
                    )
    print(f"Seeded {COUNT} students for {COURSE_CODE}")
    print(f"Student file written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

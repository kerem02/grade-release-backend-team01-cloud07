import http from "k6/http";
import { check } from "k6";
import { SharedArray } from "k6/data";
import exec from "k6/execution";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const COURSE_CODE = __ENV.COURSE_CODE || "CLOUD101";
const STUDENT_FILE = (__ENV.STUDENT_FILE || "students.csv").replace(/^benchmark\//, "");

const students = new SharedArray("students", function () {
  const raw = open(STUDENT_FILE).trim().split("\n");
  return raw
    .slice(1)
    .filter((line) => line.trim().length > 0)
    .map((line) => {
      const parts = line.split(",");
      return {
        student_id: parts[0].trim(),
        student_username: parts.length > 1 ? parts[1].trim() : "",
      };
    });
});

export const options = {
  scenarios: {
    baseline: {
      executor: "constant-arrival-rate",
      rate: 300,
      timeUnit: "1m",
      duration: "5m",
      preAllocatedVUs: 120,
      maxVUs: 300,
      gracefulStop: "0s",
      exec: "readGrades",
      tags: { phase: "baseline" },
    },
    ramp_up: {
      executor: "ramping-arrival-rate",
      startTime: "5m",
      startRate: 300,
      timeUnit: "1m",
      stages: [
        { duration: "2m", target: 450 },
        { duration: "2m", target: 600 },
        { duration: "2m", target: 750 },
        { duration: "2m", target: 900 },
        { duration: "2m", target: 900 },
      ],
      preAllocatedVUs: 120,
      maxVUs: 300,
      gracefulStop: "0s",
      exec: "readGrades",
      tags: { phase: "ramp_up" },
    },
    burst: {
      executor: "constant-arrival-rate",
      startTime: "15m",
      rate: 1650,
      timeUnit: "1m",
      duration: "7m",
      preAllocatedVUs: 120,
      maxVUs: 300,
      gracefulStop: "0s",
      exec: "readGrades",
      tags: { phase: "burst" },
    },
    recovery: {
      executor: "ramping-arrival-rate",
      startTime: "22m",
      startRate: 1650,
      timeUnit: "1m",
      stages: [
        { duration: "2m", target: 900 },
        { duration: "2m", target: 600 },
        { duration: "2m", target: 300 },
        { duration: "2m", target: 300 },
      ],
      preAllocatedVUs: 120,
      maxVUs: 300,
      gracefulStop: "0s",
      exec: "readGrades",
      tags: { phase: "recovery" },
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
  },
};

export function readGrades() {
  if (students.length === 0) {
    throw new Error("students.csv is empty or missing");
  }

  const index = exec.scenario.iterationInTest % students.length;
  const student = students[index];

  const url =
    `${BASE_URL}/students/${encodeURIComponent(student.student_id)}/grades` +
    `?course_code=${encodeURIComponent(COURSE_CODE)}`;

  const res = http.get(url, {
    tags: {
      endpoint: "read_student_grades",
      course_code: COURSE_CODE,
    },
  });

  check(res, {
    "status is 200": (r) => r.status === 200,
    "response has team_id": (r) => r.body && r.body.includes('"team_id"'),
    "response has challenge_code": (r) =>
      r.body && r.body.includes('"challenge_code"'),
  });
}

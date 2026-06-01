from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path("data")
APPLICATIONS_FILE = DATA_DIR / "applications.json"
APPLICATION_STATUSES = [
    "Saved",
    "Interested",
    "Applied",
    "Recruiter Screen",
    "Technical Screen",
    "Interviewing",
    "Final Round",
    "Offer",
    "Rejected",
    "Withdrawn",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_applications() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not APPLICATIONS_FILE.exists():
        APPLICATIONS_FILE.write_text("[]", encoding="utf-8")
    return json.loads(APPLICATIONS_FILE.read_text(encoding="utf-8"))


def save_applications(applications: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    APPLICATIONS_FILE.write_text(json.dumps(applications, indent=2), encoding="utf-8")


def add_application(
    company: str,
    role_title: str,
    job_url: str = "",
    location: str = "",
    job_description: str = "",
    resume_version: str = "",
    match_score: int = 0,
    notes: str = "",
    username: str = "",
) -> dict:
    applications = load_applications()
    application = {
        "id": str(uuid.uuid4()),
        "company": company,
        "role_title": role_title,
        "job_url": job_url,
        "location": location,
        "job_description": job_description,
        "resume_version": resume_version,
        "match_score": match_score,
        "status": "Saved",
        "notes": notes,
        "username": username,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    applications.append(application)
    save_applications(applications)
    return application


def update_application_status(application_id: str, status: str) -> None:
    if status not in APPLICATION_STATUSES:
        raise ValueError(f"Unknown status: {status}")

    applications = load_applications()
    for application in applications:
        if application["id"] == application_id:
            application["status"] = status
            application["updated_at"] = utc_now()
            break
    save_applications(applications)


def update_application_details(
    application_id: str,
    status: str | None = None,
    notes: str | None = None,
    follow_up_date: str | None = None,
    source: str | None = None,
) -> None:
    if status is not None and status not in APPLICATION_STATUSES:
        raise ValueError(f"Unknown status: {status}")

    applications = load_applications()
    for application in applications:
        if application["id"] == application_id:
            if status is not None:
                application["status"] = status
            if notes is not None:
                application["notes"] = notes
            if follow_up_date is not None:
                application["follow_up_date"] = follow_up_date
            if source is not None:
                application["source"] = source
            application["updated_at"] = utc_now()
            break
    save_applications(applications)

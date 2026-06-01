from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path("data")
MONITORS_FILE = DATA_DIR / "job_monitors.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_monitors(username: str = "") -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not MONITORS_FILE.exists():
        MONITORS_FILE.write_text("[]", encoding="utf-8")
    monitors = json.loads(MONITORS_FILE.read_text(encoding="utf-8"))
    if not username:
        return monitors
    return [monitor for monitor in monitors if monitor.get("username", "") in {"", username}]


def save_monitors(monitors: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MONITORS_FILE.write_text(json.dumps(monitors, indent=2), encoding="utf-8")


def add_monitor(
    username: str,
    name: str,
    target_companies: str,
    job_query: str,
    resume_label: str,
    max_jobs: int = 10,
    max_pages: int = 2,
) -> dict:
    monitors = load_monitors()
    monitor = {
        "id": str(uuid.uuid4()),
        "username": username,
        "name": name or "Job Monitor",
        "target_companies": target_companies,
        "job_query": job_query,
        "resume_label": resume_label,
        "max_jobs": max_jobs,
        "max_pages": max_pages,
        "seen_urls": [],
        "last_run_at": "",
        "last_new_count": 0,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    monitors.append(monitor)
    save_monitors(monitors)
    return monitor


def update_monitor_run(monitor_id: str, discovered_jobs: list, new_jobs: list) -> None:
    monitors = load_monitors()
    for monitor in monitors:
        if monitor["id"] == monitor_id:
            seen = set(monitor.get("seen_urls", []))
            seen.update(job.url for job in discovered_jobs if getattr(job, "url", ""))
            monitor["seen_urls"] = sorted(seen)
            monitor["last_run_at"] = utc_now()
            monitor["last_new_count"] = len(new_jobs)
            monitor["updated_at"] = utc_now()
            break
    save_monitors(monitors)


def identify_new_jobs(monitor: dict, discovered_jobs: list) -> list:
    seen_urls = set(monitor.get("seen_urls", []))
    return [job for job in discovered_jobs if getattr(job, "url", "") not in seen_urls]

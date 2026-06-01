from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO


DATA_DIR = Path("data")
RESUME_DIR = DATA_DIR / "resumes"


def safe_filename(filename: str) -> str:
    stem = Path(filename).stem.strip().lower()
    suffix = Path(filename).suffix.lower()
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", stem).strip("-")
    return f"{cleaned or 'resume'}{suffix}"


def save_uploaded_resume(uploaded_file: BinaryIO, destination: Path = RESUME_DIR) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(getattr(uploaded_file, "name", "resume"))
    path = destination / filename
    path.write_bytes(uploaded_file.getbuffer())
    return path

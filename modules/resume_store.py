from __future__ import annotations

import json
from pathlib import Path

from modules.parser import STRUCTURED_DIR


def load_structured_resumes() -> list[dict]:
    resumes: list[dict] = []
    STRUCTURED_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(STRUCTURED_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
            data["_source_path"] = str(path)
            resumes.append(data)
    return resumes


def save_structured_resume(resume: dict, path: Path | str | None = None) -> None:
    target_path = Path(path or resume.get("_source_path", ""))
    if not target_path:
        raise ValueError("A structured resume path is required.")

    payload = {key: value for key, value in resume.items() if key != "_source_path"}
    target_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def update_resume_metadata(path: Path | str, version_name: str, notes: str, target_roles: list[str]) -> dict:
    target_path = Path(path)
    resume = json.loads(target_path.read_text(encoding="utf-8"))
    metadata = resume.setdefault("metadata", {})
    metadata["version_name"] = version_name.strip() or metadata.get("version_name") or target_path.stem
    metadata["notes"] = notes.strip()
    resume["target_roles"] = [role.strip() for role in target_roles if role.strip()]
    save_structured_resume(resume, target_path)
    resume["_source_path"] = str(target_path)
    return resume


def delete_structured_resume(path: Path | str) -> None:
    target_path = Path(path)
    if target_path.parent.resolve() != STRUCTURED_DIR.resolve():
        raise ValueError("Can only delete resumes from the structured resume directory.")
    target_path.unlink(missing_ok=True)


def resume_summary_rows(resumes: list[dict]) -> list[dict]:
    rows = []
    for resume in resumes:
        metadata = resume.get("metadata", {})
        rows.append(
            {
                "Version": metadata.get("version_name", ""),
                "Candidate": metadata.get("candidate_name", "Unknown Candidate"),
                "Parser": metadata.get("parser", "unknown"),
                "Skills": len(resume.get("skills", [])),
                "Impact Metrics": len(resume.get("impact_metrics", [])),
                "Target Roles": ", ".join(resume.get("target_roles", [])),
                "Notes": metadata.get("notes", ""),
            }
        )
    return rows

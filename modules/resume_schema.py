from __future__ import annotations

from pydantic import BaseModel, Field


class ExperienceEntry(BaseModel):
    company: str = ""
    title: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    bullets: list[str] = Field(default_factory=list)


class StructuredResumeContent(BaseModel):
    candidate_name: str = "Unknown Candidate"
    summary: str = ""
    experience: list[ExperienceEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    leadership: list[str] = Field(default_factory=list)
    impact_metrics: list[str] = Field(default_factory=list)
    seniority_signals: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)


RESUME_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate_name": {"type": "string"},
        "summary": {"type": "string"},
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "title": {"type": "string"},
                    "location": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["company", "title", "location", "start_date", "end_date", "bullets"],
                "additionalProperties": False,
            },
        },
        "skills": {"type": "array", "items": {"type": "string"}},
        "leadership": {"type": "array", "items": {"type": "string"}},
        "impact_metrics": {"type": "array", "items": {"type": "string"}},
        "seniority_signals": {"type": "array", "items": {"type": "string"}},
        "target_roles": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "candidate_name",
        "summary",
        "experience",
        "skills",
        "leadership",
        "impact_metrics",
        "seniority_signals",
        "target_roles",
    ],
    "additionalProperties": False,
}

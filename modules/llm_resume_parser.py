from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from modules.resume_schema import RESUME_JSON_SCHEMA, StructuredResumeContent


load_dotenv()

MAX_RESUME_CHARS = 45000


class ResumeStructureError(RuntimeError):
    """Raised when AI resume structuring cannot produce validated content."""


def structure_resume_with_openai(raw_text: str) -> StructuredResumeContent:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ResumeStructureError("OPENAI_API_KEY is not configured.")

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=os.getenv("OPENAI_RESUME_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini")),
        input=[
            {
                "role": "system",
                "content": (
                    "You are a senior technical recruiter and resume intelligence parser. "
                    "Extract only facts supported by the resume. Do not infer employers, titles, dates, "
                    "certifications, metrics, or skills that are not present. Return structured JSON."
                ),
            },
            {
                "role": "user",
                "content": build_resume_extraction_prompt(raw_text),
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "structured_resume",
                "schema": RESUME_JSON_SCHEMA,
                "strict": True,
            }
        },
    )

    try:
        payload = json.loads(response.output_text)
        return StructuredResumeContent.model_validate(payload)
    except Exception as exc:
        raise ResumeStructureError(f"OpenAI response did not match the resume schema: {exc}") from exc


def build_resume_extraction_prompt(raw_text: str) -> str:
    clipped_text = raw_text[:MAX_RESUME_CHARS]
    return f"""
Extract a structured technical resume profile from the resume text below.

Rules:
- Preserve the candidate's actual wording where useful, but normalize obvious formatting noise.
- Keep skills concise and canonical, for example "Python", "Kubernetes", "OpenAI API".
- Leadership should include management, mentoring, strategy, roadmap, stakeholder, hiring, or cross-functional ownership signals.
- Impact metrics should include quantified outcomes, scale, revenue, cost, latency, reliability, productivity, team size, or usage metrics.
- Seniority signals should capture evidence such as Staff, Principal, Manager, Lead, architecture ownership, roadmap ownership, or team leadership.
- Target roles should be likely role families suggested by the resume, not job recommendations invented from outside context.
- If a field is not present, return an empty string or empty list.

Resume text:
{clipped_text}
""".strip()

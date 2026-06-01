from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from modules.llm_resume_parser import ResumeStructureError, structure_resume_with_openai


DATA_DIR = Path("data")
STRUCTURED_DIR = DATA_DIR / "structured"

SECTION_HEADERS = {
    "summary": ["summary", "profile", "professional summary"],
    "experience": ["experience", "work experience", "professional experience", "employment"],
    "skills": ["skills", "technical skills", "core skills", "technologies"],
    "leadership": ["leadership", "management", "team leadership"],
    "education": ["education", "certifications"],
}

IMPACT_PATTERN = re.compile(
    r"(.{0,80}(?:\b\d+%|\$\d+|\b\d+x\b|\b\d+\+|\b\d{2,}\b).{0,120})",
    re.IGNORECASE,
)


def parse_resume_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix == ".docx":
        return extract_docx_text(path)
    if suffix == ".txt":
        return path.read_text(encoding="utf-8")
    raise ValueError(f"Unsupported resume format: {suffix}")


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def extract_docx_text(path: Path) -> str:
    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()


def structure_resume(raw_text: str, source_file: str, version_name: str, use_llm: bool = True) -> dict:
    if use_llm:
        try:
            content = structure_resume_with_openai(raw_text)
            return build_structured_resume(
                content=content.model_dump(),
                raw_text=raw_text,
                source_file=source_file,
                version_name=version_name,
                parser_name="openai-structured-v1",
            )
        except ResumeStructureError as exc:
            fallback = structure_resume_heuristic(raw_text, source_file, version_name)
            fallback["metadata"]["parser_warning"] = str(exc)
            return fallback

    return structure_resume_heuristic(raw_text, source_file, version_name)


def structure_resume_heuristic(raw_text: str, source_file: str, version_name: str) -> dict:
    normalized = normalize_text(raw_text)
    sections = split_sections(normalized)
    content = {
        "candidate_name": infer_candidate_name(raw_text),
        "summary": sections.get("summary") or infer_summary(normalized),
        "experience": extract_experience(sections.get("experience") or normalized),
        "skills": extract_skills(sections.get("skills") or normalized),
        "leadership": extract_leadership(sections, normalized),
        "impact_metrics": extract_impact_metrics(normalized),
        "seniority_signals": extract_seniority_signals(normalized),
        "target_roles": infer_target_roles(normalized),
    }
    return build_structured_resume(
        content=content,
        raw_text=raw_text,
        source_file=source_file,
        version_name=version_name,
        parser_name="heuristic-v1",
    )


def build_structured_resume(
    content: dict,
    raw_text: str,
    source_file: str,
    version_name: str,
    parser_name: str,
) -> dict:
    return {
        "source_file": source_file,
        "raw_text": raw_text,
        "metadata": {
            "candidate_name": content.get("candidate_name") or infer_candidate_name(raw_text),
            "version_name": version_name,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "parser": parser_name,
        },
        "summary": content.get("summary", ""),
        "experience": content.get("experience", []),
        "skills": content.get("skills", []),
        "leadership": content.get("leadership", []),
        "impact_metrics": content.get("impact_metrics", []),
        "seniority_signals": content.get("seniority_signals", []),
        "target_roles": content.get("target_roles", []),
    }


def normalize_text(text: str) -> str:
    text = text.replace("\u2022", "\n- ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sections(text: str) -> dict[str, str]:
    lines = [line.strip() for line in text.splitlines()]
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in lines:
        header = detect_header(line)
        if header:
            current = header
            sections.setdefault(current, [])
            continue
        if current and line:
            sections[current].append(line)

    return {section: "\n".join(values).strip() for section, values in sections.items()}


def detect_header(line: str) -> str | None:
    cleaned = re.sub(r"[^a-zA-Z ]", "", line).strip().lower()
    if len(cleaned.split()) > 4:
        return None
    for canonical, options in SECTION_HEADERS.items():
        if cleaned in options:
            return canonical
    return None


def infer_candidate_name(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned and len(cleaned.split()) <= 4 and "@" not in cleaned:
            return cleaned
    return "Unknown Candidate"


def infer_summary(text: str) -> str:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    return paragraphs[0][:700] if paragraphs else ""


def extract_experience(text: str) -> list[dict[str, object]]:
    bullets = extract_bullets(text)
    if bullets:
        return [{"title": "Experience", "bullets": bullets[:18]}]
    return [{"title": "Experience", "bullets": [line for line in text.splitlines()[:12] if line.strip()]}]


def extract_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip(" -•\t")
        if len(cleaned) > 24 and (line.strip().startswith(("-", "•")) or re.search(r"\b(led|built|owned|launched|reduced|improved|managed|designed)\b", cleaned, re.I)):
            bullets.append(cleaned)
    return bullets


def extract_skills(text: str) -> list[str]:
    candidates = re.split(r"[,|/\n;]+", text)
    skills: list[str] = []
    for candidate in candidates:
        cleaned = re.sub(r"\s+", " ", candidate.strip(" -•\t"))
        if 1 <= len(cleaned.split()) <= 5 and 2 <= len(cleaned) <= 40:
            skills.append(cleaned)
    return sorted(set(skills), key=str.lower)[:80]


def extract_leadership(sections: dict[str, str], text: str) -> list[str]:
    leadership_text = sections.get("leadership", "")
    bullets = extract_bullets(leadership_text) if leadership_text else []
    if bullets:
        return bullets[:10]

    signals = []
    for line in text.splitlines():
        if re.search(r"\b(led|managed|mentored|hired|coached|stakeholder|roadmap|strategy)\b", line, re.I):
            cleaned = line.strip(" -•\t")
            if len(cleaned) > 24:
                signals.append(cleaned)
    return signals[:10]


def extract_impact_metrics(text: str) -> list[str]:
    metrics = [match.group(1).strip(" -•\t") for match in IMPACT_PATTERN.finditer(text)]
    return sorted(set(metrics), key=metrics.index)[:15]


def extract_seniority_signals(text: str) -> list[str]:
    signals = []
    for line in text.splitlines():
        if re.search(r"\b(staff|principal|senior|lead|manager|director|architect|roadmap|strategy)\b", line, re.I):
            cleaned = line.strip(" -•\t")
            if len(cleaned) > 18:
                signals.append(cleaned)
    return signals[:10]


def infer_target_roles(text: str) -> list[str]:
    role_signals = {
        "AI Engineer": ["llm", "openai", "rag", "machine learning", "ai"],
        "Platform Engineer": ["platform", "developer productivity", "infrastructure"],
        "SRE / Infrastructure Engineer": ["sre", "reliability", "kubernetes", "terraform", "observability"],
        "Engineering Manager": ["manager", "managed", "hiring", "mentored", "roadmap"],
        "Technical Lead": ["lead", "architecture", "stakeholder", "strategy"],
    }
    lowered = text.lower()
    roles = [role for role, terms in role_signals.items() if any(term in lowered for term in terms)]
    return roles[:5]

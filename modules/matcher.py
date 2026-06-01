from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field

from openai import OpenAI


SKILL_WEIGHTS = {
    "ai": 4,
    "llm": 5,
    "openai": 5,
    "rag": 5,
    "agents": 5,
    "python": 3,
    "fastapi": 3,
    "streamlit": 2,
    "kubernetes": 4,
    "terraform": 4,
    "aws": 4,
    "gcp": 4,
    "azure": 3,
    "sre": 5,
    "observability": 4,
    "platform": 4,
    "docker": 3,
    "postgres": 2,
    "redis": 2,
    "sql": 2,
}

TECH_TERMS = {
    "python",
    "typescript",
    "javascript",
    "react",
    "node",
    "sql",
    "postgres",
    "redis",
    "docker",
    "kubernetes",
    "terraform",
    "aws",
    "gcp",
    "azure",
    "linux",
    "ci/cd",
    "fastapi",
    "django",
    "flask",
    "machine learning",
    "llm",
    "openai",
    "rag",
    "vector",
    "embedding",
    "chromadb",
    "langchain",
    "observability",
    "prometheus",
    "grafana",
    "sre",
    "platform",
    "agents",
    "ai",
}

LEADERSHIP_TERMS = {
    "leadership",
    "manager",
    "managed",
    "mentor",
    "mentorship",
    "hiring",
    "roadmap",
    "strategy",
    "stakeholder",
    "cross-functional",
    "technical lead",
    "architecture",
}

DOMAIN_TERMS = {
    "ai": {"ai", "llm", "openai", "rag", "agents", "machine learning", "embedding", "vector"},
    "platform": {"platform", "developer productivity", "infrastructure", "kubernetes", "terraform", "ci/cd"},
    "sre": {"sre", "reliability", "observability", "prometheus", "grafana", "incident", "on-call"},
    "leadership": {"manager", "leadership", "roadmap", "strategy", "hiring", "stakeholder"},
}

SENIORITY_LEVELS = {
    "entry": 1,
    "mid": 2,
    "senior": 3,
    "staff": 4,
    "principal": 5,
    "manager": 4,
    "director": 5,
}


@dataclass
class ScoreBreakdown:
    skills: int = 0
    leadership: int = 0
    seniority: int = 0
    domain: int = 0
    gap_penalty: int = 0


@dataclass
class MatchResult:
    match_score: int
    matching_skills: list[str]
    missing_skills: list[str]
    weighted_hits: dict[str, int]
    seniority_match: str
    recommendation: str
    score_breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    matching_leadership: list[str] = field(default_factory=list)
    missing_leadership: list[str] = field(default_factory=list)
    matching_domains: list[str] = field(default_factory=list)
    resume_gaps: list[str] = field(default_factory=list)
    semantic_score: int = 0
    semantic_method: str = "token_overlap"


def score_resume_for_job(resume: dict, job_description: str) -> MatchResult:
    resume_text = resume_to_text(resume).lower()
    job_text = job_description.lower()

    required_skills = extract_terms(job_text, TECH_TERMS | set(SKILL_WEIGHTS))
    matching_skills = sorted(term for term in required_skills if term in resume_text)
    missing_skills = sorted(term for term in required_skills if term not in resume_text)

    job_leadership = extract_terms(job_text, LEADERSHIP_TERMS)
    matching_leadership = sorted(term for term in job_leadership if term in resume_text)
    missing_leadership = sorted(term for term in job_leadership if term not in resume_text)

    job_domains = infer_domains(job_text)
    resume_domains = infer_domains(resume_text)
    matching_domains = sorted(job_domains & resume_domains)
    semantic_score, semantic_method = calculate_semantic_similarity(resume_to_text(resume), job_description)

    skills_score = weighted_ratio(matching_skills, required_skills, SKILL_WEIGHTS)
    leadership_score = category_ratio(matching_leadership, job_leadership)
    domain_score = category_ratio(matching_domains, job_domains)
    seniority_match, seniority_score = infer_seniority_match(resume_text, job_text)
    gap_penalty = calculate_gap_penalty(missing_skills, missing_leadership)

    final_score = round(
        (skills_score * 0.45)
        + (leadership_score * 0.18)
        + (seniority_score * 0.17)
        + (domain_score * 0.15)
        + (semantic_score * 0.05)
        - gap_penalty
    )
    final_score = max(0, min(100, final_score))

    weighted_hits = {
        term: SKILL_WEIGHTS.get(term, 1)
        for term in matching_skills
        if SKILL_WEIGHTS.get(term, 1) > 1
    }
    resume_gaps = build_resume_gaps(missing_skills, missing_leadership, job_domains, resume_domains)
    recommendation = build_recommendation(
        score=final_score,
        matching_skills=matching_skills,
        missing_skills=missing_skills,
        seniority_match=seniority_match,
        matching_domains=matching_domains,
        resume_gaps=resume_gaps,
    )

    return MatchResult(
        match_score=final_score,
        matching_skills=matching_skills,
        missing_skills=missing_skills[:12],
        weighted_hits=weighted_hits,
        seniority_match=seniority_match,
        recommendation=recommendation,
        score_breakdown=ScoreBreakdown(
            skills=skills_score,
            leadership=leadership_score,
            seniority=seniority_score,
            domain=domain_score,
            gap_penalty=gap_penalty,
        ),
        matching_leadership=matching_leadership,
        missing_leadership=missing_leadership[:8],
        matching_domains=matching_domains,
        resume_gaps=resume_gaps,
        semantic_score=semantic_score,
        semantic_method=semantic_method,
    )


def calculate_semantic_similarity(resume_text: str, job_text: str) -> tuple[int, str]:
    embeddings_enabled = os.getenv("ENABLE_OPENAI_EMBEDDINGS", "").lower() in {"1", "true", "yes"}
    if os.getenv("OPENAI_API_KEY") and embeddings_enabled:
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
            response = client.embeddings.create(model=model, input=[resume_text[:12000], job_text[:12000]])
            resume_vector = response.data[0].embedding
            job_vector = response.data[1].embedding
            return round(max(0, min(1, cosine_similarity(resume_vector, job_vector))) * 100), "openai_embeddings"
        except Exception:
            pass
    return token_semantic_similarity(resume_text, job_text), "token_overlap"


def token_semantic_similarity(resume_text: str, job_text: str) -> int:
    resume_terms = semantic_terms(resume_text)
    job_terms = semantic_terms(job_text)
    if not resume_terms or not job_terms:
        return 0
    overlap = len(resume_terms & job_terms)
    denominator = math.sqrt(len(resume_terms) * len(job_terms))
    return round((overlap / denominator) * 100)


def semantic_terms(text: str) -> set[str]:
    stop_words = {
        "and", "the", "for", "with", "you", "are", "will", "our", "that", "this",
        "from", "role", "team", "work", "job", "jobs", "your", "their", "have",
    }
    tokens = re.findall(r"[a-zA-Z][a-zA-Z+#.]{2,}", text.lower())
    return {token for token in tokens if token not in stop_words}


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0
    return numerator / (left_norm * right_norm)


def resume_to_text(resume: dict) -> str:
    parts = [
        resume.get("summary", ""),
        " ".join(resume.get("skills", [])),
        " ".join(resume.get("leadership", [])),
        " ".join(resume.get("impact_metrics", [])),
        " ".join(resume.get("seniority_signals", [])),
        " ".join(resume.get("target_roles", [])),
        resume.get("raw_text", ""),
    ]
    return "\n".join(parts)


def extract_terms(text: str, terms: set[str]) -> set[str]:
    matches = set()
    for term in terms:
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        if re.search(pattern, text):
            matches.add(term)
    return matches


def infer_domains(text: str) -> set[str]:
    domains = set()
    for domain, terms in DOMAIN_TERMS.items():
        if extract_terms(text, terms):
            domains.add(domain)
    return domains


def weighted_ratio(matching_terms: list[str], required_terms: set[str], weights: dict[str, int]) -> int:
    if not required_terms:
        return 100
    total_weight = sum(weights.get(term, 1) for term in required_terms)
    matched_weight = sum(weights.get(term, 1) for term in matching_terms)
    return round((matched_weight / total_weight) * 100)


def category_ratio(matching_terms: list[str], required_terms: set[str]) -> int:
    if not required_terms:
        return 100
    return round((len(matching_terms) / len(required_terms)) * 100)


def infer_seniority_match(resume_text: str, job_text: str) -> tuple[str, int]:
    job_level = infer_seniority_level(job_text)
    resume_level = infer_seniority_level(resume_text)

    if resume_level == job_level:
        return "Strong", 100
    if resume_level == job_level - 1:
        return "Stretch", 72
    if resume_level > job_level:
        return "Overqualified / Leadership-heavy", 82
    if resume_level < job_level - 1:
        return "Seniority Gap", 45
    return "Aligned", 90


def infer_seniority_level(text: str) -> int:
    if re.search(r"\b(director|head of|vp)\b", text):
        return SENIORITY_LEVELS["director"]
    if re.search(r"\b(principal|distinguished)\b", text):
        return SENIORITY_LEVELS["principal"]
    if re.search(r"\b(staff|manager|engineering manager)\b", text):
        return SENIORITY_LEVELS["staff"]
    if re.search(r"\b(senior|lead|architect|managed|led)\b", text):
        return SENIORITY_LEVELS["senior"]
    if re.search(r"\b(junior|entry|new grad)\b", text):
        return SENIORITY_LEVELS["entry"]
    return SENIORITY_LEVELS["mid"]


def calculate_gap_penalty(missing_skills: list[str], missing_leadership: list[str]) -> int:
    high_weight_gap_count = sum(1 for skill in missing_skills if SKILL_WEIGHTS.get(skill, 1) >= 4)
    leadership_gap_count = len(missing_leadership)
    return min(20, (high_weight_gap_count * 4) + (leadership_gap_count * 2))


def build_resume_gaps(
    missing_skills: list[str],
    missing_leadership: list[str],
    job_domains: set[str],
    resume_domains: set[str],
) -> list[str]:
    gaps = []
    high_priority_skills = [skill for skill in missing_skills if SKILL_WEIGHTS.get(skill, 1) >= 4]
    if high_priority_skills:
        gaps.append(f"Add evidence for high-priority skills: {', '.join(high_priority_skills[:5])}.")
    elif missing_skills:
        gaps.append(f"Add or emphasize supporting skills: {', '.join(missing_skills[:5])}.")

    if missing_leadership:
        gaps.append(f"Strengthen leadership signals around: {', '.join(missing_leadership[:4])}.")

    missing_domains = sorted(job_domains - resume_domains)
    if missing_domains:
        gaps.append(f"Add domain-specific proof for: {', '.join(missing_domains)}.")

    return gaps or ["No major resume gaps detected for this job description."]


def build_recommendation(
    score: int,
    matching_skills: list[str],
    missing_skills: list[str],
    seniority_match: str,
    matching_domains: list[str],
    resume_gaps: list[str],
) -> str:
    if score >= 82:
        base = "High-priority role. The resume shows strong direct alignment."
    elif score >= 68:
        base = "Promising role. Apply with targeted edits before outreach."
    elif score >= 50:
        base = "Possible stretch. Tailoring will matter before applying."
    else:
        base = "Lower fit for this resume version. Consider another version or larger positioning changes."

    strengths = f" Lead with {', '.join(matching_skills[:5])}." if matching_skills else ""
    domains = f" Domain fit: {', '.join(matching_domains)}." if matching_domains else " Domain fit needs clearer evidence."
    gaps = f" Main gap: {resume_gaps[0]}" if resume_gaps else ""
    missing = f" Missing skills to address: {', '.join(missing_skills[:4])}." if missing_skills else ""
    return f"{base}{strengths}{domains}{missing} Seniority signal: {seniority_match}. {gaps}".strip()

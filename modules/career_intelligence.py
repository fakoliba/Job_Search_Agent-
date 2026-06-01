from __future__ import annotations

from dataclasses import dataclass


HIGH_VALUE_SKILLS = {
    "ai",
    "llm",
    "machine learning",
    "openai",
    "rag",
    "agents",
    "python",
    "kubernetes",
    "terraform",
    "aws",
    "gcp",
    "sre",
    "observability",
    "platform",
    "fastapi",
}

ROLE_SKILL_MAP = {
    "AI Engineer": {"python", "llm", "openai", "rag", "agents", "machine learning", "vector", "embedding"},
    "Platform Engineer": {"python", "kubernetes", "terraform", "aws", "gcp", "observability", "platform"},
    "SRE / Infrastructure Engineer": {"sre", "kubernetes", "terraform", "observability", "prometheus", "grafana", "aws"},
    "Engineering Manager": {"leadership", "roadmap", "strategy", "stakeholder", "hiring", "mentor"},
    "Staff Software Engineer": {"architecture", "platform", "python", "strategy", "stakeholder", "systems"},
}

TREND_SKILLS = [
    {"skill": "LLM application engineering", "terms": {"llm", "openai", "rag", "agents"}, "demand": "Very High"},
    {"skill": "AI evaluation and safety", "terms": {"ai", "machine learning", "evaluation"}, "demand": "High"},
    {"skill": "Platform engineering", "terms": {"platform", "kubernetes", "terraform"}, "demand": "High"},
    {"skill": "Cloud infrastructure", "terms": {"aws", "gcp", "azure", "terraform"}, "demand": "High"},
    {"skill": "Observability and reliability", "terms": {"sre", "observability", "prometheus", "grafana"}, "demand": "Medium-High"},
    {"skill": "Developer productivity", "terms": {"platform", "ci/cd", "automation"}, "demand": "Medium-High"},
]

COMPANY_PROFILES = [
    {
        "company": "OpenAI",
        "stage": "AI lab / product",
        "domains": {"ai", "llm", "agents", "python", "platform"},
        "role_families": ["AI Engineer", "Platform Engineer", "SRE / Infrastructure Engineer"],
        "careers_url": "https://openai.com/careers/search/",
    },
    {
        "company": "Anthropic",
        "stage": "AI lab / product",
        "domains": {"ai", "llm", "python", "platform", "sre"},
        "role_families": ["AI Engineer", "Platform Engineer", "SRE / Infrastructure Engineer"],
        "careers_url": "https://www.anthropic.com/careers",
    },
    {
        "company": "NVIDIA",
        "stage": "Enterprise / AI infrastructure",
        "domains": {"ai", "machine learning", "platform", "kubernetes", "systems"},
        "role_families": ["AI Engineer", "Platform Engineer", "Staff Software Engineer"],
        "careers_url": "https://jobs.nvidia.com/careers",
    },
    {
        "company": "Google",
        "stage": "Big tech",
        "domains": {"ai", "platform", "sre", "kubernetes", "gcp", "systems"},
        "role_families": ["AI Engineer", "Platform Engineer", "SRE / Infrastructure Engineer", "Staff Software Engineer"],
        "careers_url": "https://www.google.com/about/careers/applications/jobs/results",
    },
    {
        "company": "Apple",
        "stage": "Big tech",
        "domains": {"platform", "systems", "python", "machine learning", "infrastructure"},
        "role_families": ["Platform Engineer", "Staff Software Engineer", "AI Engineer"],
        "careers_url": "https://jobs.apple.com/en-us/search",
    },
    {
        "company": "Netflix",
        "stage": "Product engineering",
        "domains": {"platform", "sre", "aws", "observability", "systems"},
        "role_families": ["Platform Engineer", "SRE / Infrastructure Engineer", "Staff Software Engineer"],
        "careers_url": "https://explore.jobs.netflix.net/careers",
    },
    {
        "company": "Datadog",
        "stage": "Infrastructure SaaS",
        "domains": {"observability", "sre", "platform", "kubernetes", "python"},
        "role_families": ["SRE / Infrastructure Engineer", "Platform Engineer"],
        "careers_url": "https://www.datadoghq.com/careers/",
    },
    {
        "company": "Stripe",
        "stage": "Product infrastructure",
        "domains": {"platform", "systems", "python", "infrastructure", "observability"},
        "role_families": ["Platform Engineer", "Staff Software Engineer", "Engineering Manager"],
        "careers_url": "https://stripe.com/jobs/search",
    },
]

SALARY_BASES = {
    "AI Engineer": 185_000,
    "Platform Engineer": 170_000,
    "SRE / Infrastructure Engineer": 165_000,
    "Engineering Manager": 195_000,
    "Staff Software Engineer": 210_000,
}

SENIORITY_MULTIPLIERS = {
    "Mid": 0.82,
    "Senior": 1.0,
    "Staff": 1.22,
    "Principal": 1.38,
    "Manager": 1.15,
}

LOCATION_MULTIPLIERS = {
    "Remote US": 1.0,
    "San Francisco Bay Area": 1.18,
    "New York": 1.12,
    "Seattle": 1.08,
    "Austin": 0.95,
    "Other US": 0.9,
}


@dataclass
class SalaryBand:
    low: int
    mid: int
    high: int
    label: str


def build_career_coaching(resumes: list[dict], applications: list[dict]) -> dict:
    primary_resume = choose_primary_resume(resumes)
    skills = normalized_skills(primary_resume)
    leadership_count = len(primary_resume.get("leadership", []))
    impact_count = len(primary_resume.get("impact_metrics", []))
    active_apps = [app for app in applications if app.get("status") not in {"Rejected", "Withdrawn"}]
    avg_match = round(sum(int(app.get("match_score") or 0) for app in applications) / len(applications)) if applications else 0

    strengths = sorted(skills & HIGH_VALUE_SKILLS)
    gaps = infer_role_gaps(primary_resume)
    readiness_score = min(
        100,
        35
        + min(len(strengths), 8) * 5
        + min(leadership_count, 4) * 5
        + min(impact_count, 4) * 4
        + (10 if avg_match >= 75 else 0),
    )

    if {"llm", "openai", "rag", "agents"} & skills:
        positioning = "AI platform builder with hands-on LLM/product engineering signal."
    elif {"kubernetes", "terraform", "sre", "observability"} & skills:
        positioning = "Platform and reliability engineer with infrastructure depth."
    elif leadership_count >= 2:
        positioning = "Technical leader with cross-functional execution and team leverage."
    else:
        positioning = "Software engineer with room to sharpen role-specific positioning."

    next_actions = [
        "Pick one primary target lane for the next two weeks and tune one resume version around it.",
        "Add two quantified bullets for the strongest target role family.",
        "Save high-fit roles to the tracker and follow up within 5 business days.",
    ]
    if gaps:
        next_actions.insert(1, f"Close the most visible gap first: {gaps[0]}.")
    if not active_apps:
        next_actions.append("Build an initial pipeline of 8-12 active roles before optimizing too heavily.")

    return {
        "readiness_score": readiness_score,
        "positioning": positioning,
        "strengths": strengths[:10],
        "gaps": gaps[:8],
        "next_actions": next_actions,
        "pipeline_health": summarize_pipeline(applications),
        "recommended_roles": recommend_roles(primary_resume)[:4],
    }


def recommend_target_companies(
    resume: dict,
    preferred_role: str = "",
    preferred_stage: str = "Any",
    limit: int = 8,
) -> list[dict]:
    skills = normalized_skills(resume)
    target_roles = {role.lower() for role in resume.get("target_roles", [])}
    preferred_role_lower = preferred_role.lower().strip()
    preferred_stage_lower = preferred_stage.lower().strip()
    recommendations = []

    for profile in COMPANY_PROFILES:
        domain_overlap = sorted(skills & profile["domains"])
        role_bonus = 0
        if preferred_role_lower:
            role_bonus += sum(25 for role in profile["role_families"] if preferred_role_lower in role.lower())
        role_bonus += sum(10 for role in profile["role_families"] if role.lower() in target_roles)
        stage_bonus = 15 if preferred_stage_lower not in {"", "any"} and preferred_stage_lower in profile["stage"].lower() else 0
        score = min(100, len(domain_overlap) * 12 + role_bonus + stage_bonus)
        if score == 0:
            score = 10

        recommendations.append(
            {
                "company": profile["company"],
                "target_score": score,
                "stage": profile["stage"],
                "role_families": profile["role_families"],
                "matching_signals": domain_overlap,
                "careers_url": profile["careers_url"],
                "why": build_company_target_reason(profile, domain_overlap, preferred_role),
            }
        )

    return sorted(recommendations, key=lambda item: item["target_score"], reverse=True)[:limit]


def build_market_intelligence(resume: dict, role_family: str, location: str, seniority: str) -> dict:
    skills = normalized_skills(resume)
    trends = []
    for trend in TREND_SKILLS:
        matched = sorted(skills & trend["terms"])
        trends.append(
            {
                "trend": trend["skill"],
                "demand": trend["demand"],
                "resume_coverage": "Strong" if len(matched) >= 2 else "Partial" if matched else "Gap",
                "matching_skills": matched,
                "action": trend_action(trend["skill"], matched),
            }
        )

    salary_band = estimate_salary_band(role_family, location, seniority)
    return {
        "role_family": role_family,
        "location": location,
        "seniority": seniority,
        "salary_band": salary_band,
        "trends": trends,
        "market_summary": build_market_summary(trends, salary_band),
        "disclaimer": "Salary bands are heuristic US total-cash estimates for planning, not live compensation data.",
    }


def choose_primary_resume(resumes: list[dict]) -> dict:
    if not resumes:
        return {}
    return max(
        resumes,
        key=lambda resume: (
            len(normalized_skills(resume) & HIGH_VALUE_SKILLS),
            len(resume.get("leadership", [])),
            len(resume.get("impact_metrics", [])),
        ),
    )


def normalized_skills(resume: dict) -> set[str]:
    fields = [
        resume.get("summary", ""),
        " ".join(resume.get("skills", [])),
        " ".join(resume.get("leadership", [])),
        " ".join(resume.get("impact_metrics", [])),
        " ".join(resume.get("target_roles", [])),
        resume.get("raw_text", ""),
    ]
    text = " ".join(fields).lower()
    skills = {skill.lower().strip() for skill in resume.get("skills", []) if str(skill).strip()}
    known_terms = set().union(*ROLE_SKILL_MAP.values(), HIGH_VALUE_SKILLS)
    skills.update(term for term in known_terms if term in text)
    return skills


def recommend_roles(resume: dict) -> list[dict]:
    skills = normalized_skills(resume)
    roles = []
    for role, required_skills in ROLE_SKILL_MAP.items():
        matches = sorted(skills & required_skills)
        score = round((len(matches) / len(required_skills)) * 100) if required_skills else 0
        roles.append({"role": role, "score": score, "matching_skills": matches})
    return sorted(roles, key=lambda item: item["score"], reverse=True)


def infer_role_gaps(resume: dict) -> list[str]:
    recommendations = recommend_roles(resume)
    if not recommendations:
        return []
    top_role = recommendations[0]
    required = ROLE_SKILL_MAP.get(top_role["role"], set())
    present = set(top_role["matching_skills"])
    gaps = sorted(required - present)
    return [f"Add stronger evidence for {gap}" for gap in gaps]


def summarize_pipeline(applications: list[dict]) -> str:
    if not applications:
        return "No tracked applications yet. Start with a focused target list and save roles as soon as they look relevant."
    active_count = sum(1 for app in applications if app.get("status") not in {"Rejected", "Withdrawn"})
    high_fit_count = sum(1 for app in applications if int(app.get("match_score") or 0) >= 80)
    return f"{active_count} active application(s), {high_fit_count} high-fit role(s), {len(applications)} total tracked."


def build_company_target_reason(profile: dict, domain_overlap: list[str], preferred_role: str) -> str:
    role_text = preferred_role or ", ".join(profile["role_families"][:2])
    if domain_overlap:
        return f"Strong overlap for {role_text}: {', '.join(domain_overlap[:5])}."
    return f"Possible target for {role_text}, but tailor the resume before prioritizing."


def estimate_salary_band(role_family: str, location: str, seniority: str) -> SalaryBand:
    base = SALARY_BASES.get(role_family, 170_000)
    seniority_multiplier = SENIORITY_MULTIPLIERS.get(seniority, 1.0)
    location_multiplier = LOCATION_MULTIPLIERS.get(location, 1.0)
    mid = round_to_nearest_5000(base * seniority_multiplier * location_multiplier)
    return SalaryBand(
        low=round_to_nearest_5000(mid * 0.82),
        mid=mid,
        high=round_to_nearest_5000(mid * 1.22),
        label=f"${mid * 0.82 / 1000:.0f}k-${mid * 1.22 / 1000:.0f}k",
    )


def round_to_nearest_5000(value: float) -> int:
    return int(round(value / 5000) * 5000)


def trend_action(trend: str, matched: list[str]) -> str:
    if len(matched) >= 2:
        return "Feature this as a strength in resume bullets and interview stories."
    if matched:
        return "Add one project or metric that proves depth beyond keyword familiarity."
    return f"Consider a small proof-of-work project or certification aligned to {trend.lower()}."


def build_market_summary(trends: list[dict], salary_band: SalaryBand) -> str:
    strong = [trend["trend"] for trend in trends if trend["resume_coverage"] == "Strong"]
    gaps = [trend["trend"] for trend in trends if trend["resume_coverage"] == "Gap"]
    strength_text = ", ".join(strong[:3]) if strong else "no dominant market trend yet"
    gap_text = ", ".join(gaps[:3]) if gaps else "no major trend gaps"
    return f"Your strongest market signals are {strength_text}. Main watch areas: {gap_text}. Planning salary midpoint: ${salary_band.mid:,}."

from __future__ import annotations

import re
from dataclasses import dataclass


COMPANY_TYPE_SIGNALS = {
    "AI lab / product": {"ai", "llm", "model", "research", "safety", "alignment", "inference"},
    "Big Tech": {"scale", "privacy", "consumer", "device", "cloud", "platform", "ecosystem"},
    "Infrastructure SaaS": {"observability", "monitoring", "cloud", "kubernetes", "infrastructure", "reliability"},
    "Fintech / Payments": {"payment", "risk", "fraud", "ledger", "financial", "commerce", "billing"},
    "Product engineering": {"product", "customer", "experimentation", "streaming", "growth", "personalization"},
    "Startup / Scaleup": {"startup", "0 to 1", "ambiguous", "ownership", "fast-paced", "founding"},
}

ROLE_FAMILY_SIGNALS = {
    "AI Engineer": {"ai", "ml", "machine learning", "llm", "model", "rag", "agent", "inference"},
    "Platform Engineer": {"platform", "developer productivity", "kubernetes", "terraform", "infrastructure"},
    "SRE / Infrastructure Engineer": {"sre", "reliability", "observability", "incident", "on-call", "cloud"},
    "Backend Engineer": {"backend", "api", "distributed", "service", "database", "python", "java", "go"},
    "Frontend Engineer": {"frontend", "react", "typescript", "web", "design system", "ui"},
    "Engineering Manager": {"manager", "people", "hiring", "roadmap", "team", "mentoring"},
    "Staff Software Engineer": {"staff", "principal", "architecture", "technical leadership", "strategy"},
}

KNOWN_COMPANY_OVERRIDES = {
    "apple": {
        "company_type": "Big Tech",
        "confidence": "Company-specific",
        "themes": [
            "Functional-specialty depth and ownership",
            "User privacy, product quality, and craft",
            "Cross-functional collaboration across hardware, software, and product teams",
        ],
        "process_notes": [
            "Interview loops can vary heavily by team and product area.",
            "Expect deep project review, technical fundamentals, and collaboration judgment.",
        ],
    },
    "google": {
        "company_type": "Big Tech",
        "confidence": "Company-specific",
        "themes": ["Scale, system design, engineering rigor, product judgment"],
        "process_notes": ["Expect coding, technical design, behavioral, and team matching conversations."],
    },
    "openai": {
        "company_type": "AI lab / product",
        "confidence": "Company-specific",
        "themes": ["AI systems, safety, product impact, fast execution under ambiguity"],
        "process_notes": ["Expect role-specific depth, applied AI judgment, collaboration, and mission alignment."],
    },
    "nvidia": {
        "company_type": "Infrastructure SaaS",
        "confidence": "Company-specific",
        "themes": ["Accelerated computing, AI infrastructure, systems performance"],
        "process_notes": ["Expect technical depth in systems, performance, or platform areas depending on team."],
    },
}


@dataclass
class CompanyPrepRequest:
    company: str
    role_title: str
    job_description: str
    resume: dict
    careers_url: str = ""
    prep_focus: str = "Full Loop"


def build_company_interview_profile(request: CompanyPrepRequest) -> dict:
    company_key = normalize_company_name(request.company)
    override = KNOWN_COMPANY_OVERRIDES.get(company_key, {})
    company_type = override.get("company_type") or infer_company_type(request.company, request.job_description, request.careers_url)
    role_family = infer_role_family(request.role_title, request.job_description)
    resume_signals = extract_resume_signals(request.resume)
    rounds = generate_interview_rounds(company_type, role_family, request.prep_focus)
    questions = generate_interview_questions(company_type, role_family, request.prep_focus, resume_signals)
    story_map = generate_resume_story_map(request.resume, role_family, company_type)
    readiness = calculate_interview_readiness(request.resume, role_family, company_type)

    themes = build_company_themes(company_type, role_family)
    if override.get("themes"):
        themes = list(dict.fromkeys([*override["themes"], *themes]))

    process_notes = override.get("process_notes", [])
    sources = build_source_labels(bool(override), bool(request.job_description.strip()), bool(request.careers_url.strip()))

    return {
        "company": request.company or "Target Company",
        "company_type": company_type,
        "role_family": role_family,
        "prep_focus": request.prep_focus,
        "confidence": override.get("confidence") or "Company-type inferred",
        "sources": sources,
        "themes": themes,
        "process_notes": process_notes,
        "rounds": rounds,
        "technical_questions": questions["technical"],
        "behavioral_questions": questions["behavioral"],
        "resume_story_map": story_map,
        "readiness": readiness,
        "study_plan": generate_study_plan(role_family, company_type, request.prep_focus),
        "questions_to_ask": generate_questions_to_ask(company_type, role_family),
    }


def normalize_company_name(company: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", company.lower())


def infer_company_type(company: str, job_description: str, careers_url: str = "") -> str:
    text = f"{company} {job_description} {careers_url}".lower()
    best_type = "Product engineering"
    best_score = 0
    for company_type, signals in COMPANY_TYPE_SIGNALS.items():
        score = sum(1 for signal in signals if signal in text)
        if score > best_score:
            best_type = company_type
            best_score = score
    return best_type


def infer_role_family(role_title: str, job_description: str) -> str:
    text = f"{role_title} {job_description}".lower()
    best_role = "Software Engineer"
    best_score = 0
    for role_family, signals in ROLE_FAMILY_SIGNALS.items():
        score = sum(1 for signal in signals if signal in text)
        if score > best_score:
            best_role = role_family
            best_score = score
    return best_role


def extract_resume_signals(resume: dict) -> dict:
    return {
        "skills": [str(skill) for skill in resume.get("skills", [])[:10]],
        "leadership": [str(item) for item in resume.get("leadership", [])[:5]],
        "impact": [str(item) for item in resume.get("impact_metrics", [])[:5]],
        "summary": resume.get("summary", ""),
    }


def generate_interview_rounds(company_type: str, role_family: str, prep_focus: str) -> list[dict]:
    rounds = [
        {
            "round": "Recruiter Screen",
            "focus": "Motivation, timeline, compensation, location, and role alignment.",
            "source": "Common hiring-process pattern",
        },
        {
            "round": "Hiring Manager Screen",
            "focus": "Scope fit, communication style, project ownership, and team expectations.",
            "source": "Role-family inferred",
        },
    ]
    if prep_focus in {"Full Loop", "Coding"} and role_family not in {"Engineering Manager"}:
        rounds.append(
            {
                "round": "Coding / Technical Screen",
                "focus": "Practical problem solving, data structures, APIs, debugging, and code clarity.",
                "source": "Role-family inferred",
            }
        )
    if prep_focus in {"Full Loop", "System Design"} and role_family in {
        "AI Engineer",
        "Platform Engineer",
        "SRE / Infrastructure Engineer",
        "Backend Engineer",
        "Staff Software Engineer",
    }:
        rounds.append(
            {
                "round": "System or Domain Design",
                "focus": system_design_focus(company_type, role_family),
                "source": "Company-type and role-family inferred",
            }
        )
    if prep_focus in {"Full Loop", "Behavioral", "Manager Screen"}:
        rounds.append(
            {
                "round": "Behavioral / Collaboration",
                "focus": "Conflict, ambiguity, tradeoffs, stakeholder alignment, and learning from mistakes.",
                "source": "Common hiring-process pattern",
            }
        )
    return rounds


def system_design_focus(company_type: str, role_family: str) -> str:
    if role_family == "AI Engineer":
        return "LLM application architecture, evaluation, model integration, safety, and production reliability."
    if role_family == "SRE / Infrastructure Engineer":
        return "Reliability, incident response, observability, capacity, and failure-mode design."
    if role_family == "Platform Engineer":
        return "Developer platforms, paved roads, CI/CD, infrastructure abstractions, and operational ownership."
    if company_type == "Fintech / Payments":
        return "Correctness, idempotency, auditability, risk controls, and high-availability services."
    return "Scalable services, API boundaries, data modeling, reliability, and tradeoff communication."


def generate_interview_questions(company_type: str, role_family: str, prep_focus: str, resume_signals: dict) -> dict:
    skills = ", ".join(resume_signals["skills"][:5]) or "your core technical stack"
    technical = [
        f"Design a reliable system for a {role_family} responsibility in a {company_type} environment.",
        f"Walk through a production issue involving {skills}; how would you detect, debug, and prevent recurrence?",
        "What tradeoffs would you make between speed, reliability, cost, and user experience?",
        "How would you measure whether your technical solution is successful after launch?",
        "Describe a technical decision where the simplest solution was not the right one.",
        "How would you onboard a team to a platform or tool you built?",
    ]
    if role_family == "AI Engineer":
        technical.extend(
            [
                "How would you evaluate an LLM feature before releasing it to users?",
                "How would you design guardrails for hallucination, latency, and cost?",
            ]
        )
    elif role_family == "SRE / Infrastructure Engineer":
        technical.extend(
            [
                "How would you design observability for an unreliable service?",
                "How would you run a post-incident review that leads to durable improvements?",
            ]
        )

    behavioral = [
        "Tell me about a time you led through ambiguity.",
        "Tell me about a time you disagreed with a technical direction and how you handled it.",
        "Describe a project where you had to influence stakeholders without authority.",
        "Tell me about a mistake or outage and what you changed afterward.",
        "How do you decide when to push for quality versus move quickly?",
        "Tell me about a time you raised the bar for a team or system.",
    ]
    if prep_focus == "Manager Screen":
        behavioral.extend(
            [
                "How do you set priorities when a team has too many urgent requests?",
                "How do you coach an engineer who is technically strong but struggling to collaborate?",
            ]
        )

    return {"technical": technical[:8], "behavioral": behavioral[:8]}


def generate_resume_story_map(resume: dict, role_family: str, company_type: str) -> list[dict]:
    leadership = resume.get("leadership", [])
    impact = resume.get("impact_metrics", [])
    fallback_stories = [
        "A technically difficult project with measurable impact.",
        "A cross-functional project where you aligned stakeholders.",
        "A reliability, platform, or operational improvement story.",
    ]
    stories = [*leadership[:3], *impact[:3]] or fallback_stories
    themes = ["Ownership", "Technical depth", "Collaboration", "Impact", "Learning"]
    return [
        {
            "theme": themes[index % len(themes)],
            "story": story,
            "how_to_use": f"Use this to prove {role_family} readiness in a {company_type} interview loop.",
        }
        for index, story in enumerate(stories[:5])
    ]


def calculate_interview_readiness(resume: dict, role_family: str, company_type: str) -> dict:
    skills_text = " ".join(str(skill).lower() for skill in resume.get("skills", []))
    leadership_count = len(resume.get("leadership", []))
    impact_count = len(resume.get("impact_metrics", []))
    role_signals = ROLE_FAMILY_SIGNALS.get(role_family, set())
    matched_role_signals = sum(1 for signal in role_signals if signal in skills_text)

    coding = min(100, 45 + matched_role_signals * 8)
    design = min(100, 45 + impact_count * 8 + matched_role_signals * 5)
    behavioral = min(100, 50 + leadership_count * 10 + impact_count * 5)
    company = 65 if company_type else 50
    overall = round((coding + design + behavioral + company) / 4)
    return {
        "overall": overall,
        "coding": coding,
        "system_design": design,
        "behavioral": behavioral,
        "company_knowledge": company,
    }


def build_company_themes(company_type: str, role_family: str) -> list[str]:
    themes = [
        f"{role_family} depth and practical execution",
        "Clear tradeoff communication",
        "Evidence of measurable impact",
    ]
    if company_type == "AI lab / product":
        themes.append("AI safety, evaluation, product usefulness, and fast iteration")
    elif company_type == "Big Tech":
        themes.append("Scale, quality, collaboration, privacy, and long-term maintainability")
    elif company_type == "Infrastructure SaaS":
        themes.append("Reliability, customer trust, observability, and operational excellence")
    elif company_type == "Fintech / Payments":
        themes.append("Correctness, risk management, compliance, and resilience")
    return themes


def build_source_labels(has_override: bool, has_job_description: bool, has_careers_url: bool) -> list[str]:
    sources = ["Role-family inferred", "Resume-based"]
    if has_job_description:
        sources.insert(0, "Job-description inferred")
    if has_careers_url:
        sources.append("Careers-page context")
    if has_override:
        sources.insert(0, "Company-specific overlay")
    return sources


def generate_study_plan(role_family: str, company_type: str, prep_focus: str) -> list[str]:
    return [
        "Day 1: Map the job description to resume proof points and identify weak areas.",
        f"Day 2: Refresh {role_family} fundamentals and prepare one deep technical story.",
        f"Day 3: Practice a {company_type} system or domain design question.",
        "Day 4: Prepare STAR answers for ambiguity, conflict, impact, and failure recovery.",
        "Day 5: Research the company product, engineering priorities, and recent public work.",
        f"Day 6: Run a mock {prep_focus.lower()} interview and tighten weak answers.",
        "Day 7: Polish opening pitch, questions for interviewers, and closing summary.",
    ]


def generate_questions_to_ask(company_type: str, role_family: str) -> list[str]:
    return [
        f"What does excellent performance look like for this {role_family} role in the first six months?",
        "Which technical problems are most important for the team this year?",
        "How does the team balance product velocity with reliability and long-term quality?",
        f"How does this team collaborate with adjacent teams in a {company_type} environment?",
        "What would make someone unsuccessful in this role?",
    ]

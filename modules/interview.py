from __future__ import annotations

from modules.generator import DraftRequest, generate_with_llm


def generate_interview_prep(request: DraftRequest) -> str:
    return generate_with_llm(
        request,
        task=(
            "Create an interview preparation brief for this role. Include: 1) likely interview loops, "
            "2) 8 role-specific technical questions, 3) 6 behavioral questions, 4) 4 STAR story prompts "
            "grounded in the resume, 5) a focused 7-day study plan, and 6) a concise closing pitch. "
            "Keep it practical and specific to the job description."
        ),
        fallback=fallback_interview_prep,
    )


def fallback_interview_prep(request: DraftRequest) -> str:
    role = request.role_title or "this role"
    company = request.company or "the company"
    skills = request.resume.get("skills", [])[:8]
    skill_text = ", ".join(skills) or "the core role requirements"
    leadership = request.resume.get("leadership", [])[:3]

    technical_questions = [
        f"How would you design a reliable system for {role} responsibilities?",
        f"Which tradeoffs would you consider when scaling systems that depend on {skill_text}?",
        "How would you diagnose a production reliability issue end to end?",
        "How would you evaluate build-versus-buy decisions for platform or AI tooling?",
        "How would you measure success for the first 90 days in this role?",
        "How would you approach observability, incident response, and operational readiness?",
        "How would you explain a complex architecture decision to non-specialist stakeholders?",
        "How would you reduce manual workflow overhead with automation or AI?",
    ]
    behavioral_questions = [
        "Tell me about a time you led through ambiguity.",
        "Tell me about a technical decision you would make differently now.",
        "Describe a time you influenced stakeholders without direct authority.",
        "Tell me about a time you improved reliability or delivery speed.",
        "Describe a conflict around technical priorities and how you handled it.",
        "Tell me about a time you mentored or raised the bar for a team.",
    ]
    stories = leadership or [
        "A platform or infrastructure project with measurable impact.",
        "A cross-functional project where you aligned stakeholders.",
        "A reliability, incident, or operational improvement story.",
    ]

    lines = [
        f"# Interview Prep: {role} at {company}",
        "",
        "## Likely Interview Loops",
        "- Recruiter screen: motivation, fit, compensation, timeline.",
        "- Technical screen: architecture, coding or systems fundamentals.",
        "- Hiring manager: scope, leadership, execution judgment.",
        "- Cross-functional or bar-raiser: communication, tradeoffs, culture fit.",
        "",
        "## Technical Questions",
        *[f"- {question}" for question in technical_questions],
        "",
        "## Behavioral Questions",
        *[f"- {question}" for question in behavioral_questions],
        "",
        "## STAR Story Prompts",
        *[f"- {story}" for story in stories[:4]],
        "",
        "## 7-Day Study Plan",
        "- Day 1: Review the job description and map requirements to resume evidence.",
        "- Day 2: Prepare two system design stories and one reliability story.",
        f"- Day 3: Refresh technical depth around {skill_text}.",
        "- Day 4: Practice behavioral answers using STAR format.",
        "- Day 5: Prepare questions for the hiring manager and team.",
        "- Day 6: Mock interview: one technical, one behavioral.",
        "- Day 7: Polish opening pitch, closing pitch, and compensation/timeline notes.",
        "",
        "## Closing Pitch",
        f"I bring a mix of hands-on engineering, platform judgment, and execution discipline that maps well to {role}. "
        "I can help the team turn ambiguous technical goals into reliable systems and measurable outcomes.",
    ]
    return "\n".join(lines)

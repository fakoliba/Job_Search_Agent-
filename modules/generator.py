from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI


@dataclass
class DraftRequest:
    resume: dict
    job_description: str
    company: str = ""
    role_title: str = ""


def generate_resume_bullets(request: DraftRequest) -> str:
    return generate_with_llm(
        request,
        task=(
            "Create 6 tailored resume bullets for this role. Use concise, metric-oriented, recruiter-quality wording. "
            "Do not fabricate metrics; mark likely placeholders in brackets."
        ),
        fallback=fallback_resume_bullets,
    )


def generate_why_company(request: DraftRequest) -> str:
    return generate_with_llm(
        request,
        task="Write a crisp 'Why this company?' answer in first person, grounded in the role and candidate background.",
        fallback=fallback_why_company,
    )


def generate_outreach(request: DraftRequest) -> str:
    return generate_with_llm(
        request,
        task="Write a concise recruiter outreach message under 120 words with a clear value proposition and soft CTA.",
        fallback=fallback_outreach,
    )


def generate_cover_letter(request: DraftRequest) -> str:
    return generate_with_llm(
        request,
        task="Write a focused cover letter under 350 words with strong technical alignment and leadership signal.",
        fallback=fallback_cover_letter,
    )


def generate_with_llm(request: DraftRequest, task: str, fallback) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return fallback(request)

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        input=[
            {
                "role": "system",
                "content": "You are an expert technical recruiter and resume strategist for AI, platform, SRE, and engineering leadership roles.",
            },
            {
                "role": "user",
                "content": build_prompt(request, task),
            },
        ],
    )
    return response.output_text.strip()


def build_prompt(request: DraftRequest, task: str) -> str:
    resume = request.resume
    return f"""
Task:
{task}

Company:
{request.company or "Unknown"}

Role:
{request.role_title or "Unknown"}

Resume Summary:
{resume.get("summary", "")}

Skills:
{", ".join(resume.get("skills", []))}

Leadership:
{chr(10).join(resume.get("leadership", []))}

Impact Metrics:
{chr(10).join(resume.get("impact_metrics", []))}

Job Description:
{request.job_description}
""".strip()


def fallback_resume_bullets(request: DraftRequest) -> str:
    skills = ", ".join(request.resume.get("skills", [])[:6]) or "the required technical skills"
    return "\n".join(
        [
            f"- Built and improved systems aligned with {skills}, emphasizing measurable product and platform impact.",
            "- Led cross-functional execution across engineering, product, and stakeholder groups to deliver high-quality outcomes.",
            "- Improved reliability, delivery speed, or operational maturity using pragmatic engineering practices and automation.",
            "- Translated ambiguous business needs into scalable technical plans, tradeoffs, and implementation milestones.",
            "- Applied AI/platform engineering practices to increase developer productivity and reduce manual workflow overhead.",
            "- Drove measurable improvements in performance, cost, quality, or team execution [add verified metric].",
        ]
    )


def fallback_why_company(request: DraftRequest) -> str:
    company = request.company or "your company"
    role = request.role_title or "this role"
    return (
        f"I am interested in {company} because {role} sits at the intersection of technical depth, product impact, "
        "and scalable execution. My background maps well to teams that need pragmatic engineering leadership, strong "
        "platform instincts, and the ability to turn ambiguous problems into reliable systems."
    )


def fallback_outreach(request: DraftRequest) -> str:
    role = request.role_title or "the open role"
    company = request.company or "your team"
    return (
        f"Hi, I am interested in {role} at {company}. My background spans platform engineering, AI-enabled workflows, "
        "reliability, and technical leadership, and I see a strong fit with the role's needs. I would welcome the chance "
        "to share how I can help the team deliver durable engineering outcomes."
    )


def fallback_cover_letter(request: DraftRequest) -> str:
    company = request.company or "your company"
    role = request.role_title or "this role"
    return (
        f"Dear Hiring Team,\n\n"
        f"I am excited to apply for {role} at {company}. My experience combines hands-on engineering, platform thinking, "
        "and leadership across ambiguous technical initiatives. I am strongest in environments that require clear system "
        "design, reliable execution, and practical use of automation or AI to improve team outcomes.\n\n"
        "The role stood out because it calls for both technical judgment and the ability to create measurable impact. "
        "I would bring a bias for durable architecture, thoughtful prioritization, and communication that helps teams move "
        "from strategy to shipped work.\n\n"
        "Thank you for your consideration."
    )

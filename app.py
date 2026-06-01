from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from modules.auth import authenticate_user, create_user, update_user_profile
from modules.career_intelligence import (
    build_career_coaching,
    build_market_intelligence,
    recommend_target_companies,
)
from modules.generator import (
    DraftRequest,
    generate_cover_letter,
    generate_outreach,
    generate_resume_bullets,
    generate_why_company,
)
from modules.interview import generate_interview_prep
from modules.monitor import add_monitor, identify_new_jobs, load_monitors, update_monitor_run
from modules.ingestion import RESUME_DIR, save_uploaded_resume
from modules.job_discovery import (
    LAST_DISCOVERY_CACHE_EVENTS,
    classify_careers_site,
    discover_jobs_for_targets,
    is_probable_job_link,
    is_probable_rendered_card,
    parse_company_targets,
)
from modules.matcher import score_resume_for_job
from modules.parser import STRUCTURED_DIR, parse_resume_file, structure_resume
from modules.resume_store import (
    delete_structured_resume,
    load_structured_resumes,
    resume_summary_rows,
    save_structured_resume,
    update_resume_metadata,
)
from modules.tracker import (
    APPLICATION_STATUSES,
    add_application,
    load_applications,
    update_application_details,
    update_application_status,
)


st.set_page_config(
    page_title="Job Search Agent",
    page_icon=":briefcase:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def get_resume_label(resume: dict) -> str:
    metadata = resume.get("metadata", {})
    name = metadata.get("candidate_name") or resume.get("source_file") or "Resume"
    version = metadata.get("version_name") or Path(resume.get("source_file", "")).stem
    return f"{name} - {version}"


def get_application_label(application: dict) -> str:
    company = application.get("company") or "Unknown Company"
    role_title = application.get("role_title") or "Unknown Role"
    score = application.get("match_score")
    suffix = f" - {score}% match" if score not in {None, ""} else ""
    return f"{company} - {role_title}{suffix}"


def render_metric_card(label: str, value: str, help_text: str | None = None) -> None:
    st.metric(label, value, help=help_text)


def render_page_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="page-header">
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, body: str, action: str = "") -> None:
    action_html = f"<strong>{html.escape(action)}</strong>" if action else ""
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="empty-state-title">{html.escape(title)}</div>
            <p>{html.escape(body)}</p>
            {action_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_badge(label: str, variant: str = "neutral") -> None:
    st.markdown(
        f'<span class="status-badge status-{html.escape(variant)}">{html.escape(label)}</span>',
        unsafe_allow_html=True,
    )


def render_skill_chips(items: list[str], empty_text: str, variant: str = "match") -> None:
    if not items:
        st.markdown(f'<p class="empty-note">{html.escape(empty_text)}</p>', unsafe_allow_html=True)
        return

    chips = "".join(
        f'<span class="skill-chip skill-chip-{variant}">{html.escape(item)}</span>'
        for item in items
    )
    st.markdown(f'<div class="chip-row">{chips}</div>', unsafe_allow_html=True)


def render_analysis_panel(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="analysis-panel">
            <div class="analysis-panel-title">{html.escape(title)}</div>
            <p>{html.escape(body)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_resume_job_intelligence(resume: dict, job) -> dict:
    match = job.match
    resume_skills = set(str(skill).lower() for skill in resume.get("skills", []))
    missing_skills = [skill for skill in match.missing_skills if skill.lower() not in resume_skills]
    tailoring_targets = missing_skills[:5] + match.missing_leadership[:3]
    strengths = match.matching_skills[:6] + match.matching_domains[:3] + match.matching_leadership[:3]
    improvements = []
    if tailoring_targets:
        improvements.append(f"Add evidence for: {', '.join(tailoring_targets[:6])}.")
    if match.resume_gaps:
        improvements.extend(match.resume_gaps[:3])
    if job.role_relevance >= 80 and match.match_score < 70:
        improvements.append("The title is aligned, but the resume needs stronger proof against the description.")
    if not improvements:
        improvements.append("This resume already covers the strongest visible requirements.")
    return {
        "strengths": strengths,
        "gaps": tailoring_targets,
        "improvements": improvements,
        "career_path": infer_career_path(job.title, match.matching_domains),
    }


def infer_career_path(title: str, domains: list[str]) -> str:
    title_text = title.lower()
    if "manager" in title_text or "director" in title_text:
        return "Engineering leadership / technical program leadership"
    if "ai" in title_text or "machine learning" in title_text or "ml" in title_text:
        return "AI engineering / machine learning systems"
    if "platform" in title_text or "infrastructure" in title_text or "sre" in title_text:
        return "Platform engineering / infrastructure"
    if "software" in title_text or "engineer" in title_text:
        return "Software engineering"
    if domains:
        return f"{domains[0].title()}-oriented technical track"
    return "General technical track"


def job_description_preview(description: str, max_chars: int = 900) -> str:
    cleaned = " ".join((description or "").split())
    if len(cleaned) <= max_chars:
        return cleaned or "No detailed description captured yet."
    return f"{cleaned[:max_chars].rstrip()}..."


def render_resume_comparison(left_resume: dict, right_resume: dict) -> None:
    left_skills = set(left_resume.get("skills", []))
    right_skills = set(right_resume.get("skills", []))
    shared_skills = sorted(left_skills & right_skills, key=str.lower)
    left_unique = sorted(left_skills - right_skills, key=str.lower)
    right_unique = sorted(right_skills - left_skills, key=str.lower)

    left_col, right_col = st.columns(2)
    with left_col:
        st.markdown(f"**{get_resume_label(left_resume)}**")
        st.caption(f"Parser: {left_resume.get('metadata', {}).get('parser', 'unknown')}")
        st.write(left_resume.get("summary") or "No summary extracted.")
        st.markdown("**Unique Skills**")
        render_skill_chips(left_unique[:20], "No unique skills versus the compared resume.", "match")
    with right_col:
        st.markdown(f"**{get_resume_label(right_resume)}**")
        st.caption(f"Parser: {right_resume.get('metadata', {}).get('parser', 'unknown')}")
        st.write(right_resume.get("summary") or "No summary extracted.")
        st.markdown("**Unique Skills**")
        render_skill_chips(right_unique[:20], "No unique skills versus the compared resume.", "match")

    st.markdown("**Shared Skills**")
    render_skill_chips(shared_skills[:30], "No shared skills found between these versions.", "match")


st.markdown(
    """
    <style>
    .stApp {
        background: #f8fafc;
    }
    .block-container {
        max-width: 1280px;
        padding-top: 1.35rem;
        padding-bottom: 2.4rem;
    }
    h1, h2, h3 {
        color: #0f172a;
        letter-spacing: 0;
    }
    .page-header {
        border-bottom: 1px solid #e2e8f0;
        margin-bottom: 1.15rem;
        padding-bottom: 0.85rem;
    }
    .page-header h1 {
        font-size: 2rem;
        line-height: 1.15;
        margin: 0;
    }
    .page-header p {
        color: #475569;
        font-size: 0.98rem;
        line-height: 1.5;
        margin: 0.45rem 0 0;
        max-width: 840px;
    }
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e6e8ec;
        border-radius: 8px;
        padding: 14px 16px;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }
    [data-testid="stMetric"] * {
        color: #0f172a;
    }
    [data-testid="stMetricLabel"] p {
        color: #475569;
    }
    [data-testid="stMetricValue"] {
        color: #0f172a;
    }
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div {
        background: #ffffff;
    }
    [data-testid="stSidebar"] * {
        color: #0f172a;
    }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span {
        color: #0f172a;
    }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        color: #475569;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label {
        border-radius: 8px;
        padding: 0.3rem 0.45rem;
        margin-bottom: 0.15rem;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
        background: #eef6ff;
        border: 1px solid #bfdbfe;
    }
    .section-note {
        color: #64748b;
        font-size: 0.94rem;
        margin-top: -0.4rem;
        margin-bottom: 1rem;
    }
    .chip-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
        margin: 0.35rem 0 0.9rem;
    }
    .skill-chip {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        font-size: 0.86rem;
        font-weight: 600;
        line-height: 1;
        padding: 0.45rem 0.65rem;
        border: 1px solid transparent;
        color: #0f172a;
    }
    .skill-chip-match {
        background: #dcfce7;
        border-color: #86efac;
    }
    .skill-chip-gap {
        background: #fee2e2;
        border-color: #fca5a5;
    }
    .analysis-panel {
        background: #ffffff;
        border: 1px solid #e6e8ec;
        border-radius: 8px;
        padding: 1rem;
        min-height: 8rem;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    }
    .analysis-panel-title {
        color: #0f172a;
        font-size: 0.95rem;
        font-weight: 700;
        margin-bottom: 0.45rem;
    }
    .analysis-panel p,
    .empty-note {
        color: #334155;
        font-size: 0.94rem;
        line-height: 1.45;
        margin: 0;
    }
    .empty-state {
        background: #ffffff;
        border: 1px dashed #cbd5e1;
        border-radius: 8px;
        padding: 1.15rem;
        margin: 0.55rem 0 1rem;
    }
    .empty-state-title {
        color: #0f172a;
        font-weight: 750;
        margin-bottom: 0.35rem;
    }
    .empty-state p {
        color: #475569;
        line-height: 1.5;
        margin: 0 0 0.65rem;
    }
    .status-badge {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        border: 1px solid #cbd5e1;
        color: #334155;
        background: #f8fafc;
        font-size: 0.78rem;
        font-weight: 700;
        line-height: 1;
        padding: 0.35rem 0.55rem;
        white-space: nowrap;
    }
    .status-strong {
        background: #dcfce7;
        border-color: #86efac;
        color: #166534;
    }
    .status-warning {
        background: #fef3c7;
        border-color: #fcd34d;
        color: #92400e;
    }
    .status-muted {
        background: #f1f5f9;
        border-color: #cbd5e1;
        color: #475569;
    }
    div[data-testid="stDataFrame"] {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        overflow: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


with st.sidebar:
    st.title("Job Search Agent")
    st.caption("AI workflow hub for resume matching, targeting, and application tracking.")
    current_user = st.session_state.get("current_user")
    if current_user:
        display_name = " ".join(
            part for part in [current_user.get("first_name", ""), current_user.get("last_name", "")] if part
        )
        st.caption(f"Signed in as {display_name or current_user.get('email') or current_user['username']}")
        if st.button("Log out"):
            st.session_state.pop("current_user", None)
            st.rerun()


if "current_user" not in st.session_state:
    render_page_header("Sign in", "Create a local account to keep your job-search workspace separated.")
    auth_tab, signup_tab = st.tabs(["Login", "Create Account"])
    with auth_tab:
        with st.form("login_form"):
            username = st.text_input("Email address")
            password = st.text_input("Password", type="password")
            submitted_login = st.form_submit_button("Login", type="primary")
        if submitted_login:
            user = authenticate_user(username, password)
            if user:
                st.session_state["current_user"] = user
                st.success("Signed in.")
                st.rerun()
            else:
                st.error("Invalid username or password.")
    with signup_tab:
        with st.form("signup_form"):
            first_name = st.text_input("First name")
            last_name = st.text_input("Last name")
            email = st.text_input("Email address")
            new_password = st.text_input("New password", type="password")
            confirm_password = st.text_input("Confirm password", type="password")
            submitted_signup = st.form_submit_button("Create Account", type="primary")
        if submitted_signup:
            try:
                if new_password != confirm_password:
                    raise ValueError("Passwords do not match.")
                user = create_user(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=new_password,
                )
                st.session_state["current_user"] = user
                st.success("Account created.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.stop()


current_user = st.session_state["current_user"]
current_profile = current_user.get("profile", {})

with st.sidebar:
    page = st.radio(
        "Workspace",
        [
            "Dashboard",
            "Resume Library",
            "Match Lab",
            "Job Discovery",
            "Draft Studio",
            "Interview Prep",
            "Application Tracker",
            "Job Monitoring",
            "Career Coach",
            "Company Targeting",
            "Market Intelligence",
            "Account Settings",
        ],
        format_func=lambda value: {
            "Dashboard": "Home - Dashboard",
            "Resume Library": "Search - Resume Library",
            "Match Lab": "Search - Match Lab",
            "Job Discovery": "Search - Job Discovery",
            "Draft Studio": "Applications - Draft Studio",
            "Interview Prep": "Applications - Interview Prep",
            "Application Tracker": "Applications - Tracker",
            "Job Monitoring": "Monitor Jobs",
            "Career Coach": "Intelligence - Career Coach",
            "Company Targeting": "Intelligence - Company Targeting",
            "Market Intelligence": "Intelligence - Market",
            "Account Settings": "Account - Settings",
        }.get(value, value),
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("MVP stack")
    st.write("Python · Streamlit · OpenAI-ready · Modular services")


resumes = load_structured_resumes()
applications = load_applications()
applications = [
    application
    for application in applications
    if application.get("username", current_user["username"]) == current_user["username"]
]


if page == "Dashboard":
    render_page_header(
        "Job Search Command Center",
        "Track resume versions, role fit, applications, and AI-powered job-search intelligence from one workspace.",
    )

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        render_metric_card("Resume Versions", str(len(resumes)), "Structured resume JSON files stored locally.")
    with col_b:
        render_metric_card("Applications", str(len(applications)), "Tracked opportunities across statuses.")
    with col_c:
        active = sum(1 for app in applications if app.get("status") not in {"Rejected", "Withdrawn"})
        render_metric_card("Active Pipeline", str(active), "Applications still worth follow-up.")
    with col_d:
        avg_score = (
            round(sum(float(app.get("match_score", 0)) for app in applications) / len(applications))
            if applications
            else 0
        )
        render_metric_card("Avg Match", f"{avg_score}%", "Average saved fit score.")

    st.subheader("Today")
    next_actions = []
    if not resumes:
        next_actions.append("Upload your first resume in Resume Library.")
    if resumes and not applications:
        next_actions.append("Run Match Lab or Job Discovery, then save at least one role to the tracker.")
    follow_ups = [
        app for app in applications
        if app.get("follow_up_date") and app.get("status") not in {"Rejected", "Withdrawn"}
    ]
    if follow_ups:
        next_actions.append(f"Review {len(follow_ups)} application(s) with follow-up dates.")
    high_fit = [
        app for app in applications
        if int(app.get("match_score") or 0) >= 80 and app.get("status") in {"Saved", "Interested"}
    ]
    if high_fit:
        next_actions.append(f"Draft outreach or application materials for {len(high_fit)} high-fit saved role(s).")
    if not next_actions:
        next_actions.append("Your workspace is in good shape. Keep monitoring target companies and updating statuses.")

    for action in next_actions[:4]:
        st.write(f"- {action}")

    st.subheader("Recent Applications")
    if applications:
        st.dataframe(
            [
                {
                    "Company": application.get("company"),
                    "Role": application.get("role_title"),
                    "Status": application.get("status"),
                    "Match": application.get("match_score"),
                    "Follow-up": application.get("follow_up_date", ""),
                    "URL": application.get("job_url", ""),
                }
                for application in applications[-8:]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={"URL": st.column_config.LinkColumn("URL")},
        )
    else:
        render_empty_state(
            "No applications tracked yet",
            "Score a role in Match Lab or discover roles from company career pages, then save the strongest opportunities here.",
            "Start with Resume Library, then Match Lab.",
        )

    st.subheader("Recommended Flow")
    flow_a, flow_b, flow_c = st.columns(3)
    with flow_a:
        render_analysis_panel("1. Prepare", "Upload resumes, label versions, and set account preferences.")
    with flow_b:
        render_analysis_panel("2. Match", "Discover roles, score fit, and save strong jobs to the tracker.")
    with flow_c:
        render_analysis_panel("3. Advance", "Generate drafts, prep interviews, and monitor target companies.")


elif page == "Resume Library":
    render_page_header(
        "Resume Library",
        "Upload PDF, DOCX, or TXT resumes, extract text, and manage structured resume versions.",
    )

    uploaded_files = st.file_uploader(
        "Upload one or more resumes",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
    )
    version_name = st.text_input("Version label", placeholder="AI Platform Resume, EM Resume, SRE Resume")
    use_llm_parser = st.toggle(
        "Use OpenAI structured extraction",
        value=True,
        help="Uses OPENAI_API_KEY when available; falls back to the heuristic parser if not configured.",
    )

    if st.button("Parse and Save", type="primary", disabled=not uploaded_files):
        saved_results = []
        parse_status = st.status("Preparing resume parsing...", expanded=True)
        progress = st.progress(0)
        total_files = len(uploaded_files or [])

        try:
            for index, uploaded_file in enumerate(uploaded_files or [], start=1):
                file_label = getattr(uploaded_file, "name", f"resume-{index}")
                parse_status.write(f"Saving upload: {file_label}")
                saved_path = save_uploaded_resume(uploaded_file, RESUME_DIR)

                parse_status.write(f"Extracting text from {saved_path.name}")
                raw_text = parse_resume_file(saved_path)

                parser_label = "OpenAI structured extraction" if use_llm_parser else "heuristic extraction"
                parse_status.write(f"Structuring resume with {parser_label}")
                structured = structure_resume(
                    raw_text=raw_text,
                    source_file=saved_path.name,
                    version_name=version_name or saved_path.stem,
                    use_llm=use_llm_parser,
                )

                output_path = STRUCTURED_DIR / f"{saved_path.stem}.json"
                parse_status.write(f"Saving structured resume: {output_path.name}")
                save_structured_resume(structured, output_path)

                parser_name = structured.get("metadata", {}).get("parser", "unknown")
                saved_results.append((output_path.name, parser_name, structured.get("metadata", {}).get("parser_warning")))
                progress.progress(index / total_files)

            parse_status.update(label="Resume parsing completed.", state="complete", expanded=True)
            for output_name, parser_name, parser_warning in saved_results:
                st.success(f"Completed: {output_name} ({parser_name})")
                if parser_warning:
                    st.warning(f"OpenAI extraction was skipped: {parser_warning}")
        except Exception as exc:
            parse_status.update(label="Resume parsing failed.", state="error", expanded=True)
            st.error(f"Could not parse resume: {exc}")
            st.stop()

        st.rerun()

    st.divider()
    if resumes:
        st.subheader("Resume Versions")
        st.dataframe(resume_summary_rows(resumes), use_container_width=True, hide_index=True)

        selected_label = st.selectbox("Resume versions", [get_resume_label(r) for r in resumes])
        selected = resumes[[get_resume_label(r) for r in resumes].index(selected_label)]
        selected_path = selected.get("_source_path", "")
        metadata = selected.get("metadata", {})

        col_left, col_right = st.columns([0.42, 0.58])
        with col_left:
            st.subheader("Profile")
            st.caption(f"Parser: {metadata.get('parser', 'unknown')}")
            st.write(selected.get("summary") or "No summary extracted.")
            st.subheader("Skills")
            st.write(", ".join(selected.get("skills", [])) or "No skills extracted.")
            st.subheader("Leadership")
            st.write("\n".join(f"- {item}" for item in selected.get("leadership", [])) or "No leadership signals found.")
            if selected.get("target_roles"):
                st.subheader("Target Roles")
                st.write(", ".join(selected.get("target_roles", [])))
        with col_right:
            st.subheader("Version Manager")
            with st.form("resume_version_manager"):
                updated_version_name = st.text_input(
                    "Version name",
                    value=metadata.get("version_name") or Path(selected.get("source_file", "")).stem,
                )
                updated_target_roles = st.text_input(
                    "Target roles",
                    value=", ".join(selected.get("target_roles", [])),
                    help="Comma-separated role families this resume is optimized for.",
                )
                updated_notes = st.text_area(
                    "Version notes",
                    value=metadata.get("notes", ""),
                    height=110,
                    placeholder="Example: Best for AI Platform and Staff Engineer roles.",
                )
                saved_metadata = st.form_submit_button("Save Version Details", type="primary")

            if saved_metadata:
                update_resume_metadata(
                    selected_path,
                    version_name=updated_version_name,
                    notes=updated_notes,
                    target_roles=updated_target_roles.split(","),
                )
                st.success("Resume version details saved.")
                st.rerun()

            with st.expander("Delete this resume version"):
                st.warning("Deleting removes the structured JSON version from the local library.")
                confirm_delete = st.checkbox(
                    f"Delete {metadata.get('version_name') or selected.get('source_file')}",
                    key=f"delete_{selected_path}",
                )
                if st.button("Delete Resume Version", disabled=not confirm_delete, type="secondary"):
                    delete_structured_resume(selected_path)
                    st.success("Resume version deleted.")
                    st.rerun()

            st.subheader("Structured JSON")
            st.json(selected, expanded=False)

        if len(resumes) >= 2:
            st.divider()
            st.subheader("Compare Resume Versions")
            compare_left, compare_right = st.columns(2)
            resume_labels = [get_resume_label(r) for r in resumes]
            with compare_left:
                left_label = st.selectbox("First version", resume_labels, key="compare_left")
            with compare_right:
                right_default = 1 if len(resume_labels) > 1 else 0
                right_label = st.selectbox("Second version", resume_labels, index=right_default, key="compare_right")

            left_resume = resumes[resume_labels.index(left_label)]
            right_resume = resumes[resume_labels.index(right_label)]
            if left_label == right_label:
                st.info("Choose two different versions to compare.")
            else:
                render_resume_comparison(left_resume, right_resume)
    else:
        st.info("Upload your first resume to create a structured version.")


elif page == "Match Lab":
    render_page_header(
        "Match Lab",
        "Score a resume against a job description using weighted keywords, seniority, domains, and semantic signals.",
    )

    if not resumes:
        st.warning("Add at least one resume in Resume Library before matching.")
    else:
        labels = [get_resume_label(r) for r in resumes]
        selected_resume = resumes[labels.index(st.selectbox("Resume version", labels))]

        col_left, col_right = st.columns([0.42, 0.58])
        with col_left:
            company = st.text_input("Company")
            role_title = st.text_input("Role title")
            job_url = st.text_input("Job URL")
            location = st.text_input("Location", placeholder="Remote, New York, San Francisco")
        with col_right:
            job_description = st.text_area("Job description", height=280)

        if st.button("Score Role", type="primary", disabled=not job_description.strip()):
            result = score_resume_for_job(selected_resume, job_description)
            st.session_state["last_match"] = {
                "company": company,
                "role_title": role_title,
                "job_url": job_url,
                "location": location,
                "resume_label": get_resume_label(selected_resume),
                "result": result,
                "job_description": job_description,
            }

        if "last_match" in st.session_state:
            match = st.session_state["last_match"]
            result = match["result"]
            st.subheader("Fit Analysis")
            score_col, seniority_col, skills_col = st.columns(3)
            with score_col:
                render_metric_card("Match Score", f"{result.match_score}%", "Weighted keyword fit for this MVP.")
            with seniority_col:
                render_metric_card("Seniority Match", result.seniority_match)
            with skills_col:
                render_metric_card("Matching Skills", str(len(result.matching_skills)))
            render_metric_card("Semantic Similarity", f"{result.semantic_score}%", f"Method: {result.semantic_method}")

            breakdown = result.score_breakdown
            st.subheader("Score Breakdown")
            score_a, score_b, score_c, score_d, score_e = st.columns(5)
            with score_a:
                render_metric_card("Skills", f"{breakdown.skills}%")
            with score_b:
                render_metric_card("Leadership", f"{breakdown.leadership}%")
            with score_c:
                render_metric_card("Seniority", f"{breakdown.seniority}%")
            with score_d:
                render_metric_card("Domain", f"{breakdown.domain}%")
            with score_e:
                render_metric_card("Gap Penalty", f"-{breakdown.gap_penalty}")

            detail_a, detail_b, detail_c = st.columns(3)
            with detail_a:
                st.markdown("**Matching Skills**")
                render_skill_chips(result.matching_skills, "No direct skill matches found yet.", "match")
                st.caption("These are skills found in both the resume and job description.")
            with detail_b:
                st.markdown("**Missing Skills**")
                render_skill_chips(result.missing_skills, "No major missing skills detected.", "gap")
                st.caption("These are useful tailoring targets before applying.")
            with detail_c:
                render_analysis_panel("Recommendation", result.recommendation)

            signal_a, signal_b, signal_c = st.columns(3)
            with signal_a:
                st.markdown("**Leadership Match**")
                render_skill_chips(result.matching_leadership, "No explicit leadership match required or found.", "match")
            with signal_b:
                st.markdown("**Domain Fit**")
                render_skill_chips(result.matching_domains, "No strong domain overlap detected.", "match")
            with signal_c:
                st.markdown("**Resume Gaps**")
                for gap in result.resume_gaps:
                    st.write(f"- {gap}")

            if st.button("Save to Tracker"):
                add_application(
                    company=match["company"] or "Unknown Company",
                    role_title=match["role_title"] or "Unknown Role",
                    job_url=match["job_url"],
                    location=match["location"],
                    job_description=match["job_description"],
                    resume_version=match["resume_label"],
                    match_score=result.match_score,
                    notes=result.recommendation,
                    username=current_user["username"],
                )
                st.success("Application saved.")
                st.rerun()


elif page == "Job Discovery":
    render_page_header(
        "Job Discovery",
        "Scan company careers pages, rank open roles against a selected resume, and save the strongest matches.",
    )

    if not resumes:
        st.warning("Add at least one resume in Resume Library before discovering jobs.")
    else:
        labels = [get_resume_label(r) for r in resumes]
        selected_resume = resumes[labels.index(st.selectbox("Resume version", labels, key="discovery_resume"))]

        col_left, col_right = st.columns([0.42, 0.58])
        with col_left:
            company = st.text_input("Company", placeholder="OpenAI")
            careers_url = st.text_input("Company careers URL", placeholder="https://example.com/careers")
            default_job_query = ", ".join(selected_resume.get("target_roles", [])) or "AI Engineer, Software Engineer, Platform Engineer"
            job_query = st.text_input(
                "Target roles / keywords",
                value=default_job_query,
                help="Discovery searches and filters for these roles before scoring resume fit.",
            )
            max_jobs = st.slider("Max jobs per company", 1, 20, 8)
            max_pages = st.slider(
                "Max result pages",
                1,
                10,
                3,
                help="For rendered job boards, scan additional pages or Show More batches before ranking results.",
            )
            use_rendered_discovery = st.toggle(
                "Use browser-rendered discovery",
                value=True,
                help="Use this for JavaScript-heavy ATS pages such as NVIDIA/Eightfold.",
            )
            use_discovery_cache = st.toggle(
                "Use discovery cache",
                value=True,
                help="Reuse matching discovery results for a few hours to avoid re-scanning the same careers page.",
            )
            show_discovery_debug = st.toggle(
                "Show discovery debug panel",
                value=True,
                help="Show classifier, adapter, cache, and filtering details after discovery.",
            )
        with col_right:
            target_companies = st.text_area(
                "Target company list",
                height=150,
                placeholder="OpenAI | https://openai.com/careers\nAnthropic | https://www.anthropic.com/careers",
                help="One company per line. Use: Company | careers URL",
            )

        if st.button("Discover and Rank Jobs", type="primary", disabled=not (careers_url.strip() or target_companies.strip())):
            st.session_state["discovered_jobs"] = []
            st.session_state["discovery_resume_label"] = get_resume_label(selected_resume)
            targets = parse_company_targets(target_companies, fallback_company=company, fallback_url=careers_url)
            if not targets:
                st.error("Add at least one valid careers URL. Use full URLs starting with https:// or http://.")
                st.stop()

            discovery_status = st.status("Discovering jobs...", expanded=True)
            try:
                discovery_status.write(f"Scanning {len(targets)} company careers page(s).")
                classifications = {
                    target.careers_url: classify_careers_site(target.careers_url)
                    for target in targets
                }
                for target in targets:
                    classification = classifications[target.careers_url]
                    discovery_status.write(
                        f"{target.company}: classified as {classification.category.replace('_', ' ')} "
                        f"({classification.confidence}% confidence)."
                    )
                needs_rendered_discovery = any(
                    classification.category in {"hosted_ats", "custom_spa"}
                    for classification in classifications.values()
                )
                effective_rendered_discovery = use_rendered_discovery or needs_rendered_discovery
                if needs_rendered_discovery and not use_rendered_discovery:
                    discovery_status.write(
                        "Browser-rendered discovery was enabled automatically because at least one scanned site "
                        "loads job cards with JavaScript."
                    )
                if effective_rendered_discovery:
                    discovery_status.write(
                        f"Static scan will run first. If needed, a browser-rendered scan will load up to {max_pages} result page(s)."
                    )
                discovered_jobs = discover_jobs_for_targets(
                    targets,
                    selected_resume,
                    max_jobs_per_company=max_jobs,
                    max_pages_per_company=max_pages,
                    use_rendered_fallback=effective_rendered_discovery,
                    use_cache=use_discovery_cache,
                    job_query=job_query,
                )
                for cache_event in LAST_DISCOVERY_CACHE_EVENTS:
                    discovery_status.write(cache_event)
                st.session_state["discovered_jobs"] = discovered_jobs
                st.session_state["discovery_resume_label"] = get_resume_label(selected_resume)
                st.session_state["discovery_debug"] = {
                    "classifications": {
                        target.company: {
                            "category": classifications[target.careers_url].category,
                            "confidence": classifications[target.careers_url].confidence,
                            "reasons": classifications[target.careers_url].reasons,
                            "url": target.careers_url,
                        }
                        for target in targets
                    },
                    "cache_events": list(LAST_DISCOVERY_CACHE_EVENTS),
                    "rendered_enabled": effective_rendered_discovery,
                    "max_pages": max_pages,
                    "max_jobs": max_jobs,
                    "query": job_query,
                }
                if discovered_jobs:
                    discovery_status.update(label=f"Discovered {len(discovered_jobs)} ranked job result(s).", state="complete", expanded=True)
                else:
                    discovery_status.update(label="No actual job postings found on the scanned page(s).", state="complete", expanded=True)
                    st.warning(
                        "I did not find job-detail postings on that page. Some careers sites, including many ATS pages, "
                        "load jobs with JavaScript or block server-side scraping. Try a specific job-detail URL, an ATS board URL, "
                        "or another careers listing page that shows individual roles in the page HTML."
                    )
            except Exception as exc:
                discovery_status.update(label="Job discovery failed.", state="error", expanded=True)
                st.error(f"Could not discover jobs: {exc}")

        discovered_jobs = [
            job
            for job in st.session_state.get("discovered_jobs", [])
            if is_probable_job_link(job.url, job.title) or is_probable_rendered_card(job.url, job.title)
        ]
        st.session_state["discovered_jobs"] = discovered_jobs
        if discovered_jobs:
            st.subheader("Ranked Job Matches")
            debug_payload = st.session_state.get("discovery_debug", {})
            if show_discovery_debug and debug_payload:
                with st.expander("Discovery Debug Panel", expanded=False):
                    debug_a, debug_b, debug_c = st.columns(3)
                    with debug_a:
                        render_metric_card("Returned Jobs", str(len(discovered_jobs)))
                        render_metric_card("Max Pages", str(debug_payload.get("max_pages", 1)))
                    with debug_b:
                        cached_count = sum(1 for job in discovered_jobs if getattr(job, "cache_hit", False))
                        render_metric_card("Cache Hits", str(cached_count))
                        render_metric_card("Rendered Scan", "On" if debug_payload.get("rendered_enabled") else "Off")
                    with debug_c:
                        adapters = sorted(set(job.source_adapter or "unknown" for job in discovered_jobs))
                        st.markdown("**Adapters Used**")
                        render_skill_chips(adapters, "No adapter metadata captured.", "match")

                    st.markdown("**Classifications**")
                    st.json(debug_payload.get("classifications", {}), expanded=False)
                    if debug_payload.get("cache_events"):
                        st.markdown("**Cache Events**")
                        for cache_event in debug_payload["cache_events"]:
                            st.write(f"- {cache_event}")

            st.dataframe(
                [
                    {
                        "Company": job.company,
                        "Role Title": job.title,
                        "Location": job.location,
                        "Role Relevance": job.role_relevance,
                        "Match Score": job.match.match_score,
                        "Semantic": job.match.semantic_score,
                        "Seniority Match": job.match.seniority_match,
                        "Source": job.source_adapter or "unknown",
                        "Cache": "Hit" if getattr(job, "cache_hit", False) else "Fresh",
                        "URL": job.url,
                    }
                    for job in discovered_jobs
                ],
                use_container_width=True,
                hide_index=True,
                column_config={"URL": st.column_config.LinkColumn("URL")},
            )

            for index, job in enumerate(discovered_jobs):
                with st.expander(f"{job.match.match_score}% - {job.company} - {job.title}"):
                    intelligence = build_resume_job_intelligence(selected_resume, job)
                    job_a, job_b, job_c = st.columns([0.28, 0.36, 0.36])
                    with job_a:
                        render_metric_card("Role Relevance", f"{job.role_relevance}%")
                        render_metric_card("Match Score", f"{job.match.match_score}%")
                        render_metric_card("Semantic", f"{job.match.semantic_score}%")
                        render_metric_card("Seniority", job.match.seniority_match)
                        st.caption(f"Source: {job.source_adapter or 'unknown'}")
                        if getattr(job, "cache_hit", False):
                            st.caption("Loaded from discovery cache")
                        st.link_button("Open Job", job.url)
                    with job_b:
                        st.markdown("**Matching Skills**")
                        render_skill_chips(job.match.matching_skills, "No direct skill matches found.", "match")
                        st.markdown("**Missing Skills**")
                        render_skill_chips(job.match.missing_skills, "No major missing skills detected.", "gap")
                    with job_c:
                        render_analysis_panel("Recommendation", job.match.recommendation)

                    detail_tab, intelligence_tab, gaps_tab = st.tabs(["Job Details", "Resume Intelligence", "Resume Gaps"])
                    with detail_tab:
                        st.markdown("**Captured Job Description**")
                        st.write(job_description_preview(job.description))
                    with intelligence_tab:
                        intel_a, intel_b = st.columns(2)
                        with intel_a:
                            st.markdown("**Strongest Evidence**")
                            render_skill_chips(intelligence["strengths"], "No strong overlap detected.", "match")
                            st.markdown("**Likely Career Path**")
                            st.write(intelligence["career_path"])
                        with intel_b:
                            st.markdown("**Tailoring Targets**")
                            render_skill_chips(intelligence["gaps"], "No major tailoring targets detected.", "gap")
                            st.markdown("**Recommended Resume Improvements**")
                            for improvement in intelligence["improvements"]:
                                st.write(f"- {improvement}")
                    with gaps_tab:
                        if job.match.resume_gaps:
                            for gap in job.match.resume_gaps:
                                st.write(f"- {gap}")
                        else:
                            st.write("No major resume gaps detected.")

                    if st.button("Save Job to Tracker", key=f"save_discovered_{index}"):
                        add_application(
                            company=job.company,
                            role_title=job.title,
                            job_url=job.url,
                            location=job.location,
                            job_description=job.description,
                            resume_version=st.session_state.get("discovery_resume_label", get_resume_label(selected_resume)),
                            match_score=job.match.match_score,
                            notes=f"{job.match.recommendation}\n\nCareer path: {intelligence['career_path']}",
                            username=current_user["username"],
                        )
                        st.success("Job saved to Application Tracker.")
                        st.rerun()


elif page == "Draft Studio":
    render_page_header(
        "Draft Studio",
        "Generate targeted bullets, outreach, cover letters, and company-fit narratives from saved roles.",
    )

    if not resumes:
        st.warning("Add at least one resume in Resume Library before generating drafts.")
    else:
        selected_application = None
        if applications:
            job_options = ["Manual job entry"] + [get_application_label(application) for application in applications]
            selected_job_label = st.selectbox("Draft for saved job", job_options)
            if selected_job_label != "Manual job entry":
                selected_application = applications[job_options.index(selected_job_label) - 1]
        else:
            st.info("No saved jobs yet. Score and save a role from Match Lab to reuse it here.")

        labels = [get_resume_label(r) for r in resumes]
        default_resume_index = 0
        if selected_application and selected_application.get("resume_version") in labels:
            default_resume_index = labels.index(selected_application["resume_version"])
        selected_resume = resumes[
            labels.index(st.selectbox("Resume version", labels, index=default_resume_index))
        ]

        if selected_application:
            company = st.text_input("Company", value=selected_application.get("company", ""), disabled=True)
            role_title = st.text_input("Role title", value=selected_application.get("role_title", ""), disabled=True)
            saved_job_description = selected_application.get("job_description", "")
            job_description = st.text_area(
                "Job description",
                value=saved_job_description,
                height=220,
                disabled=bool(saved_job_description),
                placeholder="This saved job does not have a job description yet. Paste it here to generate a draft.",
            )
            if not saved_job_description:
                st.warning("This saved job does not include a job description. Paste one here, or re-save the job from Match Lab.")
        else:
            company = st.text_input("Company")
            role_title = st.text_input("Role title")
            job_description = st.text_area("Job description", height=220)

        draft_type = st.radio(
            "Draft type",
            ["Resume Bullets", "Why Company", "Recruiter Outreach", "Cover Letter"],
            horizontal=True,
        )

        if st.button("Generate Draft", type="primary", disabled=not job_description.strip()):
            request = DraftRequest(
                resume=selected_resume,
                job_description=job_description,
                company=company,
                role_title=role_title,
            )
            if draft_type == "Resume Bullets":
                draft = generate_resume_bullets(request)
            elif draft_type == "Why Company":
                draft = generate_why_company(request)
            elif draft_type == "Recruiter Outreach":
                draft = generate_outreach(request)
            else:
                draft = generate_cover_letter(request)

            st.session_state["last_draft"] = draft
            st.session_state["last_draft_context"] = f"{company or 'Unknown Company'} - {role_title or 'Unknown Role'}"

        if "last_draft" in st.session_state:
            context = st.session_state.get("last_draft_context")
            st.subheader("Generated Draft")
            if context:
                st.caption(f"Draft context: {context}")
            st.text_area("Output", value=st.session_state["last_draft"], height=340)


elif page == "Application Tracker":
    render_page_header(
        "Application Tracker",
        "Maintain a lightweight application CRM with status, follow-ups, resume version, and match score.",
    )

    with st.form("new_application"):
        col_a, col_b = st.columns(2)
        with col_a:
            company = st.text_input("Company")
            role_title = st.text_input("Role title")
            location = st.text_input("Location")
            job_url = st.text_input("Job URL")
        with col_b:
            resume_version = st.text_input("Resume version")
            match_score = st.slider("Match score", 0, 100, 70)
            source = st.text_input("Source", placeholder="Job Discovery, LinkedIn, Referral")
            follow_up_date = st.text_input("Follow-up date", placeholder="YYYY-MM-DD")
            notes = st.text_area("Notes", height=120)
        job_description = st.text_area("Job description", height=180)
        submitted = st.form_submit_button("Add Application", type="primary")

    if submitted:
        add_application(
            company=company,
            role_title=role_title,
            job_url=job_url,
            location=location,
            job_description=job_description,
            resume_version=resume_version,
            match_score=match_score,
            notes=notes,
            username=current_user["username"],
        )
        if source or follow_up_date:
            applications = load_applications()
            newest = applications[-1] if applications else None
            if newest:
                update_application_details(
                    newest["id"],
                    source=source,
                    follow_up_date=follow_up_date,
                )
        st.success("Application added.")
        st.rerun()

    if applications:
        st.subheader("Pipeline")
        metric_a, metric_b, metric_c, metric_d = st.columns(4)
        active_statuses = {"Saved", "Interested", "Applied", "Recruiter Screen", "Technical Screen", "Interviewing", "Final Round", "Offer"}
        with metric_a:
            render_metric_card("Tracked", str(len(applications)))
        with metric_b:
            render_metric_card("Active", str(sum(1 for app in applications if app.get("status") in active_statuses)))
        with metric_c:
            interviewing = sum(1 for app in applications if app.get("status") in {"Recruiter Screen", "Technical Screen", "Interviewing", "Final Round"})
            render_metric_card("Interview Pipeline", str(interviewing))
        with metric_d:
            high_fit = sum(1 for app in applications if int(app.get("match_score") or 0) >= 80)
            render_metric_card("High Fit", str(high_fit))

        filter_a, filter_b, filter_c = st.columns([0.28, 0.34, 0.38])
        with filter_a:
            status_filter = st.multiselect("Status filter", APPLICATION_STATUSES, default=[])
        with filter_b:
            company_filter = st.text_input("Company / role search")
        with filter_c:
            min_match_filter = st.slider("Minimum match score", 0, 100, 0)

        filtered_applications = [
            application
            for application in applications
            if (not status_filter or application.get("status") in status_filter)
            and int(application.get("match_score") or 0) >= min_match_filter
            and (
                not company_filter.strip()
                or company_filter.lower() in f"{application.get('company', '')} {application.get('role_title', '')}".lower()
            )
        ]

        st.dataframe(
            [
                {
                    "Company": application.get("company"),
                    "Role": application.get("role_title"),
                    "Status": application.get("status"),
                    "Match": application.get("match_score"),
                    "Follow-up": application.get("follow_up_date", ""),
                    "Source": application.get("source", ""),
                    "URL": application.get("job_url", ""),
                }
                for application in filtered_applications
            ],
            use_container_width=True,
            hide_index=True,
            column_config={"URL": st.column_config.LinkColumn("URL")},
        )

        for index, application in enumerate(filtered_applications):
            with st.expander(f"{application.get('company')} - {application.get('role_title')}"):
                col_a, col_b, col_c = st.columns([0.3, 0.3, 0.4])
                with col_a:
                    st.write(f"Status: {application.get('status')}")
                    st.write(f"Match: {application.get('match_score')}%")
                with col_b:
                    st.write(f"Resume: {application.get('resume_version')}")
                    st.write(f"Location: {application.get('location')}")
                with col_c:
                    new_status = st.selectbox(
                        "Update status",
                        APPLICATION_STATUSES,
                        index=APPLICATION_STATUSES.index(application.get("status", "Saved")),
                        key=f"status_{index}",
                    )
                    updated_source = st.text_input(
                        "Source",
                        value=application.get("source", ""),
                        key=f"source_{index}",
                    )
                    updated_follow_up = st.text_input(
                        "Follow-up date",
                        value=application.get("follow_up_date", ""),
                        placeholder="YYYY-MM-DD",
                        key=f"follow_up_{index}",
                    )
                    updated_notes = st.text_area(
                        "Notes",
                        value=application.get("notes", ""),
                        height=130,
                        key=f"notes_{index}",
                    )
                    if st.button("Save Application Updates", key=f"save_status_{index}"):
                        update_application_details(
                            application["id"],
                            status=new_status,
                            notes=updated_notes,
                            follow_up_date=updated_follow_up,
                            source=updated_source,
                        )
                        st.success("Application updated.")
                        st.rerun()

                with st.expander("Saved job description", expanded=False):
                    st.write(job_description_preview(application.get("job_description", ""), max_chars=1200))
    else:
        st.info("No applications yet.")


elif page == "Interview Prep":
    render_page_header(
        "Interview Prep",
        "Generate role-specific technical, behavioral, and STAR interview preparation from saved jobs.",
    )

    if not resumes:
        st.warning("Add at least one resume before generating interview prep.")
    else:
        selected_application = None
        if applications:
            job_options = ["Manual job entry"] + [get_application_label(application) for application in applications]
            selected_job_label = st.selectbox("Prepare for saved job", job_options)
            if selected_job_label != "Manual job entry":
                selected_application = applications[job_options.index(selected_job_label) - 1]
        else:
            st.info("No saved jobs yet. You can still use manual entry.")

        labels = [get_resume_label(r) for r in resumes]
        selected_resume = resumes[labels.index(st.selectbox("Resume version", labels, key="interview_resume"))]

        if selected_application:
            company = st.text_input("Company", value=selected_application.get("company", ""), disabled=True)
            role_title = st.text_input("Role title", value=selected_application.get("role_title", ""), disabled=True)
            job_description = st.text_area(
                "Job description",
                value=selected_application.get("job_description", ""),
                height=240,
                placeholder="Paste the job description if this saved job does not include one.",
            )
        else:
            company = st.text_input("Company")
            role_title = st.text_input("Role title")
            job_description = st.text_area("Job description", height=240)

        if st.button("Generate Interview Prep", type="primary", disabled=not job_description.strip()):
            prep = generate_interview_prep(
                DraftRequest(
                    resume=selected_resume,
                    job_description=job_description,
                    company=company,
                    role_title=role_title,
                )
            )
            st.session_state["last_interview_prep"] = prep

        if st.session_state.get("last_interview_prep"):
            st.subheader("Interview Prep Plan")
            st.markdown(st.session_state["last_interview_prep"])


elif page == "Job Monitoring":
    render_page_header(
        "Job Monitoring",
        "Save target company scans and run them on demand to find new matching roles.",
    )

    if not resumes:
        st.warning("Add at least one resume before creating a monitor.")
    else:
        labels = [get_resume_label(r) for r in resumes]
        selected_resume_label = st.selectbox("Resume version", labels, key="monitor_resume")
        selected_resume = resumes[labels.index(selected_resume_label)]

        with st.form("new_monitor"):
            monitor_name = st.text_input("Monitor name", placeholder="AI Platform Targets")
            monitor_query = st.text_input(
                "Target roles / keywords",
                value=", ".join(selected_resume.get("target_roles", [])) or "AI Engineer, Software Engineer, Platform Engineer",
            )
            monitor_targets = st.text_area(
                "Target company list",
                height=150,
                placeholder="Apple | https://jobs.apple.com/en-us/search?location=united-states-USA\nNetflix | https://explore.jobs.netflix.net/careers?Teams=Engineering",
                help="One company per line. Use: Company | careers URL",
            )
            monitor_a, monitor_b = st.columns(2)
            with monitor_a:
                monitor_max_jobs = st.slider("Max jobs per company", 1, 25, 10, key="monitor_max_jobs")
            with monitor_b:
                monitor_max_pages = st.slider("Max pages", 1, 10, 2, key="monitor_max_pages")
            submitted_monitor = st.form_submit_button("Create Monitor", type="primary")

        if submitted_monitor:
            if not monitor_targets.strip():
                st.error("Add at least one target company URL.")
            else:
                add_monitor(
                    username=current_user["username"],
                    name=monitor_name,
                    target_companies=monitor_targets,
                    job_query=monitor_query,
                    resume_label=selected_resume_label,
                    max_jobs=monitor_max_jobs,
                    max_pages=monitor_max_pages,
                )
                st.success("Monitor created.")
                st.rerun()

        monitors = load_monitors(current_user["username"])
        if monitors:
            st.subheader("Saved Monitors")
            for index, monitor in enumerate(monitors):
                with st.expander(f"{monitor.get('name')} - last run: {monitor.get('last_run_at') or 'Never'}"):
                    st.write(f"Query: {monitor.get('job_query')}")
                    st.write(f"Last new roles: {monitor.get('last_new_count', 0)}")
                    st.text_area("Targets", value=monitor.get("target_companies", ""), height=100, disabled=True, key=f"monitor_targets_{index}")
                    if st.button("Run Monitor Now", key=f"run_monitor_{index}"):
                        targets = parse_company_targets(monitor.get("target_companies", ""))
                        discovered_jobs = discover_jobs_for_targets(
                            targets,
                            selected_resume,
                            max_jobs_per_company=int(monitor.get("max_jobs", 10)),
                            max_pages_per_company=int(monitor.get("max_pages", 2)),
                            use_rendered_fallback=True,
                            use_cache=True,
                            job_query=monitor.get("job_query", ""),
                        )
                        new_jobs = identify_new_jobs(monitor, discovered_jobs)
                        update_monitor_run(monitor["id"], discovered_jobs, new_jobs)
                        st.session_state[f"monitor_results_{monitor['id']}"] = new_jobs
                        st.success(f"Monitor complete. Found {len(new_jobs)} new role(s).")
                        st.rerun()

                    new_jobs = st.session_state.get(f"monitor_results_{monitor['id']}", [])
                    if new_jobs:
                        st.markdown("**New Roles**")
                        st.dataframe(
                            [
                                {
                                    "Company": job.company,
                                    "Role": job.title,
                                    "Match": job.match.match_score,
                                    "Location": job.location,
                                    "URL": job.url,
                                }
                                for job in new_jobs
                            ],
                            use_container_width=True,
                            hide_index=True,
                            column_config={"URL": st.column_config.LinkColumn("URL")},
                        )
        else:
            st.info("No monitors yet.")


elif page == "Career Coach":
    render_page_header(
        "AI Career Coach",
        "Turn your resumes and application pipeline into a focused job-search strategy.",
    )

    if not resumes:
        st.warning("Add at least one resume before using career coaching.")
    else:
        coaching = build_career_coaching(resumes, applications)
        coach_a, coach_b, coach_c = st.columns([0.24, 0.38, 0.38])
        with coach_a:
            render_metric_card("Readiness", f"{coaching['readiness_score']}%")
            render_metric_card("Tracked Pipeline", str(len(applications)))
        with coach_b:
            render_analysis_panel("Positioning", coaching["positioning"])
        with coach_c:
            render_analysis_panel("Pipeline Health", coaching["pipeline_health"])

        st.subheader("Recommended Target Roles")
        st.dataframe(
            [
                {
                    "Role": role["role"],
                    "Fit": role["score"],
                    "Matching Skills": ", ".join(role["matching_skills"]),
                }
                for role in coaching["recommended_roles"]
            ],
            use_container_width=True,
            hide_index=True,
        )

        strengths_col, gaps_col = st.columns(2)
        with strengths_col:
            st.markdown("**Marketable Strengths**")
            render_skill_chips(coaching["strengths"], "No strong marketable strengths detected yet.", "match")
        with gaps_col:
            st.markdown("**Coaching Gaps**")
            for gap in coaching["gaps"] or ["No major coaching gaps detected."]:
                st.write(f"- {gap}")

        st.subheader("Next Best Actions")
        for action in coaching["next_actions"]:
            st.write(f"- {action}")


elif page == "Company Targeting":
    render_page_header(
        "Personalized Company Targeting",
        "Prioritize companies whose role families and technical domains match your resume strengths.",
    )

    if not resumes:
        st.warning("Add at least one resume before building a company target list.")
    else:
        labels = [get_resume_label(r) for r in resumes]
        target_a, target_b, target_c = st.columns([0.36, 0.32, 0.32])
        with target_a:
            selected_resume = resumes[labels.index(st.selectbox("Resume version", labels, key="targeting_resume"))]
        with target_b:
            role_options = ["", "AI Engineer", "Platform Engineer", "SRE / Infrastructure Engineer", "Engineering Manager", "Staff Software Engineer"]
            preferred_profile_role = current_profile.get("target_role_family", "")
            preferred_role = st.selectbox(
                "Preferred role family",
                role_options,
                index=role_options.index(preferred_profile_role) if preferred_profile_role in role_options else 0,
                format_func=lambda value: value or "Use resume target roles",
            )
        with target_c:
            preferred_stage = st.selectbox(
                "Company type",
                ["Any", "AI lab / product", "Big tech", "Product engineering", "Infrastructure SaaS"],
            )

        targets = recommend_target_companies(
            selected_resume,
            preferred_role=preferred_role,
            preferred_stage=preferred_stage,
            limit=10,
        )
        st.dataframe(
            [
                {
                    "Company": target["company"],
                    "Target Score": target["target_score"],
                    "Company Type": target["stage"],
                    "Role Families": ", ".join(target["role_families"]),
                    "Matching Signals": ", ".join(target["matching_signals"]),
                    "Careers": target["careers_url"],
                }
                for target in targets
            ],
            use_container_width=True,
            hide_index=True,
            column_config={"Careers": st.column_config.LinkColumn("Careers")},
        )

        for index, target in enumerate(targets):
            with st.expander(f"{target['target_score']}% - {target['company']}"):
                target_left, target_right = st.columns([0.35, 0.65])
                with target_left:
                    st.link_button("Open Careers", target["careers_url"])
                    render_skill_chips(target["matching_signals"], "No direct signal overlap yet.", "match")
                with target_right:
                    render_analysis_panel("Why Target This Company", target["why"])
                    st.write("Role families:")
                    render_skill_chips(target["role_families"], "No role families configured.", "match")


elif page == "Market Intelligence":
    render_page_header(
        "Job Trend / Salary Intelligence",
        "Inspect role-market trends, resume coverage, and planning salary bands for your target lane.",
    )

    if not resumes:
        st.warning("Add at least one resume before viewing market intelligence.")
    else:
        labels = [get_resume_label(r) for r in resumes]
        market_a, market_b, market_c, market_d = st.columns([0.34, 0.24, 0.2, 0.22])
        with market_a:
            selected_resume = resumes[labels.index(st.selectbox("Resume version", labels, key="market_resume"))]
        with market_b:
            role_options = ["AI Engineer", "Platform Engineer", "SRE / Infrastructure Engineer", "Engineering Manager", "Staff Software Engineer"]
            preferred_profile_role = current_profile.get("target_role_family", "")
            role_family = st.selectbox(
                "Role family",
                role_options,
                index=role_options.index(preferred_profile_role) if preferred_profile_role in role_options else 0,
            )
        with market_c:
            seniority_options = ["Mid", "Senior", "Staff", "Principal", "Manager"]
            preferred_seniority = current_profile.get("target_seniority", "")
            seniority = st.selectbox(
                "Seniority",
                seniority_options,
                index=seniority_options.index(preferred_seniority) if preferred_seniority in seniority_options else 1,
            )
        with market_d:
            location = st.selectbox(
                "Location market",
                ["Remote US", "San Francisco Bay Area", "New York", "Seattle", "Austin", "Other US"],
            )

        intelligence = build_market_intelligence(selected_resume, role_family, location, seniority)
        salary = intelligence["salary_band"]
        salary_a, salary_b, salary_c = st.columns(3)
        with salary_a:
            render_metric_card("Low", f"${salary.low:,}")
        with salary_b:
            render_metric_card("Planning Midpoint", f"${salary.mid:,}")
        with salary_c:
            render_metric_card("High", f"${salary.high:,}")
        st.caption(intelligence["disclaimer"])

        render_analysis_panel("Market Summary", intelligence["market_summary"])
        st.subheader("Trend Coverage")
        st.dataframe(
            [
                {
                    "Trend": trend["trend"],
                    "Demand": trend["demand"],
                    "Resume Coverage": trend["resume_coverage"],
                    "Matching Skills": ", ".join(trend["matching_skills"]),
                    "Recommended Action": trend["action"],
                }
                for trend in intelligence["trends"]
            ],
            use_container_width=True,
            hide_index=True,
        )


elif page == "Account Settings":
    render_page_header(
        "Account Settings",
        "Manage your account identity and optional preferences used for coaching, targeting, and monitoring defaults.",
    )

    profile = current_user.get("profile", {})
    with st.form("account_settings_form"):
        st.subheader("Account")
        account_a, account_b = st.columns(2)
        with account_a:
            first_name = st.text_input("First name", value=current_user.get("first_name", ""))
            email = st.text_input("Email address", value=current_user.get("email", current_user.get("username", "")))
        with account_b:
            last_name = st.text_input("Last name", value=current_user.get("last_name", ""))
            current_title = st.text_input("Current title", value=profile.get("current_title", ""))

        st.subheader("Job Search Preferences")
        pref_a, pref_b, pref_c = st.columns(3)
        with pref_a:
            target_role_family = st.selectbox(
                "Target role family",
                ["", "AI Engineer", "Software Engineer", "Platform Engineer", "SRE / Infrastructure Engineer", "Engineering Manager", "Technical Leader"],
                index=["", "AI Engineer", "Software Engineer", "Platform Engineer", "SRE / Infrastructure Engineer", "Engineering Manager", "Technical Leader"].index(
                    profile.get("target_role_family", "")
                )
                if profile.get("target_role_family", "") in {"", "AI Engineer", "Software Engineer", "Platform Engineer", "SRE / Infrastructure Engineer", "Engineering Manager", "Technical Leader"}
                else 0,
                format_func=lambda value: value or "Not set",
            )
        with pref_b:
            target_seniority = st.selectbox(
                "Target seniority",
                ["", "Mid", "Senior", "Staff", "Principal", "Manager", "Director"],
                index=["", "Mid", "Senior", "Staff", "Principal", "Manager", "Director"].index(profile.get("target_seniority", ""))
                if profile.get("target_seniority", "") in {"", "Mid", "Senior", "Staff", "Principal", "Manager", "Director"}
                else 0,
                format_func=lambda value: value or "Not set",
            )
        with pref_c:
            years_experience = st.number_input(
                "Years of experience",
                min_value=0,
                max_value=50,
                value=int(profile.get("years_experience") or 0),
            )

        location_a, location_b = st.columns(2)
        with location_a:
            preferred_locations = st.text_input(
                "Preferred locations",
                value=profile.get("preferred_locations", ""),
                placeholder="Remote, San Francisco, New York",
            )
            work_authorization = st.text_input(
                "Work authorization",
                value=profile.get("work_authorization", ""),
                placeholder="US citizen, Green card, H-1B, etc.",
            )
        with location_b:
            needs_sponsorship = st.checkbox("Needs sponsorship", value=bool(profile.get("needs_sponsorship", False)))
            open_to_relocation = st.checkbox("Open to relocation", value=bool(profile.get("open_to_relocation", False)))

        st.subheader("Professional Links")
        link_a, link_b, link_c = st.columns(3)
        with link_a:
            linkedin_url = st.text_input("LinkedIn URL", value=profile.get("linkedin_url", ""))
        with link_b:
            github_url = st.text_input("GitHub URL", value=profile.get("github_url", ""))
        with link_c:
            portfolio_url = st.text_input("Portfolio URL", value=profile.get("portfolio_url", ""))

        saved_account = st.form_submit_button("Save Account Settings", type="primary")

    if saved_account:
        try:
            updated_user = update_user_profile(
                current_user["username"],
                first_name=first_name,
                last_name=last_name,
                email=email,
                target_role_family=target_role_family,
                target_seniority=target_seniority,
                preferred_locations=preferred_locations,
                work_authorization=work_authorization,
                needs_sponsorship=needs_sponsorship,
                linkedin_url=linkedin_url,
                github_url=github_url,
                portfolio_url=portfolio_url,
                current_title=current_title,
                years_experience=years_experience,
                open_to_relocation=open_to_relocation,
            )
            st.session_state["current_user"] = updated_user
            st.success("Account settings saved.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

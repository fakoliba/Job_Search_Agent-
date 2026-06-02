# AI-Powered Job Search Agent

A polished Streamlit MVP for managing and optimizing a technical job search with resume parsing, weighted role matching, draft generation, and application tracking.

## Current MVP

- Upload multiple PDF, DOCX, or TXT resumes
- Extract resume text
- Structure resumes into summary, experience, skills, leadership, impact metrics, seniority signals, and target roles
- Use OpenAI Structured Outputs for schema-backed resume parsing when `OPENAI_API_KEY` is configured
- Store multiple resume versions as JSON
- Match a selected resume against a job description
- Score fit with weighted keyword matching
- Generate resume bullets, company-fit answers, recruiter outreach, and cover letters
- Track applications and status in a lightweight local CRM
- Generate interview prep from saved jobs
- Use semantic matching signals alongside weighted keyword fit
- Create local user accounts for separate job-search workspaces
- Save and run job monitors for target company scans
- Generate AI career coaching, personalized company targets, and market/salary intelligence

## Project Structure

```text
job-agent/
├── app.py
├── requirements.txt
├── data/
│   ├── resumes/
│   ├── structured/
│   └── applications.json
├── modules/
│   ├── ingestion.py
│   ├── parser.py
│   ├── matcher.py
│   ├── generator.py
│   └── tracker.py
├── prompts/
│   ├── resume_tailor.txt
│   ├── why_company.txt
│   └── outreach.txt
└── README.md
```

## Run Locally

```bash
cd job-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Resume structuring and draft generation work without an API key using deterministic fallback logic. For OpenAI-backed generation:

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_MODEL="gpt-4.1-mini"
export OPENAI_RESUME_MODEL="gpt-4.1-mini"
```

## Deploy on Streamlit Community Cloud

This app is ready for a polished portfolio demo on Streamlit Community Cloud.

1. Push the `job-agent` folder to a GitHub repository.
2. In Streamlit Community Cloud, create a new app from that repository.
3. Set the app entrypoint to:

```text
app.py
```

4. Add secrets in the Streamlit Cloud app settings using `.streamlit/secrets.toml.example` as the template.
5. Keep `ENABLE_OPENAI_EMBEDDINGS = "false"` for a lower-cost demo, then enable it when you want OpenAI embedding-backed semantic scoring.

The repository includes `packages.txt` so Streamlit Cloud installs the Linux libraries needed by Playwright/Chromium. On the first browser-rendered job discovery run, the app will install the Playwright Chromium browser binary if Streamlit Cloud has not cached it yet.

### Demo Deployment Notes

- Local JSON files are fine for a portfolio demo, but production should move users, applications, monitors, and resume metadata to Postgres or another managed database.
- Uploaded resumes should move to object storage before a real multi-user launch.
- Rotate any OpenAI key that was ever shared outside a private secret manager.
- Browser-rendered job discovery may still be limited by some careers sites; keep it as a best-effort demo capability until it moves to a background worker.

## Architecture Notes

The MVP keeps the application modular:

- `ingestion.py` handles upload storage and safe filenames.
- `parser.py` owns PDF/DOCX/TXT extraction and parser fallback orchestration.
- `llm_resume_parser.py` owns OpenAI Structured Outputs resume extraction.
- `resume_schema.py` owns the validated resume data contract.
- `matcher.py` owns weighted fit scoring and explanation fields.
- `generator.py` owns AI draft generation with no-key fallback behavior.
- `tracker.py` owns the local application CRM.
- `auth.py` owns local username/password authentication.
- `interview.py` owns interview preparation generation.
- `monitor.py` owns saved job monitors and new-role detection.
- `career_intelligence.py` owns coaching, company targeting, trend, and salary planning logic.

This separation keeps the Streamlit app mostly orchestration and UX, making it easier to add FastAPI, ChromaDB, background job discovery, and agentic workflows later.

## Next Milestones

1. Replace heuristic salary planning with trusted compensation data sources.
2. Add ChromaDB-backed resume and job embeddings for long-term semantic retrieval.
3. Add recruiter contact discovery.
4. Add automated outreach sequencing with follow-up reminders.
5. Add FastAPI service boundaries for background jobs and future deployment.

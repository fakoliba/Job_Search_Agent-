from __future__ import annotations

import hashlib
import re
import json
import time
from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

from modules.matcher import MatchResult, ScoreBreakdown, score_resume_for_job


DISCOVERY_CACHE_DIR = Path("data/discovery_cache")
DISCOVERY_CACHE_VERSION = 1
DEFAULT_DISCOVERY_CACHE_TTL_SECONDS = 6 * 60 * 60
LAST_DISCOVERY_CACHE_EVENTS: list[str] = []


JOB_LINK_SIGNALS = (
    "job",
    "career",
    "position",
    "opening",
    "role",
    "requisition",
    "greenhouse",
    "lever",
    "ashby",
    "workday",
    "smartrecruiters",
)

JOB_TITLE_SIGNALS = (
    "engineer",
    "developer",
    "manager",
    "architect",
    "scientist",
    "analyst",
    "designer",
    "specialist",
    "director",
    "lead",
    "staff",
    "principal",
    "intern",
    "administrator",
    "consultant",
    "product",
    "program",
    "recruiter",
    "sales",
)

MARKETING_LINK_SIGNALS = (
    "life-at",
    "life at",
    "inclusion",
    "belonging",
    "how-we-hire",
    "how we hire",
    "university",
    "students",
    "internship program",
    "benefits",
    "culture",
    "meet-our-teams",
    "meet our teams",
    "about",
    "events",
    "privacy",
    "login",
    "profile",
    "dashboard",
    "applications",
    "saved-jobs",
    "settings",
)

ATS_JOB_HOST_SIGNALS = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workdayjobs.com",
    "smartrecruiters.com",
    "eightfold.ai",
)

ROLE_QUERY_EXPANSIONS = {
    "ai": {"ai", "ml", "machine learning", "llm", "model", "research engineer", "applied ai"},
    "engineering": {"engineer", "engineering", "developer", "software", "platform", "infrastructure", "sre"},
    "engineer": {"engineer", "engineering", "developer", "software"},
    "software": {"software", "backend", "full stack", "frontend", "systems"},
    "platform": {"platform", "infrastructure", "developer productivity", "kubernetes"},
    "sre": {"sre", "reliability", "infrastructure", "observability"},
    "infrastructure": {"infrastructure", "platform", "cloud", "kubernetes", "terraform"},
    "manager": {"manager", "engineering manager", "lead"},
}

ENGINEERING_TITLE_TERMS = {
    "engineer",
    "engineering",
    "developer",
    "architect",
    "scientist",
    "sre",
    "infrastructure",
    "platform",
    "systems",
    "scientist",
    "technical staff",
}

NON_ENGINEERING_TITLE_TERMS = {
    "account",
    "accounting",
    "sales",
    "finance",
    "marketing",
    "recruiter",
    "recruiting",
    "legal",
    "policy",
}

STRONG_ENGINEERING_TITLE_TERMS = {
    "engineer",
    "engineering",
    "developer",
    "architect",
    "scientist",
    "sre",
    "platform",
    "systems",
    "technical staff",
}


@dataclass
class CompanyTarget:
    company: str
    careers_url: str


@dataclass
class DiscoveredJob:
    company: str
    title: str
    location: str
    url: str
    description: str
    match: MatchResult
    role_relevance: int = 0
    source_adapter: str = ""
    cache_hit: bool = False


@dataclass
class SiteClassification:
    category: str
    confidence: int
    reasons: list[str]


@dataclass
class DiscoveryContext:
    target: CompanyTarget
    resume: dict
    listing_html: str
    classification: SiteClassification
    max_jobs: int = 8
    max_pages: int = 1
    use_rendered_fallback: bool = True
    job_query: str = ""


class JobDiscoveryAdapter:
    name = "base"
    requires_rendered = False
    supported_categories: tuple[str, ...] = ("unknown",)

    def discover(self, context: DiscoveryContext) -> list[DiscoveredJob]:
        raise NotImplementedError


class GreenhouseApiAdapter(JobDiscoveryAdapter):
    name = "greenhouse_api"
    supported_categories = ("public_ats_api",)

    def discover(self, context: DiscoveryContext) -> list[DiscoveredJob]:
        board_token = extract_greenhouse_board_token(context.target.careers_url)
        if not board_token:
            return []
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        try:
            payload = fetch_json(url)
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []
        jobs = [
            normalize_greenhouse_job(context, job)
            for job in payload.get("jobs", [])
            if isinstance(job, dict)
        ]
        return filter_and_sort_discovered_jobs(jobs, context.job_query)[: context.max_jobs]


class LeverApiAdapter(JobDiscoveryAdapter):
    name = "lever_api"
    supported_categories = ("public_ats_api",)

    def discover(self, context: DiscoveryContext) -> list[DiscoveredJob]:
        site = extract_lever_site(context.target.careers_url)
        if not site:
            return []

        raw_jobs: list[dict] = []
        limit = 100
        for page_index in range(context.max_pages):
            url = f"https://api.lever.co/v0/postings/{site}?mode=json&skip={page_index * limit}&limit={limit}"
            try:
                payload = fetch_json(url)
            except Exception:
                break
            if not isinstance(payload, list):
                break
            raw_jobs.extend(job for job in payload if isinstance(job, dict))
            if len(payload) < limit:
                break

        jobs = [normalize_lever_job(context, job) for job in raw_jobs]
        return filter_and_sort_discovered_jobs(jobs, context.job_query)[: context.max_jobs]


class AshbyApiAdapter(JobDiscoveryAdapter):
    name = "ashby_api"
    supported_categories = ("public_ats_api",)

    def discover(self, context: DiscoveryContext) -> list[DiscoveredJob]:
        board_name = extract_ashby_board_name(context.target.careers_url)
        if not board_name:
            return []
        url = f"https://api.ashbyhq.com/posting-api/job-board/{board_name}?includeCompensation=true"
        try:
            payload = fetch_json(url)
        except Exception:
            return []
        if not isinstance(payload, dict):
            return []
        jobs = [
            normalize_ashby_job(context, job)
            for job in payload.get("jobs", [])
            if isinstance(job, dict)
        ]
        return filter_and_sort_discovered_jobs(jobs, context.job_query)[: context.max_jobs]


class SmartRecruitersApiAdapter(JobDiscoveryAdapter):
    name = "smartrecruiters_api"
    supported_categories = ("public_ats_api",)

    def discover(self, context: DiscoveryContext) -> list[DiscoveredJob]:
        company_identifier = extract_smartrecruiters_company(context.target.careers_url)
        if not company_identifier:
            return []

        raw_jobs: list[dict] = []
        limit = 100
        for page_index in range(context.max_pages):
            offset = page_index * limit
            url = f"https://api.smartrecruiters.com/v1/companies/{company_identifier}/postings?limit={limit}&offset={offset}"
            try:
                payload = fetch_json(url)
            except Exception:
                break
            if not isinstance(payload, dict):
                break
            content = payload.get("content") or payload.get("postings") or []
            if not isinstance(content, list):
                break
            raw_jobs.extend(job for job in content if isinstance(job, dict))
            total_found = payload.get("totalFound")
            if len(content) < limit or (isinstance(total_found, int) and len(raw_jobs) >= total_found):
                break

        jobs = [normalize_smartrecruiters_job(context, job) for job in raw_jobs]
        return filter_and_sort_discovered_jobs(jobs, context.job_query)[: context.max_jobs]


class StaticJobCardAdapter(JobDiscoveryAdapter):
    name = "static_job_cards"
    supported_categories = ("static_html", "custom_spa", "unknown")

    def discover(self, context: DiscoveryContext) -> list[DiscoveredJob]:
        cards = extract_static_job_cards(context.listing_html, context.target.careers_url)
        if not cards:
            return []
        return score_static_cards(
            context.target.company,
            cards,
            context.resume,
            job_query=context.job_query,
        )[: context.max_jobs]


class StaticJobLinkAdapter(JobDiscoveryAdapter):
    name = "static_job_links"
    supported_categories = ("static_html", "custom_spa", "hosted_ats", "public_ats_api", "unknown")

    def discover(self, context: DiscoveryContext) -> list[DiscoveredJob]:
        job_links = filter_job_links_by_query(
            extract_job_links(context.listing_html, context.target.careers_url),
            context.job_query,
        )[: context.max_jobs]
        return score_job_links(context, job_links)


class RenderedJobCardAdapter(JobDiscoveryAdapter):
    name = "rendered_job_cards"
    requires_rendered = True
    supported_categories = ("hosted_ats", "custom_spa", "unknown")

    def discover(self, context: DiscoveryContext) -> list[DiscoveredJob]:
        if not context.use_rendered_fallback:
            return []
        return discover_jobs_with_playwright(
            context.target,
            context.resume,
            max_jobs=context.max_jobs,
            max_pages=context.max_pages,
            job_query=context.job_query,
        )


class JsonLdJobPostingAdapter(JobDiscoveryAdapter):
    name = "json_ld_job_postings"
    supported_categories = ("json_ld", "static_html", "custom_spa", "unknown")

    def discover(self, context: DiscoveryContext) -> list[DiscoveredJob]:
        structured_jobs = extract_structured_job_postings(
            context.listing_html,
            context.target.careers_url,
        )
        if not structured_jobs:
            return []
        return score_structured_jobs(
            context.target.company,
            structured_jobs,
            context.resume,
            job_query=context.job_query,
        )[: context.max_jobs]


def build_default_discovery_adapters(
    use_rendered_fallback: bool = True,
    classification: SiteClassification | None = None,
) -> list[JobDiscoveryAdapter]:
    adapters: list[JobDiscoveryAdapter] = [
        GreenhouseApiAdapter(),
        LeverApiAdapter(),
        AshbyApiAdapter(),
        SmartRecruitersApiAdapter(),
        StaticJobCardAdapter(),
        StaticJobLinkAdapter(),
    ]
    if use_rendered_fallback:
        adapters.append(RenderedJobCardAdapter())
    adapters.append(JsonLdJobPostingAdapter())

    if not classification:
        return adapters

    priority_by_category = {
        "public_ats_api": [
            "greenhouse_api",
            "lever_api",
            "ashby_api",
            "smartrecruiters_api",
            "static_job_links",
            "json_ld_job_postings",
            "rendered_job_cards",
            "static_job_cards",
        ],
        "hosted_ats": ["rendered_job_cards", "static_job_links", "json_ld_job_postings", "static_job_cards"],
        "custom_spa": ["rendered_job_cards", "static_job_links", "static_job_cards", "json_ld_job_postings"],
        "json_ld": ["json_ld_job_postings", "static_job_links", "static_job_cards", "rendered_job_cards"],
        "static_html": ["static_job_cards", "static_job_links", "json_ld_job_postings", "rendered_job_cards"],
        "unknown": ["static_job_cards", "static_job_links", "rendered_job_cards", "json_ld_job_postings"],
    }
    priority = priority_by_category.get(classification.category, priority_by_category["unknown"])
    rank = {name: index for index, name in enumerate(priority)}
    compatible = [
        adapter
        for adapter in adapters
        if classification.category in adapter.supported_categories or "unknown" in adapter.supported_categories
    ]
    return sorted(compatible, key=lambda adapter: rank.get(adapter.name, len(priority)))


def classify_careers_site(url: str, html: str = "") -> SiteClassification:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    html_lower = html[:200000].lower()
    reasons: list[str] = []

    public_ats_hosts = {
        "boards.greenhouse.io": "Greenhouse-style hosted board",
        "job-boards.greenhouse.io": "Greenhouse-style hosted board",
        "greenhouse.io": "Greenhouse-style hosted board",
        "jobs.lever.co": "Lever-style hosted board",
        "lever.co": "Lever-style hosted board",
        "jobs.ashbyhq.com": "Ashby-style hosted board",
        "ashbyhq.com": "Ashby-style hosted board",
        "jobs.smartrecruiters.com": "SmartRecruiters-style hosted board",
        "smartrecruiters.com": "SmartRecruiters-style hosted board",
    }
    for host_signal, reason in public_ats_hosts.items():
        if host_signal in hostname:
            return SiteClassification("public_ats_api", 95, [reason])

    hosted_ats_signals = {
        "eightfold.ai": "Eightfold host signal",
        "workdayjobs.com": "Workday host signal",
        "myworkdayjobs.com": "Workday host signal",
        "icims.com": "iCIMS host signal",
        "phenompeople.com": "Phenom host signal",
    }
    for host_signal, reason in hosted_ats_signals.items():
        if host_signal in hostname:
            return SiteClassification("hosted_ats", 90, [reason])

    if "pid=" in query:
        reasons.append("URL contains ATS-style pid parameter")
    if "position-card" in html_lower or "data-test-id=\"position-card" in html_lower:
        reasons.append("HTML contains repeated position-card markers")
    if reasons:
        return SiteClassification("hosted_ats", 82, reasons)

    if "application/ld+json" in html_lower and "jobposting" in html_lower:
        return SiteClassification("json_ld", 88, ["HTML contains schema.org JobPosting JSON-LD"])

    custom_spa_signals = []
    if "/jobsearch" in path or "/jobs/results" in path or "/profile/job_details" in path:
        custom_spa_signals.append("URL path looks like a custom careers search app")
    if "__next_data__" in html_lower or "window.__" in html_lower or "data-reactroot" in html_lower:
        custom_spa_signals.append("HTML contains single-page app markers")
    if "metacareers.com" in hostname or "google.com" in hostname:
        custom_spa_signals.append("Known custom careers SPA host pattern")
    if custom_spa_signals:
        return SiteClassification("custom_spa", 78, custom_spa_signals)

    if extract_job_links(html, url) or extract_static_job_cards(html, url):
        return SiteClassification("static_html", 72, ["Static HTML contains probable job links or cards"])

    return SiteClassification("unknown", 30, ["No strong careers-site structure detected"])


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href:
            text = clean_whitespace(" ".join(self._current_text))
            self.links.append((self._current_href, text))
            self._current_href = None
            self._current_text = []


def discover_jobs_for_targets(
    targets: list[CompanyTarget],
    resume: dict,
    max_jobs_per_company: int = 8,
    max_pages_per_company: int = 1,
    use_rendered_fallback: bool = True,
    use_cache: bool = True,
    cache_ttl_seconds: int = DEFAULT_DISCOVERY_CACHE_TTL_SECONDS,
    job_query: str = "",
) -> list[DiscoveredJob]:
    LAST_DISCOVERY_CACHE_EVENTS.clear()
    discovered: list[DiscoveredJob] = []
    for target in targets:
        discovered.extend(
            discover_jobs_for_company(
                target,
                resume,
                max_jobs=max_jobs_per_company,
                max_pages=max_pages_per_company,
                use_rendered_fallback=use_rendered_fallback,
                use_cache=use_cache,
                cache_ttl_seconds=cache_ttl_seconds,
                job_query=job_query,
            )
        )
    return sorted(
        filter_jobs_by_role_query(discovered, job_query),
        key=lambda job: (job.role_relevance, job.match.match_score),
        reverse=True,
    )


def discover_jobs_for_company(
    target: CompanyTarget,
    resume: dict,
    max_jobs: int = 8,
    max_pages: int = 1,
    use_rendered_fallback: bool = True,
    use_cache: bool = True,
    cache_ttl_seconds: int = DEFAULT_DISCOVERY_CACHE_TTL_SECONDS,
    job_query: str = "",
) -> list[DiscoveredJob]:
    if use_cache:
        cached_jobs = load_cached_discovery_jobs(
            target=target,
            resume=resume,
            max_jobs=max_jobs,
            max_pages=max_pages,
            use_rendered_fallback=use_rendered_fallback,
            job_query=job_query,
            ttl_seconds=cache_ttl_seconds,
        )
        if cached_jobs is not None:
            LAST_DISCOVERY_CACHE_EVENTS.append(f"{target.company}: used cached discovery results.")
            return cached_jobs[:max_jobs]

    try:
        listing_html = fetch_url(target.careers_url)
    except Exception:
        listing_html = ""

    classification = classify_careers_site(target.careers_url, listing_html)
    context = DiscoveryContext(
        target=target,
        resume=resume,
        listing_html=listing_html,
        classification=classification,
        max_jobs=max_jobs,
        max_pages=max(1, max_pages),
        use_rendered_fallback=use_rendered_fallback,
        job_query=job_query,
    )
    for adapter in build_default_discovery_adapters(
        use_rendered_fallback=use_rendered_fallback,
        classification=classification,
    ):
        jobs = adapter.discover(context)
        if jobs:
            for job in jobs:
                job.source_adapter = adapter.name
            jobs = jobs[:max_jobs]
            if use_cache:
                save_cached_discovery_jobs(
                    target=target,
                    resume=resume,
                    max_jobs=max_jobs,
                    max_pages=max_pages,
                    use_rendered_fallback=use_rendered_fallback,
                    job_query=job_query,
                    classification=classification,
                    adapter_name=adapter.name,
                    jobs=jobs,
                )
                LAST_DISCOVERY_CACHE_EVENTS.append(f"{target.company}: saved fresh discovery results.")
            return jobs
    return []


def fetch_url(url: str, timeout: int = 12) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; JobSearchAgent/0.1; +https://localhost)"
        },
    )
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        charset = response.headers.get_content_charset() or "utf-8"
        if "text" not in content_type and "html" not in content_type and "json" not in content_type:
            return ""
        return response.read().decode(charset, errors="ignore")


def fetch_json(url: str, timeout: int = 12) -> object:
    raw = fetch_url(url, timeout=timeout)
    return json.loads(raw or "{}")


def discovery_cache_key(
    target: CompanyTarget,
    resume: dict,
    max_jobs: int,
    max_pages: int,
    use_rendered_fallback: bool,
    job_query: str,
) -> str:
    payload = {
        "version": DISCOVERY_CACHE_VERSION,
        "company": target.company,
        "url": target.careers_url,
        "resume": resume_cache_signature(resume),
        "max_jobs": max_jobs,
        "max_pages": max_pages,
        "use_rendered_fallback": use_rendered_fallback,
        "job_query": normalize_for_matching(job_query),
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resume_cache_signature(resume: dict) -> str:
    relevant_resume = {
        "summary": resume.get("summary", ""),
        "skills": resume.get("skills", []),
        "leadership": resume.get("leadership", []),
        "impact_metrics": resume.get("impact_metrics", []),
        "seniority_signals": resume.get("seniority_signals", []),
        "target_roles": resume.get("target_roles", []),
        "raw_text": resume.get("raw_text", "")[:3000],
    }
    raw = json.dumps(relevant_resume, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def discovery_cache_path(cache_key: str) -> Path:
    return DISCOVERY_CACHE_DIR / f"{cache_key}.json"


def load_cached_discovery_jobs(
    target: CompanyTarget,
    resume: dict,
    max_jobs: int,
    max_pages: int,
    use_rendered_fallback: bool,
    job_query: str,
    ttl_seconds: int,
) -> list[DiscoveredJob] | None:
    cache_key = discovery_cache_key(
        target=target,
        resume=resume,
        max_jobs=max_jobs,
        max_pages=max_pages,
        use_rendered_fallback=use_rendered_fallback,
        job_query=job_query,
    )
    path = discovery_cache_path(cache_key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("version") != DISCOVERY_CACHE_VERSION:
        return None
    cached_at = payload.get("cached_at", 0)
    if not isinstance(cached_at, (int, float)) or time.time() - cached_at > ttl_seconds:
        return None
    jobs = [job_from_cache_record(record) for record in payload.get("jobs", []) if isinstance(record, dict)]
    for job in jobs:
        job.cache_hit = True
    return jobs


def save_cached_discovery_jobs(
    target: CompanyTarget,
    resume: dict,
    max_jobs: int,
    max_pages: int,
    use_rendered_fallback: bool,
    job_query: str,
    classification: SiteClassification,
    adapter_name: str,
    jobs: list[DiscoveredJob],
) -> None:
    cache_key = discovery_cache_key(
        target=target,
        resume=resume,
        max_jobs=max_jobs,
        max_pages=max_pages,
        use_rendered_fallback=use_rendered_fallback,
        job_query=job_query,
    )
    payload = {
        "version": DISCOVERY_CACHE_VERSION,
        "cached_at": time.time(),
        "target": asdict(target),
        "classification": asdict(classification),
        "adapter": adapter_name,
        "jobs": [job_to_cache_record(job) for job in jobs],
    }
    try:
        DISCOVERY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        discovery_cache_path(cache_key).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        return


def job_to_cache_record(job: DiscoveredJob) -> dict:
    return {
        "company": job.company,
        "title": job.title,
        "location": job.location,
        "url": job.url,
        "description": job.description,
        "role_relevance": job.role_relevance,
        "source_adapter": job.source_adapter,
        "match": asdict(job.match),
    }


def job_from_cache_record(record: dict) -> DiscoveredJob:
    match_payload = record.get("match", {})
    score_breakdown_payload = match_payload.get("score_breakdown", {})
    match = MatchResult(
        match_score=int(match_payload.get("match_score", 0)),
        matching_skills=list(match_payload.get("matching_skills", [])),
        missing_skills=list(match_payload.get("missing_skills", [])),
        weighted_hits=dict(match_payload.get("weighted_hits", {})),
        seniority_match=str(match_payload.get("seniority_match", "Unknown")),
        recommendation=str(match_payload.get("recommendation", "")),
        score_breakdown=ScoreBreakdown(**score_breakdown_payload),
        matching_leadership=list(match_payload.get("matching_leadership", [])),
        missing_leadership=list(match_payload.get("missing_leadership", [])),
        matching_domains=list(match_payload.get("matching_domains", [])),
        resume_gaps=list(match_payload.get("resume_gaps", [])),
        semantic_score=int(match_payload.get("semantic_score", 0)),
        semantic_method=str(match_payload.get("semantic_method", "token_overlap")),
    )
    return DiscoveredJob(
        company=str(record.get("company", "")),
        title=str(record.get("title", "Open Role")),
        location=str(record.get("location", "Not specified")),
        url=str(record.get("url", "")),
        description=str(record.get("description", "")),
        match=match,
        role_relevance=int(record.get("role_relevance", 0)),
        source_adapter=str(record.get("source_adapter", "")),
    )


def extract_greenhouse_board_token(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if query.get("for"):
        return query["for"][0]
    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname and "boards-api.greenhouse.io" in parsed.hostname and "boards" in path_parts:
        board_index = path_parts.index("boards")
        if len(path_parts) > board_index + 1:
            return path_parts[board_index + 1]
    if path_parts and parsed.hostname and "greenhouse.io" in parsed.hostname:
        return path_parts[0]
    return ""


def extract_lever_site(url: str) -> str:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname and "api.lever.co" in parsed.hostname and "postings" in path_parts:
        site_index = path_parts.index("postings")
        if len(path_parts) > site_index + 1:
            return path_parts[site_index + 1]
    if path_parts and parsed.hostname and "lever.co" in parsed.hostname:
        return path_parts[0]
    return ""


def extract_ashby_board_name(url: str) -> str:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if "job-board" in path_parts:
        board_index = path_parts.index("job-board")
        if len(path_parts) > board_index + 1:
            return path_parts[board_index + 1]
    if path_parts and parsed.hostname and "ashbyhq.com" in parsed.hostname:
        return path_parts[0]
    return ""


def extract_smartrecruiters_company(url: str) -> str:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if "companies" in path_parts:
        company_index = path_parts.index("companies")
        if len(path_parts) > company_index + 1:
            return path_parts[company_index + 1]
    if path_parts and parsed.hostname and "smartrecruiters.com" in parsed.hostname:
        return path_parts[0]
    return ""


def normalize_greenhouse_job(context: DiscoveryContext, job: dict) -> DiscoveredJob:
    title = clean_whitespace(str(job.get("title") or "Open Role"))
    description = extract_page_text(str(job.get("content") or title))
    location = clean_whitespace(str((job.get("location") or {}).get("name") or "Not specified"))
    url = str(job.get("absolute_url") or context.target.careers_url)
    return build_discovered_job(context, title, location, url, description)


def normalize_lever_job(context: DiscoveryContext, job: dict) -> DiscoveredJob:
    title = clean_whitespace(str(job.get("text") or job.get("title") or "Open Role"))
    location = clean_whitespace(str((job.get("categories") or {}).get("location") or "Not specified"))
    description_parts = [
        title,
        str((job.get("categories") or {}).get("team") or ""),
        str((job.get("categories") or {}).get("commitment") or ""),
        str(job.get("descriptionPlain") or job.get("description") or ""),
    ]
    description = clean_whitespace("\n".join(part for part in description_parts if part))
    url = str(job.get("hostedUrl") or job.get("applyUrl") or context.target.careers_url)
    return build_discovered_job(context, title, location, url, description)


def normalize_ashby_job(context: DiscoveryContext, job: dict) -> DiscoveredJob:
    title = clean_whitespace(str(job.get("title") or "Open Role"))
    location = clean_whitespace(str(job.get("location") or "Not specified"))
    description_parts = [
        title,
        str(job.get("department") or ""),
        str(job.get("team") or ""),
        str(job.get("descriptionHtml") or job.get("descriptionPlain") or ""),
    ]
    description = extract_page_text("\n".join(part for part in description_parts if part))
    url = str(job.get("jobUrl") or job.get("applyUrl") or context.target.careers_url)
    return build_discovered_job(context, title, location, url, description)


def normalize_smartrecruiters_job(context: DiscoveryContext, job: dict) -> DiscoveredJob:
    title = clean_whitespace(str(job.get("name") or job.get("title") or "Open Role"))
    location = smartrecruiters_location(job.get("location"))
    description_parts = [
        title,
        str(job.get("department", {}).get("label") if isinstance(job.get("department"), dict) else job.get("department") or ""),
        str(job.get("function", {}).get("label") if isinstance(job.get("function"), dict) else job.get("function") or ""),
        str(job.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text") if isinstance(job.get("jobAd"), dict) else ""),
    ]
    description = extract_page_text("\n".join(part for part in description_parts if part))
    url = smartrecruiters_candidate_url(context, job)
    return build_discovered_job(context, title, location, url, description)


def smartrecruiters_location(value: object) -> str:
    if not isinstance(value, dict):
        return "Not specified"
    if value.get("fullLocation"):
        return clean_location_text(str(value.get("fullLocation")))
    parts = [
        value.get("city"),
        value.get("region"),
        value.get("country"),
    ]
    return clean_whitespace(", ".join(str(part) for part in parts if part)) or "Not specified"


def clean_location_text(text: str) -> str:
    parts = [clean_whitespace(part) for part in text.split(",")]
    return ", ".join(part for part in parts if part) or "Not specified"


def smartrecruiters_candidate_url(context: DiscoveryContext, job: dict) -> str:
    explicit_url = job.get("postingUrl") or job.get("applyUrl") or job.get("url")
    if explicit_url:
        return str(explicit_url)
    company_identifier = extract_smartrecruiters_company(context.target.careers_url)
    posting_id = job.get("id") or job.get("uuid")
    if company_identifier and posting_id:
        slug = slugify(str(job.get("name") or job.get("title") or "job"))
        return f"https://jobs.smartrecruiters.com/{company_identifier}/{posting_id}-{slug}"
    return str(job.get("ref") or context.target.careers_url)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "job"


def build_discovered_job(
    context: DiscoveryContext,
    title: str,
    location: str,
    url: str,
    description: str,
) -> DiscoveredJob:
    match = score_resume_for_job(context.resume, f"{title}\n{description}")
    role_relevance = calculate_role_relevance(title, description, context.job_query)
    return DiscoveredJob(
        company=context.target.company,
        title=title,
        location=location or "Not specified",
        url=url,
        description=description,
        match=match,
        role_relevance=role_relevance,
    )


def filter_and_sort_discovered_jobs(jobs: list[DiscoveredJob], job_query: str = "") -> list[DiscoveredJob]:
    if job_query.strip():
        jobs = [job for job in jobs if job.role_relevance > 0]
    return sorted(jobs, key=lambda job: (job.role_relevance, job.match.match_score), reverse=True)


def score_job_links(context: DiscoveryContext, job_links: list[tuple[str, str]]) -> list[DiscoveredJob]:
    jobs: list[DiscoveredJob] = []
    for url, link_text in job_links:
        try:
            job_html = fetch_url(url)
        except Exception:
            job_html = context.listing_html

        description = extract_page_text(job_html)
        title = infer_title(job_html, link_text, url)
        location = infer_location(description)
        match = score_resume_for_job(context.resume, description or link_text)
        role_relevance = calculate_role_relevance(title, description, context.job_query)
        jobs.append(
            DiscoveredJob(
                company=context.target.company,
                title=title,
                location=location,
                url=url,
                description=description,
                match=match,
                role_relevance=role_relevance,
            )
        )

    return sorted(jobs, key=lambda job: (job.role_relevance, job.match.match_score), reverse=True)


def discover_jobs_with_playwright(
    target: CompanyTarget,
    resume: dict,
    max_jobs: int = 8,
    max_pages: int = 1,
    job_query: str = "",
) -> list[DiscoveredJob]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run `pip install playwright` and `playwright install chromium` "
            "to enable rendered job discovery for JavaScript career sites."
        ) from exc

    jobs: list[DiscoveredJob] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        network_payloads: list[object] = []
        page.on("response", lambda response: capture_network_json_response(response, network_payloads))
        try:
            page.goto(target.careers_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(6000)
            cards = collect_rendered_cards_across_pages(
                page,
                target.careers_url,
                network_payloads=network_payloads,
                job_query=job_query,
                max_pages=max_pages,
            )
            if not cards and job_query.strip() and "google.com" not in (urlparse(target.careers_url).hostname or ""):
                apply_rendered_search_query(page, job_query)
                cards = collect_rendered_cards_across_pages(
                    page,
                    target.careers_url,
                    network_payloads=network_payloads,
                    job_query=job_query,
                    max_pages=max_pages,
                )
            cards = cards[:max_jobs]

            for card in cards:
                job_url = card["url"]
                title = card["title"]
                location = card.get("location") or "Not specified"
                description = fetch_rendered_job_description(page, job_url, title, fallback_description=card.get("text", ""))
                match = score_resume_for_job(resume, f"{title}\n{description}")
                role_relevance = calculate_role_relevance(title, description, job_query)
                jobs.append(
                    DiscoveredJob(
                        company=target.company,
                        title=title,
                        location=location,
                        url=job_url,
                        description=description,
                        match=match,
                        role_relevance=role_relevance,
                    )
                )
        finally:
            browser.close()

    return jobs


def capture_network_json_response(response, payloads: list[object], max_payloads: int = 40) -> None:
    if len(payloads) >= max_payloads:
        return
    url = response.url.lower()
    content_type = response.headers.get("content-type", "").lower()
    if "json" not in content_type and not any(signal in url for signal in ("job", "career", "position", "posting", "requisition")):
        return
    try:
        payload = response.json()
    except Exception:
        return
    payloads.append(payload)


def collect_rendered_cards_across_pages(
    page,
    base_url: str,
    network_payloads: list[object] | None = None,
    job_query: str = "",
    max_pages: int = 1,
) -> list[dict]:
    collected: dict[str, dict] = {}
    pages_to_scan = max(1, max_pages)

    for page_index in range(pages_to_scan):
        for card in extract_rendered_job_cards(page, base_url):
            key = card.get("url") or card.get("title")
            if key and key not in collected:
                collected[key] = card

        if page_index == pages_to_scan - 1:
            break
        if not advance_rendered_results_page(page):
            break

    for card in extract_network_job_cards(network_payloads or [], base_url):
        key = card.get("url") or card.get("title")
        if key and key not in collected:
            collected[key] = card

    return filter_rendered_cards_by_query(list(collected.values()), job_query)


def extract_network_job_cards(payloads: list[object], base_url: str) -> list[dict]:
    cards: list[dict] = []
    seen: set[str] = set()
    for payload in payloads:
        for item in find_job_like_objects(payload):
            card = normalize_network_job_card(item, base_url)
            if not card:
                continue
            key = card.get("url") or card.get("title")
            if key in seen:
                continue
            seen.add(key)
            cards.append(card)
    return cards


def find_job_like_objects(value: object, depth: int = 0) -> list[dict]:
    if depth > 8:
        return []
    if isinstance(value, list):
        jobs: list[dict] = []
        for item in value:
            jobs.extend(find_job_like_objects(item, depth + 1))
        return jobs
    if not isinstance(value, dict):
        return []

    jobs = [value] if is_job_like_object(value) else []
    for child in value.values():
        if isinstance(child, (dict, list)):
            jobs.extend(find_job_like_objects(child, depth + 1))
    return jobs


def is_job_like_object(value: dict) -> bool:
    keys = {str(key).lower() for key in value.keys()}
    title_keys = {"title", "jobtitle", "name", "text"}
    has_title = any(key in keys for key in title_keys)
    has_job_signal = bool(
        keys
        & {
            "location",
            "locations",
            "department",
            "team",
            "jobid",
            "job_id",
            "id",
            "url",
            "joburl",
            "applyurl",
            "description",
            "descriptionhtml",
            "descriptionplain",
        }
    )
    if not (has_title and has_job_signal):
        return False

    title = str(first_present(value, ("title", "jobTitle", "name", "text")) or "")
    return any(signal in title.lower() for signal in JOB_TITLE_SIGNALS)


def normalize_network_job_card(value: dict, base_url: str) -> dict | None:
    title = clean_whitespace(str(first_present(value, ("title", "jobTitle", "name", "text")) or ""))
    if not title:
        return None
    url = normalize_network_job_url(value, base_url, title)
    location = normalize_network_location(first_present(value, ("location", "locations", "jobLocation", "office")))
    description = clean_whitespace(
        extract_page_text(
            str(
                first_present(
                    value,
                    (
                        "description",
                        "descriptionHtml",
                        "descriptionPlain",
                        "content",
                        "jobDescription",
                        "summary",
                    ),
                )
                or ""
            )
        )
    )
    team = clean_whitespace(str(first_present(value, ("department", "team", "category", "function")) or ""))
    text = clean_whitespace("\n".join(part for part in (title, location, team, description) if part))
    return {
        "title": title,
        "url": url,
        "location": location or "Not specified",
        "text": text or title,
    }


def normalize_network_job_url(value: dict, base_url: str, title: str) -> str:
    explicit_url = first_present(
        value,
        ("url", "jobUrl", "job_url", "absoluteUrl", "absolute_url", "hostedUrl", "applyUrl", "externalUrl"),
    )
    if explicit_url:
        return urljoin(base_url, str(explicit_url))

    identifier = first_present(value, ("id", "jobId", "job_id", "requisitionId", "requisition_id", "postingId"))
    if identifier:
        return urljoin(base_url, f"#{identifier}")
    return urljoin(base_url, f"#{slugify(title)}")


def normalize_network_location(value: object) -> str:
    if isinstance(value, str):
        return clean_location_text(value)
    if isinstance(value, list):
        locations = [normalize_network_location(item) for item in value]
        return clean_whitespace(", ".join(location for location in locations if location and location != "Not specified"))
    if isinstance(value, dict):
        if value.get("name"):
            return clean_location_text(str(value.get("name")))
        if value.get("fullLocation"):
            return clean_location_text(str(value.get("fullLocation")))
        parts = [
            value.get("city"),
            value.get("state"),
            value.get("region"),
            value.get("country"),
        ]
        return clean_location_text(", ".join(str(part) for part in parts if part))
    return "Not specified"


def first_present(value: dict, keys: tuple[str, ...]) -> object:
    lower_key_map = {str(key).lower(): key for key in value.keys()}
    for key in keys:
        actual_key = lower_key_map.get(key.lower())
        if actual_key is None:
            continue
        candidate = value.get(actual_key)
        if candidate not in (None, "", []):
            return candidate
    return None


def advance_rendered_results_page(page) -> bool:
    page.mouse.wheel(0, 2500)
    page.wait_for_timeout(700)
    selectors = [
        'button[aria-label*="Next" i]',
        'a[aria-label*="Next" i]',
        '[role="button"][aria-label*="Next" i]',
        'button:has-text("Next")',
        'a:has-text("Next")',
        '[role="button"]:has-text("Next")',
        'button:has-text("Show more")',
        '[role="button"]:has-text("Show more")',
        'button:has-text("Load more")',
        '[role="button"]:has-text("Load more")',
        'button:has-text("More positions")',
        '[role="button"]:has-text("More positions")',
    ]

    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = min(locator.count(), 5)
        except Exception:
            continue

        for index in range(count):
            candidate = locator.nth(index)
            try:
                if not candidate.is_visible(timeout=1000):
                    continue
                if candidate.is_disabled(timeout=1000):
                    continue
                before_url = page.url
                before_text = page.locator("body").inner_text(timeout=3000)[:2000]
                candidate.scroll_into_view_if_needed(timeout=2000)
                candidate.click(timeout=3000)
                page.wait_for_timeout(3500)
                after_text = page.locator("body").inner_text(timeout=3000)[:2000]
                return page.url != before_url or after_text != before_text
            except Exception:
                continue
    return False


def apply_rendered_search_query(page, job_query: str) -> None:
    query = job_query.strip()
    if not query:
        return

    selectors = [
        'input[aria-label*="Search for keywords" i]',
        'input[placeholder*="Search" i]',
        'input[type="search"]',
        '[role="combobox"][aria-label*="Search for keywords" i]',
        '[role="combobox"]',
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        if callable(locator):
            locator = locator()
        try:
            if locator.count() == 0:
                continue
            locator.fill(query, timeout=3000)
            locator.press("Enter", timeout=3000)
            page.wait_for_timeout(3500)
            return
        except Exception:
            continue

    try:
        page.keyboard.type(query)
        page.keyboard.press("Enter")
        page.wait_for_timeout(3500)
    except Exception:
        return


def extract_rendered_job_cards(page, base_url: str) -> list[dict]:
    cards = page.evaluate(
        """(baseUrl) => {
            const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
            const results = [];
            const baseHost = new URL(baseUrl).hostname;

            const anchors = [...document.querySelectorAll('a[href]')];
            results.push(...anchors
                .map((el) => {
                    const aria = normalize(el.getAttribute('aria-label'));
                    const heading = normalize(el.querySelector('h1,h2,h3')?.textContent);
                    const text = normalize(el.textContent);
                    const href = el.getAttribute('href');
                    const label = aria || heading || text;
                    return {
                        title: label.replace(/^View job:\\s*/i, '').trim(),
                        url: new URL(href, baseUrl).toString(),
                        text,
                        aria,
                        heading,
                    };
                })
                .filter((item) => {
                    const path = new URL(item.url).pathname;
                    const isViewJob = /^View job:/i.test(item.aria);
                    const isCareerPosting = item.heading && /^\\/careers\\/[^/]+\\/?$/.test(path) && !path.includes('/search');
                    const isDetailPosting = item.heading && /\\/details\\/[^/]+\\//.test(path);
                    return (isViewJob || isCareerPosting || isDetailPosting) && item.url;
                }));

            const resultRows = [...document.querySelectorAll('li, article, [role="listitem"], [role="row"]')];
            results.push(...resultRows.map((el) => {
                const link = el.querySelector('a[href]');
                const heading = normalize(el.querySelector('h2,h3')?.textContent || link?.textContent);
                const text = normalize(el.textContent);
                const href = link?.getAttribute('href');
                const locationMatch = text.match(/Location\\s+(.+?)\\s+Actions/i) || text.match(/Location\\s+(.+?)\\s+(?:Role Number|Share)/i);
                return {
                    title: heading,
                    url: href ? new URL(href, baseUrl).toString() : new URL(window.location.pathname + window.location.search + `#${encodeURIComponent(heading)}`, baseUrl).toString(),
                    text,
                    location: locationMatch ? normalize(locationMatch[1]) : '',
                    aria: normalize(link?.getAttribute('aria-label')),
                    heading,
                };
            }).filter((item) => {
                if (!item.title || !item.url || item.title.length > 180) return false;
                const path = new URL(item.url).pathname;
                return /\\/details\\/[^/]+\\//.test(path) || /Location\\s+.+?\\s+Actions/i.test(item.text);
            }));

            const positionCards = [...document.querySelectorAll('[role="button"][aria-label][data-test-id^="position-card"], .position-card[aria-label]')];
            results.push(...positionCards.map((el, index) => {
                const title = normalize(el.getAttribute('aria-label') || el.querySelector('.position-title')?.textContent || el.textContent);
                const location = normalize(el.querySelector('[id^="position-location"]')?.textContent);
                const department = normalize(el.querySelector('[id^="position-department"]')?.textContent);
                return {
                    title,
                    url: new URL(window.location.pathname + window.location.search + `#${encodeURIComponent(title)}`, baseUrl).toString(),
                    text: normalize(`${title} ${location} ${department}`),
                    location,
                    department,
                    aria: title,
                    heading: title,
                };
            }));

            const metaJobLinks = anchors.filter((el) => {
                const href = el.getAttribute('href') || '';
                return href.includes('/profile/job_details/');
            });
            results.push(...metaJobLinks.map((el) => {
                const title = normalize(el.querySelector('h3')?.textContent || el.textContent);
                const text = normalize(el.textContent);
                const afterTitle = text.startsWith(title) ? text.slice(title.length) : text;
                const location = normalize(afterTitle.split('⋅')[0]);
                return {
                    title,
                    url: new URL(el.getAttribute('href'), baseUrl).toString(),
                    text,
                    location,
                    aria: normalize(el.getAttribute('aria-label')),
                    heading: title,
                };
            }));

            const googleJobHeadings = baseHost.includes('google.com') ? [...document.querySelectorAll('h3')]
                .filter((el) => {
                    const title = normalize(el.textContent);
                    return title && title.length <= 140;
                }) : [];
            results.push(...googleJobHeadings.map((el) => {
                const title = normalize(el.textContent);
                const card = normalize(el.closest('li, div')?.parentElement?.parentElement?.textContent || el.closest('li, div')?.parentElement?.textContent || el.parentElement?.textContent || title);
                const locationMatch = card.match(/place\\s+(.+?)\\s+bar_chart/i) || card.match(/Google\\s+\\|\\s+(.+?)\\s+Minimum qualifications/i);
                return {
                    title,
                    url: new URL(window.location.pathname + window.location.search + `#${encodeURIComponent(title)}`, baseUrl).toString(),
                    text: card,
                    location: locationMatch ? normalize(locationMatch[1]) : '',
                    aria: title,
                    heading: title,
                };
            }));

            return results;
        }""",
        base_url,
    )

    seen = set()
    normalized_cards = []
    for card in cards:
        title = clean_whitespace(card.get("title", ""))
        url = card.get("url", "")
        if not title or not url or url in seen:
            continue
        is_probable = is_probable_job_link(url, title) or is_probable_rendered_card(url, title)
        if not is_probable:
            continue
        seen.add(url)
        normalized_cards.append(
            {
                "title": title,
                "url": url,
                "location": card.get("location") or infer_card_location(card.get("text", "")),
                "text": card.get("text", ""),
            }
        )
    return normalized_cards


def is_probable_rendered_card(url: str, title: str) -> bool:
    parsed = urlparse(url)
    if not parsed.fragment:
        return False
    title_text = title.lower()
    if any(signal in title_text for signal in MARKETING_LINK_SIGNALS):
        return False
    return any(signal in title_text for signal in JOB_TITLE_SIGNALS)


def filter_rendered_cards_by_query(cards: list[dict], job_query: str) -> list[dict]:
    if not job_query.strip():
        return cards
    scored = [
        (calculate_role_relevance(card.get("title", ""), "", job_query), card)
        for card in cards
    ]
    relevant = [(score, card) for score, card in scored if score > 0]
    return [card for _, card in sorted(relevant, key=lambda item: item[0], reverse=True)]


def fetch_rendered_job_description(page, job_url: str, fallback_title: str, fallback_description: str = "") -> str:
    if "#" in job_url:
        return clean_whitespace(fallback_description or fallback_title)
    try:
        page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
        description = page.locator("main").inner_text(timeout=5000)
        return clean_whitespace(description)
    except Exception:
        try:
            html = fetch_url(job_url)
            return extract_page_text(html)
        except Exception:
            return fallback_title


def filter_jobs_by_role_query(jobs: list[DiscoveredJob], job_query: str) -> list[DiscoveredJob]:
    if not job_query.strip():
        return jobs
    relevant = [job for job in jobs if job.role_relevance > 0]
    return relevant


def filter_job_links_by_query(job_links: list[tuple[str, str]], job_query: str) -> list[tuple[str, str]]:
    if not job_query.strip():
        return job_links
    scored = [
        (calculate_role_relevance(title or infer_title_from_url(url), "", job_query), (url, title))
        for url, title in job_links
    ]
    relevant = [(score, link) for score, link in scored if score > 0]
    return [link for _, link in sorted(relevant, key=lambda item: item[0], reverse=True)]


def calculate_role_relevance(title: str, description: str, job_query: str) -> int:
    query_terms = expand_role_query(job_query)
    if not query_terms:
        return 0

    title_text = normalize_for_matching(strip_company_suffix(title))
    description_text = normalize_for_matching(description)
    query_text = normalize_for_matching(job_query)
    engineering_intent = any(term in query_text for term in {"engineering", "engineer", "software", "platform", "sre", "infrastructure"})
    ai_intent = any(term in query_text for term in {"ai", "ml", "machine learning", "llm"})

    title_is_engineering = any(term in title_text for term in ENGINEERING_TITLE_TERMS)
    if engineering_intent and not title_is_engineering:
        return 0
    if (
        engineering_intent
        and any(term in title_text for term in NON_ENGINEERING_TITLE_TERMS)
        and not any(term in title_text for term in STRONG_ENGINEERING_TITLE_TERMS)
    ):
        return 0

    if ai_intent and title_is_engineering:
        title_has_ai_signal = any(term in title_text for term in ROLE_QUERY_EXPANSIONS["ai"])
        title_has_software_signal = any(term in title_text for term in ROLE_QUERY_EXPANSIONS["software"] | ROLE_QUERY_EXPANSIONS["platform"])
        description_has_ai_signal = any(term in description_text for term in ROLE_QUERY_EXPANSIONS["ai"])
        if not (title_has_ai_signal or title_has_software_signal or description_has_ai_signal):
            return 0

    score = 0
    for term in query_terms:
        if term in title_text:
            score += 5
        elif title_is_engineering and term in description_text:
            score += 1

    if title_is_engineering:
        score += 2
    if any(ai_term in title_text for ai_term in ROLE_QUERY_EXPANSIONS["ai"]):
        score += 3

    return min(100, score * 10)


def expand_role_query(job_query: str) -> set[str]:
    normalized_query = normalize_for_matching(job_query)
    terms = {
        token
        for token in re.split(r"[,/| ]+", normalized_query)
        if len(token) >= 2
    }
    for phrase in re.split(r"[,/|]+", normalized_query):
        phrase = phrase.strip()
        if phrase:
            terms.add(phrase)

    expanded = set(terms)
    for term in terms:
        expanded.update(ROLE_QUERY_EXPANSIONS.get(term, set()))
    return expanded


def normalize_for_matching(text: str) -> str:
    return clean_whitespace(re.sub(r"[^a-z0-9+#. ]+", " ", text.lower()))


def strip_company_suffix(title: str) -> str:
    return re.sub(r"\s+@\s+.+$", "", title).strip()


def parse_company_targets(raw_targets: str, fallback_company: str = "", fallback_url: str = "") -> list[CompanyTarget]:
    targets: list[CompanyTarget] = []
    if fallback_url.strip():
        targets.append(CompanyTarget(company=fallback_company.strip() or infer_company_from_url(fallback_url), careers_url=fallback_url.strip()))

    for line in raw_targets.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if "|" in cleaned:
            company, url = [part.strip() for part in cleaned.split("|", 1)]
        elif "," in cleaned:
            company, url = [part.strip() for part in cleaned.split(",", 1)]
        else:
            company, url = infer_company_from_url(cleaned), cleaned

        if not url.startswith(("http://", "https://")):
            continue
        targets.append(CompanyTarget(company=company or infer_company_from_url(url), careers_url=url))

    deduped: dict[str, CompanyTarget] = {}
    for target in targets:
        deduped[target.careers_url] = target
    return list(deduped.values())


def extract_job_links(html: str, base_url: str) -> list[tuple[str, str]]:
    extractor = LinkExtractor()
    extractor.feed(html)
    seen = set()
    jobs: list[tuple[str, str]] = []

    for href, text in extractor.links:
        absolute_url = urljoin(base_url, href)
        if not is_probable_job_link(absolute_url, text):
            continue
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        jobs.append((absolute_url, text or infer_title_from_url(absolute_url)))

    return jobs


def extract_static_job_cards(html: str, base_url: str) -> list[dict]:
    cards: list[dict] = []
    pattern = re.compile(r'(?is)<a[^>]+href=["\'](?P<href>/careers/(?!search/)[^"\']+/)["\'][^>]*>(?P<body>.*?)</a>')
    seen = set()
    for match in pattern.finditer(html):
        url = urljoin(base_url, unescape(match.group("href")))
        if url in seen:
            continue
        body = unescape(match.group("body"))
        title_match = re.search(r"(?is)<h2[^>]*>(.*?)</h2>", body)
        if not title_match:
            continue
        spans = [
            clean_whitespace(strip_tags(span))
            for span in re.findall(r"(?is)<span[^>]*>(.*?)</span>", body)
        ]
        title = clean_whitespace(strip_tags(title_match.group(1)))
        team = spans[0] if spans else ""
        location = spans[-1] if len(spans) >= 2 else "Not specified"
        if not title or not is_probable_job_link(url, title):
            continue
        seen.add(url)
        cards.append({"title": title, "team": team, "location": location, "url": url})
    return cards


def score_static_cards(company: str, cards: list[dict], resume: dict, job_query: str = "") -> list[DiscoveredJob]:
    jobs = []
    for card in cards:
        title = card["title"]
        description = f"{title}\n{card.get('team', '')}\n{card.get('location', '')}"
        role_relevance = calculate_role_relevance(title, description, job_query)
        if job_query.strip() and role_relevance == 0:
            continue
        match = score_resume_for_job(resume, description)
        jobs.append(
            DiscoveredJob(
                company=company,
                title=title,
                location=card.get("location") or "Not specified",
                url=card["url"],
                description=description,
                match=match,
                role_relevance=role_relevance,
            )
        )
    return sorted(jobs, key=lambda job: (job.role_relevance, job.match.match_score), reverse=True)


def extract_structured_job_postings(html: str, base_url: str) -> list[dict]:
    postings: list[dict] = []
    for match in re.finditer(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html):
        raw_json = unescape(match.group(1)).strip()
        if not raw_json:
            continue
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue
        postings.extend(find_jobposting_objects(payload, base_url))
    return postings


def find_jobposting_objects(payload: object, base_url: str) -> list[dict]:
    postings: list[dict] = []
    if isinstance(payload, list):
        for item in payload:
            postings.extend(find_jobposting_objects(item, base_url))
    elif isinstance(payload, dict):
        item_type = payload.get("@type")
        item_types = item_type if isinstance(item_type, list) else [item_type]
        if "JobPosting" in item_types:
            posting = dict(payload)
            posting["url"] = urljoin(base_url, str(posting.get("url") or posting.get("sameAs") or base_url))
            postings.append(posting)
        for value in payload.values():
            if isinstance(value, (list, dict)):
                postings.extend(find_jobposting_objects(value, base_url))
    return postings


def score_structured_jobs(company: str, postings: list[dict], resume: dict, job_query: str = "") -> list[DiscoveredJob]:
    jobs = []
    for posting in postings:
        title = clean_whitespace(str(posting.get("title") or "Open Role"))
        description = extract_page_text(str(posting.get("description") or ""))
        role_relevance = calculate_role_relevance(title, description, job_query)
        if job_query.strip() and role_relevance == 0:
            continue
        location = structured_location(posting.get("jobLocation")) or structured_location(posting.get("applicantLocationRequirements")) or "Not specified"
        url = str(posting.get("url") or "")
        match = score_resume_for_job(resume, f"{title}\n{description}")
        jobs.append(
            DiscoveredJob(
                company=company,
                title=title,
                location=location,
                url=url,
                description=description,
                match=match,
                role_relevance=role_relevance,
            )
        )
    return sorted(jobs, key=lambda job: (job.role_relevance, job.match.match_score), reverse=True)


def structured_location(value: object) -> str:
    if isinstance(value, list) and value:
        return structured_location(value[0])
    if not isinstance(value, dict):
        return ""

    address = value.get("address")
    if isinstance(address, dict):
        parts = [
            address.get("addressLocality"),
            address.get("addressRegion"),
            address.get("addressCountry"),
        ]
        return clean_whitespace(", ".join(str(part) for part in parts if part))
    return clean_whitespace(str(value.get("name") or ""))


def is_probable_job_link(url: str, text: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/")
    query = parsed.query.lower()
    searchable = f"{url} {text}".lower()

    if parsed.fragment:
        return False
    if text.strip().lower() in {"apply now", "apply now (opens in a new window)", "apply"}:
        return False
    is_meta_job_detail = "/profile/job_details" in path
    if not is_meta_job_detail and any(signal in searchable for signal in MARKETING_LINK_SIGNALS):
        return False
    if path in {"", "/", "/careers", "/career", "/jobs", "/job", "/careers/search", "/search"}:
        return False

    has_role_title = any(signal in text.lower() for signal in JOB_TITLE_SIGNALS)
    has_job_detail_url = (
        "pid=" in query
        or "/careers/job" in path
        or is_meta_job_detail
        or re.search(r"/details/[a-z0-9_-]+/", path) is not None
        or (path.startswith("/careers/") and has_role_title)
        or "/careers/apply" in path
        or re.search(r"/jobs?/[a-z0-9_-]*\\d+[a-z0-9_-]*", path) is not None
        or any(host_signal in (parsed.hostname or "") for host_signal in ATS_JOB_HOST_SIGNALS)
    )

    return bool(has_job_detail_url and (has_role_title or "pid=" in query or any(signal in searchable for signal in JOB_LINK_SIGNALS)))


def extract_page_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|h1|h2|h3|section)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return clean_whitespace(unescape(text))


def strip_tags(html: str) -> str:
    return re.sub(r"(?is)<[^>]+>", " ", html)


def infer_title(html: str, link_text: str, url: str) -> str:
    for pattern in (r"(?is)<h1[^>]*>(.*?)</h1>", r"(?is)<title[^>]*>(.*?)</title>"):
        match = re.search(pattern, html)
        if match:
            title = clean_whitespace(re.sub(r"(?is)<[^>]+>", " ", unescape(match.group(1))))
            title = re.sub(r"\s+[-|]\s+.*$", "", title).strip()
            if title:
                return title[:120]
    if link_text:
        return link_text[:120]
    return infer_title_from_url(url)


def infer_title_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/").split("/")[-1]
    path = re.sub(r"[-_]+", " ", path)
    return clean_whitespace(path).title() or "Open Role"


def infer_company_from_url(url: str) -> str:
    hostname = urlparse(url).hostname or "Company"
    hostname = hostname.removeprefix("www.")
    return hostname.split(".")[0].replace("-", " ").title()


def infer_location(text: str) -> str:
    location_patterns = [
        r"\bRemote\b(?:\s*[-,]\s*[A-Za-z ]+)?",
        r"\b(?:San Francisco|New York|Seattle|Austin|Boston|Chicago|Los Angeles|London|Toronto|Vancouver)\b(?:,\s*[A-Z]{2})?",
        r"\b(?:Cupertino|Sunnyvale|San Jose|San Diego|Santa Clara|Palo Alto|Redmond)\b(?:,\s*[A-Z]{2})?",
        r"\bHybrid\b(?:\s*[-,]\s*[A-Za-z ]+)?",
    ]
    for pattern in location_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return normalize_inferred_location(match.group(0))
    return "Not specified"


def normalize_inferred_location(text: str) -> str:
    location = clean_whitespace(text)
    lowercase_state_match = re.search(r",\s*([a-z]{1,2})$", location)
    if lowercase_state_match:
        location = location[: lowercase_state_match.start()].strip()
    return location


def infer_card_location(text: str) -> str:
    match = re.search(r"JR\d+\s*(.+)$", text)
    if match:
        return clean_whitespace(normalize_location_text(match.group(1)))
    return infer_location(text)


def normalize_location_text(text: str) -> str:
    text = re.sub(r"(?<=[a-z])(?=Remote\b)", " ", text)
    text = re.sub(r"\bRemote\s+Remote\b", "Remote", text, flags=re.IGNORECASE)
    return text


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

from __future__ import annotations

import unittest

from modules.job_discovery import (
    CompanyTarget,
    DiscoveredJob,
    build_default_discovery_adapters,
    calculate_role_relevance,
    classify_careers_site,
    discovery_cache_key,
    extract_ashby_board_name,
    extract_greenhouse_board_token,
    extract_job_links,
    extract_lever_site,
    extract_network_job_cards,
    extract_smartrecruiters_company,
    extract_structured_job_postings,
    filter_rendered_cards_by_query,
    filter_job_links_by_query,
    infer_card_location,
    infer_location,
    infer_title,
    is_missing_playwright_browser_error,
    is_probable_job_link,
    is_probable_rendered_card,
    job_from_cache_record,
    job_to_cache_record,
    parse_company_targets,
)
from modules.matcher import MatchResult, ScoreBreakdown


class JobDiscoveryTests(unittest.TestCase):
    def test_default_discovery_adapters_run_from_cheapest_to_rendered_to_structured(self) -> None:
        adapters = build_default_discovery_adapters(use_rendered_fallback=True)

        self.assertEqual(
            [adapter.name for adapter in adapters],
            [
                "greenhouse_api",
                "lever_api",
                "ashby_api",
                "smartrecruiters_api",
                "static_job_cards",
                "static_job_links",
                "rendered_job_cards",
                "json_ld_job_postings",
            ],
        )

    def test_default_discovery_adapters_can_skip_rendered_discovery(self) -> None:
        adapters = build_default_discovery_adapters(use_rendered_fallback=False)

        self.assertEqual(
            [adapter.name for adapter in adapters],
            [
                "greenhouse_api",
                "lever_api",
                "ashby_api",
                "smartrecruiters_api",
                "static_job_cards",
                "static_job_links",
                "json_ld_job_postings",
            ],
        )

    def test_missing_playwright_browser_error_is_detected(self) -> None:
        error = RuntimeError("BrowserType.launch: Executable doesn't exist. Please run playwright install.")

        self.assertTrue(is_missing_playwright_browser_error(error))
        self.assertFalse(is_missing_playwright_browser_error(RuntimeError("Navigation timeout")))

    def test_public_ats_classification_prioritizes_api_adapters(self) -> None:
        classification = classify_careers_site("https://jobs.lever.co/example")
        adapters = build_default_discovery_adapters(
            use_rendered_fallback=True,
            classification=classification,
        )

        self.assertEqual(
            [adapter.name for adapter in adapters[:4]],
            ["greenhouse_api", "lever_api", "ashby_api", "smartrecruiters_api"],
        )

    def test_public_ats_token_extractors_support_common_urls(self) -> None:
        self.assertEqual(
            extract_greenhouse_board_token("https://boards.greenhouse.io/acme/jobs/123"),
            "acme",
        )
        self.assertEqual(
            extract_greenhouse_board_token("https://boards.greenhouse.io/embed/job_board?for=acme"),
            "acme",
        )
        self.assertEqual(extract_lever_site("https://jobs.lever.co/acme/123"), "acme")
        self.assertEqual(extract_ashby_board_name("https://jobs.ashbyhq.com/acme"), "acme")
        self.assertEqual(
            extract_smartrecruiters_company("https://jobs.smartrecruiters.com/Acme/123"),
            "Acme",
        )

    def test_discovery_cache_key_changes_with_query(self) -> None:
        target = CompanyTarget("Example", "https://example.com/careers")
        resume = {"summary": "Platform engineer", "skills": ["Python"]}

        first_key = discovery_cache_key(target, resume, 8, 2, True, "software engineer")
        second_key = discovery_cache_key(target, resume, 8, 2, True, "sales")

        self.assertNotEqual(first_key, second_key)

    def test_discovered_job_cache_record_round_trips_match_details(self) -> None:
        job = DiscoveredJob(
            company="Example",
            title="Senior Platform Engineer",
            location="Remote",
            url="https://example.com/jobs/1",
            description="Build Kubernetes platforms.",
            role_relevance=100,
            source_adapter="static_job_links",
            match=MatchResult(
                match_score=91,
                matching_skills=["kubernetes"],
                missing_skills=["terraform"],
                weighted_hits={"kubernetes": 4},
                seniority_match="Strong",
                recommendation="Strong fit.",
                score_breakdown=ScoreBreakdown(skills=90, leadership=80, seniority=100, domain=90, gap_penalty=5),
                matching_leadership=["architecture"],
                missing_leadership=[],
                matching_domains=["platform"],
                resume_gaps=["Add Terraform evidence."],
                semantic_score=77,
                semantic_method="token_overlap",
            ),
        )

        restored = job_from_cache_record(job_to_cache_record(job))

        self.assertEqual(restored.title, job.title)
        self.assertEqual(restored.match.match_score, 91)
        self.assertEqual(restored.match.score_breakdown.domain, 90)
        self.assertEqual(restored.match.semantic_score, 77)
        self.assertEqual(restored.match.semantic_method, "token_overlap")
        self.assertEqual(restored.source_adapter, "static_job_links")

    def test_classifier_identifies_public_ats_hosts(self) -> None:
        classification = classify_careers_site("https://boards.greenhouse.io/acme")

        self.assertEqual(classification.category, "public_ats_api")
        self.assertGreaterEqual(classification.confidence, 90)

    def test_classifier_identifies_hosted_ats_by_pid(self) -> None:
        classification = classify_careers_site(
            "https://explore.jobs.netflix.net/careers?pid=123&domain=netflix.com"
        )

        self.assertEqual(classification.category, "hosted_ats")

    def test_classifier_identifies_json_ld_job_pages(self) -> None:
        classification = classify_careers_site(
            "https://example.com/careers",
            '<script type="application/ld+json">{"@type":"JobPosting"}</script>',
        )

        self.assertEqual(classification.category, "json_ld")

    def test_classifier_identifies_custom_spa_careers_pages(self) -> None:
        classification = classify_careers_site("https://www.metacareers.com/jobsearch")

        self.assertEqual(classification.category, "custom_spa")

    def test_classification_reorders_adapters_for_rendered_sites(self) -> None:
        classification = classify_careers_site("https://www.metacareers.com/jobsearch")
        adapters = build_default_discovery_adapters(
            use_rendered_fallback=True,
            classification=classification,
        )

        self.assertEqual(adapters[0].name, "rendered_job_cards")

    def test_parse_company_targets_supports_single_and_list_inputs(self) -> None:
        targets = parse_company_targets(
            "OpenAI | https://openai.com/careers\nAnthropic, https://www.anthropic.com/careers",
            fallback_company="Example",
            fallback_url="https://example.com/jobs",
        )

        self.assertEqual(len(targets), 3)
        self.assertEqual(targets[0].company, "Example")
        self.assertEqual(targets[1].company, "OpenAI")
        self.assertEqual(targets[2].company, "Anthropic")

    def test_extract_job_links_filters_likely_job_links(self) -> None:
        html = """
        <a href="/about">About</a>
        <a href="/careers/job/software-engineer-123">Senior Software Engineer</a>
        <a href="https://boards.greenhouse.io/acme/jobs/123">AI Platform Engineer</a>
        <a href="https://www.metacareers.com/profile/job_details/123">Software Engineer, Infrastructure</a>
        <a href="https://jobs.apple.com/en-us/details/200665933/os-performance-tools-engineer">OS Performance Tools Engineer</a>
        <a href="/jobs/listing/backend-engineer-ai-security/7826765">Backend Engineer, AI Security</a>
        """

        links = extract_job_links(html, "https://example.com")

        self.assertEqual(len(links), 5)
        self.assertEqual(links[0][0], "https://example.com/careers/job/software-engineer-123")
        self.assertIn("greenhouse", links[1][0])
        self.assertIn("metacareers", links[2][0])
        self.assertIn("jobs.apple.com", links[3][0])
        self.assertEqual(links[4][0], "https://example.com/jobs/listing/backend-engineer-ai-security/7826765")

    def test_probable_job_link_accepts_stripe_listing_urls(self) -> None:
        self.assertTrue(
            is_probable_job_link(
                "https://stripe.com/jobs/listing/backend-engineer-ai-security/7826765",
                "Backend Engineer, AI Security",
            )
        )

    def test_extract_job_links_rejects_marketing_careers_pages(self) -> None:
        html = """
        <a href="https://jobs.nvidia.com/careers">Careers at NVIDIA Corporation</a>
        <a href="https://www.nvidia.com/en-us/about-nvidia/careers/">Like No Place You’ve Ever Worked</a>
        <a href="https://www.nvidia.com/en-us/about-nvidia/careers/inclusion/">Inclusion, and Belonging</a>
        <a href="https://www.nvidia.com/en-us/about-nvidia/careers/how-we-hire/">Want to Be an NVIDIAN?</a>
        """

        self.assertEqual(extract_job_links(html, "https://jobs.nvidia.com/careers"), [])

    def test_filter_job_links_by_query_prefers_engineering_roles(self) -> None:
        links = [
            ("https://jobs.example.com/1", "Abuse Investigator"),
            ("https://jobs.example.com/2", "Account Director"),
            ("https://jobs.example.com/3", "Software Engineer, Applied AI"),
            ("https://jobs.example.com/4", "Platform Engineer"),
        ]

        filtered = filter_job_links_by_query(links, "AI engineering")

        self.assertEqual([title for _, title in filtered], ["Software Engineer, Applied AI", "Platform Engineer"])

    def test_calculate_role_relevance_scores_target_roles(self) -> None:
        engineering_score = calculate_role_relevance("Software Engineer, Applied AI", "", "AI engineering")
        sales_score = calculate_role_relevance("Account Director, Digital Native", "", "AI engineering")
        accounting_score = calculate_role_relevance("Infrastructure Accounting Manager", "", "AI engineering")

        self.assertGreater(engineering_score, sales_score)
        self.assertEqual(sales_score, 0)
        self.assertEqual(accounting_score, 0)

    def test_rendered_card_filter_keeps_search_results_with_job_title_fragments(self) -> None:
        self.assertTrue(
            is_probable_rendered_card(
                "https://www.google.com/about/careers/applications/jobs/results#Software%20Engineer%20III",
                "Software Engineer III, AI Infrastructure",
            )
        )
        self.assertFalse(
            is_probable_rendered_card(
                "https://www.nvidia.com/en-us/about-nvidia/careers/#life",
                "NVIDIA Life",
            )
        )

    def test_filter_rendered_cards_by_query_prefers_engineering_cards(self) -> None:
        cards = [
            {"title": "Manager, Physical Identity Access Management", "url": "https://example.com#manager"},
            {"title": "Software Engineer 5 - Ads Audience Activation", "url": "https://example.com#software"},
            {"title": "Software Engineer III, AI Infrastructure", "url": "https://example.com#ai"},
        ]

        filtered = filter_rendered_cards_by_query(cards, "AI engineering, software engineer, platform engineer")

        filtered_titles = [card["title"] for card in filtered]
        self.assertNotIn("Manager, Physical Identity Access Management", filtered_titles)
        self.assertCountEqual(
            filtered_titles,
            ["Software Engineer III, AI Infrastructure", "Software Engineer 5 - Ads Audience Activation"],
        )

    def test_extract_network_job_cards_reads_nested_job_payloads(self) -> None:
        payloads = [
            {
                "data": {
                    "positions": [
                        {
                            "jobTitle": "Senior Platform Engineer",
                            "jobId": "123",
                            "location": {"city": "San Francisco", "state": "CA"},
                            "description": "<p>Build developer infrastructure.</p>",
                        },
                        {
                            "title": "Careers Home",
                            "url": "/careers",
                        },
                    ]
                }
            }
        ]

        cards = extract_network_job_cards(payloads, "https://jobs.example.com/careers")

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["title"], "Senior Platform Engineer")
        self.assertEqual(cards[0]["location"], "San Francisco, CA")
        self.assertEqual(cards[0]["url"], "https://jobs.example.com/careers#123")

    def test_infer_card_location_normalizes_eightfold_remote_spacing(self) -> None:
        location = infer_card_location(
            "Senior System Software Engineer JR12345 Vietnam, Hanoi + 1 moreRemote Remote"
        )

        self.assertEqual(location, "Vietnam, Hanoi + 1 more Remote")

    def test_infer_location_recognizes_common_tech_hubs(self) -> None:
        self.assertEqual(infer_location("Location Sunnyvale Actions"), "Sunnyvale")
        self.assertEqual(infer_location("Location Cupertino Actions"), "Cupertino")
        self.assertEqual(infer_location("reasonable accommodation in San Francisco, re"), "San Francisco")

    def test_extract_structured_job_postings_reads_json_ld(self) -> None:
        html = """
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "Staff Platform Engineer",
          "description": "Build Kubernetes infrastructure.",
          "url": "/jobs/staff-platform-engineer",
          "jobLocation": {
            "@type": "Place",
            "address": {
              "@type": "PostalAddress",
              "addressLocality": "San Francisco",
              "addressRegion": "CA",
              "addressCountry": "US"
            }
          }
        }
        </script>
        """

        postings = extract_structured_job_postings(html, "https://example.com/careers")

        self.assertEqual(len(postings), 1)
        self.assertEqual(postings[0]["title"], "Staff Platform Engineer")
        self.assertEqual(postings[0]["url"], "https://example.com/jobs/staff-platform-engineer")

    def test_infer_title_prefers_h1(self) -> None:
        title = infer_title("<html><h1>Staff AI Engineer</h1><title>Other</title></html>", "Link Text", "https://example.com/jobs/1")

        self.assertEqual(title, "Staff AI Engineer")


if __name__ == "__main__":
    unittest.main()

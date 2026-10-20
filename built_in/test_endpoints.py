"""Live endpoint smoke tests: one call per /built-in/* route against a running
service, with example values proven to return data (2026-10-19). The
listing tooling reads each route's FIRST call from this file's AST as its
working example, so the values stay literals.

Skipped unless BUILT_IN_BASE points at a running service:

    ONLY_SCRAPER=built-in python run.py
    BUILT_IN_BASE=http://127.0.0.1:6002 python -m pytest built_in/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("BUILT_IN_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set BUILT_IN_BASE to run live endpoint tests")


def call(path, status=200, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=180)
    assert resp.status_code == status, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def _live_job():
    """A fresh posting for the slug/id form checks."""
    found = call("/built-in/jobs/search", query="software engineer", location="chicago")
    return found["jobs"][0]


def test_jobs_search():
    page = call("/built-in/jobs/search", query="software engineer", location="San Francisco, CA", work_mode="remote,hybrid", experience="senior", posted_within="30d")
    assert len(page["jobs"]) >= 10 and page["total_pages"] >= 2 and page["next"] and page["estimated_count"]
    first = page["jobs"][0]
    assert first["id"] and first["link"].startswith("https://builtin.com/job/") and first["company"]["alias"]
    assert page["applied"]["work_modes"] == ["remote", "hybrid"] and page["applied"]["experience_levels"] == ["senior"]
    assert page["applied"]["city"] == "San Francisco" and page["applied"]["posted_within"] == "30d" and page["skill_facets"]
    # any place name resolves through the site's own lookup; another country board
    berlin = call("/built-in/jobs/search", query="python", location="Berlin")
    assert berlin["applied"]["country"] == "DEU" and berlin["applied"]["location_resolved"]["city"] == "Berlin"
    gb = call("/built-in/jobs/search", query="data scientist", country="GB")
    assert gb["applied"]["country"] == "GBR" and gb["jobs"]
    # a builtin.com board link as the query carries its own filters
    linked = call("/built-in/jobs/search", query="https://builtin.com/jobs/remote/chicago/engineering?search=python")
    assert linked["applied"]["query"] == "python" and linked["applied"]["work_modes"] == ["remote"] and linked["applied"]["category"] == "engineering"
    # company scope, category + subcategory + radius, empty result
    stripe = call("/built-in/jobs/search", company="stripe")
    assert stripe["applied"]["company_id"] == 84805 and stripe["jobs"]
    austin = call("/built-in/jobs/search", location="Austin, TX", category="engineering", subcategory="software-engineering", radius_miles=25)
    assert austin["applied"]["subcategories"] == ["software-engineering"] and austin["applied"]["radius_miles"] == 25
    assert call("/built-in/jobs/search", query="zzzzqqqqxxxx")["jobs"] == []
    call("/built-in/jobs/search", status=400, query="x", industry="spaceships")


def test_jobs_details():
    body = call("/built-in/jobs/details", job="https://builtin.com/job/software-engineer-l5-traffic-engineering/11527168")
    record = body["job"]
    assert record["id"] == 11527168 and record["company"]["alias"] == "netflix" and record["salary"]["currency"] == "USD"
    assert record["description_html"] and record["description_text"] and record["skills_required"] and record["benefits"]
    assert record["posted_at"] and record["apply"]["type"] and record["similar_jobs"]
    job = _live_job()
    by_slug = call("/built-in/jobs/details", job=f"{job['slug']}/{job['id']}")
    assert by_slug["job"]["id"] == job["id"]
    call("/built-in/jobs/details", status=400, job=str(job["id"]))
    call("/built-in/jobs/details", status=404, job="no-such-job/1")


def test_jobs_filters():
    body = call("/built-in/jobs/filters")
    assert len(body["categories"]) >= 16 and body["categories"][0]["subcategories"] and len(body["industries"]) >= 100
    assert len(body["metros"]) >= 80 and "senior" in [e["name"] for e in body["experience_levels"]]


def test_companies_search_and_details():
    body = call("/built-in/companies/details", company="coinbase")
    company = body["company"]
    assert company["alias"] == "coinbase" and company["website"] and company["employees_count"] > 1000 and company["open_jobs_count"]
    assert company["technologies"] and company["benefits"]["perks_count"] > 20 and company["benefits"]["sections"][0]["categories"][0]["perks"]
    assert company["office_locations"] and company["recent_jobs"] and company["industries"] and company["gallery"]
    assert company["employee_reviews"] and company["insiders"]
    hits = call("/built-in/companies/search", query="openai")
    assert hits["companies"][0]["name"] == "OpenAI"
    atlassian = call("/built-in/companies/details", company="atlassian")["company"]
    assert atlassian["id"] == 81667 and atlassian["teams"] and any(o["is_headquarters"] for o in atlassian["office_locations"])
    hubspot = call("/built-in/companies/details", company="hubspot")["company"]
    assert hubspot["name"] == "HubSpot"     # its hasRemoteJobs field 500s server-side; the rest must still come through
    by_id = call("/built-in/companies/details", company="84805", include="offices")["company"]
    assert by_id["alias"] == "stripe" and by_id["benefits"] is None and by_id["office_locations"]
    by_link = call("/built-in/companies/details", company="https://builtin.com/company/stripe/jobs")["company"]
    assert by_link["id"] == 84805 and by_link["ats"]["type"] == "greenhouse"
    call("/built-in/companies/details", status=404, company="no-such-company-zzz")


def test_companies_list_and_filters():
    page = call("/built-in/companies/list", location="chicago", industry="fintech", company_size="51-200")
    assert len(page["companies"]) == 20 and page["total_pages"] >= 2 and page["next"]
    assert page["applied"]["industries"] == ["fintech"] and page["applied"]["company_sizes"] == ["51-200"] and page["applied"]["city"] == "Chicago"
    first = page["companies"][0]
    assert first["id"] and first["alias"] and first["link"] and first["employees_count"]
    remote = call("/built-in/companies/list", hiring_remote="true", perk="401k")
    assert remote["companies"] and remote["applied"]["perks"] == ["401k"]
    filters = call("/built-in/companies/filters")
    assert len(filters["perks"]) >= 80 and len(filters["tech_stacks"]) >= 200


def test_companies_insights_articles_jobs():
    insights = call("/built-in/companies/insights", company="netflix", topic="compensation_benefits")
    assert insights["title"] == "Netflix Compensation & Benefits" and insights["key_insight"] and insights["positive_themes"] and insights["considerations"]
    articles = call("/built-in/companies/articles", company="netflix", per_page=5)
    assert articles["count"] >= 20 and len(articles["articles"]) == 5 and articles["articles"][0]["link"].startswith("https://builtin.com/articles/")
    jobs = call("/built-in/companies/jobs", company="openai", work_mode="remote")
    assert jobs["applied"]["company_id"] and jobs["jobs"] and jobs["next"]
    paged = call("/built-in/companies/jobs", company="atlassian", work_mode="remote", page=2)
    assert paged["applied"]["company_id"] == 81667 and paged["current_page"] == 2 and paged["jobs"] and paged["previous"]


def test_salaries():
    metro = call("/built-in/salaries/title", title="Software Engineer", location="San Francisco, CA")
    assert metro["location"] == "San Francisco, CA" and metro["base"]["average"] > 100000 and metro["base"]["percentiles"]["p90"]
    assert metro["by_gender"]["women_average"] and metro["by_experience"] and metro["related_titles"]["rows"]
    national = call("/built-in/salaries/title", title="product-manager")
    assert national["location"] == "United States" and national["best_paying_cities"]["rows"] and national["recent_reports"]
    location = call("/built-in/salaries/location", location="San Francisco, CA")
    assert location["by_category"] and location["titles_count"] > 100
    filters = call("/built-in/salaries/filters")
    assert len(filters["titles"]) > 150 and len(filters["locations"]) > 50
    call("/built-in/salaries/title", status=404, title="astronaut")


def test_articles():
    body = call("/built-in/articles/details", article="https://builtin.com/articles/tech-companies-with-best-benefits")
    assert body["article"]["title"] == "60 Tech Companies With the Best Benefits" and len(body["article"]["body_text"]) > 10000
    assert len(body["article"]["companies"]) >= 50 and body["article"]["headings"]
    news = call("/built-in/articles/details", article="yext-acquires-hearsay-systems-20240613")
    assert news["article"]["companies"][0]["alias"] == "yext"
    latest = call("/built-in/articles/latest", per_page=3)
    assert latest["count"] > 10000 and len(latest["articles"]) == 3
    call("/built-in/articles/details", status=404, article="no-such-article-zzz")


def test_suggest():
    places = call("/built-in/locations/suggest", query="San Francisco", resolve="true")
    assert places["locations"][0]["label"].startswith("San Francisco") and places["locations"][0]["place"]["country"] == "USA"
    titles = call("/built-in/job-titles/suggest", query="machine learning")
    assert titles["titles"] and all(isinstance(t, str) for t in titles["titles"])

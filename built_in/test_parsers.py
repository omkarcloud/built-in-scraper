"""Offline tests: ref parsing, the request schemas and the normalizers
against raw builtin.com pages captured 2026-10-19 (built_in/fixtures/; the
HTML is stripped of scripts, styles and SVG except the Builtin.*Init and
JSON-LD scripts the parsers read).

    python -m pytest built_in/test_parsers.py -q
"""
import json
import os

import pytest
from marshmallow import ValidationError

from built_in import fetch, parsers as P, refdata, refs, schemas
from built_in.jobs import search_path, upstream_params

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def page(name):
    with open(os.path.join(FIX, name + ".html"), encoding="utf-8") as f:
        return f.read()


def fx(name):
    with open(os.path.join(FIX, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _no_camel_or_url_keys(obj, path="$"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert key == key.lower() and " " not in key, f"{path}.{key} not snake_case"
            assert "url" not in key, f"{path}.{key} should be a *link"
            _no_camel_or_url_keys(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            _no_camel_or_url_keys(value, f"{path}[{i}]")


# ---- refs -----------------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("https://builtin.com/job/senior-software-engineer/11741949", {"id": "11741949", "slug": "senior-software-engineer"}),
    ("builtin.com/job/x-y/5?ref=abc", {"id": "5", "slug": "x-y"}),
    ("senior-software-engineer/11741949", {"id": "11741949", "slug": "senior-software-engineer"}),
    ("/job/senior-software-engineer/11741949", {"id": "11741949", "slug": "senior-software-engineer"}),
])
def test_resolve_job(value, expected):
    assert refs.resolve_job(value) == expected


@pytest.mark.parametrize("value", ["", "11741949", "https://www.indeed.com/job/x/1", "https://builtin.com/jobs/remote", "abc"])
def test_resolve_job_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_job(value)


@pytest.mark.parametrize("value, expected", [
    ("stripe", {"alias": "stripe", "id": None}),
    ("/company/Stripe", {"alias": "stripe", "id": None}),
    ("https://builtin.com/company/stripe/jobs", {"alias": "stripe", "id": None}),
    ("84805", {"alias": None, "id": 84805}),
])
def test_resolve_company(value, expected):
    assert refs.resolve_company(value) == expected


def test_resolve_article():
    assert refs.resolve_article("https://builtin.com/articles/yext-acquires-hearsay-systems-20240613") == "yext-acquires-hearsay-systems-20240613"
    assert refs.resolve_article("yext-acquires-hearsay-systems-20240613") == "yext-acquires-hearsay-systems-20240613"
    with pytest.raises(ValueError):
        refs.resolve_article("https://builtin.com/company/stripe")


def test_parse_search_link():
    link = refs.parse_search_link("https://builtin.com/jobs/remote/hybrid/chicago/engineering/software-engineering/senior/fintech/51-200"
                                  "?search=python&daysSinceUpdated=7&companyId=84805&skills=aws,sql&page=2&searcharea=25mi")
    assert link["work_modes"] == ["remote", "hybrid"] and link["location"] == "chicago"
    assert link["category"] == "engineering" and link["subcategory"] == "software-engineering"
    assert link["experience"] == "senior" and link["industry"] == "fintech" and link["company_size"] == "51-200"
    assert link["query"] == "python" and link["posted_within"] == "7d" and link["company_id"] == 84805
    assert link["skills"] == ["aws", "sql"] and link["page"] == 2 and link["radius_miles"] == 25
    legacy = refs.parse_search_link("https://builtin.com/jobs/eu/germany/dev-engineering/search/python")
    assert legacy["country"] == "DEU" and legacy["query"] == "python" and legacy["extra_segments"] == ["dev-engineering"]
    with pytest.raises(ValueError):
        refs.parse_search_link("https://builtin.com/company/stripe")


# ---- refdata ----------------------------------------------------------------------------

def test_refdata_lookups():
    assert refdata.category("Engineering")["id"] == 8
    assert refdata.subcategory("software-engineering")[1]["id"] == 58
    assert refdata.subcategory("Data Science")[0]["alias"] == "ai-machine-learning"
    assert refdata.industry("Fintech")["alias"] == "fintech"
    assert refdata.metro("New York, NY")["alias"] == "new-york-city" and refdata.metro("chicago")["state_code"] == "IL"
    assert refdata.alpha3("us") == "USA" and refdata.alpha3("GBR") == "GBR" and refdata.alpha2("DEU") == "DE"
    assert refdata.experience_public("Senior level") == "senior" and refdata.experience_public("Expert/Leader") == "expert_leader"
    assert refdata.experience_public("Entry Level (0-1 Years)") == "entry_level"


# ---- schemas ----------------------------------------------------------------------------

def test_job_search_schema():
    data = schemas.JobSearchSchema().load({"query": "python", "location": "chicago", "work_mode": "remote,hybrid", "experience": "senior",
                                           "industry": "Fintech", "country": "gb", "posted_within": "7d", "radius_miles": "25", "page": "2"})
    assert data["country"] == "GBR" and data["work_mode"] == ["remote", "hybrid"] and data["industry"] == "fintech"
    assert data["radius_miles"] == 25 and data["page"] == 2
    with pytest.raises(ValidationError):
        schemas.JobSearchSchema().load({"industry": "spaceships"})
    with pytest.raises(ValidationError):
        schemas.JobSearchSchema().load({"radius_miles": "25"})      # radius needs a location
    with pytest.raises(ValidationError):
        schemas.JobSearchSchema().load({"query": "x", "bogus": "1"})
    with pytest.raises(ValidationError):
        schemas.JobSchema().load({"job": "11741949"})


def test_search_path_and_params():
    kw = {"query": "python", "location": "chicago", "work_mode": ["remote", "hybrid"], "category": "engineering",
          "subcategory": "software-engineering", "experience": "senior", "industry": "fintech", "company_size": "51-200",
          "posted_within": "7d", "skills": ["aws"], "radius_miles": 25, "early_applicant": True, "page": 2, "country": "USA"}
    path, metro = search_path(kw)
    assert path == "/jobs/remote/hybrid/chicago/engineering/software-engineering/senior/fintech/51-200"
    params = upstream_params(kw, metro, None, None)
    assert params["search"] == "python" and params["daysSinceUpdated"] == 7 and params["searcharea"] == "25mi"
    assert params["earlyApplicant"] is True and params["page"] == 2 and params["country"] == "USA"
    params = upstream_params({"query": None, "page": 1}, None, None, 84805)
    assert params["companyId"] == 84805 and params["allLocations"] is True and "country" not in params


# ---- job board ------------------------------------------------------------------------------

def test_job_cards():
    html = page("job_board")
    cards = P.job_cards(html)
    assert len(cards) == 12 and P.last_page(html) == 361
    first = cards[0]
    _no_camel_or_url_keys(cards)
    assert first["id"] == 8570204 and first["link"] == "https://builtin.com/job/senior-software-engineer/8570204"
    assert first["company"]["alias"] == "circle" and first["company"]["logo"].startswith("https://")
    assert first["salary"] == {"min": 153000, "max": 205000, "period": "annual", "currency": None, "text": "153K-205K Annually"}
    assert first["work_modes"] == ["in_office", "remote"] and first["experience_level"] == "senior"
    assert len(first["locations"]) == 12 and "Chicago, IL, USA" in first["locations"]
    assert first["industries"][:2] == ["Blockchain", "Fintech"] and first["top_skills"] and first["summary"]
    assert first["is_reposted"] is True and first["posted_at"]
    assert any(c["is_easy_apply"] for c in cards)
    init = fetch.embedded_init(html, "jobBoardInit")
    applied = P.applied_criteria(init["criteria"])
    assert applied["work_modes"] == ["remote"] and applied["category"] == "engineering"
    assert applied["subcategories"] == ["software-engineering"] and applied["city"] == "Chicago"
    assert P.skill_facets(init)[0]["skill"] == "Python"


def test_empty_partial():
    html = page("search_partial_empty")
    assert P.job_cards(html) == [] and P.last_page(html) == 0


def test_job_page():
    html = page("job_page")
    job = P.job_page(html, slug="data-scientist-intern-2027-summer-u-s", job_id="11345450",
                     init=fetch.embedded_init(html, "jobPostInit"), ld=fetch.ld_node(html, "JobPosting"))
    _no_camel_or_url_keys(job)
    assert job["id"] == 11345450 and job["title"] == "Data Scientist Intern, 2027 Summer U.S."
    assert job["company"]["name"] == "Atlassian" and job["company"]["alias"] == "atlassian"
    assert job["company"]["hq"] == "San Francisco, CA" and job["company"]["employees_count"] == 11000 and job["company"]["year_founded"] == 2012
    assert job["company"]["what_we_do"] and job["company"]["why_work_with_us"] and len(job["company"]["gallery"]) == 10
    assert job["company"]["teams"][0]["name"] == "Product + Tech" and job["company"]["workplace"]["type"] == "Remote Workspace"
    assert any(o["is_headquarters"] for o in job["company"]["offices"])
    assert job["employment_type"] == "INTERN" and job["valid_through"] == "2026-11-18T08:17:58Z"
    assert job["salary"] == {"min": 39, "max": 53, "period": "hourly", "currency": "USD", "text": "39-53 Hourly"}
    assert job["experience_level"] == "internship" and job["work_modes"] == ["in_office"] and job["locations"] == ["Seattle, WA, USA"]
    assert job["location_addresses"][0]["city"] == "Seattle" and job["applicant_countries"] == ["USA"]
    assert job["summary"].startswith("Conduct statistical analysis") and job["description_html"] and job["description_text"]
    assert len(job["skills_required"]) == 10 and len(job["benefits"]) > 50
    assert job["benefits_highlights"][0]["title"] == "Parental & Family Support"
    assert {i["topic"] for i in job["insights"]} >= {"compensation-benefits", "culture-values"}
    assert len(job["team_quotes"]) == 6 and job["team_quotes"][0]["name"] == "Tiffany" and job["team_quotes"][0]["quote"]
    assert job["apply"]["type"] == "on_site_login" and job["apply"]["requires_login"] is True
    assert len(job["similar_jobs"]) == 4 and job["similar_jobs"][0]["company"]["alias"] == "atlassian"
    assert job["similar_jobs"][0]["work_modes"] == ["in_office", "remote"]


def test_job_page_remote_two_countries():
    html = page("job_page_remote")
    job = P.job_page(html, slug="junior-software-engineer", job_id="11741949",
                     init=fetch.embedded_init(html, "jobPostInit"), ld=fetch.ld_node(html, "JobPosting"))
    assert job["locations"] == ["India", "United States"] and job["is_remote_eligible"] is True
    assert job["salary"]["period"] == "hourly" and job["salary"]["min"] == 150
    assert job["experience_level"] == "junior" and job["company"]["name"] == "Weekday, Inc."


# ---- companies -------------------------------------------------------------------------------

def test_company_header_and_tabs():
    header = P.company_header(page("company_profile"))
    assert header["name"] == "Stripe" and header["hq"] == "San Francisco" and header["offices_count"] == 9
    assert header["employees_count"] == 5360 and header["year_founded"] == 2010
    assert header["website"] == "https://stripe.com" and header["jobs_count"] == 570 and "Dublin" in header["office_names"]
    benefits = P.benefits_tab(page("tab_benefits"))
    assert benefits["perks_count"] == 104 and benefits["sections"][0]["name"] == "Compensation & Benefits"
    assert "Offers 401(K)" in benefits["sections"][0]["categories"][0]["perks"]
    offices = P.offices_tab(page("tab_offices"))
    assert offices["offices_count"] == 17 and offices["headquarters"] == "San Francisco"
    hq = next(o for o in offices["offices"] if o["is_headquarters"])
    assert hq["city"] == "San Francisco" and hq["country"] == "USA" and hq["address"].startswith("350 Bush St")
    assert offices["workplace"]["type"] == "Remote Workplace"
    teams = P.teams_tab(page("tab_teams"))
    assert [t["name"] for t in teams] == ["Product + Tech", "Atlassian Data Science Team"] and teams[0]["image"]
    overview = P.company_overview(page("tab_overview"))
    assert overview["company_id"] == 81667 and overview["industries"][0]["name"] == "Cloud"
    assert overview["tagline"].startswith("Atlassian provides") and overview["description"] and overview["gallery"] and overview["videos"]
    assert overview["recent_jobs"][0]["id"] and overview["recent_jobs"][0]["work_modes"]
    _no_camel_or_url_keys([header, benefits, offices, teams, overview])


def test_graphql_company():
    company = P.graphql_company(fx("graphql_company"))
    _no_camel_or_url_keys(company)
    assert company["id"] == 84805 and company["alias"] == "stripe" and company["link"] == "https://builtin.com/company/stripe"
    assert company["employees_count"] == 5360 and company["year_founded"] == 2010 and company["perks_count"] == 33
    assert company["offices"][0] == {"city": "San Francisco", "state": "CA", "country": "US", "postal_code": "94103", "street": "510 Townsend St",
                                     "street_2": None, "is_headquarters": True, "neighborhood_description": None, "nearest_market_id": 8}
    assert company["ats"]["type"] == "greenhouse" and company["industries"][0]["name"] == "Payments"
    assert company["employee_reviews"] == [] and company["insiders"] is None and company["funding"] == []
    assert company["last_updated"] == "2026-08-27T16:38:41Z"


def test_faq_and_directory():
    faq = P.faq_page(page("company_faq"), topic="compensation-benefits")
    assert faq["title"] == "Stripe Compensation & Benefits" and faq["updated_on"] == "2026-08-27"
    assert faq["question"].startswith("How are") and faq["key_insight"] and len(faq["evidence"]) == 2
    assert faq["positive_themes"][0]["title"] == "Healthcare Strength" and len(faq["considerations"]) == 3
    assert len(faq["related_insights"]) == 6
    html = page("directory")
    cards = P.directory_cards(html)
    assert len(cards) == 20 and P.last_page(html) == 500
    first = cards[0]
    assert first["id"] == 64688 and first["alias"] == "farmers-dog" and first["industries"] == ["eCommerce", "Food", "Pet"]
    assert first["offices_count"] == 3 and first["employees_count"] == 800 and first["benefits_count"] == 43 and first["is_hiring"] is True
    crit = P.directory_criteria(fetch.embedded_init(html, "companyDirectoryInit"))
    assert crit["page"] == 2 and crit["per_page"] == 20
    _no_camel_or_url_keys([faq, cards])


# ---- salaries / articles ---------------------------------------------------------------------

def test_salary_pages():
    metro = P.salary_page(page("salary_title_metro"), title_slug="software-engineer", location_slug="chicago-il")
    _no_camel_or_url_keys(metro)
    assert metro["location"] == "Chicago, IL" and metro["base"]["average"] == 133404 and metro["base"]["median"] == 134000
    assert metro["base"]["percentiles"] == {"p10": 78800, "p25": 104000, "p75": 188000, "p90": 213200}
    assert metro["additional_cash_average"] == 28563 and metro["total_compensation_average"] == 161967
    assert metro["by_gender"] == {"women_average": 141933, "men_average": 127180}
    assert metro["by_experience"] == [{"experience": "7+ years", "average": 157943}, {"experience": "<1 year", "average": 122375}]
    assert metro["most_common_range"] == {"min": 130000, "max": 140000}
    assert metro["related_titles"]["rows"][0] == {"title": "Test Engineer", "link": "https://builtin.com/salaries/engineering/test-engineer/chicago-il",
                                                  "average": 67981, "min": 29000, "max": 90000}
    national = P.salary_page(page("salary_title"), title_slug="software-engineer")
    assert national["location"] == "United States" and national["base"]["average"] == 139721
    assert national["best_paying_cities"]["rows"][0]["location"] == "San Francisco, CA" and national["best_paying_cities"]["rows"][0]["vs_national_percent"] == 33
    assert national["related_titles"]["rows"][0]["title"] == "Wordpress Developer"
    assert national["top_skills"][0] == {"rank": 1, "skill": "Javascript", "share_percent": 3}
    assert national["by_company_size"] == {"best_paying_size": "201-500", "average": 123437}
    assert national["recent_reports"][0]["salary"] == 129000 and national["recent_reports"][0]["location"] == "Seattle, WA"
    assert national["taxonomy"]["title_id"] == 1000139 and len(national["faq"]) == 3
    location = P.salary_location_page(page("salary_location"), location_slug="chicago-il")
    assert location["location"] == "Chicago, IL" and location["by_category"][0] == {"category": "Engineering", "average": 139866, "jobs_link": "https://builtin.com/jobs/dev-engineering"}
    assert location["titles_by_category"][0]["category"] == "Data & Analytics" and location["titles_count"] > 100
    filters = P.salary_filters(page("salary_index"))
    assert len(filters["categories"]) == 18 and len(filters["titles"]) == 199 and len(filters["locations"]) == 59


def test_article_page():
    html = page("article")
    article = P.article_page(html, slug="yext-acquires-hearsay-systems-20240613", ld=fetch.ld_node(html, "Article") or fetch.ld_node(html, "NewsArticle"))
    _no_camel_or_url_keys(article)
    assert article["id"] == 53600 and article["title"].startswith("Yext Announces") and article["published_at"] == "2024-06-13T17:21:34Z"
    assert article["author"]["name"] == "Built In Staff, With AI" and article["image"] and article["image_caption"] == "Image: Shutterstock"
    assert article["body_html"].startswith("<p>") and article["body_text"].startswith("Yext, a company")
    assert article["companies"][0] == {"name": "Yext", "alias": "yext", "link": "https://builtin.com/company/yext", "open_jobs_count": 23}


# ---- value helpers ------------------------------------------------------------------------------

def test_value_helpers():
    assert P.salary_text("174K-274K Annually") == {"min": 174000, "max": 274000, "period": "annual", "currency": None, "text": "174K-274K Annually"}
    assert P.salary_text("39-53 Hourly")["period"] == "hourly" and P.salary_text("Not disclosed") is None
    assert P.work_modes("In-Office or Remote") == ["in_office", "remote"] and P.work_modes("Hybrid") == ["hybrid"]
    assert P.relative_time("Reposted 8 Days Ago")[1] is True and P.relative_time("An Hour Ago")[0].endswith("Z")
    assert P.tooltip_items("<div class='x'>India</div><div class='x'>United States</div>") == ["India", "United States"]
    assert P.tooltip_items("San Francisco<br/>Chicago (2)") == ["San Francisco", "Chicago (2)"]
    assert P.human_date("Published on Jun. 13, 2024") == "2024-06-13" and P.human_date("Updated on August 27, 2026") == "2026-08-27"
    assert P.unique_images(["https://cdn.builtin.com/cdn-cgi/image/w=1/sites/a.png", "https://cdn.builtin.com/cdn-cgi/image/w=2/sites/a.png"]) == ["https://cdn.builtin.com/cdn-cgi/image/w=1/sites/a.png"]


def test_article_card_and_salary_us_row():
    html = page("article")
    ld = fetch.ld_node(html, "Article") or fetch.ld_node(html, "NewsArticle")
    row = {"id": 53600, "title": "Yext Announces $125M Acquisition of Hearsay Systems",
           "alias": "https://builtin.com/articles/yext-acquires-hearsay-systems-20240613", "subTitle": None, "createdAt": None}
    card = P.article_card(row, ld)
    _no_camel_or_url_keys(card)
    assert card["slug"] == "yext-acquires-hearsay-systems-20240613" and card["published_at"] == "2024-06-13T17:21:34Z"
    assert card["author"]["name"] and card["image"].startswith("https://") and card["subtitle"]
    bare = P.article_card(row, None)
    assert bare["title"] and bare["published_at"] is None and bare["author"] == {"name": None, "link": None}
    us = P.salary_filters(page("salary_index"))["locations"][0]
    assert us["name"] == "US" and us["slug"] is None and us["link"] == "https://builtin.com/salaries"


def test_job_page_never_borrows_from_similar_jobs():
    """The job's div#id wraps the whole page, similar jobs included: a job
    with one industry (no "•" line) or no salary must not pick up another
    job's values from further down the page."""
    html = page("job_page_single_industry")
    job = P.job_page(html, slug="software-engineer-l5-traffic-engineering", job_id="11527168",
                     init=fetch.embedded_init(html, "jobPostInit"), ld=fetch.ld_node(html, "JobPosting"))
    assert job["company"]["name"] == "Netflix" and job["company"]["industries"] == ["News + Entertainment"]
    assert job["salary"]["min"] == 388000 and job["location"] == "Los Gatos, CA, USA"
    html = page("job_page_no_salary")
    job = P.job_page(html, slug="software-engineer-iii-python-full-stack-developer", job_id="11766329",
                     init=fetch.embedded_init(html, "jobPostInit"), ld=fetch.ld_node(html, "JobPosting"))
    assert job["company"]["name"] == "JPMorganChase" and job["salary"] is None
    assert job["location"] == "Plano, TX, USA" and job["work_mode_text"] == "Hybrid"

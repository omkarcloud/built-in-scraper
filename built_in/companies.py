"""/built-in/companies/* — company search, one company in full (the public
GraphQL object merged with the profile header and the benefits / offices /
teams tab partials), the directory with its path filters, the AI insights
pages, a company's articles and a company's live jobs.

Company identity: `company` takes an alias ('stripe'), a profile link or
the numeric id. The GraphQL answers either (companyByAliasAndRegionID /
companyByID); the HTML tabs need the alias, which the GraphQL object
carries (`alias`).
"""
import re

from built_in import parsers as P
from built_in import refdata, refs
from built_in.fetch import (SITE_ID, BuiltInNotFound, BuiltInUpstreamError, embedded_init, gather, get_html,
                            get_json, get_page, graphql)

COMPANY_FIELDS = """
id name alias city state totalEmployees localEmployees yearFounded mission miniDescription introHeader whyWorkWithUs
perksOverview workplacePolicy officeType hybridDetails{onsiteType onsiteValue} industries{id name urlName} perksCount
technologies{id name urlName categoryName} extraTechnologies{id name categoryName}
cultureTopics{id title category overview quoteQuestion quoteText quoteName quoteTitle featuredName featuredTitle fileData{uri}}
employeeReviews{reviewerJobTitle reviewerName reviewerAvatarURL review}
insidersView{intro introPhotos{main gallery} fourOneOne{question answer}}
offices{city state country postalCode streetAddress1 streetAddress2 headquarters nearestMarket neighborhoodDescription}
galleries featuredImage logo logoUrl video funding showFunding exitHistory adjectives isEasyApply isBrandBoost
isLimitedListings publishInsidersPage subscription{level} regionAlias regionName lastUpdated
marketSites{regionID} companyATSDetails{atsType atsUrl atsSourceType}
"""
# Asked separately: for some companies (HubSpot) the server 500s on it and
# the error takes the whole object down. `jobs{count}` is never asked — the
# GraphQL job index is stale (0 for every company); the live count comes from
# the profile page.
HAS_REMOTE_QUERY = "query($id:Int!){ companyByID(id:$id){ hasRemoteJobs } }"
INSIGHT_TOPICS = {
    "workplace_perception": "workplace-perception", "culture_values": "culture-values",
    "career_growth_development": "career-growth-development", "compensation_benefits": "compensation-benefits",
    "work_life_balance_wellbeing": "work-life-balance-wellbeing", "leadership_management": "leadership-management",
    "stability_growth": "stability-growth",
}
DIRECTORY_PER_PAGE = 20


def _graphql_company(company):
    """The full GraphQL company object. Always fetched BY ID: the by-alias
    query panics server-side on optional sub-objects and nulls siblings
    (technologies come back null, HubSpot's whole object fails), while
    companyByID answers the same field set cleanly — so an alias is first
    resolved to its id with an id-only query."""
    company_id = company.get("id") or company_id_for_alias(company["alias"])
    query = "query($id:Int!){ companyByID(id:$id){ %s } }" % COMPANY_FIELDS
    data, errors = graphql(query, {"id": int(company_id)}, label="companyByID")
    node = (data or {}).get("companyByID")
    if not isinstance(node, dict) or not node.get("id"):
        message = "; ".join(e.get("message", "") for e in errors[:2]) if errors else ""
        missing = any(m in (e.get("message") or "").lower() for e in errors for m in ("no rows", "not found"))
        if node is None and errors and not missing:
            raise BuiltInUpstreamError(f"company lookup failed: {message[:200]}")
        raise BuiltInNotFound(f"company {company.get('alias') or company_id} not found on builtin.com")
    return node


def _page_company_id(alias):
    """The company id the profile page embeds (companyProfileInit), or None
    when builtin.com has no such page."""
    status, html, _ = get_page(f"/company/{alias}", label="company profile")
    if status != 200:
        return None
    init = embedded_init(html, "companyProfileInit") or {}
    return P.to_int(init.get("companyId"))


def company_id_for_alias(alias):
    """'stripe' -> 84805: one GraphQL lookup on the national market; companies
    the GraphQL does not know (newer profiles, other markets) fall back to the
    id their own profile page embeds."""
    data, _ = graphql("query($name:String!,$r:Int!){ companyByAliasAndRegionID(name:$name, regionId:$r){ id } }",
                      {"name": alias, "r": SITE_ID}, label="company id")
    node = (data or {}).get("companyByAliasAndRegionID")
    if isinstance(node, dict) and node.get("id"):
        return int(node["id"])
    page_id = _page_company_id(alias)
    if page_id:
        return page_id
    raise BuiltInNotFound(f"company '{alias}' not found on builtin.com")


def search(query, limit=10):
    """Company name autocomplete (the header search's own endpoint)."""
    rows = get_json("/companyapi/search", {"query": query, "siteid": SITE_ID, "max_results": limit}, label="company search")
    rows = rows if isinstance(rows, list) else []
    companies = [P.company_search_row(r) for r in rows][:limit]
    return {"query": query, "count": len(companies), "companies": companies}


def _tab(alias, tab):
    path = f"/company/{alias}/{tab}" if tab else f"/company/{alias}"
    status, html, _ = get_page(path, {"handler": "ChangeTab"}, label=f"company {tab or 'overview'} tab")
    return html if status == 200 else None


def _has_remote_jobs(company_id):
    data, errors = graphql(HAS_REMOTE_QUERY, {"id": int(company_id)}, label="hasRemoteJobs")
    node = (data or {}).get("companyByID") if not errors else None
    return node.get("hasRemoteJobs") if isinstance(node, dict) else None


def details(company, include=None):
    """GraphQL core + profile header + the Benefits / Offices / Teams tabs.
    A company the GraphQL has no record of (newer profiles, e.g.
    openai-deployment-company) is built from its pages alone: the GraphQL-only
    fields stay null and the header / tabs fill the rest."""
    try:
        core = P.graphql_company(_graphql_company(company))
    except BuiltInNotFound:
        if not company.get("alias"):
            raise
        core = None
    if core is None:
        status, html, _ = get_page(f"/company/{company['alias']}", label="company profile")
        init = embedded_init(html, "companyProfileInit") if status == 200 else None
        if not init:
            raise BuiltInNotFound(f"company {company['alias']} not found on builtin.com")
        core = P.graphql_company({"id": init.get("companyId"), "name": init.get("companyName"),
                                  "alias": "/company/" + (init.get("companyAlias") or company["alias"])})
    alias = core["alias"] or company.get("alias")
    if not alias:
        raise BuiltInNotFound("company has no public profile alias")
    include = set(include or ("benefits", "offices", "teams"))
    fetches = {
        "header": lambda: get_page(f"/company/{alias}", label="company profile"),
        "overview": lambda: _tab(alias, None),
        "has_remote_jobs": lambda: _has_remote_jobs(core["id"]),
    }
    if "benefits" in include:
        fetches["benefits"] = lambda: _tab(alias, "benefits")
    if "offices" in include:
        fetches["offices"] = lambda: _tab(alias, "offices")
    if "teams" in include:
        fetches["teams"] = lambda: _tab(alias, "teams")
    got = gather(fetches, optional=tuple(k for k in fetches if k != "header"))
    status, header_html, _ = got["header"]
    if status != 200:
        raise BuiltInNotFound(f"company profile /company/{alias} not found on builtin.com")
    header = P.company_header(header_html)
    profile_init = embedded_init(header_html, "companyProfileInit") or {}
    overview = P.company_overview(got.get("overview")) if got.get("overview") else {}
    benefits = P.benefits_tab(got["benefits"]) if got.get("benefits") else None
    if benefits is not None:
        # the tab's intro is the GraphQL perksOverview again: keep one copy
        tab_overview = benefits.pop("overview", None)
        if not core.get("perks_overview"):
            core["perks_overview"] = tab_overview
    offices = P.offices_tab(got["offices"]) if got.get("offices") else None
    teams = P.teams_tab(got["teams"]) if got.get("teams") else None
    out = dict(core)
    out.update({
        "name": header["name"] or core["name"],
        "logo": header["logo"] or core["logo"],
        "drupal_id": P.to_int(profile_init.get("drupalId")),
        "website": header["website"],
        "tagline": overview.get("tagline") or core.get("mini_description"),
        "description": overview.get("description"),
        "hq": header["hq"],
        "offices_count": header["offices_count"] or (offices or {}).get("offices_count"),
        "office_names": header["office_names"],
        "employees_count": header["employees_count"] or core["employees_count"],
        "year_founded": header["year_founded"] or core["year_founded"],
        "open_jobs_count": header["jobs_count"],
        "industries": overview.get("industries") or core["industries"],
        "gallery": overview.get("gallery") or core["galleries"],
        "videos": overview.get("videos") or [],
        "recent_jobs": overview.get("recent_jobs") or [],
        "benefits": benefits,
        "workplace": (offices or {}).get("workplace"),
        "office_locations": (offices or {}).get("offices") or [],
        "teams": teams or [],
        "has_remote_jobs": got.get("has_remote_jobs"),
        "insights_links": [{"topic": v, "link": refs.absolute(f"/company/{alias}/faq/{v}")} for v in INSIGHT_TOPICS.values()],
    })
    out.pop("galleries", None)
    out.pop("mini_description", None)
    return {"company": out}


def _directory_path(kw):
    segments = ["/companies"]
    if kw.get("location"):
        metro = refdata.metro(kw["location"])
        if metro is None and kw["location"].lower().replace(" ", "-") != "fully-remote":
            raise ValueError("location must be one of the directory's metros (see /built-in/jobs/filters -> metros) or 'fully-remote'")
        segments += ["location", metro["alias"] if metro else "fully-remote"]
    if kw.get("company_size"):
        segments += ["size", refdata.COMPANY_SIZE_PUBLIC[kw["company_size"]]]
    if kw.get("industry"):
        segments += ["type", refdata.industry(kw["industry"])["alias"] + "-companies"]
    if kw.get("tech"):
        tech = refdata.tech_stack(kw["tech"])
        segments += ["tech", tech["alias"] if tech else kw["tech"].lower().replace(" ", "-")]
    if kw.get("perk"):
        perk = refdata.perk(kw["perk"])
        if perk is None:
            raise ValueError("perk must be one of the directory's perk aliases (see /built-in/companies/filters)")
        segments += ["perks", perk["alias"]]
    if kw.get("diversity"):
        dei = refdata.diversity(kw["diversity"])
        if dei is None:
            raise ValueError("diversity must be one of the directory's diversity aliases (see /built-in/companies/filters)")
        segments += ["diversity", dei["alias"]]
    if kw.get("hiring_remote"):
        segments += ["hiring", "remote"]
    return "/".join(segments)


def list_companies(page=1, country="USA", **kw):
    """The /companies directory with its path filters."""
    path = _directory_path(kw)
    html = get_html(path, {"page": page if page > 1 else None, "country": country}, label="company directory")
    init = embedded_init(html, "companyDirectoryInit") or {}
    companies = P.directory_cards(html)
    # last_page's no-pagination fallback looks for job cards, not company cards
    total_pages = P.last_page(html) or (1 if companies else 0)
    if not companies and page > 1:
        raise BuiltInNotFound(f"page {page} is past the last page of this directory")
    applied = P.directory_criteria(init)
    return {
        "applied": applied,
        "pagination": {"page": page, "items_per_page": applied.get("per_page") or DIRECTORY_PER_PAGE,
                       "total_pages": total_pages, "total_count": None},
        "companies": companies,
    }


def directory_filters(**_):
    data = refdata.DATA
    return {
        "metros": [{"alias": m["alias"], "name": m["name"], "state_code": m["state_code"]} for m in data["metros"]] + [{"alias": "fully-remote", "name": "Fully Remote", "state_code": None}],
        "company_sizes": list(refdata.COMPANY_SIZE_PUBLIC),
        "industries": [{"alias": i["alias"], "name": i["name"]} for i in data["industries"]],
        "tech_stacks": [{"alias": t["alias"], "name": t["name"]} for t in data["tech_stacks"]],
        "perks": [{"alias": p["alias"], "name": p["name"]} for p in data["perks"]],
        "diversity": [{"alias": d["alias"], "name": d["name"]} for d in data["diversity"]],
        "insight_topics": list(INSIGHT_TOPICS),
    }


def _alias_of(company):
    if company.get("alias"):
        return company["alias"]
    node = P.graphql_company(_graphql_company(company))
    if not node.get("alias"):
        raise BuiltInNotFound("company has no public profile alias")
    return node["alias"]


def insights(company, topic="workplace_perception"):
    alias = _alias_of(company)
    slug = INSIGHT_TOPICS[topic]
    status, html, _ = get_page(f"/company/{alias}/faq/{slug}", label="company insights")
    if status != 200:
        raise BuiltInNotFound(f"no '{topic}' insights page for company {alias}")
    page = P.faq_page(html, topic=slug)
    if not page.get("title") and not page.get("summary"):
        raise BuiltInNotFound(f"no '{topic}' insights published for company {alias}")
    page["company"] = {"alias": alias, "link": refs.company_link(alias)}
    page["link"] = refs.absolute(f"/company/{alias}/faq/{slug}")
    return page


def _article_rows(params, label):
    """One page of the site's article index, each row enriched from its
    page's JSON-LD (fetched in parallel; a failed page keeps the bare row)."""
    from built_in.fetch import ld_node
    body = get_json("/articles", params, label=label)
    body = body if isinstance(body, dict) else {}
    rows = [r for r in body.get("items") or [] if isinstance(r, dict)]

    def page_ld(row):
        link = row.get("alias") or ""
        path = link.replace("https://builtin.com", "") if link.startswith("https://builtin.com/articles/") else None
        if not path:
            return None
        status, html, _ = get_page(path, label="article page")
        if status != 200:
            return None
        return ld_node(html, "Article") or ld_node(html, "NewsArticle") or ld_node(html, "BlogPosting")

    lds = gather({i: (lambda r=row: page_ld(r)) for i, row in enumerate(rows)}, optional=tuple(range(len(rows))))
    total = P.to_int(body.get("totalItems")) or 0
    per = P.to_int(body.get("pageSize")) or params.get("pageSize") or 10
    return {
        "pagination": {"page": params.get("page") or 1, "items_per_page": per, "total_count": total,
                       "total_pages": (total + per - 1) // per if per else 0},
        "articles": [P.article_card(row, lds.get(i)) for i, row in enumerate(rows)],
    }


def articles(company, page=1, per_page=10):
    """A company's articles (the site's own list, newest first)."""
    company_id = company.get("id") or company_id_for_alias(company["alias"])
    out = _article_rows({"companyId": company_id, "page": page, "pageSize": per_page}, "company articles")
    return {"company_id": company_id, **out}


def latest_articles(page=1, per_page=10):
    return _article_rows({"page": page, "pageSize": per_page}, "articles")


def jobs(company, page=1, **kw):
    """Every live job of one company (the board scoped by companyId, all
    locations unless a location filter is given)."""
    from built_in.jobs import search as job_search
    return job_search(page=page, company=company, **kw)

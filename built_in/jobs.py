"""/built-in/jobs/* — the job board with every filter the site has (and a
builtin.com job-board link accepted as the query), one job in full, and the
filter vocabularies.

A search is ONE page load of the server-rendered board. The filters ride in
the URL path in the site's own order — /jobs/{remote|hybrid|office}…/{metro}/
{category}/{subcategory}/{experience}/{industry}/{company-size} — and the
rest in the query (search, daysSinceUpdated, earlyApplicant, companyId,
skills, city/state/country, searcharea, page). The board geo-defaults
results to the caller's IP, so `country` (ISO alpha-3 upstream) is ALWAYS
sent: the API's default is US. A metro alias (chicago, new-york-city, …)
becomes a path segment; any other place name is resolved through the
site's location suggest -> place lookup into city/state/country +
coordinates. The page size is the site's (25 on the plain board, 10 on the
filtered / company boards); pagination stops at page 400.
"""
from built_in import parsers as P
from built_in import refdata, refs
from built_in.fetch import BuiltInBadRequest, BuiltInNotFound, BuiltInUpstreamError, embedded_init, get_html, get_json, ld_node

MAX_PAGE = 400

FILTER_KEYS = ("location", "country", "work_mode", "category", "subcategory", "experience", "industry",
               "company_size", "posted_within", "skills", "radius_miles", "early_applicant", "company")


def _merge_link(link, kwargs):
    """A parsed job-board link's own filters fill the gaps of the explicit
    params (explicit values win)."""
    if not link:
        return kwargs
    out = dict(kwargs)
    for src, dst in (("location", "location"), ("category", "category"), ("subcategory", "subcategory"),
                     ("experience", "experience"), ("industry", "industry"), ("company_size", "company_size"),
                     ("posted_within", "posted_within"), ("skills", "skills"), ("radius_miles", "radius_miles"),
                     ("page", "page"), ("country", "country"), ("city", "city"), ("state", "state")):
        if out.get(dst) in (None, [], "") and link.get(src) not in (None, [], ""):
            out[dst] = link[src]
    if not out.get("work_mode") and link.get("work_modes"):
        out["work_mode"] = list(link["work_modes"])
    if out.get("early_applicant") is None and link.get("early_applicant"):
        out["early_applicant"] = True
    if out.get("company") is None and link.get("company_id"):
        out["company"] = {"alias": None, "id": link["company_id"]}
    if link.get("extra_segments"):
        out["extra_segments"] = link["extra_segments"]
    return out


def _resolve_place(name):
    """A free-text place -> {city, state, country, latitude, longitude} via
    the site's own suggest + place lookup (None when it knows no such place)."""
    rows = get_json("/locationapi/suggest/autocomplete", {"SearchText": name, "MaxResults": 1}, label="location suggest")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict) or not rows[0].get("placeId"):
        return None
    detail = get_json("/locationapi/place", {"placeId": rows[0]["placeId"]}, label="location lookup")
    return P.place(detail) if isinstance(detail, dict) else None


def _company_id(company):
    """{alias, id} -> the numeric company id (one GraphQL lookup for an alias)."""
    if not company:
        return None
    if company.get("id"):
        return company["id"]
    from built_in.companies import company_id_for_alias
    return company_id_for_alias(company["alias"])


def search_path(kw):
    """The board path that carries the path-borne filters."""
    segments = ["/jobs"]
    for mode in kw.get("work_mode") or []:
        segments.append(refdata.WORK_MODE_PUBLIC[mode])
    metro = refdata.metro(kw.get("location")) if kw.get("location") else None
    if metro:
        segments.append(metro["alias"])
    category = refdata.category(kw.get("category")) if kw.get("category") else None
    sub = None
    if kw.get("subcategory"):
        hit = refdata.subcategory(kw["subcategory"], category)
        if hit is None:
            raise ValueError(f"subcategory '{kw['subcategory']}' is not one of this category's subcategories (see /built-in/jobs/filters)")
        category, sub = hit
    if category:
        segments.append(category["alias"])
    if sub:
        segments.append(sub["alias"])
    if kw.get("experience"):
        segments.append(refdata.EXPERIENCE_PUBLIC[kw["experience"]])
    if kw.get("industry"):
        segments.append(refdata.industry(kw["industry"])["alias"])
    if kw.get("company_size"):
        segments.append(refdata.COMPANY_SIZE_PUBLIC[kw["company_size"]])
    for extra in kw.get("extra_segments") or []:
        if extra not in segments:
            segments.append(extra)
    return "/".join(segments), metro


def upstream_params(kw, metro, place, company_id):
    params = {
        "search": kw.get("query"),
        "daysSinceUpdated": refdata.POSTED_WITHIN_PUBLIC.get(kw.get("posted_within")),
        "earlyApplicant": True if kw.get("early_applicant") else None,
        "companyId": company_id,
        "skills": kw.get("skills"),
        "page": kw.get("page") if (kw.get("page") or 1) > 1 else None,
    }
    if metro is None and place:
        params.update({"city": place.get("city"), "state": place.get("state"), "country": place.get("country"),
                       "latitude": place.get("latitude"), "longitude": place.get("longitude")})
    elif metro is None and kw.get("city"):
        params.update({"city": kw.get("city"), "state": kw.get("state"), "country": kw.get("country")})
    else:
        params["country"] = kw.get("country")
    if company_id and not (metro or place or kw.get("city")):
        params["allLocations"] = True
        params.pop("country", None)
    if kw.get("radius_miles") and (metro or place or kw.get("city")):
        params["searcharea"] = f"{kw['radius_miles']}mi"
    return params


def search(query=None, page=1, **kw):
    """One board page -> {applied, pagination, skill_facets, jobs}."""
    kw = dict(kw)
    kw["page"] = page
    link = None
    if query and refs.is_link(query):
        link = refs.parse_search_link(query)
        query = link.get("query")
    kw["query"] = query
    kw = _merge_link(link, kw)
    kw["country"] = kw.get("country") or "USA"
    if kw.get("page", 1) > MAX_PAGE:
        raise ValueError(f"builtin.com serves at most {MAX_PAGE} pages of one search")
    path, metro = search_path(kw)
    place = None
    if kw.get("location") and metro is None:
        place = _resolve_place(kw["location"])
        if place is None:
            raise BuiltInNotFound(f"builtin.com knows no location named '{kw['location']}'")
    company_id = _company_id(kw.get("company"))
    html = get_html(path, upstream_params(kw, metro, place, company_id), label="job search")
    init = embedded_init(html, "jobBoardInit") or {}
    criteria = init.get("criteria") if isinstance(init.get("criteria"), dict) else {}
    jobs = P.job_cards(html)
    per_page = P.to_int(criteria.get("pageSize")) or (25 if path == "/jobs" else 10)
    current = P.to_int(criteria.get("pageNumber")) or kw["page"]
    total_pages = P.last_page(html)
    if total_pages == 0 and current > 1:
        raise BuiltInNotFound(f"page {current} is past the last page of this search")
    applied = P.applied_criteria(criteria)
    applied["location_resolved"] = place
    applied["metro"] = {"alias": metro["alias"], "name": metro["name"], "city": metro["city"], "state": metro["state"]} if metro else None
    return {
        "applied": applied,
        # the board prints no total: `count` stays null and estimated_count is
        # the page capacity (last page x page size); the site stops at page 400
        "pagination": {"page": current, "items_per_page": per_page, "total_pages": total_pages, "total_count": None},
        "estimated_count": total_pages * per_page,
        "is_capped": total_pages >= MAX_PAGE,
        "skill_facets": P.skill_facets(init),
        "jobs": jobs,
    }


def details(job):
    """One job page -> the job in full."""
    slug, job_id = job["slug"], job["id"]
    status, html, final_url = __import__("built_in.fetch", fromlist=["get_page"]).get_page(f"/job/{slug}/{job_id}", label=f"job {job_id}")
    if status != 200:
        raise BuiltInNotFound(f"job {slug}/{job_id} not found on builtin.com (expired, removed or the slug is wrong)")
    init = embedded_init(html, "jobPostInit")
    ld = ld_node(html, "JobPosting")
    if init is None and ld is None:
        raise BuiltInUpstreamError("job page carried no job data (layout changed?)")
    return {"job": P.job_page(html, slug=slug, job_id=job_id, init=init, ld=ld)}


def filters(**_):
    """The live filter vocabularies of the board (falls back to the captured
    copy when the page cannot be read)."""
    live = None
    try:
        html = get_html("/jobs", {"country": "USA"}, label="job board")
        live = embedded_init(html, "jobBoardInit")
    except (BuiltInUpstreamError, BuiltInBadRequest, BuiltInNotFound):
        live = None
    data = refdata.DATA
    if isinstance(live, dict) and live.get("categoriesFilterOptions"):
        categories = []
        for c in live["categoriesFilterOptions"]:
            subs = live.get("subCategoriesFilterOptions", {}).get(str(c.get("id")), [])
            categories.append({"id": c.get("id"), "alias": c.get("alias"), "name": c.get("name"),
                               "subcategories": [{"id": s.get("id"), "alias": s.get("alias") or s.get("urlName"), "name": s.get("name")} for s in subs]})
        industries = [{"id": i.get("id"), "alias": i.get("alias"), "name": i.get("name")} for i in live.get("industryFilterOptions") or []]
        source = "live"
    else:
        categories, industries, source = data["categories"], data["industries"], "captured"
    return {
        "source": source,
        "categories": categories,
        "experience_levels": [{"name": k, "label": next((e["name"] for e in data["experiences"] if e["alias"] == v), v)} for k, v in refdata.EXPERIENCE_PUBLIC.items()],
        "work_modes": list(refdata.WORK_MODE_PUBLIC),
        "company_sizes": list(refdata.COMPANY_SIZE_PUBLIC),
        "posted_within": [{"name": k, "days": v} for k, v in refdata.POSTED_WITHIN_PUBLIC.items()],
        "radius_miles": refdata.RADIUS_MILES,
        "industries": industries,
        "metros": [{"alias": m["alias"], "name": m["name"], "city": m["city"], "state": m["state"], "state_code": m["state_code"]} for m in data["metros"]],
        "country_boards": sorted(set(refdata.COUNTRY_BOARDS.values()) | {"USA"}),
    }

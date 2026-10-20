"""Built In reference parsing: ONE param per input that auto-detects its
forms (tripadvisor QueryOrIdField convention — never a sibling `url`/`id`
pair).

  job       https://builtin.com/job/senior-software-engineer/11741949
            | senior-software-engineer/11741949 | /job/.../11741949
            (builtin.com needs the slug — an id-only path is a 404 — so a
            bare numeric id is rejected with that explanation)
  company   stripe | /company/stripe | https://builtin.com/company/stripe[/jobs]
            | 84805 (the numeric company id the site's own GraphQL / links use)
  article   https://builtin.com/articles/yext-acquires-hearsay-systems-20240613
            | yext-acquires-hearsay-systems-20240613
  query     free text | a builtin.com job-board link, whose own filters are
            then applied (parse_search_link)

The legacy city hosts (builtinchicago.org, builtinnyc.com, …) redirect to
builtin.com and are accepted as the same site.
"""
import re
from urllib.parse import parse_qsl, unquote, urlparse

from built_in import refdata

SITE = "https://builtin.com"

_ID_RE = re.compile(r"^\d{1,12}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,200}$", re.I)
_HOST_RE = re.compile(r"^(?:[a-z0-9-]+\.)*builtin[a-z]*\.(?:com|org)$", re.I)
_BARE_HOST_RE = re.compile(r"^(?:www\.)?builtin[a-z]*\.(?:com|org)(?=/|$)", re.I)


def is_link(value):
    value = str(value or "").strip()
    return value.startswith(("http://", "https://", "//")) or bool(_BARE_HOST_RE.match(value))


def _parse(value):
    """A builtin.com link -> (path segments, query pairs). Raises ValueError
    for another site."""
    url = value.strip()
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not _HOST_RE.match(host):
        raise ValueError("not a builtin.com link")
    segments = [unquote(s) for s in parsed.path.split("/") if s]
    return segments, parse_qsl(parsed.query, keep_blank_values=False)


def _truthy(raw):
    return str(raw).strip().lower() in ("true", "1", "yes", "on")


# ---- links out -----------------------------------------------------------------

def absolute(path):
    if not path or not isinstance(path, str):
        return None
    path = path.strip()
    if path.startswith("http"):
        return path
    if path.startswith("//"):
        return "https:" + path
    if not path.startswith("/"):
        path = "/" + path
    return SITE + path


def strip_tracking(link):
    """Drop utm_* / tracking query parts from an outbound link."""
    if not link or not isinstance(link, str):
        return None
    parsed = urlparse(link)
    if not parsed.query:
        return link
    kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not k.lower().startswith(("utm_", "source", "ref"))]
    base = link.split("?", 1)[0]
    if not kept:
        return base
    from urllib.parse import urlencode
    return base + "?" + urlencode(kept)


def job_link(slug, job_id):
    if not job_id:
        return None
    return f"{SITE}/job/{slug or 'job'}/{job_id}"


def company_link(alias):
    if not alias:
        return None
    alias = alias.strip("/")
    if alias.startswith("company/"):
        alias = alias[len("company/"):]
    return f"{SITE}/company/{alias}"


def company_alias_from_path(path):
    """'/company/stripe' | 'https://builtin.com/company/stripe/jobs' -> 'stripe'."""
    if not path or not isinstance(path, str):
        return None
    try:
        segments, _ = _parse(path) if is_link(path) else ([s for s in path.split("/") if s], [])
    except ValueError:
        return None
    if len(segments) >= 2 and segments[0].lower() == "company":
        return segments[1]
    return None


def article_link(slug):
    return f"{SITE}/articles/{slug}" if slug else None


def salary_link(title_slug, location_slug=None):
    if not title_slug:
        return None
    if location_slug:
        return f"{SITE}/salaries/us/{location_slug}/{title_slug}"
    return f"{SITE}/salaries/us/{title_slug}"


# ---- resolvers -------------------------------------------------------------------

def _job_from_segments(segments):
    if len(segments) >= 3 and segments[0].lower() == "job" and _ID_RE.match(segments[-1]):
        return {"id": segments[-1], "slug": segments[-2]}
    return None


def resolve_job(value):
    """A builtin.com job link or '{slug}/{id}' -> {"id": str, "slug": str}."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("job is required")
    if is_link(value):
        try:
            segments, _ = _parse(value)
        except ValueError:
            raise ValueError("job must be a builtin.com job link (https://builtin.com/job/senior-software-engineer/11741949)")
        hit = _job_from_segments(segments)
        if hit:
            return hit
        raise ValueError("job link must look like https://builtin.com/job/{title-slug}/{job_id}")
    parts = [p for p in value.split("/") if p]
    if parts and parts[0].lower() == "job":
        parts = parts[1:]
    if len(parts) == 2 and _ID_RE.match(parts[1]) and _SLUG_RE.match(parts[0]):
        return {"id": parts[1], "slug": parts[0]}
    if _ID_RE.match(value):
        raise ValueError("builtin.com cannot open a job by id alone: pass the job link "
                         "(https://builtin.com/job/{title-slug}/{job_id}) or '{title-slug}/{job_id}' "
                         "— every job in a search result carries both as `link`")
    raise ValueError("job must be a builtin.com job link or '{title-slug}/{job_id}'")


def resolve_company(value):
    """Company alias ('stripe', '/company/stripe'), a profile link or the
    numeric company id -> {"alias": str|None, "id": int|None}."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("company is required")
    if is_link(value):
        try:
            segments, _ = _parse(value)
        except ValueError:
            raise ValueError("company must be a builtin.com company link (https://builtin.com/company/stripe), an alias or a company id")
        if len(segments) >= 2 and segments[0].lower() == "company" and _SLUG_RE.match(segments[1]):
            return {"alias": segments[1].lower(), "id": None}
        raise ValueError("company link must look like https://builtin.com/company/{alias}")
    if _ID_RE.match(value):
        return {"alias": None, "id": int(value)}
    parts = [p for p in value.split("/") if p]
    if len(parts) >= 2 and parts[0].lower() == "company":
        parts = parts[1:]
    if len(parts) >= 1 and _SLUG_RE.match(parts[0]):
        return {"alias": parts[0].lower(), "id": None}
    raise ValueError("company must be a builtin.com company alias (stripe), a company link or a numeric company id")


def resolve_article(value):
    """An article slug or a builtin.com article link -> the slug."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("article is required")
    if is_link(value):
        try:
            segments, _ = _parse(value)
        except ValueError:
            raise ValueError("article must be a builtin.com article link (https://builtin.com/articles/{slug}) or its slug")
        if len(segments) >= 2 and segments[0].lower() == "articles" and _SLUG_RE.match(segments[1]):
            return segments[1]
        raise ValueError("article link must look like https://builtin.com/articles/{slug}")
    parts = [p for p in value.split("/") if p]
    if len(parts) >= 2 and parts[0].lower() == "articles":
        parts = parts[1:]
    if len(parts) == 1 and _SLUG_RE.match(parts[0]):
        return parts[0]
    raise ValueError("article must be a builtin.com article link or its slug")


# ---- search links ----------------------------------------------------------------------

def parse_search_link(value):
    """A builtin.com job-board link -> the search kwargs it encodes (absent
    parts are None): {query, work_modes[], location, category, subcategory,
    experience, industry, company_size, country, city, state, radius_miles,
    posted_within, early_applicant, company_id, skills[], page,
    extra_segments[]}. Path grammar (any part optional, in this order):
    /jobs/{remote|hybrid|office}…/{metro}/{category}/{subcategory}/
    {experience}/{industry}/{company-size}, or /jobs/{region}/{country}/… for
    the non-US boards; `/search/{term}` is the sitemap's keyword form.
    Legacy aliases the site still honours but no longer lists
    (dev-engineering/python) are kept verbatim in `extra_segments`."""
    segments, pairs = _parse(value)
    if not segments or segments[0].lower() != "jobs":
        raise ValueError("query must be search text or a builtin.com job-board link (https://builtin.com/jobs/remote/chicago/engineering?search=python)")
    out = {"query": None, "work_modes": [], "location": None, "category": None, "subcategory": None,
           "experience": None, "industry": None, "company_size": None, "country": None, "city": None,
           "state": None, "radius_miles": None, "posted_within": None, "early_applicant": None,
           "company_id": None, "skills": None, "page": None, "extra_segments": []}
    rest = [s.lower() for s in segments[1:]]
    index = 0
    category_row = None
    while index < len(rest):
        segment = rest[index]
        nxt = rest[index + 1] if index + 1 < len(rest) else None
        if segment == "search" and nxt:
            out["query"] = nxt.replace("-", " ")
            index += 2
            continue
        if segment in refdata.REGION_CODES and nxt and refdata.country_board(nxt):
            out["country"] = refdata.country_board(nxt)
            index += 2
            continue
        if refdata.is_work_mode_alias(segment):
            mode = refdata.WORK_MODE_FROM_ALIAS[segment]
            if mode not in out["work_modes"]:
                out["work_modes"].append(mode)
        elif refdata.category(segment) and out["category"] is None:
            category_row = refdata.category(segment)
            out["category"] = category_row["alias"]
        elif refdata.subcategory(segment, category_row) and out["subcategory"] is None:
            cat, sub = refdata.subcategory(segment, category_row)
            out["category"] = out["category"] or cat["alias"]
            out["subcategory"] = sub["alias"]
        elif refdata.is_experience_alias(segment) and out["experience"] is None:
            out["experience"] = {v: k for k, v in refdata.EXPERIENCE_PUBLIC.items()}[segment]
        elif refdata.industry(segment) and out["industry"] is None:
            out["industry"] = refdata.industry(segment)["alias"]
        elif refdata.is_size_alias(segment) and out["company_size"] is None:
            out["company_size"] = refdata.COMPANY_SIZE_FROM_ALIAS[segment]
        elif refdata.metro(segment) and out["location"] is None:
            out["location"] = refdata.metro(segment)["alias"]
        else:
            out["extra_segments"].append(segment)
        index += 1
    for key, raw in pairs:
        key = key.lower()
        raw = raw.strip()
        if not raw:
            continue
        if key == "search":
            out["query"] = " ".join(raw.split()) or None
        elif key == "country":
            out["country"] = refdata.alpha3(raw) or raw.upper()
        elif key == "city":
            out["city"] = raw
        elif key == "state":
            out["state"] = raw
        elif key == "searcharea":
            miles = re.sub(r"\D", "", raw)
            if miles:
                out["radius_miles"] = int(miles)
        elif key == "dayssinceupdated" and raw.isdigit():
            out["posted_within"] = refdata.POSTED_WITHIN_FROM_DAYS.get(int(raw))
        elif key == "earlyapplicant" and _truthy(raw):
            out["early_applicant"] = True
        elif key == "companyid" and raw.isdigit():
            out["company_id"] = int(raw)
        elif key == "skills":
            skills = [s.strip() for s in raw.split(",") if s.strip()]
            out["skills"] = skills or None
        elif key == "page" and raw.isdigit() and int(raw) >= 1:
            out["page"] = int(raw)
    return out

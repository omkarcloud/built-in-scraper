"""Built In (builtin.com) transport: plain curl_cffi with browser-impersonated
TLS. No browser, no login, no token (validated 2026-10-19 from direct Indian
egress: every surface below answered 200 first try, a 15-request burst 15/15;
Cloudflare fronts the site but only its passive beacon is present for Chrome
TLS).

Upstream surfaces:

  * JOB BOARD (server-rendered Drupal + Alpine, https://builtin.com)
      /jobs[/{remote|hybrid|office}][/{metro}][/{category}][/{subcategory}]
          [/{experience}][/{industry}][/{company-size}]?search=&country=&...
        The filters ride in the PATH in that order (the aliases are in
        refdata.json); the query carries search, daysSinceUpdated,
        earlyApplicant, companyId, skills, city/state/country, searcharea,
        allLocations, page. The page embeds `Builtin.jobBoardInit({...})`
        with the normalised criteria (incl. pageSize) and every filter list;
        results are geo-defaulted by the caller's IP, so `country=` (ISO
        alpha-3) is always sent. Pagination stops at page 400.
      /job/{slug}/{id}            job page: JobPosting JSON-LD + the HTML
        (the slug is REQUIRED — an id-only path is a 404).
  * COMPANIES
      https://api.builtin.com/graphql  public, introspectable; companyByID /
        companyByAliasAndRegionID(name, regionId: 9) carry offices, tech
        stack, reviews, culture topics, perks count, ATS, funding. Its jobs
        query is stale and crashes on most filters — never used for jobs.
      /company/{alias}            profile header (HQ, offices, employees,
        founded, website, live job count); the tabs load as partials:
        /company/{alias}/{benefits|offices|teams|jobs|articles}?handler=ChangeTab
      /company/{alias}/faq/{topic} AI "insights" pages (server-rendered)
      /companies[/location/{metro}][/size/{s}][/type/{industry}-companies]
          [/tech/{t}][/perks/{p}][/diversity/{d}][/hiring/remote]?page=
        directory, embeds `Builtin.companyDirectoryInit({...})`
      https://api.builtin.com/companyapi/search?query=&siteid=9&max_results=
      https://api.builtin.com/articles?companyId=&page=&pageSize=
  * SALARIES (Nuxt SSR): /salaries/us/{title}, /salaries/us/{metro-st}/{title},
      /salaries/location/{metro-st} — Occupation JSON-LD + the HTML tables.
  * ARTICLES: /articles/{slug} (Article JSON-LD + body).
  * LOOKUPS: https://api.builtin.com/locationapi/suggest/autocomplete,
      /locationapi/place?placeId=, /jobsapi/jobtitles?searchTerm=

Blocks: none seen. Defensive handling only — a 403 / 429 or a Cloudflare
challenge page sends the worker's new sessions through a sticky residential
US exit (config.built_in_fallback_proxy()) for config.BUILT_IN_BLOCK_COOLDOWN
seconds, the same shape as the reed / vinted transports.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  BuiltInUpstreamError  transport failure / 5xx            — retryable
  BuiltInBlocked        403 / 429 / challenge page         — retryable on a new exit
  BuiltInBadRequest     upstream 400                       — never retried
  BuiltInNotFound       404 / missing entity               — never retried
"""
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

SITE = "https://builtin.com"
API = "https://api.builtin.com"
GRAPHQL = API + "/graphql"
SITE_ID = 9            # the national builtin.com market ("regionId" in the GraphQL)
IMPERSONATE = "chrome"
TIMEOUT = 30            # per request; 3 retries keep the worst case under ~100 s
FANOUT_WORKERS = 12

PAGE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "upgrade-insecure-requests": "1",
}
JSON_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "origin": SITE,
    "referer": SITE + "/",
}

_CHALLENGE_RE = re.compile(r"cf-mitigated|_cf_chl_opt|Just a moment|Access Denied|Attention Required", re.I)
# the site writes the type as application/ld&#x2B;json (the + is HTML-escaped)
_LD_RE = re.compile(r'<script[^>]+type="application/ld(?:\+|&#x2B;|&#43;|&plus;)json"[^>]*>(.*?)</script>', re.S | re.I)


class BuiltInUpstreamError(UpstreamError):
    """Transport failure or 5xx — retryable."""


class BuiltInBlocked(BuiltInUpstreamError, Blocked):
    """403 / 429 or a challenge page — retryable on a fresh exit."""


class BuiltInBadRequest(BadRequest):
    """Upstream 400 — the params were rejected. Never retried."""


class BuiltInNotFound(NotFound):
    """Entity / page does not exist — never retried."""


# ---- sessions ------------------------------------------------------------------
# One curl session per worker thread. Direct egress by default; after a block
# the thread's new sessions go through a sticky residential exit for a while.
_local = threading.local()
_fallback_until = 0.0
_fallback_lock = threading.Lock()


def _proxy_for_new_session():
    forced = config.built_in_proxy()
    if forced:
        return forced
    if time.time() < _fallback_until:
        return config.built_in_fallback_proxy()
    return None


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = _proxy_for_new_session()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        _local.session = sess
    return sess


def _drop_session():
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _note_block():
    global _fallback_until
    if config.built_in_fallback_proxy() is not None:
        with _fallback_lock:
            _fallback_until = time.time() + config.BUILT_IN_BLOCK_COOLDOWN


def dump_debug(name, text):
    dbg = os.environ.get("BUILT_IN_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass


# ---- requests --------------------------------------------------------------------

def _retrying(fn):
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except BuiltInUpstreamError as e:          # includes BuiltInBlocked
            last = e
            _drop_session()
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def clean_params(params):
    """Drop None / empty values; lists become comma strings; booleans become
    the site's lower-case `true` (a false flag is simply not sent)."""
    query = {}
    for key, value in (params or {}).items():
        if value is None or value == "" or value == [] or value is False:
            continue
        if value is True:
            value = "true"
        elif isinstance(value, (list, tuple)):
            value = ",".join(str(v) for v in value)
        query[key] = value
    return query


def _url(path, base=SITE):
    return path if path.startswith("http") else base + path


def get_page(path, params=None, *, label=None, not_found_status=(404, 410)):
    """GET one HTML page -> (status, body, final url). 404 / 410 are returned
    (callers decide); 403 / 429 and challenge pages are blocks; anything
    else non-200 is upstream."""
    label = label or path
    query = clean_params(params)

    def once():
        sess = _session()
        try:
            resp = sess.get(_url(path), params=query, headers=PAGE_HEADERS, timeout=TIMEOUT, allow_redirects=True)
        except Exception as e:
            raise BuiltInUpstreamError(f"request failed: {type(e).__name__}: {e}")
        finally:
            sess.cookies.clear()
        status = resp.status_code
        body = resp.text or ""
        if status in not_found_status:
            return status, body, str(resp.url)
        if status in (403, 429) or (status == 200 and _CHALLENGE_RE.search(body[:4000])):
            dump_debug("blocked", body)
            _note_block()
            raise BuiltInBlocked(f"HTTP {status} on {label}")
        if status == 400:
            raise BuiltInBadRequest(f"upstream rejected {label}")
        if status != 200:
            raise BuiltInUpstreamError(f"HTTP {status} on {label}")
        if not body.strip():
            raise BuiltInUpstreamError(f"empty body on {label}")
        return status, body, str(resp.url)

    return _retrying(once)


def get_html(path, params=None, *, label=None):
    """GET one HTML page that must exist (404 / 410 -> BuiltInNotFound)."""
    label = label or path
    status, body, _ = get_page(path, params, label=label)
    if status != 200:
        raise BuiltInNotFound(f"{label} not found")
    return body


def get_json(path, params=None, *, label=None, base=API):
    """GET one JSON route of api.builtin.com (or an absolute URL). HTML where
    JSON is expected is a block; an empty body is None."""
    label = label or path
    query = clean_params(params)

    def once():
        sess = _session()
        try:
            resp = sess.get(_url(path, base), params=query, headers=JSON_HEADERS, timeout=TIMEOUT, allow_redirects=True)
        except Exception as e:
            raise BuiltInUpstreamError(f"request failed: {type(e).__name__}: {e}")
        finally:
            sess.cookies.clear()
        status = resp.status_code
        body = resp.text or ""
        if status in (404, 410):
            raise BuiltInNotFound(f"{label} not found")
        if status in (403, 429):
            dump_debug("blocked", body)
            _note_block()
            raise BuiltInBlocked(f"HTTP {status} on {label}")
        if status == 400:
            raise BuiltInBadRequest(f"upstream rejected {label}: {body[:200]}")
        if status == 204 or (status == 200 and not body.strip()):
            return None
        if status != 200:
            raise BuiltInUpstreamError(f"HTTP {status} on {label}: {body[:200]}")
        if not body.lstrip().startswith(("{", "[")):
            dump_debug("nonjson", body)
            raise BuiltInBlocked(f"{label} returned HTML, not JSON")
        try:
            return resp.json()
        except Exception:
            dump_debug("badjson", body)
            raise BuiltInUpstreamError(f"could not parse JSON from {label}")

    return _retrying(once)


def graphql(query, variables=None, *, label="graphql"):
    """POST one query to api.builtin.com/graphql -> (data, errors). Partial
    data with field-level errors is normal on this API (nil-pointer panics
    on optional sub-objects), so errors are returned, not raised; only a
    transport failure or a response without `data` raises."""
    payload = {"query": query, "variables": variables or {}}

    def once():
        sess = _session()
        try:
            resp = sess.post(GRAPHQL, json=payload, headers=JSON_HEADERS, timeout=TIMEOUT)
        except Exception as e:
            raise BuiltInUpstreamError(f"request failed: {type(e).__name__}: {e}")
        finally:
            sess.cookies.clear()
        status = resp.status_code
        body = resp.text or ""
        if status in (403, 429):
            dump_debug("blocked_graphql", body)
            _note_block()
            raise BuiltInBlocked(f"HTTP {status} on {label}")
        if status != 200:
            raise BuiltInUpstreamError(f"HTTP {status} on {label}: {body[:200]}")
        try:
            doc = resp.json()
        except Exception:
            dump_debug("badjson_graphql", body)
            raise BuiltInBlocked(f"{label} returned non-JSON")
        if not isinstance(doc, dict) or ("data" not in doc and "errors" not in doc):
            raise BuiltInUpstreamError(f"{label}: unexpected GraphQL envelope")
        return doc.get("data"), doc.get("errors") or []

    return _retrying(once)


# ---- embedded data ---------------------------------------------------------------

def _balanced_json(text, start):
    """The JSON object that starts at text[start] == '{' (brace matching
    that respects strings)."""
    depth = 0
    in_str = False
    escape = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def embedded_init(html, name):
    """The JSON handed to `Builtin.<name>({...})` in a page's inline script
    (jobBoardInit, companyDirectoryInit, companyProfileInit, jobPostInit),
    or None when the page carries none."""
    marker = f"Builtin.{name}("
    index = (html or "").find(marker)
    if index < 0:
        return None
    start = html.find("{", index)
    if start < 0:
        return None
    raw = _balanced_json(html, start)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def json_ld(html):
    """Every JSON-LD node of a page as a flat list (@graph unpacked)."""
    out = []
    for match in _LD_RE.finditer(html or ""):
        try:
            doc = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        nodes = doc if isinstance(doc, list) else [doc]
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("@graph"), list):
                out.extend(n for n in node["@graph"] if isinstance(n, dict))
            elif isinstance(node, dict):
                out.append(node)
    return out


def ld_node(html, type_name):
    """The first JSON-LD node of @type `type_name` (None when absent)."""
    for node in json_ld(html):
        node_type = node.get("@type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if type_name in types:
            return node
    return None


# ---- fan-out ------------------------------------------------------------------------
_pool = ThreadPoolExecutor(max_workers=FANOUT_WORKERS, thread_name_prefix="built_in")


def run_parallel(fns):
    if not fns:
        return []
    if len(fns) == 1:
        return [fns[0]()]
    futures = [_pool.submit(fn) for fn in fns]
    return [f.result() for f in futures]


def gather(mapping, optional=()):
    """{key: callable} in parallel -> {key: result}. Keys named in
    `optional` yield None instead of failing the set when they raise any
    scraper error (an enrichment must not sink the endpoint)."""
    keys = list(mapping)

    def guarded(key):
        fn = mapping[key]
        if key not in optional:
            return fn

        def run():
            try:
                return fn()
            except (UpstreamError, BadRequest, NotFound):
                return None
        return run

    results = run_parallel([guarded(k) for k in keys])
    return dict(zip(keys, results))


if __name__ == "__main__":
    # Smoke test: python built_in/fetch.py [search] [country]
    term = sys.argv[1] if len(sys.argv) > 1 else "python"
    country = sys.argv[2] if len(sys.argv) > 2 else "USA"
    html = get_html("/jobs", {"search": term, "country": country})
    init = embedded_init(html, "jobBoardInit") or {}
    print("criteria:", init.get("criteria"))
    print("cards:", html.count('data-id="job-card"'))
    data, errors = graphql('query{ companyByAliasAndRegionID(name:"stripe", regionId:9){ id name totalEmployees } }')
    print("graphql:", data, errors[:1])
    print("suggest:", get_json("/locationapi/suggest/autocomplete", {"SearchText": "chic", "MaxResults": 3}))

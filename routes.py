"""The 17 Built In endpoints. Every path is served with and without the
`/built-in` prefix, so code generated against the hosted API on RapidAPI
(paths like /jobs/details) runs unchanged against this server.

Params are validated by the marshmallow schemas in built_in/schemas.py —
the same ones the hosted API uses — so names, defaults and error messages
match it exactly."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from built_in import articles, companies, jobs, reference, salaries, schemas
from schema_fields import load_query
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

# path -> (schema, function, paginated)
ENDPOINTS = [
    ("/jobs/details", schemas.JobSchema, jobs.details, False),
    ("/jobs/search", schemas.JobSearchSchema, jobs.search, True),
    ("/companies/details", schemas.CompanySchema, companies.details, False),
    ("/companies/jobs", schemas.CompanyJobsSchema, companies.jobs, True),
    ("/companies/search", schemas.CompanySearchSchema, companies.search, False),
    ("/companies/list", schemas.CompanyListSchema, companies.list_companies, True),
    ("/companies/insights", schemas.CompanyInsightsSchema, companies.insights, False),
    ("/companies/articles", schemas.CompanyArticlesSchema, companies.articles, True),
    ("/salaries/title", schemas.SalaryTitleSchema, salaries.by_title, False),
    ("/salaries/location", schemas.SalaryLocationSchema, salaries.by_location, False),
    ("/articles/details", schemas.ArticleSchema, articles.details, False),
    ("/articles/latest", schemas.ArticlesSchema, companies.latest_articles, True),
    ("/locations/suggest", schemas.LocationSuggestSchema, reference.locations, False),
    ("/job-titles/suggest", schemas.SuggestSchema, reference.job_titles, False),
    ("/jobs/filters", schemas.EmptySchema, jobs.filters, False),
    ("/companies/filters", schemas.EmptySchema, companies.directory_filters, False),
    ("/salaries/filters", schemas.EmptySchema, salaries.filters, False),
]


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The query as unicode strings (bottle 0.12's .get() hands back latin-1
    decoded bytes, so a UTF-8 "São Paulo" would arrive as "SÃ£o Paulo")."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_link(params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "", False)}
    query["page"] = page
    scheme, host = request.urlparts.scheme, request.urlparts.netloc
    return f"{scheme}://{host}{request.path}?{urlencode(query, doseq=True)}"


def paginate(result, params):
    """Lift the scraper's `pagination` block into the flat shape the hosted
    API returns: count / per_page / current_page / total_pages / next / previous."""
    pagination = result.pop("pagination", None) or {}
    page = _int(pagination.get("page")) or _int(params.get("page")) or 1
    total_pages = max(_int(pagination.get("total_pages")), 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(params, page + 1 if page < total_pages else None),
        "previous": _page_link(params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(schema, fn, paginated, label):
    """Validate, run, map errors: bad params -> 400, missing entity -> 404,
    blocks / upstream failures -> 502, anything else -> 500."""
    raw = query_dict()
    data, error = load_query(schema, raw)
    if error:
        return json_response(error, 400)
    try:
        result = fn(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response({"error": f"built-in rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Blocked as e:
        return json_response({"error": f"built-in blocked the request, retry later: {e}"}, 502)
    except UpstreamError as e:
        return json_response({"error": f"built-in {label} failed: {e}"}, 502)
    except Exception as e:
        return json_response({"error": f"built-in {label} failed: {type(e).__name__}: {e}"}, 500)
    if paginated:
        result = paginate(result, raw)
    return json_response(result)


def mount(path, schema, fn, paginated):
    """Serve a handler at /path and /built-in/path."""
    label = path.strip("/")

    def handler():
        return call(schema, fn, paginated, label)

    handler.__name__ = "built_in_" + label.replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/built-in" + path, method="GET")(handler)


for _path, _schema, _fn, _paginated in ENDPOINTS:
    mount(_path, _schema, _fn, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})

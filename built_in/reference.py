"""/built-in/locations/suggest and /built-in/job-titles/suggest — the
site's own autocompletes (api.builtin.com locationapi / jobsapi)."""
from built_in import parsers as P
from built_in.fetch import gather, get_json


def locations(query, limit=10, resolve=False):
    rows = get_json("/locationapi/suggest/autocomplete", {"SearchText": query, "MaxResults": limit}, label="location suggest")
    rows = rows if isinstance(rows, list) else []
    suggestions = [P.place_suggestion(r) for r in rows][:limit]
    if resolve and suggestions:
        detail = gather({s["place_id"]: (lambda pid=s["place_id"]: get_json("/locationapi/place", {"placeId": pid}, label="place"))
                         for s in suggestions if s["place_id"]}, optional=tuple(s["place_id"] for s in suggestions))
        for s in suggestions:
            s["place"] = P.place(detail.get(s["place_id"])) if isinstance(detail.get(s["place_id"]), dict) else None
    return {"query": query, "count": len(suggestions), "locations": suggestions}


def job_titles(query, limit=10):
    rows = get_json("/jobsapi/jobtitles", {"searchTerm": query}, label="job title suggest")
    titles = [t for t in (P.text(r) for r in (rows if isinstance(rows, list) else [])) if t][:limit]
    return {"query": query, "count": len(titles), "titles": titles}

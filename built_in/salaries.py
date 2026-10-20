"""/built-in/salaries/* — Built In's salary explorer: one job title
nationally or in a metro, a metro overview, and the explorer's own title /
location lists.

Pages: /salaries/us/{title}, /salaries/us/{metro-st}/{title} (the
category-prefixed /salaries/{category}/{title}/{metro-st} links the site
prints redirect there), /salaries/location/{metro-st}. Every page embeds an
Occupation JSON-LD (median / min / max / percentiles) and prints the
averages, the gender and experience sentences and the related-titles table.
"""
import re

from built_in import parsers as P
from built_in import refs
from built_in.fetch import BuiltInNotFound, get_html, get_page


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def _location_slug(location):
    """'chicago-il' | 'Chicago, IL' | 'chicago' -> 'chicago-il' (the
    explorer's own list decides; a metro alias without the state is
    completed from the captured metro table)."""
    from built_in import refdata
    raw = _slug(location)
    if not raw or raw in ("us", "united-states", "national"):
        return None
    if re.search(r"-[a-z]{2}$", raw) or raw == "remote":
        return raw
    metro = refdata.metro(raw)
    if metro and metro.get("state_code"):
        return f"{metro['alias']}-{metro['state_code'].lower()}"
    return raw


def by_title(title, location=None):
    title_slug = _slug(title)
    location_slug = _location_slug(location)
    path = f"/salaries/us/{location_slug}/{title_slug}" if location_slug else f"/salaries/us/{title_slug}"
    status, html, final_url = get_page(path, label="salary page")
    if status != 200 or "/salaries/" not in final_url:
        raise BuiltInNotFound(f"builtin.com has no salary page for '{title}'" + (f" in '{location}'" if location else "")
                              + " (see /built-in/salaries/filters for the titles and locations it covers)")
    page = P.salary_page(html, title_slug=title_slug, location_slug=location_slug)
    if page["base"]["average"] is None and page["base"]["median"] is None:
        raise BuiltInNotFound(f"builtin.com has no salary data for '{title}'" + (f" in '{location}'" if location else ""))
    return page


def by_location(location):
    location_slug = _location_slug(location)
    if not location_slug:
        raise ValueError("location is required (a metro like 'chicago-il' or 'Chicago, IL')")
    status, html, final_url = get_page(f"/salaries/location/{location_slug}", label="salary location page")
    if status != 200:
        raise BuiltInNotFound(f"builtin.com has no salary overview for '{location}' (see /built-in/salaries/filters -> locations)")
    page = P.salary_location_page(html, location_slug=location_slug)
    if not page["titles_by_category"] and not page["by_category"]:
        raise BuiltInNotFound(f"builtin.com has no salary overview for '{location}'")
    return page


def filters(**_):
    html = get_html("/salaries", label="salary explorer")
    return P.salary_filters(html)

"""Built In reference data: the job-board and company-directory filter
vocabularies the site embeds in its pages (`Builtin.jobBoardInit` /
`Builtin.companyDirectoryInit`, captured 2026-10-19 into refdata.json), with
lookups from the public names the /built-in/* params accept to the path
aliases and ids builtin.com uses.

The static copy is the fallback; /built-in/jobs/filters re-reads the live
page (cached) so new industries / metros show up without a deploy.
"""
import json
import os
import re

from built_in.countries import ALPHA2_TO_ALPHA3 as _ALPHA2_TO_ALPHA3

_HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_HERE, "refdata.json"), encoding="utf-8") as _f:
    DATA = json.load(_f)

CATEGORIES = DATA["categories"]
EXPERIENCES = DATA["experiences"]
WORK_MODES = DATA["work_modes"]
COMPANY_SIZES = DATA["company_sizes"]
POSTED_WITHIN = DATA["posted_within"]
SEARCH_AREAS = DATA["search_areas"]
INDUSTRIES = DATA["industries"]
METROS = DATA["metros"]
TECH_STACKS = DATA["tech_stacks"]
PERKS = DATA["perks"]
DIVERSITY = DATA["diversity"]

# the non-US boards the sitemap lists (/jobs/{region}/{country}) -> ISO alpha-3
REGION_CODES = {"eu", "as", "na", "sam", "mena", "oc", "af"}
COUNTRY_BOARDS = {
    "czechia": "CZE", "france": "FRA", "germany": "DEU", "hungary": "HUN", "italy": "ITA",
    "netherlands": "NLD", "poland": "POL", "portugal": "PRT", "romania": "ROU", "spain": "ESP",
    "united-kingdom": "GBR", "ireland": "IRL", "india": "IND", "japan": "JPN", "malaysia": "MYS",
    "philippines": "PHL", "singapore": "SGP", "israel": "ISR", "turkey": "TUR", "canada": "CAN",
    "mexico": "MEX", "australia": "AUS", "new-zealand": "NZL", "brazil": "BRA",
}

# public experience names (what the API accepts) -> site alias
EXPERIENCE_PUBLIC = {
    "internship": "internship", "entry_level": "entry-level", "junior": "junior", "mid_level": "mid-level",
    "senior": "senior", "expert_leader": "expert-leader", "not_specified": "not-specified",
}
EXPERIENCE_FROM_SITE = {
    "Internship": "internship", "Entry-level": "entry_level", "Entry level": "entry_level", "Junior": "junior",
    "Mid-level": "mid_level", "Mid level": "mid_level", "Senior-level": "senior", "Senior": "senior",
    "Expert/Leader": "expert_leader", "Not Specified": "not_specified",
}
WORK_MODE_PUBLIC = {"remote": "remote", "hybrid": "hybrid", "in_office": "office"}
WORK_MODE_FROM_ALIAS = {v: k for k, v in WORK_MODE_PUBLIC.items()}
WORK_MODE_IDS = {"remote": 2, "hybrid": 3, "in_office": 1}
COMPANY_SIZE_PUBLIC = {"1-10": "1-10", "11-50": "11-50", "51-200": "51-200", "201-500": "201-500",
                       "501-1000": "501-1000", "1000+": "1000"}
COMPANY_SIZE_FROM_ALIAS = {v: k for k, v in COMPANY_SIZE_PUBLIC.items()}
POSTED_WITHIN_PUBLIC = {"24h": 1, "3d": 3, "7d": 7, "30d": 30}
POSTED_WITHIN_FROM_DAYS = {v: k for k, v in POSTED_WITHIN_PUBLIC.items()}
RADIUS_MILES = [s["miles"] for s in SEARCH_AREAS]          # 5, 10, 25, 50, 100
SALARY_PERIODS = {"annually": "annual", "annual": "annual", "hourly": "hourly", "monthly": "monthly",
                  "weekly": "weekly", "daily": "daily"}


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def _index(rows, *keys):
    out = {}
    for row in rows:
        for key in keys:
            value = row.get(key)
            if value:
                out.setdefault(_slug(value), row)
    return out


_CATEGORY_INDEX = _index(CATEGORIES, "alias", "name")
_SUBCATEGORY_INDEX = {}
for _cat in CATEGORIES:
    for _sub in _cat["subcategories"]:
        for _key in (_sub.get("alias"), _sub.get("name")):
            if _key:
                _SUBCATEGORY_INDEX.setdefault(_slug(_key), (_cat, _sub))
_INDUSTRY_INDEX = _index(INDUSTRIES, "alias", "name")
_METRO_INDEX = _index(METROS, "alias", "name")
for _metro in METROS:
    # "Chicago, IL" / "chicago il" / "New York" forms
    _METRO_INDEX.setdefault(_slug(f"{_metro['city']} {_metro['state_code']}"), _metro)
    _METRO_INDEX.setdefault(_slug(_metro["city"]), _metro)
_TECH_INDEX = _index(TECH_STACKS, "alias", "name")
_PERK_INDEX = _index(PERKS, "alias", "name")
_DIVERSITY_INDEX = _index(DIVERSITY, "alias", "name")
_EXPERIENCE_ALIASES = {e["alias"] for e in EXPERIENCES}
_SIZE_ALIASES = {s["alias"] for s in COMPANY_SIZES}
_WORK_MODE_ALIASES = {w["alias"] for w in WORK_MODES}


def category(value):
    return _CATEGORY_INDEX.get(_slug(value)) if value else None


def subcategory(value, parent=None):
    """-> (category row, subcategory row) or None. With `parent` the
    subcategory must belong to that category."""
    hit = _SUBCATEGORY_INDEX.get(_slug(value)) if value else None
    if hit and parent and hit[0]["alias"] != parent["alias"]:
        for sub in parent["subcategories"]:
            if _slug(sub["alias"]) == _slug(value) or _slug(sub["name"]) == _slug(value):
                return parent, sub
        return None
    return hit


def industry(value):
    return _INDUSTRY_INDEX.get(_slug(value)) if value else None


def metro(value):
    return _METRO_INDEX.get(_slug(value)) if value else None


def tech_stack(value):
    return _TECH_INDEX.get(_slug(value)) if value else None


def perk(value):
    return _PERK_INDEX.get(_slug(value)) if value else None


def diversity(value):
    return _DIVERSITY_INDEX.get(_slug(value)) if value else None


def is_experience_alias(segment):
    return segment in _EXPERIENCE_ALIASES


def is_size_alias(segment):
    return segment in _SIZE_ALIASES


def is_work_mode_alias(segment):
    return segment in _WORK_MODE_ALIASES


_EXPERIENCE_SLUGS = {}
for _public, _alias in EXPERIENCE_PUBLIC.items():
    _EXPERIENCE_SLUGS[_slug(_alias)] = _public
    _EXPERIENCE_SLUGS[_slug(_public)] = _public
for _site, _public in EXPERIENCE_FROM_SITE.items():
    _EXPERIENCE_SLUGS[_slug(_site)] = _public
for _row in EXPERIENCES:
    _EXPERIENCE_SLUGS.setdefault(_slug(_row["name"]), _EXPERIENCE_SLUGS.get(_slug(_row["alias"])))
    _EXPERIENCE_SLUGS.setdefault(_slug(_row["filter_value"]), _EXPERIENCE_SLUGS.get(_slug(_row["alias"])))
_EXPERIENCE_SLUGS.update({"senior-level": "senior", "mid-level": "mid_level", "entry-level": "entry_level",
                          "expert-leader": "expert_leader", "expert": "expert_leader", "leader": "expert_leader",
                          "intern": "internship", "entry": "entry_level", "mid": "mid_level"})


def experience_public(site_value):
    """'Senior-level' / 'Senior level' / 'senior' / 'Expert/Leader' -> the public name."""
    if not site_value:
        return None
    key = _slug(site_value)
    if key in _EXPERIENCE_SLUGS:
        return _EXPERIENCE_SLUGS[key]
    key = re.sub(r"-\(?\d.*$", "", key)          # "entry-level-0-1-years" -> "entry-level"
    return _EXPERIENCE_SLUGS.get(key)


def alpha3(country_code):
    """ISO alpha-2 ('US') or alpha-3 ('USA') -> alpha-3 (None when unknown)."""
    if not country_code:
        return None
    code = str(country_code).strip().upper()
    if len(code) == 3 and code in _ALPHA2_TO_ALPHA3.values():
        return code
    return _ALPHA2_TO_ALPHA3.get(code)


def alpha2(country_code):
    """ISO alpha-3 ('USA') -> alpha-2 ('US'); an alpha-2 passes through."""
    if not country_code:
        return None
    code = str(country_code).strip().upper()
    if len(code) == 2:
        return code
    for two, three in _ALPHA2_TO_ALPHA3.items():
        if three == code:
            return two
    return None


def country_board(slug):
    """'germany' -> 'DEU' for the /jobs/{region}/{country} board paths."""
    return COUNTRY_BOARDS.get(_slug(slug))

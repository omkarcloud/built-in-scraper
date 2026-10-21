"""Built In normalizers: the job-board cards + embedded criteria, job pages
(JSON-LD JobPosting + HTML), company profile header / tab partials / FAQ
pages / directory cards, the api.builtin.com GraphQL company object and REST
rows, the Nuxt salary pages and article pages -> one clean snake_case shape
per entity.

Output conventions (shared with the other scrapers here): `link` for page
URLs (absolute), `logo` / `image` / `photo` for picture links, `*_count`
for counters, `is_*` / `has_*` for booleans, ISO-8601 for dates
("2026-10-19", "2026-10-19T07:11:17Z"), money as numeric amount + a
separate `currency` (null when the page shows none — job cards print
"174K-274K Annually" with no symbol; the job page's JSON-LD carries the
code), null for missing.

Entity vocabulary:
  job card     {id, slug, title, link, company{name, alias, link, logo},
                posted_text, posted_at (approximate, from "56 Minutes Ago"),
                is_reposted, work_modes[], work_mode_text, location,
                locations[], salary{}, experience_level, industries[],
                summary, top_skills[], is_easy_apply, is_early_applicant,
                is_featured}
  job details  the card fields + employment_type, valid_through,
                applicant_countries, description_html / description_text,
                skills_required, benefits, benefits_highlights, insights,
                team_quotes, apply{}, company{} in full, similar_jobs
  company      the GraphQL object merged with the profile header and the
                benefits / offices / teams partials (companies.py)
  salary       {title, location, currency, base{average, median, min, max,
                percentiles}, additional_cash_average, total_average,
                by_gender, by_experience, most_common_range, related_titles}

Deliberately dropped as noise:
  * job cards: the Alpine x-data / tracking attributes, the "Save"/"Saved"
    toggles, the per-company brand colour of the card border
    (style="border-left: … #0052CB"), the collapse button
  * job pages: the resume-upload / "Am I a good fit" widget, the apply
    form's Salesforce web-to-case ids (jobPostInit.salesforceData), the
    anonymous-user popup, login / signup destinations, the Cloudflare
    e-mail obfuscation of the "Send resume to" address (the browser
    decodes it client-side; it is not in the HTML)
  * GraphQL company: salesforceID, marketSites (region/company id pairs
    kept as `market_region_ids` only), subscription level beyond the name,
    metaTags, the `funding` JSON string's zero rows, perks[] whose
    `details` the API returns empty (names come from the benefits tab),
    easyApplyCategories, elitePageType (the API cannot serialise it)
  * directory cards: the "Create job alert" / save buttons, the slotted
    `my-item` web components, the srcset variants of the photo
  * salary pages: the chart <canvas> elements (the numbers are repeated in
    the sentences below them), the "Add your salary" CTA
  * articles: share buttons, the "Recent Articles" footer rail, the CDN
    `cdn-cgi/image/...` resize prefix is KEPT (it is the only form the
    site serves)
"""
import html as html_lib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlparse

from bs4 import BeautifulSoup

from built_in import refdata, refs
from built_in.values import bool_or_none, first_number, number, strip_html, text, to_int

_BULLET_RE = re.compile(r"\s*[•·|]\s*")
# a K/M suffix never starts a word ("6000 Monthly" is 6000, not 6000M)
_MONEY_RE = re.compile(r"(\d[\d,.]*)\s*([KkMm](?![A-Za-z]))?")
_RANGE_RE = re.compile(r"(\d[\d,.]*\s*(?:[KkMm](?![A-Za-z]))?)\s*[-–]\s*(\d[\d,.]*\s*(?:[KkMm](?![A-Za-z]))?)")
_AGO_RE = re.compile(r"(?:(?P<n>\d+|an?)\s+(?P<unit>minute|hour|day|week|month|year)s?\s+ago)|(?P<yday>yesterday)|(?P<today>today|just now)", re.I)
_DOLLARS_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)\s*([KkMm](?![A-Za-z]))?")
_NUMBERS_RE = re.compile(r"[\d,]+")
_WS_RE = re.compile(r"\s+")


# ---- value helpers ------------------------------------------------------------

def soup(markup):
    return BeautifulSoup(markup or "", "lxml")


def node_text(node):
    """Collapsed text of a bs4 node (None when empty / missing)."""
    if node is None:
        return None
    return text(node.get_text(" ", strip=True))


def money_amount(raw):
    """'174K' -> 174000, '39' -> 39, '1.2M' -> 1200000, '$141,933' -> 141933."""
    if raw is None:
        return None
    match = _MONEY_RE.search(str(raw).replace("$", ""))
    if not match:
        return None
    value = number(match.group(1))
    if value is None:
        return None
    suffix = (match.group(2) or "").lower()
    if suffix == "k":
        value = value * 1000
    elif suffix == "m":
        value = value * 1_000_000
    return number(value)


def salary_text(raw, currency=None):
    """'174K-274K Annually' / '39-53 Hourly' / '150-200 Hourly' ->
    {min, max, period, currency, text} (None when the text carries no pay)."""
    raw = text(raw)
    if not raw or not re.search(r"\d", raw):
        return None
    period = None
    for word, public in refdata.SALARY_PERIODS.items():
        if word in raw.lower():
            period = public
            break
    match = _RANGE_RE.search(raw)
    if match:
        low, high = money_amount(match.group(1)), money_amount(match.group(2))
    else:
        low = high = money_amount(raw)
    return {"min": low, "max": high, "period": period, "currency": currency, "text": raw}


def relative_time(raw, now=None):
    """'Reposted 56 Minutes Ago' -> ('2026-10-19T08:04:00Z' approx, True).
    Day-or-coarser phrases give a date-precision stamp (midnight UTC is
    not implied; the time part is dropped)."""
    raw = text(raw)
    if not raw:
        return None, None
    is_reposted = raw.lower().startswith("reposted")
    now = now or datetime.now(timezone.utc)
    match = _AGO_RE.search(raw)
    if not match:
        return None, is_reposted
    if match.group("today"):
        return now.strftime("%Y-%m-%d"), is_reposted
    if match.group("yday"):
        return (now - timedelta(days=1)).strftime("%Y-%m-%d"), is_reposted
    n = match.group("n").lower()
    n = 1 if n in ("a", "an") else int(n)
    unit = match.group("unit").lower()
    if unit == "minute":
        return (now - timedelta(minutes=n)).strftime("%Y-%m-%dT%H:%M:00Z"), is_reposted
    if unit == "hour":
        return (now - timedelta(hours=n)).strftime("%Y-%m-%dT%H:%M:00Z"), is_reposted
    days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
    return (now - timedelta(days=days)).strftime("%Y-%m-%d"), is_reposted


def work_modes(raw):
    """'In-Office or Remote' -> ['in_office', 'remote']; 'Remote or Hybrid' -> [...]."""
    raw = text(raw)
    if not raw:
        return []
    out = []
    for part in re.split(r"\s+or\s+|,|/", raw):
        key = part.strip().lower().replace("-", " ")
        mode = {"in office": "in_office", "on site": "in_office", "onsite": "in_office", "office": "in_office",
                "remote": "remote", "fully remote": "remote", "hybrid": "hybrid"}.get(key)
        if mode and mode not in out:
            out.append(mode)
    return out


def split_bullets(raw):
    raw = text(raw)
    if not raw:
        return []
    return [p for p in (text(x) for x in _BULLET_RE.split(raw)) if p]


def tooltip_items(title_attr):
    """The site's multi-location tooltip: an HTML fragment in a `title`
    attribute ('<div class=row><div class=col>India</div>…') or '<br/>'
    separated names -> ['India', 'United States']."""
    if not title_attr:
        return []
    fragment = html_lib.unescape(title_attr)
    if "<" in fragment:
        parts = re.split(r"<br\s*/?>|</div>|</li>|</p>", fragment, flags=re.I)
        items = [text(re.sub(r"<[^>]+>", " ", p)) for p in parts]
    else:
        items = [text(p) for p in re.split(r"[|;\n]", fragment)]
    out = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


def parse_count(raw):
    """'5,360 Total Employees' / '10 Offices' -> 5360 / 10."""
    raw = text(raw)
    if not raw:
        return None
    match = _NUMBERS_RE.search(raw.replace("+", ""))
    return to_int(match.group(0)) if match else None


def iso_from_ld(value):
    """'2026-11-18T07:11:17+00:00' -> '2026-11-18T07:11:17Z'; '2026-10-19' stays a date."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def human_date(raw):
    """'Jun. 13, 2024' / 'June 13, 2024' / 'August 27, 2026' -> '2024-06-13'."""
    raw = text(raw)
    if not raw:
        return None
    raw = re.sub(r"^(?:Published|Updated)\s+on\s+", "", raw, flags=re.I).replace(".", "").strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def image_key(link):
    """The file behind a CDN resize link: the same picture served at two
    sizes dedupes to one."""
    if not link:
        return None
    return re.sub(r"/cdn-cgi/image/[^/]+/", "/", link).split("?")[0]


def unique_images(links):
    out, seen = [], set()
    for link in links:
        key = image_key(link)
        if link and key not in seen:
            seen.add(key)
            out.append(link)
    return out


def _img_src(img):
    if img is None:
        return None
    src = img.get("src") or img.get("data-src")
    return refs.absolute(src) if src else None


def _icon_value(root, icon_class):
    """The text next to a FontAwesome icon (<i class="fa-… {icon_class}">):
    the icon's own container when it has text, else the next sibling."""
    icon = root.select_one(f"i.{icon_class}")
    if icon is None:
        return None, None
    container = icon.parent
    value = node_text(container)
    if value:
        return value, container
    sibling = container.find_next_sibling()
    if sibling is not None:
        return node_text(sibling), sibling
    return None, None


def _tooltip_locations(location_node, location_text):
    """The locations of a card / job header: the "N Locations" tooltip list
    (title= or data-bs-title=) when there is one, else the single place."""
    if location_node is not None:
        for holder in [location_node] + location_node.select("[title], [data-bs-title]"):
            raw = holder.get("data-bs-title") or holder.get("title")
            if raw:
                items = tooltip_items(raw)
                if items:
                    return items
    if location_text and not re.fullmatch(r"\d+ Locations?", location_text):
        return [location_text]
    return []


# ---- job cards ------------------------------------------------------------------

def _job_from_anchor(anchor):
    """<a href="/job/{slug}/{id}"> -> (slug, id)."""
    href = anchor.get("href") if anchor is not None else None
    if not href:
        return None, None
    parts = [p for p in href.split("?")[0].split("/") if p]
    if len(parts) >= 3 and parts[0] == "job":
        return parts[1], parts[2]
    return None, None


def _company_from_anchor(anchor):
    href = anchor.get("href") if anchor is not None else None
    alias = refs.company_alias_from_path(href) if href else None
    return alias


def job_card(card, featured_ids=()):
    """One `div[data-id=job-card]` -> a job row."""
    job_id = (card.get("id") or "").replace("job-card-", "") or None
    title_a = card.select_one('a[data-id="job-card-title"]') or card.select_one('a[href^="/job/"]')
    slug, link_id = _job_from_anchor(title_a)
    job_id = job_id or link_id
    company_a = card.select_one('a[data-id="company-title"]') or card.select_one('a[href^="/company/"]')
    logo = card.select_one('img[data-id="company-img"]') or card.select_one('a[href^="/company/"] img')
    posted_text, _ = _icon_value(card, "fa-clock")
    posted_text = text(re.sub(r"\bSaved\b", "", posted_text or "")) if posted_text else None
    posted_at, is_reposted = relative_time(posted_text)
    mode_text, _ = _icon_value(card, "fa-house-building")
    location_text, location_node = _icon_value(card, "fa-location-dot")
    locations = _tooltip_locations(location_node, location_text)
    salary_raw, _ = _icon_value(card, "fa-sack-dollar")
    experience_raw, _ = _icon_value(card, "fa-trophy")
    drop = card.select_one(f'#drop-data-{job_id}') if job_id else None
    industries, summary, top_skills = [], None, []
    if drop is not None:
        skills_label = drop.find(string=re.compile(r"Top Skills", re.I))
        if skills_label is not None:
            holder = skills_label.find_parent().find_next_sibling("span") or skills_label.find_parent().parent
            top_skills = [t for t in (node_text(s) for s in holder.select("span span, span")) if t and not t.lower().startswith("top skills")]
            top_skills = list(dict.fromkeys(top_skills))
        for div in drop.find_all("div"):
            t = node_text(div)
            if not t or div.find("div") is not None:
                continue
            if "•" in t and not industries:
                industries = split_bullets(t)
            elif summary is None and len(t) > 40 and "top skills" not in t.lower() and not re.search(r"(Annually|Hourly)$", t):
                summary = t
    card_text = card.get_text(" ", strip=True)
    return {
        "id": to_int(job_id),
        "slug": slug,
        "title": node_text(title_a),
        "link": refs.job_link(slug, job_id),
        "company": {
            "name": node_text(company_a),
            "alias": _company_from_anchor(company_a),
            "link": refs.company_link(_company_from_anchor(company_a)),
            "logo": _img_src(logo),
        },
        "posted_text": posted_text,
        "posted_at": posted_at,
        "is_reposted": is_reposted,
        "work_modes": work_modes(mode_text),
        "work_mode_text": text(mode_text),
        "location": location_text,
        "locations": locations,
        "salary": salary_text(salary_raw),
        "experience_level": refdata.experience_public(text(experience_raw)),
        "industries": industries,
        "summary": summary,
        "top_skills": top_skills,
        "is_easy_apply": "Easy Apply" in card_text,
        "is_early_applicant": "Early Applicant" in card_text,
    }


def job_cards(markup):
    """Every job card of a job-board page or its ?handler=SearchResults
    partial, in page order."""
    doc = soup(markup)
    rows = []
    for card in doc.select('[data-id="job-card"]'):
        row = job_card(card)
        if row["id"] or row["link"]:
            rows.append(row)
    return rows


def last_page(markup):
    """The highest page number in the page's pagination links (1 when the
    page has results but no pagination, 0 when it has neither)."""
    doc = soup(markup)
    pages = []
    for a in doc.select('#pagination a[href*="page="], nav a[href*="page="]'):
        for key, value in parse_qsl(urlparse(a.get("href", "")).query):
            if key == "page" and value.isdigit():
                pages.append(int(value))
    if pages:
        return max(pages)
    return 1 if doc.select_one('[data-id="job-card"]') else 0


def applied_criteria(criteria):
    """jobBoardInit.criteria -> the filters the site actually applied."""
    c = criteria if isinstance(criteria, dict) else {}
    modes = [refdata.WORK_MODE_FROM_ALIAS.get(w["alias"]) for w in refdata.WORK_MODES
             if str(w["id"]) in str(c.get("remotePreferences") or "").split(",")]
    category = next((row for row in refdata.CATEGORIES if row["id"] == to_int(c.get("categories"))), None)
    sub_ids = [to_int(s) for s in str(c.get("subCategories") or "").split(",") if to_int(s)]
    subcategories = []
    for row in refdata.CATEGORIES:
        for sub in row["subcategories"]:
            if sub["id"] in sub_ids:
                subcategories.append(sub["alias"])
    industry_ids = [to_int(s) for s in str(c.get("industry") or "").split(",") if to_int(s)]
    industries = [row["alias"] for row in refdata.INDUSTRIES if row["id"] in industry_ids]
    sizes = [refdata.COMPANY_SIZE_FROM_ALIAS.get(s, s) for s in str(c.get("companySizes") or "").split(",") if s]
    experiences = [refdata.experience_public(e) or e for e in str(c.get("experiences") or "").split(",") if e]
    radius = first_number(str(c.get("searchArea") or ""))
    return {
        "query": text(c.get("search")),
        "work_modes": [m for m in modes if m],
        "category": category["alias"] if category else None,
        "subcategories": subcategories,
        "experience_levels": experiences,
        "industries": industries,
        "company_sizes": sizes,
        "posted_within": refdata.POSTED_WITHIN_FROM_DAYS.get(to_int(c.get("daysSinceUpdated"))),
        "early_applicant_only": bool(c.get("earlyApplicant")),
        "company_id": to_int(c.get("companyId")),
        "skills": [s for s in str(c.get("skills") or "").split(",") if s] or [],
        "city": text(c.get("city")),
        "state": text(c.get("state")),
        "country": text(c.get("country")),
        "radius_miles": to_int(radius),
        "all_locations": bool(c.get("allLocations")),
        "latitude": c.get("latitude"),
        "longitude": c.get("longitude"),
    }


def skill_facets(init):
    rows = (init or {}).get("jobSkillsFilterOptions") or []
    return [{"skill": text(r.get("skill")), "jobs_count": to_int(r.get("count"))} for r in rows if isinstance(r, dict) and text(r.get("skill"))]


# ---- job page --------------------------------------------------------------------

def _ld_salary(ld):
    base = (ld or {}).get("baseSalary")
    if not isinstance(base, dict):
        return None
    value = base.get("value") if isinstance(base.get("value"), dict) else {}
    unit = (value.get("unitText") or "").upper()
    period = {"HOUR": "hourly", "YEAR": "annual", "MONTH": "monthly", "WEEK": "weekly", "DAY": "daily"}.get(unit)
    low = number(value.get("minValue")) if value.get("minValue") not in (None, "") else number(value.get("value"))
    high = number(value.get("maxValue")) if value.get("maxValue") not in (None, "") else low
    return {"min": low, "max": high, "period": period, "currency": text(base.get("currency")), "text": None}


def _ld_countries(ld):
    reqs = (ld or {}).get("applicantLocationRequirements")
    rows = reqs if isinstance(reqs, list) else ([reqs] if isinstance(reqs, dict) else [])
    return [text(r.get("name")) for r in rows if isinstance(r, dict) and text(r.get("name"))]


def _ld_locations(ld):
    rows = (ld or {}).get("jobLocation")
    rows = rows if isinstance(rows, list) else ([rows] if isinstance(rows, dict) else [])
    out = []
    for row in rows:
        address = row.get("address") if isinstance(row, dict) else None
        if not isinstance(address, dict):
            continue
        out.append({k: text(address.get(src)) for k, src in (("street", "streetAddress"), ("city", "addressLocality"),
                                                             ("state", "addressRegion"), ("postal_code", "postalCode"),
                                                             ("country", "addressCountry"))})
    return out


def _heading(doc, pattern):
    """The first h1-h4 (or label div) whose text matches `pattern`."""
    regex = re.compile(pattern, re.I)
    for node in doc.find_all(["h1", "h2", "h3", "h4"]):
        if regex.search(node.get_text(" ", strip=True) or ""):
            return node
    return None


def _label_div(doc, label):
    for node in doc.find_all("div"):
        if node.find("div") is None and (node.get_text(strip=True) or "") == label:
            return node
    return None


def _section_after(node):
    """The container that follows a heading: the heading's parent's next
    sibling, else the heading's own parent."""
    if node is None:
        return None
    for candidate in (node.find_next_sibling(), node.parent.find_next_sibling() if node.parent else None,
                      node.parent.parent.find_next_sibling() if node.parent and node.parent.parent else None):
        if candidate is not None and candidate.get_text(strip=True):
            return candidate
    return node.parent


def _list_after_heading(doc, pattern):
    heading = _heading(doc, pattern)
    if heading is None:
        return []
    ul = heading.find_next("ul")
    if ul is None:
        return []
    return [t for t in (node_text(li) for li in ul.find_all("li", recursive=False)) if t]


def _titled_items(ul):
    """<li><div><span>Title</span><span>—</span><span>Text</span></div></li> rows."""
    out = []
    for li in ul.find_all("li", recursive=False) if ul is not None else []:
        spans = [node_text(s) for s in li.find_all("span")]
        spans = [s for s in spans if s and s not in ("—", "-", "–")]
        if not spans:
            continue
        title = spans[0].rstrip(":") if len(spans) > 1 else None
        body = " ".join(spans[1:]) if len(spans) > 1 else spans[0]
        out.append({"title": title, "text": body})
    return out


def _team_quotes(doc):
    heading = _heading(doc, r"What the Team is Saying")
    if heading is None:
        return []
    section = heading.find_parent("div")
    while section is not None and not section.select("template, p"):
        section = section.parent
    out = []
    seen = set()
    for template in (section.select("template") if section is not None else []):
        block = soup(template.decode_contents())   # bs4 hides template strings from get_text
        quote = node_text(block.find("p"))
        img = block.find("img")
        labels = [t for t in (node_text(d) for d in block.find_all("div") if d.find("div") is None and d.find("p") is None) if t]
        name = labels[0] if labels else None
        title = labels[1] if len(labels) > 1 else None
        key = (name, quote)
        if quote and key not in seen:
            seen.add(key)
            out.append({"name": name, "title": title, "quote": quote, "photo": _img_src(img)})
    return out


def _company_block(doc):
    """'The Company' panel of a job page: HQ / size / founded facts, What We
    Do, Why Work With Us, gallery, teams and the offices overview."""
    label = _label_div(doc, "The Company")
    panel = label.parent if label is not None else None
    out = {"hq": None, "employees_count": None, "year_founded": None, "what_we_do": None,
           "why_work_with_us": None, "gallery": [], "teams": [], "workplace": None, "offices": []}
    if panel is None:
        return out
    full = panel.get_text(" | ", strip=True)
    match = re.search(r"HQ:\s*([^|]+)", full)
    out["hq"] = text(match.group(1)) if match else None
    match = re.search(r"([\d,]+)\s+Employees", full)
    out["employees_count"] = to_int(match.group(1)) if match else None
    match = re.search(r"Year Founded:\s*(\d{4})", full)
    out["year_founded"] = to_int(match.group(1)) if match else None
    for key, pattern in (("what_we_do", r"^What We Do$"), ("why_work_with_us", r"^Why Work With Us$")):
        heading = _heading(panel, pattern)
        if heading is not None:
            nxt = heading.find_next_sibling()
            out[key] = node_text(nxt) if nxt is not None and nxt.name in ("p", "div") else None
    gallery = _heading(panel, r"^Gallery$")
    if gallery is not None:
        holder = gallery.find_next_sibling()
        out["gallery"] = unique_images(_img_src(i) for i in (holder.find_all("img") if holder else []))
    teams = _heading(panel, r"\bTeams$")
    if teams is not None:
        track = panel.select_one("#teamsSlider-blaze-track")
        for item in (track.find_all("div", recursive=False) if track is not None else []):
            name = node_text(item.find("span"))
            if name and name.lower() != "about our teams":
                out["teams"].append({"name": name, "image": _img_src(item.find("img"))})
    offices = _heading(panel, r"\bOffices$")
    if offices is not None:
        section = offices.find_next("section")
        if section is not None:
            paragraphs = [node_text(p) for p in section.find_all("p", recursive=False)]
            paragraphs = [p for p in paragraphs if p]
            onsite = re.search(r"Typical time on-site:\s*\|?\s*([^|]+)", section.get_text(" | ", strip=True))
            out["workplace"] = {
                "type": paragraphs[0] if paragraphs else None,
                "summary": paragraphs[1] if len(paragraphs) > 1 else None,
                "description": paragraphs[2] if len(paragraphs) > 2 else None,
                "time_onsite": text(onsite.group(1)) if onsite else None,
            }
            track = section.select_one("#officesSlider-blaze-track")
            for item in (track.find_all("div", recursive=False) if track is not None else []):
                spans = [t for t in (node_text(s) for s in item.find_all("span")) if t]
                if not spans:
                    continue
                is_hq = spans[0].upper() == "HQ"
                name = spans[1] if is_hq and len(spans) > 1 else spans[0]
                out["offices"].append({"name": name, "is_headquarters": is_hq})
    return out


def _similar_jobs(doc):
    heading = _heading(doc, r"^Similar Jobs$")
    if heading is None:
        return []
    section = heading
    for _ in range(6):
        section = section.parent
        if section is None or len(section.select('a[href^="/job/"]')) >= 1 and section.name in ("div", "section"):
            break
    out = []
    seen = set()
    anchors = section.select('a[href^="/job/"]') if section is not None else []
    titled = {}
    for a in anchors:
        _, jid = _job_from_anchor(a)
        if jid and node_text(a) and jid not in titled:
            titled[jid] = a
    for anchor in anchors:
        slug, job_id = _job_from_anchor(anchor)
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        anchor = titled.get(job_id, anchor)
        card = anchor.find_parent("div", id="main")
        if card is None:
            card = anchor
            for _ in range(6):
                if card.parent is None:
                    break
                card = card.parent
                if card.select_one('a[href^="/company/"]') is not None and card.find("i") is not None:
                    break
        company_a = card.select_one('a[href^="/company/"]')
        card_text = card.get_text(" | ", strip=True)
        mode = next((m for m in ("In-Office or Remote", "Remote or Hybrid", "In-Office or Hybrid", "Remote", "Hybrid", "In-Office")
                     if f"| {m} |" in f"| {card_text} |"), None)
        employees = re.search(r"([\d,]+)\s+Employees", card_text)
        industries_text = next((t for t in card_text.split(" | ") if "•" in t), None)
        location_text, location_node = _icon_value(card, "fa-location-dot")
        locations = _tooltip_locations(location_node, location_text)
        out.append({
            "id": to_int(job_id), "slug": slug, "title": node_text(anchor), "link": refs.job_link(slug, job_id),
            "company": {"name": node_text(company_a.find(["h2", "h3", "span"]) or company_a) if company_a else None,
                        "alias": _company_from_anchor(company_a), "link": refs.company_link(_company_from_anchor(company_a)),
                        "logo": _img_src(card.select_one('a[href^="/company/"] img'))},
            "industries": split_bullets(industries_text) if industries_text else [],
            "work_modes": work_modes(mode), "work_mode_text": mode,
            "location": location_text, "locations": locations or ([location_text] if location_text and "Location" not in location_text else []),
            "employees_count": to_int(employees.group(1)) if employees else None,
        })
    return out


def _similar_companies(doc):
    heading = _heading(doc, r"^Similar Companies Hiring$")
    if heading is None:
        return []
    section = heading
    for _ in range(6):
        section = section.parent
        if section is None or len(section.select('a[href^="/company/"]')) >= 1:
            break
    out = []
    seen = set()
    for anchor in (section.select('a[href^="/company/"]') if section is not None else []):
        alias = _company_from_anchor(anchor)
        if not alias or alias in seen:
            continue
        card = anchor
        for _ in range(5):
            if card.parent is None:
                break
            card = card.parent
            if re.search(r"Employees", card.get_text(" ", strip=True) or ""):
                break
        card_text = card.get_text(" | ", strip=True)
        name = node_text(anchor.find(["h2", "h3", "span"]) or anchor)
        if not name:
            continue
        seen.add(alias)
        employees = re.search(r"([\d,]+)\s+Employees", card_text)
        industries_text = next((t for t in card_text.split(" | ") if "•" in t), None)
        location_text, _ = _icon_value(card, "fa-location-dot")
        out.append({"name": name, "alias": alias, "link": refs.company_link(alias),
                    "logo": _img_src(card.find("img")), "industries": split_bullets(industries_text) if industries_text else [],
                    "location": location_text, "employees_count": to_int(employees.group(1)) if employees else None})
    return out


def job_page(markup, *, slug=None, job_id=None, init=None, ld=None):
    """A /job/{slug}/{id} page -> the job in full."""
    doc = soup(markup)
    init = init or {}
    job = init.get("job") if isinstance(init.get("job"), dict) else {}
    ld = ld or {}
    job_id = str(job.get("id") or job_id or "")
    header = doc.select_one(f'div[id="{job_id}"]') if job_id else None
    header = header or doc.select_one("main") or doc
    # the header block = the h1's ancestors up to (not including) the one that
    # also holds "The Role"; the job's div#id wraps the whole page, similar
    # jobs included, so a page-wide lookup picks up other jobs' salary,
    # location or industries whenever this job lacks one
    top = header.find("h1") or header
    while top.parent is not None and top is not header and top.parent is not header \
            and "The Role" not in top.parent.get_text(" ", strip=True):
        top = top.parent
    title = node_text(header.find("h1")) or text(ld.get("title")) or text(job.get("title"))
    company_a = next((a for a in top.select('a[href^="/company/"]') if node_text(a)), None) or top.select_one('a[href^="/company/"]')
    company_alias = _company_from_anchor(company_a)
    org = ld.get("hiringOrganization") if isinstance(ld.get("hiringOrganization"), dict) else {}
    if not company_alias:
        company_alias = refs.company_alias_from_path(org.get("sameAs"))
    logo = top.select_one('a[href^="/company/"] img')
    ld_logo = org.get("logo", {}).get("url") if isinstance(org.get("logo"), dict) else None
    posted_text, _ = _icon_value(top, "fa-clock")
    posted_text = text(re.sub(r"\bSaved\b", "", posted_text or "")) if posted_text else None
    posted_at, is_reposted = relative_time(posted_text)
    mode_text, _ = _icon_value(top, "fa-house-building")
    location_text, location_node = _icon_value(top, "fa-location-dot")
    locations = _tooltip_locations(location_node, location_text)
    salary_raw, _ = _icon_value(top, "fa-sack-dollar")
    experience_raw, _ = _icon_value(top, "fa-trophy")
    salary = _ld_salary(ld)
    shown = salary_text(salary_raw, currency=(salary or {}).get("currency"))
    if salary and shown:
        salary["text"] = shown["text"]
        salary["period"] = salary["period"] or shown["period"]
    elif shown:
        salary = shown
    top_text = top.get_text(" | ", strip=True)
    industries_text = next((t for t in top_text.split(" | ") if "•" in t), None)
    ld_industry = ld.get("industry")
    if isinstance(ld_industry, str):
        ld_industry = [ld_industry]
    industries = [i for i in (text(x) for x in (ld_industry or [])) if i] if isinstance(ld_industry, list) else []
    if not industries and industries_text:
        industries = split_bullets(industries_text)
    tagline = None
    if industries_text:
        node = top.find(string=re.compile(re.escape(industries_text.split(" • ")[0])))
        if node is not None:
            nxt = node.find_parent("div").find_next_sibling("div") if node.find_parent("div") else None
            tagline = node_text(nxt) if nxt is not None else None
    body_div = doc.select_one(f'#job-post-body-{job_id}') if job_id else None
    body_div = body_div or doc.select_one('[id^="job-post-body-"]')
    description_html = body_div.decode_contents().strip() if body_div is not None else (ld.get("description") or None)
    summary = None
    marker = doc.find(string=re.compile(r"Summary Generated by Built In"))
    if marker is not None:
        block = marker.find_parent("div")
        for _ in range(4):
            if block is None:
                break
            prev = block.find_previous_sibling("div")
            if prev is not None and node_text(prev):
                summary = node_text(prev)
                break
            block = block.parent
    benefits_heading = _heading(doc, r"Compensation & Benefits Highlights|Benefits Highlights")
    insights = []
    seen_topics = set()
    for a in doc.select('a[href*="/faq/"]'):
        href = a.get("href") or ""
        topic = href.rstrip("/").rsplit("/", 1)[-1]
        if topic in seen_topics:
            continue
        seen_topics.add(topic)
        insights.append({"topic": topic, "title": node_text(a), "link": refs.absolute(href)})
    apply_url = text(job.get("applyUrl"))
    apply_type = "easy_apply" if job.get("isEasyApply") else ("external" if apply_url else "on_site_login")
    company_block = _company_block(doc)
    return {
        "id": to_int(job_id) or to_int(ld.get("identifier", {}).get("value") if isinstance(ld.get("identifier"), dict) else None),
        "slug": slug,
        "title": title,
        "link": refs.job_link(slug, job_id) if slug and job_id else None,
        "company": {
            "name": node_text(company_a.find(["h2", "h3", "span"]) or company_a) if company_a is not None else (text(org.get("name")) or text(job.get("companyName"))),
            "alias": company_alias,
            "link": refs.company_link(company_alias),
            "logo": _img_src(logo) or refs.absolute(ld_logo),
            "tagline": tagline,
            "industries": industries,
            **company_block,
        },
        "posted_text": posted_text,
        "posted_at": iso_from_ld(ld.get("datePosted")) or posted_at,
        "is_reposted": is_reposted,
        "valid_through": iso_from_ld(ld.get("validThrough")),
        "employment_type": text(ld.get("employmentType")),
        "experience_level": refdata.experience_public(text(experience_raw)),
        "work_modes": work_modes(mode_text),
        "work_mode_text": text(mode_text),
        "is_remote_eligible": (ld.get("jobLocationType") == "TELECOMMUTE") or ("remote" in work_modes(mode_text)),
        "location": location_text,
        "locations": locations,
        "location_addresses": _ld_locations(ld),
        "applicant_countries": _ld_countries(ld),
        "salary": salary,
        "summary": summary,
        "description_html": description_html,
        "description_text": strip_html(description_html),
        "skills_required": _list_after_heading(doc, r"^Skills Required$"),
        "benefits": [b for b in (text(x) for x in (ld.get("jobBenefits") or [])) if b] if isinstance(ld.get("jobBenefits"), list) else [],
        "benefits_highlights": _titled_items(benefits_heading.find_next("ul")) if benefits_heading is not None else [],
        "insights": insights,
        "team_quotes": _team_quotes(doc),
        "apply": {
            "type": apply_type,
            # Built In's own apply redirect; it reveals the employer's ATS page
            # to signed-in visitors only (anonymous hits bounce back to the job)
            "link": refs.absolute(apply_url) if apply_url else None,
            "button_text": text(job.get("applyText")),
            "is_easy_apply": bool(job.get("isEasyApply")),
            "is_direct_apply": bool_or_none(ld.get("directApply")),
            "requires_login": (not apply_url and not job.get("isEasyApply")) or "ApplyRedirect" in (apply_url or ""),
        },
        "similar_jobs": _similar_jobs(doc),
        "similar_companies": _similar_companies(doc),
    }


# ---- company pages ----------------------------------------------------------------

def company_header(markup):
    """The profile page's header: name, logo, HQ, offices, size, founded,
    website, live job count, plus companyProfileInit's ids."""
    doc = soup(markup)
    main = doc.select_one("main") or doc
    h1 = main.find("h1")
    logo = None
    if h1 is not None:
        picture = h1.find_previous("img")
        logo = _img_src(picture)
    full = main.get_text(" | ", strip=True)
    hq = None
    match = re.search(r"\| HQ \| ([^|]+) \|", full)
    if match:
        hq = text(match.group(1))
    offices_count = None
    match = re.search(r"Total Offices:\s*\|?\s*([\d,]+)", full)
    if match:
        offices_count = to_int(match.group(1))
    office_names = []
    tooltip = main.find(lambda tag: tag.name == "span" and tag.get("title") and "Total Offices" in (tag.parent.get_text() if tag.parent else ""))
    if tooltip is not None:
        office_names = tooltip_items(tooltip.get("title"))
    employees = re.search(r"([\d,]+)\s+Total Employees", full)
    founded = re.search(r"Year Founded:\s*(\d{4})", full)
    website_a = main.find("a", string=re.compile(r"View Website"))
    website = refs.strip_tracking(website_a.get("href")) if website_a is not None else None
    jobs_count = None
    for a in main.select('a[href*="companyId="], a[href$="/jobs"]'):
        match = re.search(r"View All ([\d,]+) Jobs", a.get_text(" ", strip=True) or "")
        if match:
            jobs_count = to_int(match.group(1))
            break
    if jobs_count is None:
        nav = main.select_one("#page-nav-container")
        if nav is not None:
            match = re.search(r"Jobs\s*\|?\s*([\d,]+)", nav.get_text(" | ", strip=True))
            jobs_count = to_int(match.group(1)) if match else None
    return {
        "name": node_text(h1),
        "logo": logo,
        "hq": hq,
        "offices_count": offices_count,
        "office_names": office_names,
        "employees_count": to_int(employees.group(1)) if employees else None,
        "year_founded": to_int(founded.group(1)) if founded else None,
        "website": website,
        "jobs_count": jobs_count,
    }


def company_overview(markup):
    """The Overview tab partial: industry links, tagline, description,
    gallery (images + YouTube), recent jobs, the offices overview."""
    doc = soup(markup)
    industries = []
    for a in doc.select('a[href^="/companies/type/"]'):
        name = node_text(a)
        if name:
            industries.append({"name": name, "alias": (a.get("href") or "").rstrip("/").rsplit("/", 1)[-1].replace("-companies", ""),
                               "link": refs.absolute(a.get("href"))})
    tagline = description = None
    first_industry = doc.select_one('a[href^="/companies/type/"]')
    if first_industry is not None:
        holder = first_industry.parent
        nxt = holder.find_next_sibling("div")
        tagline = node_text(nxt) if nxt is not None else None
        nxt2 = nxt.find_next_sibling("div") if nxt is not None else None
        description = node_text(nxt2) if nxt2 is not None else None
    gallery = []
    videos = []
    gallery = unique_images(src for src in (_img_src(img) for img in doc.select("[data-gallery-id] img, [data-lightbox-carousel-id] img"))
                            if src and "img.youtube.com" not in src)
    for frame in doc.select("iframe[src*='youtube.com/embed']"):
        src = frame.get("src")
        if src and src not in videos:
            videos.append(src)
    jobs = []
    track = doc.select_one("#jobsSlider-blaze-track")
    for anchor in (track.select('a[href^="/job/"]') if track is not None else []):
        slug, job_id = _job_from_anchor(anchor)
        card = anchor.find_parent("div", id="main") or anchor.parent
        mode_text, _ = _icon_value(card, "fa-house-building")
        location_text, _ = _icon_value(card, "fa-location-dot")
        jobs.append({"id": to_int(job_id), "slug": slug, "title": node_text(anchor), "link": refs.job_link(slug, job_id),
                     "work_modes": work_modes(mode_text), "work_mode_text": text(mode_text), "location": location_text})
    view_all = doc.select_one('a[href*="companyId="]')
    company_id = None
    if view_all is not None:
        match = re.search(r"companyId=(\d+)", view_all.get("href") or "")
        company_id = to_int(match.group(1)) if match else None
    return {"company_id": company_id, "industries": industries, "tagline": tagline, "description": description,
            "gallery": gallery, "videos": videos, "recent_jobs": jobs}


def benefits_tab(markup):
    """The Benefits tab partial -> overview text and the perks grouped by
    section (Compensation + Benefits, Company Culture, …) and category
    (Retirement Benefits + Financial Planning, …)."""
    doc = soup(markup)
    overview = None
    h1 = doc.find("h1")
    if h1 is not None:
        p = h1.find_next_sibling("p")
        overview = node_text(p) if p is not None else None
    sections = []
    total = 0
    for section in doc.select("div[id] > h2"):
        holder = section.parent
        categories = []
        for h3 in holder.find_all("h3"):
            name = node_text(h3)
            if name is None:
                continue
            collapse = h3.find_next_sibling("div")
            perks = [t for t in (node_text(p) for p in (collapse.find_all("p") if collapse is not None else [])) if t]
            total += len(perks)
            categories.append({"name": name.replace("+", "&") if " + " in name else name, "perks": perks})
        if categories:
            name = node_text(section)
            sections.append({"name": name.replace(" + ", " & ") if name else None, "slug": holder.get("id"), "categories": categories})
    return {"overview": overview, "perks_count": total, "sections": sections}


def offices_tab(markup):
    """The Offices tab partial -> the workplace policy and every office with
    its address and the "jobs at this office" scope."""
    doc = soup(markup)
    h1 = doc.find("h1")
    summary = node_text(h1.find_next_sibling("p")) if h1 is not None else None
    paragraphs = [node_text(p) for p in (h1.find_next_siblings("p") if h1 is not None else [])]
    paragraphs = [p for p in paragraphs if p]
    workplace = {"type": None, "summary": None, "description": None}
    if len(paragraphs) > 1:
        workplace = {"type": paragraphs[1], "summary": paragraphs[2] if len(paragraphs) > 2 else None,
                     "description": paragraphs[3] if len(paragraphs) > 3 else None}
    match = re.search(r"headquartered in (.+?) and has (\d+) office locations", summary or "")
    us_names = set()
    us_heading = _heading(doc, r"U\.S\. Office Locations")
    if us_heading is not None:
        holder = us_heading.find_next_sibling("div")
        us_names = {(a.get("href") or "").lstrip("#") for a in (holder.select("a[href^='#']") if holder is not None else [])}
    offices = []
    for block in doc.select("div[id]"):
        office_id = block.get("id")
        if not office_id or not office_id.isdigit():
            continue
        name = node_text(block.find("h3"))
        is_hq = any((node_text(d) or "").upper() == "HQ" for d in block.find_all("div") if d.find("div") is None and d.find("h3") is None)
        paragraphs_here = [node_text(p) for p in block.find_all("p")]
        paragraphs_here = [p for p in paragraphs_here if p]
        jobs_a = block.find("a", href=re.compile(r"companyId="))
        jobs_href = jobs_a.get("href") if jobs_a is not None else None
        scope = dict(parse_qsl(urlparse(jobs_href).query)) if jobs_href else {}
        frame = block.find("iframe")
        map_query = None
        if frame is not None:
            for key, value in parse_qsl(urlparse(frame.get("src") or "").query):
                if key == "q":
                    map_query = text(value)
        address = next((p for p in paragraphs_here if re.search(r"\d", p) and len(p) < 160), None)
        description = next((p for p in paragraphs_here if p != address), None)
        offices.append({
            "id": to_int(office_id), "name": name, "is_headquarters": is_hq, "is_us": office_id in us_names,
            "address": address or map_query, "description": description,
            "city": text(scope.get("city")), "state": text(scope.get("state")), "country": text(scope.get("country")),
            "jobs_link": refs.absolute(jobs_href),
        })
    return {"summary": summary, "headquarters": text(match.group(1)) if match else None,
            "offices_count": to_int(match.group(2)) if match else len(offices) or None,
            "workplace": workplace, "offices": offices}


def teams_tab(markup):
    """The Teams tab partial -> [{name, image, description}] (best effort:
    the page is a free-form showcase)."""
    doc = soup(markup)
    out = []
    seen = set()
    for anchor in doc.select('a[href*="/teams/"]'):
        href = anchor.get("href") or ""
        name = node_text(anchor)
        if not name or name.lower() == "learn more" or href in seen:
            continue
        seen.add(href)
        block = anchor.find_parent("div", id=True) or anchor.parent
        out.append({"name": name, "slug": href.rstrip("/").rsplit("/", 1)[-1], "link": refs.absolute(href),
                    "image": _img_src(block.find("img")), "description": node_text(block.find("p"))})
    return out


def faq_page(markup, topic=None):
    """A /company/{alias}/faq/{topic} insights page."""
    doc = soup(markup)
    panel = doc.select_one("#tab-partial") or doc.select_one("main") or doc
    h1 = panel.find("h1")
    updated = None
    if h1 is not None:
        nxt = h1.find_next_sibling("div")
        updated = human_date(node_text(nxt)) if nxt is not None else None
    disclaimer = None
    for p in panel.find_all("p"):
        t = node_text(p)
        if t and t.startswith("This page summarizes"):
            disclaimer = t
            break
    question_h = next((h for h in panel.find_all("h2") if (node_text(h) or "").endswith("?")), None)
    question = node_text(question_h)
    summary = None
    if question_h is not None:
        holder = question_h.parent.find_next_sibling("div")
        first = holder.find("span") if holder is not None else None
        summary = node_text(first)
    key_h = _heading(panel, r"^Key Insight")
    key_insight = node_text(key_h.find_next_sibling("span")) if key_h is not None else None

    def items_after(pattern):
        heading = _heading(panel, pattern)
        if heading is None:
            return []
        ul = heading.find_next("ul")
        return _titled_items(ul)

    related = []
    for a in panel.select('a[href*="/faq/"]'):
        href = a.get("href") or ""
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        if slug != topic and slug not in {r["topic"] for r in related}:
            related.append({"topic": slug, "title": node_text(a), "link": refs.absolute(href)})
    return {
        "topic": topic,
        "title": node_text(h1),
        "updated_on": updated,
        "question": question,
        "summary": summary,
        "key_insight": key_insight,
        "evidence": items_after(r"^Evidence in Action"),
        "positive_themes": items_after(r"^Positive Themes"),
        "considerations": items_after(r"^Considerations"),
        "disclaimer": disclaimer,
        "related_insights": related,
    }


def directory_cards(markup):
    """The /companies directory cards."""
    doc = soup(markup)
    out = []
    seen = set()
    for card in doc.select('div[class*="company-card"]'):
        title_a = card.select_one('a[data-track-id="title"]') or card.select_one('a[href^="/company/"] h2')
        if title_a is not None and title_a.name == "h2":
            title_a = title_a.parent
        alias = _company_from_anchor(title_a)
        if not alias or alias in seen:
            continue
        seen.add(alias)
        company_id = to_int(card.get("data-company-id") or (title_a.get("data-company-id") if title_a else None))
        if company_id is None:
            holder = card.select_one("[data-company-id]")
            company_id = to_int(holder.get("data-company-id")) if holder is not None else None
        industries_div = title_a.parent.find_next_sibling("div") if title_a is not None and title_a.parent else None
        logo = card.select_one('a[data-track-id="logo"] img') or card.select_one("img")
        photo = card.select_one('img[data-track-id="photo"]')
        full = card.get_text(" | ", strip=True)
        offices = re.search(r"(\d+)\s+Offices?", full)
        employees = re.search(r"([\d,]+)\s+Employees", full)
        benefits = re.search(r"(\d+)\s+Benefits", full)
        description = node_text(card.find("p"))
        out.append({
            "id": company_id, "name": node_text(title_a.find("h2") or title_a) if title_a is not None else None,
            "alias": alias, "link": refs.company_link(alias), "logo": _img_src(logo), "photo": _img_src(photo),
            "industries": split_bullets(node_text(industries_div)) if industries_div is not None else [],
            "offices_count": to_int(offices.group(1)) if offices else None,
            "employees_count": to_int(employees.group(1)) if employees else None,
            "benefits_count": to_int(benefits.group(1)) if benefits else None,
            "is_hiring": "Hiring Now" in full,
            "is_featured": (card.select_one('[data-featured="true"]') is not None),
            "description": description,
            "benefits_link": refs.absolute(f"/company/{alias}/benefits"),
            "jobs_link": refs.absolute(f"/company/{alias}/jobs"),
        })
    return out


def directory_criteria(init):
    c = (init or {}).get("criteria") if isinstance(init, dict) else {}
    c = c or {}
    size_aliases = [s for s in str(c.get("companySizes") or "").split(",") if s]
    industry_ids = [to_int(s) for s in str(c.get("industries") or "").split(",") if to_int(s)]
    perk_ids = [to_int(s) for s in str(c.get("perks") or "").split(",") if to_int(s)]
    dei_ids = [to_int(s) for s in str(c.get("diversityOptions") or "").split(",") if to_int(s)]
    return {
        "company_sizes": [refdata.COMPANY_SIZE_FROM_ALIAS.get(s, s) for s in size_aliases],
        "industries": [row["alias"] for row in refdata.INDUSTRIES if row["id"] in industry_ids],
        "tech_stacks": [s for s in str(c.get("techStacks") or "").split(",") if s],
        "perks": [row["alias"] for row in refdata.PERKS if row["id"] in perk_ids],
        "diversity": [row["alias"] for row in refdata.DIVERSITY if row["id"] in dei_ids],
        "hiring_remote": bool(c.get("remoteHiring")),
        "city": text(c.get("city")), "state": text(c.get("state")), "country": text(c.get("country")),
        "page": to_int(c.get("pageNumber")) or 1, "per_page": to_int(c.get("pageSize")) or 20,
    }


# ---- api.builtin.com ---------------------------------------------------------------

OFFICE_TYPES = {1: "on_site", 2: "hybrid", 3: "remote"}
FILES = "https://builtin.com/sites/www.builtin.com/files/"


def file_link(value):
    """A Drupal file reference ('public://2021-10/stripe.jpeg', a bare
    '2026-08/x.jpg' or a full link) -> an absolute https link."""
    value = text(value)
    if not value:
        return None
    if value.startswith("public://"):
        link = FILES + value[len("public://"):].lstrip("/")
    elif value.startswith("s3://prod-company-images.builtin.com/"):
        link = "https://static.builtin.com/" + value[len("s3://prod-company-images.builtin.com/"):]
    elif value.startswith(("http://", "https://", "//", "/")):
        link = refs.absolute(value)
    else:
        link = FILES + value.lstrip("/")
    return link.replace(" ", "%20")


def _funding(raw):
    try:
        rows = json.loads(raw) if isinstance(raw, str) and raw.strip() else (raw if isinstance(raw, list) else [])
    except json.JSONDecodeError:
        return []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        amount = number(row.get("funding_amt"))
        if not amount and not text(row.get("funding_type")) and not text(row.get("funding_date")):
            continue
        out.append({"amount": amount, "currency": "USD" if amount else None, "round": text(row.get("funding_type")),
                    "category": text(row.get("funding_cat")), "date": text(row.get("funding_date")),
                    "investors": text(row.get("funding_investors"))})
    return out


def graphql_company(node):
    """companyByID / companyByAliasAndRegionID -> the company core."""
    c = node if isinstance(node, dict) else {}
    alias = refs.company_alias_from_path(c.get("alias")) or (c.get("alias") or "").strip("/").replace("company/", "") or None
    offices = []
    for o in c.get("offices") or []:
        if not isinstance(o, dict):
            continue
        offices.append({"city": text(o.get("city")), "state": text(o.get("state")), "country": text(o.get("country")),
                        "postal_code": text(o.get("postalCode")), "street": text(o.get("streetAddress1")),
                        "street_2": text(o.get("streetAddress2")), "is_headquarters": bool(o.get("headquarters")),
                        "neighborhood_description": text(o.get("neighborhoodDescription")),
                        "nearest_market_id": to_int(o.get("nearestMarket")) or None})
    technologies = [{"id": to_int(t.get("id")), "name": text(t.get("name")), "alias": text(t.get("urlName")),
                     "category": text(t.get("categoryName"))} for t in (c.get("technologies") or []) if isinstance(t, dict) and text(t.get("name"))]
    extra = [{"id": to_int(t.get("id")), "name": text(t.get("name")), "category": text(t.get("categoryName"))}
             for t in (c.get("extraTechnologies") or []) if isinstance(t, dict) and text(t.get("name"))]
    reviews = [{"reviewer_name": text(r.get("reviewerName")), "reviewer_title": text(r.get("reviewerJobTitle")),
                "reviewer_photo": file_link(r.get("reviewerAvatarURL")),
                "text": text(r.get("review"))}
               for r in (c.get("employeeReviews") or []) if isinstance(r, dict) and text(r.get("review"))]
    culture = []
    for t in c.get("cultureTopics") or []:
        if not isinstance(t, dict) or not (text(t.get("title")) or text(t.get("overview"))):
            continue
        culture.append({"id": to_int(t.get("id")), "title": text(t.get("title")), "category": text(t.get("category")),
                        "overview": text(t.get("overview")), "quote": text(t.get("quoteText")),
                        "quote_question": text(t.get("quoteQuestion")), "quote_name": text(t.get("quoteName")),
                        "quote_title": text(t.get("quoteTitle")), "featured_name": text(t.get("featuredName")),
                        "featured_title": text(t.get("featuredTitle")),
                        "images": [file_link(f.get("uri")) for f in (t.get("fileData") or []) if isinstance(f, dict) and text(f.get("uri"))]})
    insiders = c.get("insidersView") if isinstance(c.get("insidersView"), dict) else {}
    # insidersView.fourOneOne keeps the heading in `answer` and the body in
    # `question`; unfilled entries are bare slugs ("people-focused-perks")
    qa = []
    for q in insiders.get("fourOneOne") or []:
        if not isinstance(q, dict):
            continue
        body, heading = text(q.get("question")), text(q.get("answer"))
        if body and " " not in body and not heading:
            continue
        if body or heading:
            qa.append({"title": heading, "text": body})
    photos = insiders.get("introPhotos") if isinstance(insiders.get("introPhotos"), dict) else {}
    hybrid = c.get("hybridDetails") if isinstance(c.get("hybridDetails"), dict) else {}
    ats = c.get("companyATSDetails") if isinstance(c.get("companyATSDetails"), dict) else {}
    subscription = c.get("subscription") if isinstance(c.get("subscription"), dict) else {}
    return {
        "id": to_int(c.get("id")),
        "name": text(c.get("name")),
        "alias": alias,
        "link": refs.company_link(alias),
        "logo": file_link(c.get("logoUrl") or c.get("logo")),
        "featured_image": file_link(c.get("featuredImage")),
        "video": text(c.get("video")),
        "mission": text(c.get("mission")),
        "mini_description": text(c.get("miniDescription")),
        "intro_header": text(c.get("introHeader")),
        "why_work_with_us": text(c.get("whyWorkWithUs")),
        "perks_overview": text(c.get("perksOverview")),
        "workplace_policy": text(c.get("workplacePolicy")),
        "office_type": OFFICE_TYPES.get(to_int(c.get("officeType"))),
        "hybrid": {"onsite_type": to_int(hybrid.get("onsiteType")), "onsite_value": number(hybrid.get("onsiteValue"))} if hybrid else None,
        "adjectives": [a for a in (text(x) for x in (c.get("adjectives") or [])) if a],
        "industries": [{"id": to_int(i.get("id")), "name": text(i.get("name")), "alias": text(i.get("urlName"))}
                       for i in (c.get("industries") or []) if isinstance(i, dict) and text(i.get("name"))],
        "hq_city": text(c.get("city")),
        "hq_state": text(c.get("state")),
        "year_founded": to_int(c.get("yearFounded")) or None,
        "employees_count": to_int(c.get("totalEmployees")) or None,
        "local_employees_count": to_int(c.get("localEmployees")) or None,
        "perks_count": to_int(c.get("perksCount")),
        "offices": offices,
        "technologies": technologies,
        "extra_technologies": extra,
        "culture_topics": culture,
        "employee_reviews": reviews,
        "insiders": {"intro": text(insiders.get("intro")), "main_photo": file_link(photos.get("main")),
                     "gallery": [file_link(g) for g in (photos.get("gallery") or []) if text(g)], "highlights": qa}
                    if (text(insiders.get("intro")) or qa) else None,
        "galleries": [file_link(g) for g in (c.get("galleries") or []) if text(g)],
        "funding": _funding(c.get("funding")) if c.get("showFunding", True) else [],
        "exit_history": text(c.get("exitHistory")),
        "ats": {"type": text(ats.get("atsType")), "link_or_token": text(ats.get("atsUrl"))} if text(ats.get("atsType")) else None,
        "is_easy_apply": bool(c.get("isEasyApply")),
        "is_brand_boost": bool(c.get("isBrandBoost")),
        "is_limited_listings": bool(c.get("isLimitedListings")),
        "has_remote_jobs": bool_or_none(c.get("hasRemoteJobs")),
        "has_insiders_page": bool(c.get("publishInsidersPage")),
        "subscription_level": text(subscription.get("level")),
        "region": {"alias": text(c.get("regionAlias")), "name": text(c.get("regionName"))},
        "market_region_ids": [to_int(m.get("regionID")) for m in (c.get("marketSites") or []) if isinstance(m, dict) and to_int(m.get("regionID"))],
        "last_updated": iso_from_ld(str(c.get("lastUpdated")).replace(" +0000 UTC", "+00:00").replace(" ", "T", 1)) if text(c.get("lastUpdated")) and not str(c.get("lastUpdated")).startswith("0001") else None,
    }


def company_search_row(row):
    r = row if isinstance(row, dict) else {}
    alias = refs.company_alias_from_path(r.get("alias"))
    return {"id": to_int(r.get("id")), "name": text(r.get("title")), "alias": alias, "link": refs.company_link(alias),
            "logo": file_link(r.get("logo")),
            "industries": [i for i in (text(x) for x in re.split(r",\s*", r.get("industries") or "")) if i]}


def article_card(row, ld=None):
    """One article list row: the site's REST index row (id, title, link —
    its other fields are always empty) enriched from the article page's
    JSON-LD (description, author, dates, image). `ld` None = not enriched."""
    r = row if isinstance(row, dict) else {}
    ld = ld if isinstance(ld, dict) else {}
    link = r.get("alias") or ld.get("url")
    slug = link.rstrip("/").rsplit("/", 1)[-1] if isinstance(link, str) and "/articles/" in link else None
    author = ld.get("author")
    author = author[0] if isinstance(author, list) and author else author
    author = author if isinstance(author, dict) else {}
    image = ld.get("image")
    if isinstance(image, list) and image:
        image = image[0]
    if isinstance(image, dict):
        image = image.get("url")
    return {
        "id": to_int(r.get("id")),
        "title": text(r.get("title")) or text(ld.get("headline")),
        "slug": slug,
        "link": refs.absolute(link) if text(link) else refs.article_link(slug),
        "subtitle": text(ld.get("description")) or text(r.get("subTitle")),
        "author": {"name": text(author.get("name")), "link": refs.absolute(author.get("@id") or author.get("url")) if text(author.get("@id") or author.get("url")) else None},
        "published_at": iso_from_ld(ld.get("datePublished")) or iso_from_ld(r.get("createdAt")),
        "updated_at": iso_from_ld(ld.get("dateModified")) or iso_from_ld(r.get("updatedAt")),
        "image": refs.absolute(image) if isinstance(image, str) and image.strip() else None,
    }


def place_suggestion(row):
    r = row if isinstance(row, dict) else {}
    return {"place_id": text(r.get("placeId")), "label": text(r.get("text"))}


def place(row):
    r = row if isinstance(row, dict) else {}
    return {"label": text(r.get("label")), "city": text(r.get("city") or r.get("municipality")), "state": text(r.get("state") or r.get("region")),
            "country": text(r.get("country")), "postal_code": text(r.get("postalCode")),
            "latitude": number(r.get("latitude")), "longitude": number(r.get("longitude"))}


# ---- salaries --------------------------------------------------------------------

def _dollars(raw):
    match = _DOLLARS_RE.search(raw or "")
    return money_amount(match.group(0)) if match else None


def _table_rows(table):
    """A striped table -> list of cell lists (bs4 cells)."""
    return [tr.find_all("td") for tr in table.select("tbody tr") if tr.find_all("td")]


def _range_cell(cell):
    raw = cell.get_text(" ", strip=True)
    low = re.search(r"Min:\s*(\$[\d,.]+\s*[kK]?)", raw)
    high = re.search(r"Max:\s*(\$[\d,.]+\s*[kK]?)", raw)
    return money_amount(low.group(1)) if low else None, money_amount(high.group(1)) if high else None


def salary_page(markup, *, title_slug=None, location_slug=None):
    """A /salaries/us/[{location}/]{title} page: the headline numbers, the
    Occupation JSON-LD distribution, gender / experience / company-size
    sentences, the best-paying-cities table, the related-titles table, the
    skills ranking, the recent self-reported salaries and the FAQ."""
    from built_in.fetch import json_ld as _json_ld
    doc = soup(markup)
    main = doc.select_one("main") or doc
    occupation = next((n for n in _json_ld(markup) if n.get("@type") == "Occupation"), {})
    faq = next((n for n in _json_ld(markup) if n.get("@type") == "FAQPage"), {})
    base = next((d for d in (occupation.get("estimatedSalary") or []) if isinstance(d, dict) and d.get("name") == "base"), {})
    bonus = next((d for d in (occupation.get("estimatedSalary") or []) if isinstance(d, dict) and d.get("name") == "bonus"), {})
    full = main.get_text(" | ", strip=True)
    h1 = node_text(main.find("h1"))
    match = re.search(r"Average Base Salary[^|]*\|\s*(\$[\d,]+)", full)
    average = _dollars(match.group(1)) if match else None
    match = re.search(r"(\$[\d,]+)\s*\|\s*Additional Cash Compensation", full)
    additional = _dollars(match.group(1)) if match else None
    match = re.search(r"(\$[\d,]+)\s*\|\s*Total Compensation", full)
    total = _dollars(match.group(1)) if match else None
    gender = None
    match = re.search(r"salary for women is (\$[\d,]+) and the average [^|]*? for men is (\$[\d,]+)", full)
    if match:
        gender = {"women_average": _dollars(match.group(1)), "men_average": _dollars(match.group(2))}
    experience = []
    for years, amount in re.findall(r"(<\s*1 year|\d+\+? years?|\d+\s*[-–]\s*\d+ years?) of experience is (\$[\d,]+)", full):
        row = {"experience": text(years), "average": _dollars(amount)}
        if row not in experience:
            experience.append(row)
    common = None
    match = re.search(r"most common [^|]*? salary [^|]*? is between (\$[\d,.]+\s*[kK]?) - (\$[\d,.]+\s*[kK]?)", full)
    if match:
        common = {"min": money_amount(match.group(1)), "max": money_amount(match.group(2))}
    company_size = None
    match = re.search(r"make the most at companies with ([^|,]+?) employees, earning (\$[\d,]+) on average", full)
    if match:
        company_size = {"best_paying_size": text(match.group(1)), "average": _dollars(match.group(2))}
    # tables: each sits right after its <h2>
    by_city, related = [], {"heading": None, "rows": []}
    for table in main.find_all("table"):
        heading = table.find_previous(["h2", "h3"])
        heading_text = node_text(heading) or ""
        header_cells = [node_text(th) for th in table.select("thead th")]
        for cells in _table_rows(table):
            a = cells[0].find("a")
            link = refs.absolute(a.get("href")) if a is not None else None
            label = node_text(cells[0])
            avg = _dollars(cells[1].get_text()) if len(cells) > 1 else None
            if header_cells and header_cells[0] and "city" in header_cells[0].lower():
                delta = cells[2].get_text(" ", strip=True) if len(cells) > 2 else ""
                pct = re.search(r"([+-])\s*(\d+)%", delta)
                nat = re.search(r"\(([\d,]+)\)", delta)
                by_city.append({"location": label, "link": link, "average": avg,
                                "vs_national_percent": (int(pct.group(2)) * (-1 if pct.group(1) == "-" else 1)) if pct else None,
                                "national_average": to_int(nat.group(1)) if nat else None})
            else:
                low, high = _range_cell(cells[-1]) if len(cells) > 2 else (None, None)
                related["heading"] = related["heading"] or heading_text or None
                related["rows"].append({"title": label, "link": link, "average": avg, "min": low, "max": high})
    best_cities_sentence = None
    match = re.search(r"The metropolitan areas that pay the highest salaries for [^|]*? are ([^|]+?)\s*\|", full)
    if match:
        best_cities_sentence = text(match.group(1))
    skills = []
    skills_h = _heading(main, r"^Skills that affect")
    if skills_h is not None:
        holder = skills_h.find_next_sibling("div")
        for rank, name, pct in re.findall(r"\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)%\s*\|\s*have this skill", "| " + (holder.get_text(" | ", strip=True) if holder is not None else "")):
            skills.append({"rank": int(rank), "skill": text(name), "share_percent": int(pct)})
    recent = []
    recent_h = _heading(main, r"^Recent .+ salaries")
    if recent_h is not None:
        holder = recent_h.find_next_sibling("div")
        for block in (holder.find_all("div", recursive=False) if holder is not None else []):
            for entry in block.select("div"):
                sentence = entry.get_text(" ", strip=True)
                if not sentence.startswith("A ") or "reported a yearly salary" not in sentence or entry.find("div") is None:
                    continue
                card = entry.parent
                lines = [t for t in (node_text(d) for d in card.find_all("div") if d.find("div") is None) if t]
                m_title = re.search(r"^A (.+?) reported a yearly salary of (\$[\d,]+)(?: with \+?(\$[\d,]+) in additional cash compensation)?", sentence)
                if not m_title:
                    continue
                tail = [t for t in lines if t != "Yearly Salary" and not t.startswith("$") and not t.startswith("A ")]
                recent.append({
                    "title": text(m_title.group(1)), "salary": _dollars(m_title.group(2)),
                    "additional_cash": _dollars(m_title.group(3)) if m_title.group(3) else None, "period": "annual",
                    "experience": next((t for t in tail if "Experience" in t), None),
                    "gender": next((t for t in tail if t in ("Male", "Female", "Non-binary")), None),
                    "company_size": next((t for t in tail if "Employees" in t), None),
                    "location": tail[-1] if tail and tail[-1] not in ("Male", "Female") and "Employees" not in tail[-1] and "Experience" not in tail[-1] else None,
                })
                break
    jobs_widget = main.select_one("#salary-jobs")
    taxonomy = None
    if jobs_widget is not None:
        taxonomy = {"category_id": to_int(jobs_widget.get("data-category-tid")), "category": text(jobs_widget.get("data-category-name")),
                    "title_id": to_int(jobs_widget.get("data-title-tid")), "title": text(jobs_widget.get("data-title-name")),
                    "keywords": [k for k in (text(x) for x in (jobs_widget.get("data-keywords") or "").split(",")) if k]}
    questions = []
    for q in (faq or {}).get("mainEntity") or []:
        if isinstance(q, dict):
            answer = q.get("acceptedAnswer") if isinstance(q.get("acceptedAnswer"), dict) else {}
            questions.append({"question": text(q.get("name")), "answer": strip_html(answer.get("text")) or text(answer.get("text"))})
    location_node = occupation.get("occupationLocation")
    location_node = location_node[0] if isinstance(location_node, list) and location_node else location_node
    location_name = text(location_node.get("name")) if isinstance(location_node, dict) else None
    page_meta = occupation.get("mainEntityOfPage") if isinstance(occupation.get("mainEntityOfPage"), dict) else {}
    percentiles = {k: number(base.get(src)) for k, src in (("p10", "percentile10"), ("p25", "percentile25"), ("p75", "percentile75"), ("p90", "percentile90"))}
    return {
        "title": text(occupation.get("name")) or (h1.split(" salary in")[0] if h1 else None),
        "title_slug": title_slug,
        "location": "United States" if (not location_slug or location_name in (None, "US")) else location_name,
        "location_slug": location_slug,
        "link": refs.salary_link(title_slug, location_slug),
        "currency": text(base.get("currency")) or "USD",
        "base": {"average": average, "median": number(base.get("median")), "min": number(base.get("minValue")),
                 "max": number(base.get("maxValue")), "percentiles": percentiles if any(v is not None for v in percentiles.values()) else None},
        "additional_cash_average": additional if additional is not None else number(bonus.get("median")),
        "total_compensation_average": total,
        "by_gender": gender,
        "by_experience": experience,
        "by_company_size": company_size,
        "most_common_range": common,
        "best_paying_cities": {"summary": best_cities_sentence, "rows": by_city},
        "related_titles": related,
        "top_skills": skills,
        "recent_reports": recent,
        "taxonomy": taxonomy,
        "faq": questions,
        "last_reviewed": iso_from_ld(page_meta.get("lastReviewed")),
    }


def salary_filters(markup):
    """The salary explorer's dropdown lists: categories, titles (with their
    category ids), locations."""
    doc = soup(markup)
    categories, titles, locations = [], [], []
    seen = set()
    for span in doc.select("span[data-value][data-url]"):
        name = node_text(span)
        value = span.get("data-value")
        slug = span.get("data-url")
        key = (slug, name)
        if not name or key in seen:
            continue
        seen.add(key)
        if span.has_attr("data-parent") and not slug:
            # the national row ("US") has no slug; its page is /salaries itself
            locations.append({"id": to_int(value), "slug": None, "name": name, "parent_slug": None,
                              "link": refs.absolute("/salaries")})
            continue
        if span.has_attr("data-category"):
            titles.append({"id": to_int(value), "slug": slug, "name": name,
                           "category_ids": [to_int(c) for c in (span.get("data-category") or "").split("+") if to_int(c)],
                           "link": refs.salary_link(slug)})
        elif span.has_attr("data-parent"):
            locations.append({"id": to_int(value), "slug": slug, "name": name, "parent_slug": text(span.get("data-parent")),
                              "link": refs.absolute(f"/salaries/location/{slug}")})
        else:
            categories.append({"id": to_int(value), "slug": slug, "name": name})
    return {"categories": categories, "titles": titles, "locations": locations}


def salary_location_page(markup, *, location_slug=None):
    """A /salaries/location/{metro} page: the per-category averages and the
    titles (grouped by category) the metro has data for."""
    doc = soup(markup)
    main = doc.select_one("main") or doc
    h1 = node_text(main.find("h1")) or ""
    by_category = []
    heading = _heading(main, r"Salary by Category")
    if heading is not None:
        section = heading.find_next_sibling("div") or heading.parent
        for a in section.select("a[href]"):
            name = node_text(a)
            holder = a.parent
            amount = _dollars(holder.get_text(" ", strip=True)) if holder is not None else None
            if name and amount:
                by_category.append({"category": name, "average": amount, "jobs_link": refs.absolute(a.get("href"))})
    groups = []
    titles_h = _heading(main, r"^Average Salaries in")
    if titles_h is not None:
        section = titles_h.find_next_sibling("div") or titles_h.parent
        current = None
        for node in section.find_all(["div", "a"]):
            if node.name == "a" and (node.get("href") or "").startswith("/salaries/"):
                label = node_text(node) or ""
                row = {"title": text(label.split(" Salary in")[0]), "link": refs.absolute(node.get("href"))}
                if current is None:
                    current = {"category": None, "titles": []}
                    groups.append(current)
                if row not in current["titles"]:
                    current["titles"].append(row)
            elif node.name == "div" and node.find("div") is None and node.find("a") is None:
                label = node_text(node)
                if label and not label.startswith("$"):
                    current = {"category": label, "titles": []}
                    groups.append(current)
    groups = [g for g in groups if g["titles"]]
    location = text(re.sub(r"\s*Tech \+ Startup Salaries.*$|\s*Tech Salaries.*$", "", h1)) or None
    return {"location": location, "location_slug": location_slug,
            "link": refs.absolute(f"/salaries/location/{location_slug}") if location_slug else None,
            "by_category": by_category, "titles_by_category": groups,
            "titles_count": sum(len(g["titles"]) for g in groups)}


# ---- articles -----------------------------------------------------------------------

def article_page(markup, *, slug=None, ld=None):
    doc = soup(markup)
    ld = ld or {}
    main = doc.select_one("main") or doc
    h1 = main.find("h1")
    subtitle = node_text(h1.find_next_sibling("p")) if h1 is not None else None
    author_a = main.select_one('a[data-testid="article-author-link"], a[href*="/authors/"]')
    published = None
    updated = None
    for div in main.find_all("div"):
        t = node_text(div) if div.find("div") is None else None
        if t and t.startswith("Published on"):
            published = human_date(t)
        elif t and t.startswith("Updated on"):
            updated = human_date(t)
    article = main.find("article") or main
    hero = article.find("img")
    caption = None
    if hero is not None:
        nxt = hero.find_next_sibling("div")
        caption = node_text(nxt) if nxt is not None else None
    body_holder = article.select_one("div.article-content")
    if body_holder is None:
        for div in article.find_all("div"):
            if len(div.find_all("p", recursive=False)) >= 1 and div.find("img") is None:
                body_holder = div
                break
    body_html = body_holder.decode_contents().strip() if body_holder is not None else None
    headings = [t for t in (node_text(h) for h in (body_holder.find_all(["h2", "h3"]) if body_holder is not None else [])) if t]
    companies = []
    seen = set()
    for a in article.select('a[href*="/company/"]'):
        alias = _company_from_anchor(a)
        if not alias:
            continue
        label = node_text(a) or ""
        jobs = re.search(r"View (\d+) Jobs", label)
        if alias in seen:
            if jobs:
                for row in companies:
                    if row["alias"] == alias:
                        row["open_jobs_count"] = to_int(jobs.group(1))
            continue
        seen.add(alias)
        companies.append({"name": text(label.split(" is Hiring")[0]) if " is Hiring" in label else label or alias,
                          "alias": alias, "link": refs.company_link(alias),
                          "open_jobs_count": to_int(jobs.group(1)) if jobs else None})
    topics = [node_text(a) for a in main.select('header nav a, nav a[href^="/tag/"]')]
    saved = main.select_one("my-item[entity-type='article']")
    author_ld = ld.get("author") if isinstance(ld.get("author"), dict) else (ld.get("author")[0] if isinstance(ld.get("author"), list) and ld["author"] else {})
    image_ld = ld.get("image")
    if isinstance(image_ld, dict):
        image_ld = image_ld.get("url")
    elif isinstance(image_ld, list) and image_ld:
        image_ld = image_ld[0].get("url") if isinstance(image_ld[0], dict) else image_ld[0]
    return {
        "id": to_int(saved.get("entity-id")) if saved is not None else None,
        "slug": slug,
        "title": node_text(h1) or text(ld.get("headline")),
        "link": refs.article_link(slug),
        "subtitle": subtitle or text(ld.get("description")),
        "author": {"name": node_text(author_a) or text(author_ld.get("name")), "link": refs.absolute(author_a.get("href")) if author_a is not None else None},
        "published_at": iso_from_ld(ld.get("datePublished")) or published,
        "updated_at": iso_from_ld(ld.get("dateModified")) or updated,
        "image": _img_src(hero) or (refs.absolute(image_ld) if isinstance(image_ld, str) else None),
        "image_caption": caption,
        "topics": [t for t in topics if t],
        "headings": headings,
        "body_html": body_html,
        "body_text": strip_html(body_html) or text(ld.get("articleBody")),
        "companies": companies,
    }

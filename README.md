# 💼 Built In Scraper

Built In Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Built In tech jobs, companies and salaries data for free.

## ✨ What Can I Get?

- 💼 **500K+ tech jobs** — salary range, full description, skills, benefits, work mode & every location
- 🔍 **Search with 15 filters** — any city, remote / hybrid, category, experience, industry, company size & date posted
- 🏢 **100K+ company profiles** — tech stack, benefits, offices, employee reviews, AI culture insights & open jobs
- 💰 **Salaries for 199 tech job titles** — average, median, percentiles, gender & experience splits across 50+ US metros

## 🎥 Example: A Full Built In Job

```json
{
  "id": 11527168,
  "title": "Software Engineer (L5) - Traffic Engineering",
  "link": "https://builtin.com/job/software-engineer-l5-traffic-engineering/11527168",
  "company": { "name": "Netflix", "alias": "netflix", "hq": "Los Gatos, CA", "employees_count": 13212, "year_founded": 1997 },
  "posted_at": "2026-10-06",
  "valid_through": "2026-11-05T16:56:58Z",
  "employment_type": "FULL_TIME",
  "experience_level": "senior",
  "work_modes": ["in_office"],
  "location": "Los Gatos, CA, USA",
  "location_addresses": [{ "street": "100 Winchester Circle", "city": "Los Gatos", "state": "California", "country": "USA" }],
  "salary": { "min": 388000, "max": 619000, "period": "annual", "currency": "USD", "text": "388K-619K Annually" },
  "summary": "Design, build, and operate scalable traffic-management infrastructure across Netflix cloud and edge environments...",
  "skills_required": [
    "7+ years of experience crafting complex, scalable distributed data infrastructure",
    "Proficiency in Java, Golang, or Python"
  ],
  "benefits": ["Offers 401(K)", "Offers disability insurance", "Offers life insurance"],
  "benefits_highlights": [
    { "title": "Equity Value & Accessibility", "text": "Employees can choose the mix of cash versus fully vested 10‑year stock options..." }
  ]
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Built In Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/built-in-scraper
cd built-in-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/jobs/details?job=https://builtin.com/job/software-engineer-l5-traffic-engineering/11527168"
```

```json
{
  "job": {
    "id": 11527168,
    "title": "Software Engineer (L5) - Traffic Engineering",
    "link": "https://builtin.com/job/software-engineer-l5-traffic-engineering/11527168",
    "company": { "name": "Netflix", "alias": "netflix", "hq": "Los Gatos, CA", "employees_count": 13212, "year_founded": 1997 },
    "posted_at": "2026-10-06",
    "employment_type": "FULL_TIME",
    "experience_level": "senior",
    "work_modes": ["in_office"],
    "location": "Los Gatos, CA, USA",
    "salary": { "min": 388000, "max": 619000, "period": "annual", "currency": "USD", "text": "388K-619K Annually" },
    "skills_required": [
      "7+ years of experience crafting complex, scalable distributed data infrastructure",
      "Proficiency in Java, Golang, or Python"
    ],
    "benefits": ["Offers 401(K)", "Offers disability insurance", "Offers life insurance"],
    "valid_through": "2026-11-05T16:56:58Z"
  }
}
```

All 17 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

17 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Job Details | `/jobs/details` | Salary, full description, skills, benefits, locations and the company |
| Search Jobs | `/jobs/search` | Jobs by keyword, city, remote, category, experience, industry and date |
| Company Details | `/companies/details` | Tech stack, benefits, offices, reviews, size, funding and open jobs |
| Company Jobs | `/companies/jobs` | Every open job at one company, with all search filters |
| Search Companies | `/companies/search` | Company IDs, aliases, logos and industries by name |
| Company Directory | `/companies/list` | Companies by metro, size, industry, tech stack, perk and diversity |
| Company Insights | `/companies/insights` | AI read on culture, pay, growth, balance, leadership and stability |
| Company Articles | `/companies/articles` | Built In articles featuring a company, with author and dates |
| Salary by Job Title | `/salaries/title` | Average, median, percentiles, gender, experience and top-paying cities |
| Salaries by Location | `/salaries/location` | A metro's average pay per category and every covered title |
| Article Details / Latest Articles | `/articles/details`, `/articles/latest` | A full article with featured companies, or the newest articles |
| Location / Job Title Autocomplete | `/locations/suggest`, `/job-titles/suggest` | Typeahead for places (with coordinates) and job titles |
| Job / Company / Salary Filters | `/jobs/filters`, `/companies/filters`, `/salaries/filters` | Every filter value: categories, industries, metros, perks, titles |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-built-in-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-built-in-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-built-in-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/jobs/search",
    params={"query": "software engineer", "location": "San Francisco, CA"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Built In Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Built%20In%20Scraper%20API.)

[![Ask Us by Email about Built In Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Built%20In%20Scraper%20API&body=I%20need%20help%20using%20the%20Built%20In%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**Glassdoor Scraper**](https://github.com/omkarcloud/glassdoor-scraper) — Glassdoor jobs, company ratings, salaries & reviews
- [**We Work Remotely Scraper**](https://github.com/omkarcloud/we-work-remotely-scraper) — remote jobs with salary ranges, skills, countries & company profiles
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/built-in-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/built-in-scraper)

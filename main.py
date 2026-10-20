"""Use the scraper straight from Python — no server needed.

    python main.py

Every call returns the same JSON the API does; results are written to
output/*.json. Params go through the same schemas as the API, so you can pass
links, aliases and filter names exactly as you would in a query string.
"""
import json
import os

from built_in import companies, jobs, schemas

os.makedirs("output", exist_ok=True)


def run(schema, fn, **params):
    """Validate `params` like the API does, then call the scraper."""
    return fn(**schema().load(params))


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a builtin.com job link (or "{title-slug}/{job_id}")
    save("job_netflix_software_engineer.json", run(
        schemas.JobSchema, jobs.details,
        job="https://builtin.com/job/software-engineer-l5-traffic-engineering/11527168"))

    # every filter of the site: place, work mode, category, experience, recency …
    save("search_software_engineer_san_francisco.json", run(
        schemas.JobSearchSchema, jobs.search,
        query="software engineer", location="San Francisco, CA", work_mode="remote,hybrid"))

    # tech stack, benefits, offices, reviews, size, open jobs
    save("company_coinbase.json", run(schemas.CompanySchema, companies.details, company="coinbase"))

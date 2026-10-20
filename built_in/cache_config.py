"""Cache TTL per /built-in/* endpoint (cache.py, keyed on the validated
params). Job lists move hourly (new posts / reposts float to the top), job
and company pages change rarely, salaries and reference lists are monthly."""
from datetime import timedelta

SEARCH_CACHE = timedelta(hours=2)          # jobs/search, companies/jobs
JOB_CACHE = timedelta(hours=12)            # jobs/details
COMPANY_CACHE = timedelta(days=1)          # companies/details
COMPANY_SEARCH_CACHE = timedelta(days=3)   # companies/search
DIRECTORY_CACHE = timedelta(hours=12)      # companies/list
INSIGHTS_CACHE = timedelta(days=7)         # companies/insights
ARTICLES_CACHE = timedelta(hours=12)       # companies/articles, articles/latest
ARTICLE_CACHE = timedelta(days=7)          # articles/details
SALARY_CACHE = timedelta(days=7)           # salaries/*
FILTERS_CACHE = timedelta(days=7)          # jobs/filters, salaries/filters
SUGGEST_CACHE = timedelta(days=30)         # locations/suggest, job-titles/suggest

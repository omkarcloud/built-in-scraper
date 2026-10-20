"""Marshmallow request schemas for every /built-in/* route. Generic fields
come from the shared schema_fields.py; this module adds the Built In
resolvers. Every schema's load() output is the kwargs dict its endpoint
takes.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    job        a builtin.com job link OR '{title-slug}/{job_id}' (the site
               cannot open a job by id alone)
    company    an alias (stripe) OR a profile link OR the numeric company id
    article    an article slug OR a builtin.com article link
    query      free text OR (on /built-in/jobs/search) a builtin.com job-board
               link, whose own filters are then applied
    location   a Built In metro alias (chicago, new-york-city, …) OR any
               place name (resolved through the site's own location lookup)
"""
from marshmallow import ValidationError, fields, validates_schema

from built_in import refdata, refs
from built_in.companies import INSIGHT_TOPICS
from schema_fields import (BaseSchema, ChoiceField, CommaListField, CountryCodeField, Flag, LimitField, PageField,
                           PageSizeField, QueryField, RefField, StrippedString)

MAX_PAGE = 400


# ---- fields ------------------------------------------------------------------------

class JobField(RefField):
    resolver = staticmethod(refs.resolve_job)


class CompanyField(RefField):
    resolver = staticmethod(refs.resolve_company)


class ArticleField(RefField):
    resolver = staticmethod(refs.resolve_article)


class Alpha3CountryField(CountryCodeField):
    """ISO alpha-2 in (US, GB, DE) -> the alpha-3 the board takes (USA, GBR, DEU)."""

    def _deserialize(self, value, attr, data, **kwargs):
        two = super()._deserialize(value, attr, data, **kwargs)
        if two is None:
            return None
        three = refdata.alpha3(two)
        if not three:
            raise ValidationError("Country code not supported by builtin.com.")
        return three


class LookupChoiceField(StrippedString):
    """A value that must resolve through one of the refdata lookups
    (industry / category / subcategory …); the alias is returned."""

    def __init__(self, lookup, what, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)
        self.lookup = lookup
        self.what = what

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        hit = self.lookup(value)
        if hit is None:
            raise ValidationError(f"Unknown {self.what} '{value}' (see /built-in/jobs/filters).")
        row = hit[1] if isinstance(hit, tuple) else hit
        return row["alias"]


# ---- schemas -------------------------------------------------------------------------

class EmptySchema(BaseSchema):
    pass


class JobSearchSchema(BaseSchema):
    query = QueryField(required=False, load_default=None, max_length=300)
    location = StrippedString(required=False, load_default=None)
    # no "USA" default here: a board link's own country (/jobs/eu/germany,
    # ?country=GBR) must fill the gap; jobs.search() defaults to USA after
    country = Alpha3CountryField()
    work_mode = CommaListField(allowed=list(refdata.WORK_MODE_PUBLIC), upper=False, max_items=3)
    category = LookupChoiceField(refdata.category, "category")
    subcategory = LookupChoiceField(refdata.subcategory, "subcategory")
    experience = ChoiceField(list(refdata.EXPERIENCE_PUBLIC))
    industry = LookupChoiceField(refdata.industry, "industry")
    company_size = ChoiceField(list(refdata.COMPANY_SIZE_PUBLIC))
    posted_within = ChoiceField(list(refdata.POSTED_WITHIN_PUBLIC))
    skills = CommaListField(upper=False, max_items=10)
    radius_miles = fields.Integer(required=False, load_default=None, strict=False)
    early_applicant = Flag()
    company = CompanyField(required=False, load_default=None)
    page = PageField(max_page=MAX_PAGE)

    @validates_schema
    def _check(self, data, **kwargs):
        if data.get("radius_miles") is not None and data["radius_miles"] not in refdata.RADIUS_MILES:
            raise ValidationError({"radius_miles": [f"Must be one of: {', '.join(map(str, refdata.RADIUS_MILES))}."]})
        if data.get("radius_miles") is not None and not data.get("location"):
            raise ValidationError({"radius_miles": ["Needs a location."]})
        if not any(data.get(k) for k in ("query", "location", "category", "subcategory", "industry", "company", "skills",
                                           "work_mode", "experience", "company_size", "posted_within")):
            # a bare board is still a valid listing (newest tech jobs), nothing to reject
            pass


class JobSchema(BaseSchema):
    job = JobField()


class CompanyJobsSchema(JobSearchSchema):
    company = CompanyField(required=True)


class CompanySearchSchema(BaseSchema):
    query = QueryField(max_length=100)
    limit = LimitField(default=10, max_size=20)


class CompanySchema(BaseSchema):
    company = CompanyField()
    include = CommaListField(allowed=["benefits", "offices", "teams"], upper=False, max_items=3)


class CompanyListSchema(BaseSchema):
    location = StrippedString(required=False, load_default=None)
    company_size = ChoiceField(list(refdata.COMPANY_SIZE_PUBLIC))
    industry = LookupChoiceField(refdata.industry, "industry")
    tech = StrippedString(required=False, load_default=None)
    perk = StrippedString(required=False, load_default=None)
    diversity = StrippedString(required=False, load_default=None)
    hiring_remote = Flag()
    country = Alpha3CountryField(load_default="USA")
    page = PageField(max_page=500)


class CompanyInsightsSchema(BaseSchema):
    company = CompanyField()
    topic = ChoiceField(list(INSIGHT_TOPICS), load_default="workplace_perception")


class CompanyArticlesSchema(BaseSchema):
    company = CompanyField()
    page = PageField(max_page=1000)
    per_page = PageSizeField(default=10, max_size=25)


class ArticlesSchema(BaseSchema):
    page = PageField(max_page=5000)
    per_page = PageSizeField(default=10, max_size=25)


class ArticleSchema(BaseSchema):
    article = ArticleField()


class SalaryTitleSchema(BaseSchema):
    title = QueryField(max_length=100)
    location = StrippedString(required=False, load_default=None)


class SalaryLocationSchema(BaseSchema):
    location = QueryField(max_length=100)


class SuggestSchema(BaseSchema):
    query = QueryField(max_length=100)
    limit = LimitField(default=10, max_size=20)


class LocationSuggestSchema(SuggestSchema):
    resolve = Flag(load_default=False)

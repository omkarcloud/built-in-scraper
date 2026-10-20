"""/built-in/articles/* — one Built In article in full (JSON-LD + body) and
the site's newest articles."""
from built_in import parsers as P
from built_in.fetch import BuiltInNotFound, get_page, ld_node


def details(article):
    status, html, _ = get_page(f"/articles/{article}", label="article")
    if status != 200:
        raise BuiltInNotFound(f"article '{article}' not found on builtin.com")
    ld = ld_node(html, "Article") or ld_node(html, "NewsArticle") or ld_node(html, "BlogPosting")
    page = P.article_page(html, slug=article, ld=ld)
    if not page.get("title"):
        raise BuiltInNotFound(f"article '{article}' not found on builtin.com")
    return {"article": page}

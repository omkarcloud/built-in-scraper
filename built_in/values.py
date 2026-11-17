"""Value helpers for the Built In normalizers (the generic ones come from
scraper_utils; the rest are the site's own)."""
import html as html_lib
import re
from scraper_utils.values import bool_or_none, num as to_float, number, to_int
from scraper_utils.text import clean as text

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def strip_html(value):
    """HTML -> readable plain text (block tags become newlines)."""
    if not isinstance(value, str) or not value.strip():
        return None
    out = re.sub(r"(?i)<\s*br\s*/?>", "\n", value)
    out = re.sub(r"(?i)</\s*(p|div|li|h[1-6]|tr|ul|ol|section|article|header)\s*>", "\n", out)
    out = re.sub(r"(?i)<\s*(p|div|h[1-6]|tr|ul|ol|section|article|header)(\s[^>]*)?>", "\n", out)
    out = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", out)
    out = _TAG_RE.sub("", out)
    out = html_lib.unescape(out)
    lines = [_WS_RE.sub(" ", line).strip() for line in out.splitlines()]
    out = "\n".join(line for line in lines if line)
    return out or None


def first_number(value):
    """'£85,425' / '334 jobs' -> 85425 / 334 (None when there is none)."""
    if not isinstance(value, str):
        return None
    match = _NUMBER_RE.search(value)
    return number(match.group(0)) if match else None

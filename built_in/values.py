"""Value helpers for the Built In normalizers (kept local so the package
stands alone, like the other site packages)."""
import html as html_lib
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def to_int(value):
    try:
        return int(value) if value not in (None, "") and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        try:
            return int(float(str(value).replace(",", "")))
        except (TypeError, ValueError):
            return None


def to_float(value):
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def number(value):
    """A float that is whole -> int (salaries, prices)."""
    out = to_float(value)
    if out is None:
        return None
    return int(out) if out.is_integer() else out


def text(value):
    if not isinstance(value, str):
        return None
    value = _WS_RE.sub(" ", html_lib.unescape(value)).strip()
    return value or None


def bool_or_none(value):
    return value if isinstance(value, bool) else None


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

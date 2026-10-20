"""Configuration for the Built In Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT                      port the API listens on (default 8000)
    BUILT_IN_PROXY            proxy URL for every request, e.g. http://user:pass@host:port
                              (default: none — direct). builtin.com answered a
                              15-request burst from one IP without a block, so
                              you very likely don't need this.
    BUILT_IN_FALLBACK_PROXY   proxy URL used only after builtin.com refuses a
                              request (403 / 429 / challenge page), for
                              BUILT_IN_BLOCK_COOLDOWN seconds (default: none)

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# How long new sessions keep using BUILT_IN_FALLBACK_PROXY after a block.
BUILT_IN_BLOCK_COOLDOWN = 900


def built_in_proxy():
    """Proxy for every session (None = direct)."""
    return os.environ.get("BUILT_IN_PROXY") or None


def built_in_fallback_proxy():
    """Proxy for sessions opened after a block (None = no fallback)."""
    return os.environ.get("BUILT_IN_FALLBACK_PROXY") or None

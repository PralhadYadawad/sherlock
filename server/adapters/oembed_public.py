"""oembed_public adapter — no-auth public metadata + stub transcript.

Studied source: yt-dlp docs/README only (interface pattern: metadata-only
read with ``--skip-download`` discipline, per-URL cache key, failure
taxonomy where private/deleted/rate-limited URLs fail cleanly) plus the
public oEmbed/noembed response shape. Clean-room reimplementation — no
code copied. MIT (ours).

Pattern: fetch public metadata for a reel/post URL with a short timeout
and no credentials. The fetch helper ALWAYS returns a dict (``{}`` on any
failure). A stub transcript loader serves the DEMO-CASE-001 transcript
fixture (2 resource links) for the documented demo reel ID only.

Free cap / rate behavior: no-auth endpoints, no keys; honor 429 with
backoff; cache per URL (link rot). Demo transcript stub is local compute.

Failure taxonomy: private/deleted/unknown/bad URLs return ``rejected``
with a reason and ZERO findings — metadata is never hallucinated. Only
the documented demo reel (``DMYosint001``) resolves to stub data, and its
transcript findings are marked low confidence as stub data.
"""

try:
    from urllib.parse import quote, urlparse
except Exception:  # pragma: no cover
    quote = None
    urlparse = None

try:
    import requests
except Exception:  # pragma: no cover - offline fallback
    requests = None

NAME = "oembed_public"
LICENSE_NOTE = (
    "clean-room reimplementation, MIT (ours). "
    "Studied yt-dlp + public oEmbed docs only."
)

TIMEOUT = 5

# DEMO-CASE-001 reel fixture. Caption MUST contain "open-source research";
# transcript stub carries exactly 2 resource links.
DEMO_REEL_ID = "DMYosint001"
DEMO_REEL_URL = "https://www.instagram.com/reel/DMYosint001/"
DEMO_AUTHOR = "@demo.archivist"
DEMO_CAPTION = (
    "open-source research notes: tracing public handles across demo "
    "sites for DEMO-CASE-001. Methods only, no private data."
)
DEMO_TRANSCRIPT = {
    "text": (
        "Demo transcript stub for DMYosint001: this open-source research "
        "walkthrough covers public presence checks and certificate intel."
    ),
    "links": [
        "https://example.com/resource-1",
        "https://example.com/resource-2",
    ],
    "lang": "en",
}

_PRIVATE_HINTS = ("private", "deleted", "removed", "login", "checkpoint",
                  "challenge", "unavailable")


def _looks_private(target):
    lowered = target.lower()
    return any(hint in lowered for hint in _PRIVATE_HINTS)


def fetch_oembed(url, timeout=TIMEOUT):
    """No-auth public metadata fetch. ALWAYS returns a dict ({} on failure).

    Shaped like a minimal oEmbed response: title / author_name /
    provider_name when the endpoint cooperates, {} otherwise.
    """
    if requests is None:
        return {}
    try:
        endpoint = "https://noembed.com/embed?url=" + quote(url, safe="")
        resp = requests.get(
            endpoint, timeout=timeout,
            headers={"User-Agent": "SherlockDemo/0.1"},
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()
        if not isinstance(data, dict) or data.get("error"):
            return {}
        return data
    except Exception:
        return {}


def load_transcript_stub(reel_id):
    """Return the demo transcript stub for the documented demo ID, else None."""
    if reel_id == DEMO_REEL_ID:
        return dict(DEMO_TRANSCRIPT)
    return None


def _extract_reel_id(target):
    if urlparse is None:
        return None
    try:
        parts = urlparse(target)
    except Exception:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    segments = [seg for seg in parts.path.split("/") if seg]
    for i, seg in enumerate(segments):
        if seg.lower() in ("reel", "reels", "p") and i + 1 < len(segments):
            return segments[i + 1]
    return None


def run(target: str) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [...]}."""
    if target is None or (isinstance(target, str) and not target.strip()):
        return {"status": "rejected",
                "reason": "empty target: pass a public reel URL", "findings": []}
    if not isinstance(target, str):
        return {"status": "rejected",
                "reason": "rejected: invalid reel URL", "findings": []}
    text = target.strip()
    if _looks_private(text):
        return {"status": "rejected",
                "reason": "rejected: private/deleted/login-gated URL "
                          "(no hallucinated metadata)",
                "findings": []}
    reel_id = _extract_reel_id(text)
    if not reel_id:
        return {"status": "rejected",
                "reason": "rejected: bad reel URL; expected "
                          "https://www.instagram.com/reel/<id>/",
                "findings": []}
    if reel_id == DEMO_REEL_ID:
        transcript = load_transcript_stub(reel_id)
        findings = [
            {"type": "author", "value": DEMO_AUTHOR, "source": NAME,
             "confidence": "medium"},
            {"type": "caption", "value": DEMO_CAPTION, "source": NAME,
             "confidence": "medium"},
        ]
        for link in transcript["links"]:
            findings.append(
                {"type": "transcript_link", "value": link, "source": NAME,
                 "confidence": "low"}  # low: stub data, honestly marked
            )
        return {"status": "ok",
                "reason": "demo fixture transcript for %s "
                          "(stub, 2 resource links)" % reel_id,
                "findings": findings}
    # Non-demo public URL: attempt one no-auth metadata read, never invent.
    try:
        meta = fetch_oembed(text)
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    findings = []
    author = meta.get("author_name")
    title = meta.get("title")
    if isinstance(author, str) and author.strip():
        findings.append(
            {"type": "author", "value": author.strip()[:128], "source": NAME,
             "confidence": "medium"}
        )
    if isinstance(title, str) and title.strip():
        findings.append(
            {"type": "caption", "value": title.strip()[:512], "source": NAME,
             "confidence": "medium"}
        )
    if not findings:
        return {"status": "rejected",
                "reason": "rejected: reel %s not found or not public "
                          "(no hallucinated metadata)" % reel_id,
                "findings": []}
    return {"status": "ok",
            "reason": "public metadata for %s" % reel_id, "findings": findings}

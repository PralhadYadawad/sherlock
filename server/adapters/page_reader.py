"""page_reader adapter — polite public-page read with Scrapling-first extraction.

Clean-room reimplementation, MIT (ours). Studied docs only: Scrapling
(D4Vinci/Scrapling, BSD-3-Clause, (c) 2024 Karim Shoair — see attribution
below) + trafilatura (adbar/trafilatura) + readability
(mozilla/readability, buriy/python-readability) README/docs for the
*interface pattern* (HTML-in -> title/text/metadata-out). No code copied
from any of those projects.

Scrapling attribution (BSD-3-Clause, required by license):
  Scrapling by Karim Shoair (karim.shoair@pm.me), Copyright (c) 2024.
  BSD 3-Clause License. Pinned dependency: scrapling==0.4.15 (latest per
  `pip index versions scrapling` on 2026-10-06; PyPI BSD License classifier).
  Used here ONLY as unmodified imports of the plain tiers:
    - `scrapling.Selector` (lxml-backed HTML parser) for structured
      extraction (title / headings / links / body text).
    - `scrapling.spiders.SitemapSpider` PATTERN for the domain-sweep helper
      (`SherlockSitemapSpider`: robots_txt_obey=True, polite throttle,
      max-pages cap). The spider class is defined but never executed with
      live network in this adapter or its tests (fixtures only).
  EXCLUDED (never imported, never used): StealthyFetcher / DynamicFetcher /
  stealth / turnstile / proxy-rotation tiers (scrapling.fetchers.stealth_chrome,
  scrapling.fetchers.chrome, scrapling.engines.toolbelt.proxy_rotation,
  scrapling.engines._browsers._stealth). Rationale: public-GET-only lane,
  no bypass, no obfuscation — plain Fetcher/parser + spiders only.

Optional extraction deps (used ONLY as unmodified imports, never vendored):
  - scrapling (BSD-3-Clause) — primary structured parser (see above)
  - trafilatura (Apache-2.0) — fallback main-text extractor
  - readability-lxml (Apache-2.0) — fallback main-text extractor
All are optional at runtime: when Scrapling is unimportable the adapter
degrades through trafilatura -> readability-lxml -> stdlib fallback
(HTMLParser: <title> + meta description + headings + links). API drift in
any lib degrades to the next tier, never raises.
See server/requirements.txt pins.

What it does: single public-GET of a user-supplied page URL (10s timeout,
Sherlock UA), then extracts title, headings (h1-h3), email addresses ONLY
when already published on the page (visible text or mailto: links — no
lookup, no enrichment, no PII lane), published phones ONLY when already
published (visible text patterns or tel: links — no lookup, no inference),
outbound (cross-host http/https) links, and a short text snippet.
Findings of type ``title`` / ``heading`` / ``email`` / ``outbound_link`` /
``text_snippet`` are legacy (kept for contract stability); NEW in Phase 2:
``published_contact`` findings (``email:addr (published at URL)`` /
``phone:number (published at URL)``) carry the source page URL in the value
(the finding schema has no URL field) with confidence ``low``. Page text
only — never personal/non-published inference.

What it does NOT do (v1 hard rules, unchanged):
  - No JS rendering. Pages that need script execution to show content
    (JS-shell/empty bodies) return ``ok`` + [] with a reason. Never
    hallucinated text.
  - No login-walled / paywalled bypass. Detected walls are ``rejected``
    with a reason naming the rule. Detection is content-based (wall
    phrases + password forms); nothing is submitted, no session, no cookies.
  - No bulk crawling in run(). Exactly one GET per run() call; honor HTTP
    429 with a clean ``rejected`` (back off); cache guidance is 24h at the
    tools layer. Robots/ToS note: this lane fetches only the single
    user-supplied public URL, never follows links, never posts forms, and
    identifies itself with the Sherlock UA so operators can throttle/block
    us. The separate sitemap-sweep helper (plan_sweep / sweep_domain /
    SherlockSitemapSpider) is opt-in, robots_txt_obey=True, polite throttle
    (2.0s delay, 1 concurrent/domain, autothrottle on), max-pages cap, and
    plans from sitemap XML without bulk-fetching pages (page reads still go
    through run() one-by-one).

Free cap / rate behavior: one plain GET per run, no keys, no quotas beyond
the target site's own rate limits (429 -> rejected-clean, see taxonomy).

Failure taxonomy (never hallucinated findings):
  - ``rejected`` + []: empty/non-URL/non-http(s) input, credentialed URLs,
    out-of-scope hosts (fixture mode: non-example.com; live mode: literal
    private/loopback hosts), HTTP 429 (rate-limited), login/paywall content.
  - ``ok`` + []: fetch errors (timeout/DNS/reset), 404/410, 403/bot-gate,
    5xx, non-HTML content, JS-shell/empty pages.
  - ``ok`` + findings: readable public page. Confidence is never "high"
    from a scrape alone (multi-signal -> "medium" title, else "low").

Guardrails (hard): public GET only. NO logins, NO passwords, NO session or
cookie flows, NO email/phone-to-account PII lanes (published on-page
addresses are reported as-is with source URL, never resolved), NO breach
data, NO POSTs, NO stealth/turnstile/proxy tiers.
"""

import gzip
import os
import re
import xml.etree.ElementTree as _ET
from html.parser import HTMLParser
from html import unescape as _unescape
from urllib.parse import urljoin, urlparse

try:
    import requests
except Exception:  # pragma: no cover - offline fallback
    requests = None

NAME = "page_reader"
LICENSE_NOTE = (
    "clean-room reimplementation, MIT (ours). "
    "Studied Scrapling (D4Vinci/Scrapling, BSD-3-Clause (c) 2024 Karim Shoair) "
    "+ trafilatura + readability docs only. "
    "Optional deps scrapling (BSD-3-Clause) + trafilatura + readability-lxml "
    "(Apache-2.0) are pip packages (plain Fetcher/parser + spiders with "
    "robots_txt_obey only; stealth/turnstile/proxy tiers excluded)."
)
# Pinned primary parser version (verified via `pip index versions scrapling`
# on 2026-10-06: latest 0.4.15). Mirrors server/requirements.txt pin.
SCRAPLING_PIN = "0.4.15"

TIMEOUT = 10
USER_AGENT = "SherlockOSINT/0.1 (+https://example.com/osint; public-page-reader)"
MAX_BODY_CHARS = 2_000_000  # demo bound: truncate oversized pages, never OOM
MAX_HEADINGS = 30
MAX_EMAILS = 5
MAX_PHONES = 5
MAX_CONTACTS = 10
MAX_LINKS = 20
SNIPPET_CHARS = 500

# Sitemap-sweep politeness (Scrapling SitemapSpider pattern: robots-obey,
# polite throttle, max-pages cap). run() itself still does exactly one GET.
SPIDER_MAX_PAGES = 20
SPIDER_POLITE_DELAY = 2.0  # seconds between requests (matches 1 req/2s lane style)
SPIDER_CONCURRENT = 1
SPIDER_SITEMAP_CANDIDATES = ("/sitemap.xml", "/sitemap_index.xml")

DEMO_HOST = "example.com"

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)
_WS_RE = re.compile(r"\s+")

# Phone candidates in visible text: optional leading +, then digit-led run of
# digits/separators/parens. Validation (_is_published_phone) decides; the
# regex alone is intentionally loose so negatives are tested at the gate.
_PHONE_CANDIDATE_RE = re.compile(r"\+?\(?\d[\d\s\-\.\(\)]{5,}\d")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YEAR_RANGE_RE = re.compile(r"^\d{4}\s*[-\u2013\u2014]\s*\d{4}$")
_VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)+$")
_IPV4_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")

# Login/paywall wall phrases (lowercase substring match on page text+HTML).
# Kept tight: generic words ("account", "subscribe" alone) do NOT trigger.
_WALL_MARKERS = (
    "log in to continue",
    "login to continue",
    "sign in to continue",
    "sign-in to continue",
    "login required",
    "sign-in required",
    "please log in",
    "please sign in",
    "members only",
    "members-only",
    "subscribe to continue",
    "subscription required",
    "to continue reading, subscribe",
    "for subscribers only",
    "this article is for subscribers",
    "this content is for subscribers",
    "paywall",
    "enter your password",
    "type your password",
)


def is_live_enabled() -> bool:
    """Live reads are opt-in via SHERLOCK_LIVE=1 (else demo/example scope)."""
    return os.environ.get("SHERLOCK_LIVE") == "1"


def _is_demo_host(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    return host == DEMO_HOST or host.endswith("." + DEMO_HOST)


def _is_private_literal(host: str) -> bool:
    """True for loopback/private/non-public literal IPs (live-mode guard)."""
    h = (host or "").lower().rstrip(".")
    if h in ("localhost",):
        return True
    try:
        import ipaddress
        ip = ipaddress.ip_address(h)
    except Exception:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _normalize_url(target, live: bool = False):
    """Return (url, error). Only public http(s) page URLs pass."""
    if target is None:
        return None, "empty target: pass a public page URL"
    text = target.strip() if isinstance(target, str) else ""
    if not text:
        return None, "empty target: pass a public page URL"
    if len(text) > 2048:
        return None, "rejected: URL over 2048 chars"
    lowered = text.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return None, (
            "rejected: pass a public http(s) page URL "
            "(no ftp/data/javascript/bare-host input)"
        )
    try:
        parts = urlparse(text)
    except Exception:
        return None, "rejected: malformed URL"
    host = (parts.hostname or "").lower()
    if not host:
        return None, "rejected: malformed URL (no host)"
    if parts.username or parts.password or "@" in (parts.netloc or ""):
        # Credentialed URLs imply a login flow — out of scope, never fetched.
        return None, "rejected: credentialed URLs are out of scope (no logins)"
    if not live and not _is_demo_host(host):
        return None, (
            "rejected: demo scope is example.com pages only "
            "(no live third-party reads; set SHERLOCK_LIVE=1 for public URLs)"
        )
    if live and _is_private_literal(host):
        return None, (
            "rejected: non-public host (loopback/private/reserved "
            "literals are never fetched)"
        )
    return text, None


def _fetch_page(url, timeout=TIMEOUT):
    """Single polite public-GET. Never raises.

    Returns (status:int|None, content_type:str, body:str). Body is truncated
    to MAX_BODY_CHARS. Any failure -> (None, "", "").
    """
    if requests is None:
        return None, "", ""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        try:
            status = resp.status_code
        except Exception:
            return None, "", ""
        try:
            ctype = resp.headers.get("content-type", "") if resp.headers else ""
        except Exception:
            ctype = ""
        try:
            body = resp.text or ""
        except Exception:
            body = ""
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS]
        return status, str(ctype or ""), body
    except Exception:
        return None, "", ""


def _has_password_form(html: str) -> bool:
    t = (html or "").lower()
    return 'type="password"' in t or "type='password'" in t


def _detect_wall(html: str):
    """Return a wall reason string, or None when the page looks public."""
    lowered = (html or "").lower()
    for marker in _WALL_MARKERS:
        if marker in lowered:
            return (
                "rejected: login-walled/paywalled page "
                "(matched %r; no bypass, public sources only)" % marker
            )
    if _has_password_form(html) and any(
        phrase in lowered
        for phrase in ("log in", "login", "sign in", "account")
    ):
        return (
            "rejected: login-walled page (password form; "
            "no bypass, public sources only)"
        )
    return None


class _PageParser(HTMLParser):
    """Stdlib HTML parse: title, meta description, h1-h3, links, text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self.description = ""
        self.headings = []
        self._in_heading = None
        self._heading_buf = []
        self.links = []  # [(href, link_text)]
        self._in_a = False
        self._a_href = ""
        self._a_text = []
        self.text_chunks = []
        self._skip_depth = 0  # inside script/style/noscript

    def handle_starttag(self, tag, attrs):
        t = (tag or "").lower()
        if t in ("script", "style", "noscript"):
            self._skip_depth += 1
            return
        if t == "title" and not self.title:
            self._in_title = True
        elif t in ("h1", "h2", "h3"):
            self._in_heading = t
            self._heading_buf = []
        elif t == "a":
            href = ""
            for k, v in attrs or []:
                if (k or "").lower() == "href" and isinstance(v, str):
                    href = v.strip()
                    break
            self._in_a = True
            self._a_href = href
            self._a_text = []
        elif t == "meta" and not self.description:
            d = {(k or "").lower(): v for k, v in (attrs or [])}
            name = str(d.get("name", "") or "").lower()
            prop = str(d.get("property", "") or "").lower()
            if name == "description" or prop == "og:description":
                content = d.get("content", "")
                if isinstance(content, str) and content.strip():
                    self.description = content.strip()[:500]

    def handle_endtag(self, tag):
        t = (tag or "").lower()
        if t in ("script", "style", "noscript"):
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if t == "title":
            self._in_title = False
        elif t in ("h1", "h2", "h3") and self._in_heading == t:
            text = _WS_RE.sub(" ", "".join(self._heading_buf)).strip()
            if text and len(self.headings) < MAX_HEADINGS:
                self.headings.append(text[:200])
            self._in_heading = None
            self._heading_buf = []
        elif t == "a" and self._in_a:
            text = _WS_RE.sub(" ", "".join(self._a_text)).strip()
            if self._a_href:
                self.links.append((self._a_href, text[:200]))
            self._in_a = False
            self._a_href = ""
            self._a_text = []

    def handle_data(self, data):
        if self._skip_depth or not data or not data.strip():
            return
        if self._in_title:
            # <title> is head metadata, not visible body text: keep it out
            # of text_chunks so title-only pages read as snippet-less.
            self.title += data
            return
        if self._in_heading is not None:
            self._heading_buf.append(data)
        if self._in_a:
            self._a_text.append(data)
        self.text_chunks.append(data)


def parse_page(html: str, base_url: str = "") -> dict:
    """Parse HTML with stdlib only. Pure function (no I/O, no deps)."""
    parser = _PageParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        pass
    title = _WS_RE.sub(" ", parser.title or "").strip()[:200]
    text = _WS_RE.sub(" ", " ".join(parser.text_chunks or [])).strip()
    return {
        "title": title,
        "description": parser.description,
        "headings": list(parser.headings),
        "links": list(parser.links),
        "text": text,
        "base_url": base_url,
    }


def _scrapling_parse(html: str, base_url: str = ""):
    """Structured parse via Scrapling Selector (plain parser tier only).

    Lazy import so a blocked/missing Scrapling install degrades to None
    (callers fall back to stdlib). Never raises; API drift degrades to None.
    NEVER imports stealth/turnstile/proxy tiers (see module docstring).
    Returns parsed dict (same shape as parse_page + engine tag) or None.
    """
    try:
        from scrapling import Selector  # type: ignore  # BSD-3-Clause
    except Exception:
        return None
    try:
        sel = Selector(html or "", url=base_url or "")
    except Exception:
        return None
    try:
        title_nodes = sel.css("title")
        title = ""
        try:
            if len(title_nodes):
                title = str(title_nodes[0].text or "").strip()[:200]
                title = _WS_RE.sub(" ", title).strip()[:200]
        except Exception:
            title = ""
        description = ""
        try:
            meta = sel.css('meta[name="description"]')
            if len(meta):
                try:
                    description = str(meta[0].attrib.get("content", "") or "")
                except Exception:
                    description = ""
                description = description.strip()[:500]
            if not description:
                og = sel.css('meta[property="og:description"]')
                if len(og):
                    try:
                        description = str(og[0].attrib.get("content", "") or "")
                    except Exception:
                        description = ""
                    description = description.strip()[:500]
        except Exception:
            description = ""
        headings = []
        try:
            for node in sel.css("h1, h2, h3"):
                try:
                    t = _WS_RE.sub(" ", str(node.text or "")).strip()
                except Exception:
                    t = ""
                if t and len(headings) < MAX_HEADINGS:
                    headings.append(t[:200])
        except Exception:
            pass
        links = []
        try:
            for a in sel.css("a"):
                try:
                    href = a.attrib.get("href", "") or ""
                except Exception:
                    href = ""
                if not isinstance(href, str):
                    try:
                        href = str(href)
                    except Exception:
                        continue
                href = href.strip()
                if not href:
                    continue
                try:
                    ltext = str(a.text or "").strip()[:200]
                except Exception:
                    ltext = ""
                links.append((href, ltext))
        except Exception:
            pass
        # Body-only visible text (excludes <title> head metadata so
        # title-only pages read as snippet-less, matching stdlib behavior).
        text = ""
        try:
            bodies = sel.css("body")
            if len(bodies):
                try:
                    raw = str(
                        bodies[0].get_all_text(separator=" ", strip=True) or ""
                    )
                except Exception:
                    raw = ""
            else:
                try:
                    raw = str(sel.get_all_text(separator=" ", strip=True) or "")
                except Exception:
                    raw = ""
                # No <body>: strip a leading title echo if present.
                if title and raw.startswith(title):
                    raw = raw[len(title):]
            text = _WS_RE.sub(" ", raw or "").strip()
        except Exception:
            text = ""
        return {
            "title": title,
            "description": description,
            "headings": list(headings),
            "links": list(links),
            "text": text,
            "base_url": base_url,
            "engine": "scrapling",
        }
    except Exception:
        return None


def _parse_structured(html: str, base_url: str = ""):
    """Scrapling-first structured parse with stdlib fallback.

    Returns (parsed_dict, engine_name) where engine is "scrapling" or
    "stdlib". Never raises (stdlib parse_page never raises either).
    """
    parsed = _scrapling_parse(html, base_url)
    if isinstance(parsed, dict) and (
        parsed.get("title") or parsed.get("text")
        or parsed.get("headings") or parsed.get("links")
        or parsed.get("description")
    ):
        return parsed, "scrapling"
    if isinstance(parsed, dict):
        # Scrapling parsed but page is empty-shell: still prefer its empty
        # shape only when stdlib agrees it is empty; otherwise fall through.
        std = parse_page(html, base_url)
        if not (std.get("title") or std.get("text") or std.get("headings")
                or std.get("links") or std.get("description")):
            parsed["engine"] = "scrapling"
            return parsed, "scrapling"
        return std, "stdlib"
    return parse_page(html, base_url), "stdlib"


def _extract_emails(parsed: dict):
    """Addresses published on the page only (visible text + mailto:)."""
    found = []
    seen = set()

    def _add(addr):
        addr = (addr or "").strip().lower()
        if not addr or addr in seen or len(addr) > 254:
            return
        if _EMAIL_RE.fullmatch(addr):
            seen.add(addr)
            found.append(addr)

    for href, _text in parsed.get("links", []):
        if href.lower().startswith("mailto:"):
            target = href[7:].split("?")[0].strip()
            # percent-decoded mailto bodies stay out; address part only.
            try:
                from urllib.parse import unquote as _uq
                target = _uq(target)
            except Exception:
                pass
            for piece in target.split(","):
                _add(piece.strip())
    for match in _EMAIL_RE.findall(parsed.get("text", "")):
        _add(match)
    return found[:MAX_EMAILS]


def _is_published_phone(candidate: str, *, from_tel_link: bool = False) -> bool:
    """Gate for published-phone acceptance (page text / tel: only).

    Accepts explicit human phone shapes; refuses dates, versions, IPs, year
    ranges, bare short/long digit runs, and anything without a phone signal.
    Never infers: only the literal candidate string is judged.
    """
    s = _WS_RE.sub(" ", (candidate or "")).strip().strip(".,;:!?\"'").strip()
    if not s or len(s) > 40:
        return False
    if "@" in s:  # email fragment, not a phone
        return False
    digits = re.sub(r"\D", "", s)
    if len(digits) < 7 or len(digits) > 15:
        return False
    if _DATE_RE.match(s):
        return False
    if _YEAR_RANGE_RE.match(s):
        return False
    if _VERSION_RE.match(s):
        return False
    if _IPV4_RE.match(s):
        return False
    if from_tel_link:
        # tel: is an explicit published-callable signal: digit count suffices.
        return True
    # Visible text needs a phone signal: leading + or separator/parens.
    if s.startswith("+"):
        return True
    return any(c in s for c in (" ", "-", ".", "(", ")"))


def _extract_phones(parsed: dict):
    """Phone numbers published on the page only (visible text + tel:)."""
    found = []
    seen_digits = set()

    def _add(raw, *, from_tel_link=False):
        norm = _WS_RE.sub(" ", (raw or "")).strip().strip(".,;:!?\"'").strip()
        if not norm:
            return
        if not _is_published_phone(norm, from_tel_link=from_tel_link):
            return
        digits = re.sub(r"\D", "", norm)
        if digits in seen_digits:
            return
        seen_digits.add(digits)
        found.append(norm[:40])

    for href, _text in parsed.get("links", []):
        if href.lower().startswith("tel:"):
            target = href[4:].split("?")[0].split(";")[0].strip()
            try:
                from urllib.parse import unquote as _uq
                target = _uq(target)
            except Exception:
                pass
            _add(target.strip(), from_tel_link=True)
    for match in _PHONE_CANDIDATE_RE.findall(parsed.get("text", "")):
        _add(match.strip(), from_tel_link=False)
    return found[:MAX_PHONES]


def _extract_published_contacts(parsed: dict, page_url: str):
    """Published contacts only -> [{"kind","value"}] (page text / links only).

    Kinds: "email" (visible text or mailto:) / "phone" (visible pattern or
    tel:). NEVER personal/non-published inference: only literal page strings
    passing _EMAIL_RE / _is_published_phone are returned. Empty list when the
    page publishes nothing contact-like.
    """
    contacts = []
    seen = set()
    for addr in _extract_emails(parsed):
        key = ("email", addr.lower())
        if key not in seen:
            seen.add(key)
            contacts.append({"kind": "email", "value": addr})
    for num in _extract_phones(parsed):
        key = ("phone", re.sub(r"\D", "", num))
        if key not in seen:
            seen.add(key)
            contacts.append({"kind": "phone", "value": num})
    return contacts[:MAX_CONTACTS]


def _extract_outbound(parsed: dict, page_url: str):
    """Cross-host http(s) links, resolved absolute, doc order, deduped."""
    try:
        page_host = (urlparse(page_url).hostname or "").lower().rstrip(".")
    except Exception:
        page_host = ""
    out = []
    seen = set()
    for href, _text in parsed.get("links", []):
        h = (href or "").strip()
        if not h or h.lower().startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        try:
            abs_url = urljoin(page_url, h)
        except Exception:
            continue
        try:
            parts = urlparse(abs_url)
        except Exception:
            continue
        if parts.scheme not in ("http", "https") or not parts.hostname:
            continue
        host = parts.hostname.lower().rstrip(".")
        if page_host and host == page_host:
            continue  # internal navigation, not outbound
        clean = abs_url.strip()
        if len(clean) > 2048 or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= MAX_LINKS:
            break
    return out


def _lib_main_text(html: str):
    """Best-effort main-text via optional Apache-2.0 libs.

    Returns (text, engine) or (None, None). Never raises; API drift in
    either lib degrades to None so callers fall back to stdlib text.
    """
    try:
        import trafilatura  # type: ignore
    except Exception:
        trafilatura = None
    if trafilatura is not None:
        try:
            extract = getattr(trafilatura, "extract", None)
            text = extract(html, include_comments=False, include_tables=False) \
                if callable(extract) else None
        except Exception:
            text = None
        if isinstance(text, str) and text.strip():
            return text.strip()[:5000], "trafilatura"
    try:
        from readability import Document  # type: ignore
    except Exception:
        Document = None
    if Document is not None:
        try:
            summary_html = Document(html).summary()
        except Exception:
            summary_html = None
        if isinstance(summary_html, str) and summary_html.strip():
            text = _WS_RE.sub(
                " ", re.sub(r"<[^>]+>", " ", summary_html)).strip()
            text = _unescape(text)
            if text:
                return text[:5000], "readability-lxml"
    return None, None


def extract(html: str, page_url: str):
    """Pure extraction: HTML string -> (findings, detail). No I/O."""
    parsed, _engine = _parse_structured(html, base_url=page_url)
    try:
        lib_text, _engine2 = _lib_main_text(html)
    except Exception:
        lib_text = None
    stdlib_text = parsed.get("text", "")
    # Fallback chain for the snippet body: optional trafilatura/readability
    # main-text first (higher quality when libs are present), otherwise the
    # Scrapling-or-stdlib structured body text. Scrapling-blocked installs
    # therefore degrade cleanly to the pre-Phase-2 behavior.
    main = lib_text if (isinstance(lib_text, str) and lib_text.strip()) \
        else stdlib_text
    main = _WS_RE.sub(" ", main or "").strip()
    findings = []
    title = parsed.get("title", "")
    if title:
        findings.append({
            "type": "title",
            "value": title,
            "source": NAME,
            # Multi-signal (title + body) -> medium, title alone -> low.
            "confidence": "medium" if main else "low",
        })
    for heading in parsed.get("headings", [])[:MAX_HEADINGS]:
        findings.append({
            "type": "heading", "value": heading,
            "source": NAME, "confidence": "low",
        })
    for addr in _extract_emails(parsed):
        findings.append({
            "type": "email", "value": addr,
            "source": NAME, "confidence": "low",
        })
    for link in _extract_outbound(parsed, page_url):
        findings.append({
            "type": "outbound_link", "value": link,
            "source": NAME, "confidence": "low",
        })
    # Phase 2: published contacts with source URL in the value (the finding
    # schema has no URL field). Page text/links only, never inferred.
    for contact in _extract_published_contacts(parsed, page_url):
        kind = contact.get("kind", "")
        raw = contact.get("value", "")
        if not raw:
            continue
        findings.append({
            "type": "published_contact",
            "value": "%s:%s (published at %s)" % (kind, raw, page_url),
            "source": NAME,
            "confidence": "low",
        })
    if main:
        snippet = main[:SNIPPET_CHARS].strip()
        if snippet:
            findings.append({
                "type": "text_snippet", "value": snippet,
                "source": NAME, "confidence": "low",
            })
    elif not findings:
        return [], "empty"
    # Description-only pages (title + meta, no body text): surface the
    # meta description as the snippet so stdlib fallback still reports.
    if main or any(f["type"] == "text_snippet" for f in findings):
        return findings, "full"
    desc = parsed.get("description", "")
    if desc and not any(f["type"] == "text_snippet" for f in findings):
        findings.append({
            "type": "text_snippet", "value": desc[:SNIPPET_CHARS].strip(),
            "source": NAME, "confidence": "low",
        })
        return findings, "meta-fallback"
    return findings, "full"


# ---------------------------------------------------------------------------
# Sitemap-sweep helper (Scrapling SitemapSpider pattern, robots-obey, polite)
# ---------------------------------------------------------------------------

def _strip_ns(tag: str) -> str:
    """Strip an ElementTree ``{ns}local`` tag down to ``local``."""
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def parse_sitemap_xml(body) -> dict:
    """Parse a sitemap/sitemapindex body (pure, no I/O, no network).

    Accepts bytes or str (gzipped bodies decompressed via stdlib gzip).
    Returns {"urls": [...], "sitemaps": [...]} with http(s) URLs only,
    doc order, deduped. Unknown roots / parse failures -> empty (never raises).
    """
    if body is None:
        return {"urls": [], "sitemaps": []}
    raw = body
    if isinstance(raw, str):
        raw = raw.encode("utf-8", errors="replace")
    if not isinstance(raw, (bytes, bytearray)):
        return {"urls": [], "sitemaps": []}
    raw = bytes(raw)
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except Exception:
            return {"urls": [], "sitemaps": []}
    if len(raw) > 5_000_000:  # demo bound, never OOM on hostile sitemaps
        raw = raw[:5_000_000]
    try:
        root = _ET.fromstring(raw)
    except Exception:
        return {"urls": [], "sitemaps": []}
    kind = _strip_ns(getattr(root, "tag", "")).lower()
    urls: list = []
    sitemaps: list = []
    seen_u = set()
    seen_s = set()

    def _clean(u):
        u = (u or "").strip()
        if not u or len(u) > 2048:
            return ""
        try:
            parts = urlparse(u)
        except Exception:
            return ""
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return ""
        return u

    if kind == "urlset":
        for url_el in list(root):
            if _strip_ns(getattr(url_el, "tag", "")).lower() != "url":
                continue
            for child in list(url_el):
                if _strip_ns(getattr(child, "tag", "")).lower() == "loc":
                    loc = _clean(child.text or "")
                    if loc and loc not in seen_u:
                        seen_u.add(loc)
                        urls.append(loc)
                    break
    elif kind == "sitemapindex":
        for sm_el in list(root):
            if _strip_ns(getattr(sm_el, "tag", "")).lower() != "sitemap":
                continue
            for child in list(sm_el):
                if _strip_ns(getattr(child, "tag", "")).lower() == "loc":
                    loc = _clean(child.text or "")
                    if loc and loc not in seen_s:
                        seen_s.add(loc)
                        sitemaps.append(loc)
                    break
    else:
        return {"urls": [], "sitemaps": []}
    return {"urls": urls[:1000], "sitemaps": sitemaps[:1000]}


def plan_sweep(candidate_urls, max_pages: int = SPIDER_MAX_PAGES) -> dict:
    """Cap a candidate URL list to a polite sweep plan (pure, no I/O).

    Dedupes preserving doc order, keeps http(s) only, truncates to max_pages.
    Returns {"pages", "total_found", "capped", "max_pages"}.
    """
    try:
        cap = int(max_pages)
    except Exception:
        cap = SPIDER_MAX_PAGES
    if cap < 1:
        cap = 1
    if cap > 100:
        cap = 100
    deduped = []
    seen = set()
    for u in (candidate_urls or []):
        if not isinstance(u, str):
            continue
        u = u.strip()
        if not u or len(u) > 2048 or u in seen:
            continue
        try:
            parts = urlparse(u)
        except Exception:
            continue
        if parts.scheme not in ("http", "https") or not parts.hostname:
            continue
        seen.add(u)
        deduped.append(u)
    total = len(deduped)
    pages = deduped[:cap]
    return {
        "pages": pages,
        "total_found": total,
        "capped": total > cap,
        "max_pages": cap,
    }


def sweep_domain(domain: str, max_pages: int = SPIDER_MAX_PAGES,
                 fetch_fn=None, sitemap_body=None) -> dict:
    """Plan a polite domain sweep from its sitemap (1 sitemap GET at most).

    Scrapling SitemapSpider pattern: robots_txt_obey=True (callers must honor
    robots.txt before fetching planned pages), polite throttle
    (SPIDER_POLITE_DELAY, 1 concurrent/domain), max-pages cap. This helper
    fetches/parses ONLY the sitemap index (or uses the injected sitemap_body
    in tests) and returns the capped page plan — it never bulk-fetches pages.
    Page reads still go through run() one-by-one.

    fetch_fn(url, timeout) -> (status, ctype, body) defaults to _fetch_page.
    sitemap_body (bytes/str) short-circuits network for tests/fixtures.
    Demo scope: example.com hosts unless SHERLOCK_LIVE=1 (private literals
    never swept). Never raises.
    """
    try:
        cap = int(max_pages)
    except Exception:
        cap = SPIDER_MAX_PAGES
    if cap < 1:
        cap = 1
    if cap > 100:
        cap = 100
    dom = (domain or "").strip().lower().rstrip(".").rstrip("/")
    if not dom:
        return {"status": "rejected",
                "reason": "rejected: empty domain for sweep",
                "pages": []}
    # Allow "https://example.com/..." or bare "example.com".
    try:
        host = (urlparse(dom).hostname if "://" in dom else
                urlparse("https://" + dom).hostname) or ""
    except Exception:
        host = ""
    host = (host or "").lower().rstrip(".")
    if not host:
        return {"status": "rejected",
                "reason": "rejected: malformed domain for sweep",
                "pages": []}
    live = is_live_enabled()
    if not live and not _is_demo_host(host):
        return {"status": "rejected",
                "reason": "rejected: demo sweep scope is example.com only "
                          "(set SHERLOCK_LIVE=1 for public domains)",
                "pages": []}
    if live and _is_private_literal(host):
        return {"status": "rejected",
                "reason": "rejected: non-public host never swept",
                "pages": []}
    parsed = {"urls": [], "sitemaps": []}
    if sitemap_body is not None:
        try:
            parsed = parse_sitemap_xml(sitemap_body)
        except Exception:
            parsed = {"urls": [], "sitemaps": []}
    else:
        fn = fetch_fn or _fetch_page
        sitemap_url = "https://%s/sitemap.xml" % host
        try:
            status, _ctype, sbody = fn(sitemap_url, timeout=TIMEOUT)
        except Exception:
            status, sbody = None, ""
        if status is None:
            return {"status": "ok",
                    "reason": "sweep planned for %s: sitemap unreachable "
                              "(no hallucination; robots_txt_obey=True, "
                              "delay=%.1fs, cap=%d)" % (host, SPIDER_POLITE_DELAY, cap),
                    "pages": []}
        if status is not None and not (200 <= status < 300):
            return {"status": "ok",
                    "reason": "sweep planned for %s: sitemap HTTP %d "
                              "(robots_txt_obey=True, delay=%.1fs, cap=%d)" % (
                                  host, status, SPIDER_POLITE_DELAY, cap),
                    "pages": []}
        try:
            parsed = parse_sitemap_xml(sbody or "")
        except Exception:
            parsed = {"urls": [], "sitemaps": []}
    # Child sitemaps are noted but not recursively fetched here (polite:
    # one sitemap GET per sweep_domain call). Surface them in the reason.
    plan = plan_sweep(parsed.get("urls", []), max_pages=cap)
    note = ("robots_txt_obey=True, delay=%.1fs, 1 concurrent/domain, "
            "cap=%d" % (SPIDER_POLITE_DELAY, cap))
    if parsed.get("sitemaps"):
        return {"status": "ok",
                "reason": "sweep planned for %s: %d page(s) from sitemap "
                          "(+%d child sitemap(s) noted, not fetched; %s)" % (
                              host, len(plan["pages"]),
                              len(parsed["sitemaps"]), note),
                "pages": plan["pages"]}
    return {"status": "ok",
            "reason": "sweep planned for %s: %d page(s) (%s%s)" % (
                host, len(plan["pages"]), note,
                "; capped" if plan["capped"] else ""),
            "pages": plan["pages"]}


# Scrapling SitemapSpider pattern subclass (defined, never executed with live
# network in tests). Import is lazy/guarded so spider extras (curl_cffi and
# friends, needed by scrapling[fetchers]) are NOT required for the adapter or
# its hermetic tests: when the spider tier is unavailable we fall back to an
# equivalent plain-object declaration carrying the same politeness contract.
try:
    from scrapling.spiders import SitemapSpider as _SitemapBase  # type: ignore
    _HAS_SPIDER_TIER = True
except Exception:  # pragma: no cover - spider extras not installed
    _SitemapBase = object  # type: ignore
    _HAS_SPIDER_TIER = False


class SherlockSitemapSpider(_SitemapBase):  # type: ignore
    """Domain-sweep spider declaration (Scrapling SitemapSpider pattern).

    Politeness contract (asserted in tests without network): robots_txt_obey
    True, 2.0s download delay, 1 concurrent request (per domain), autothrottle
    on, max-pages cap. Stealth/turnstile/proxy tiers are NOT used anywhere
    in this module. Instantiate + crawl only against example.com fixtures or
    with SHERLOCK_LIVE=1 public targets, honoring robots.txt.
    """

    name = "sherlock-sitemap"
    # Robots compliance (Scrapling default is False — we override to True).
    robots_txt_obey = True
    # Polite throttle.
    download_delay = SPIDER_POLITE_DELAY
    concurrent_requests = SPIDER_CONCURRENT
    concurrent_requests_per_domain = SPIDER_CONCURRENT
    autothrottle_enabled = True
    autothrottle_start_delay = SPIDER_POLITE_DELAY
    autothrottle_max_delay = 30.0
    # Sweep bound (enforced by plan_sweep/sweep_domain; spiders check it per page).
    max_pages = SPIDER_MAX_PAGES
    sitemap_urls: list = []
    allowed_domains: set = set()


def run(target: str) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [...]}."""
    live = is_live_enabled()
    url, error = _normalize_url(target, live=live)
    if error:
        return {"status": "rejected", "reason": error, "findings": []}
    try:
        status, content_type, body = _fetch_page(url)
    except Exception:
        status, content_type, body = None, "", ""
    if status == 429:
        return {"status": "rejected",
                "reason": "rejected: rate-limited (HTTP 429 from %s); "
                          "backing off, no findings" % url,
                "findings": []}
    if status is None:
        return {"status": "ok",
                "reason": "fetch failed for %s (timeout/DNS/reset; "
                          "no hallucination)" % url,
                "findings": []}
    if status in (404, 410):
        return {"status": "ok",
                "reason": "page not found (HTTP %d) for %s; "
                          "no hallucination" % (status, url),
                "findings": []}
    if status == 403:
        return {"status": "ok",
                "reason": "forbidden/bot-gate (HTTP 403) for %s; "
                          "classified as error, not content" % url,
                "findings": []}
    if status is not None and not (200 <= status < 300):
        return {"status": "ok",
                "reason": "unavailable (HTTP %d) for %s; "
                          "no hallucination" % (status, url),
                "findings": []}
    ctype = (content_type or "").lower()
    if ctype and "html" not in ctype and "text" not in ctype:
        return {"status": "ok",
                "reason": "non-HTML content (%s) for %s; text lane only"
                          % (content_type, url),
                "findings": []}
    if not (body or "").strip():
        return {"status": "ok",
                "reason": "empty body for %s (JS-shell? no JS rendering "
                           "in v1)" % url,
                "findings": []}
    wall = _detect_wall(body)
    if wall:
        return {"status": "rejected", "reason": wall, "findings": []}
    try:
        findings, detail = extract(body, url)
    except Exception as exc:
        return {"status": "rejected",
                "reason": "rejected: unparseable page (%s)"
                          % type(exc).__name__,
                "findings": []}
    if not findings or detail == "empty":
        return {"status": "ok",
                "reason": "no readable text for %s (JS-rendered shell? "
                          "no JS rendering in v1)" % url,
                "findings": []}
    counts = {}
    for f in findings:
        counts[f["type"]] = counts.get(f["type"], 0) + 1
    summary = ", ".join("%d %s" % (counts[k], k)
                        for k in ("title", "heading", "email",
                                  "published_contact",
                                  "outbound_link", "text_snippet")
                        if k in counts)
    return {"status": "ok",
            "reason": "page read for %s (%s)" % (url, summary or "empty"),
            "findings": findings}

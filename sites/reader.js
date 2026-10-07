/* Sherlock page-reader (client-side extractor) — standalone, zero network on load.
 *
 * Clean-room reimplementation, MIT (ours). Studied docs only:
 * mozilla/readability (Apache-2.0) for the interface pattern
 * (DOM-in -> {title, text} finding, zero extra traffic). No code copied,
 * no dependency bundled, nothing fetched on load.
 *
 * What it does:
 *  - extractPageData(doc): extracts {url, title, headings, links} JSON from
 *    the page the user is ALREADY viewing (own DOM) — zero extra traffic.
 *  - extractFromHtml(html, baseUrl): same shape from an HTML string via
 *    DOMParser (pure, no network; never throws, never invents).
 *  - toFindings(data): maps extraction to page_reader findings
 *    (title/heading/outbound_link, low — medium for titled multi-signal).
 *  - fetchAndExtract(url): ONE user-initiated GET from the VISITOR browser
 *    (visitor IP egress — never our server), then extract. Failures resolve
 *    to ok/rejected + [] with a reason; never fake findings.
 *
 * WIRED (Phase 4 doors): sites/index.html loads this file via
 *   <script src="./reader.js"></script>
 * and calls it ONLY inside click handlers (Fetch button). The dashboard
 * stays offline-first: fixtures render with zero network even when this
 * file fails to load (callers guard `typeof SherlockReader`).
 *
 * Contract: SherlockReader.extractPageData(doc, opts) -> plain JSON
 *   {url, title, headings: [{level, text}], links: [{href, text}]}.
 * Never throws on odd DOMs (returns best-effort partial + empty arrays).
 * Caps: 50 headings, 100 links (demo bounds). http(s) links only;
 * mailto:/tel:/javascript: never appear in links (reported server-side
 * as published emails instead).
 */
'use strict';

var SherlockReader = (function () {
  var MAX_HEADINGS = 50;
  var MAX_LINKS = 100;
  var MAX_TEXT = 200;
  var MAX_BODY_CHARS = 2000000;
  var TIMEOUT_MS = 10000;

  function cleanText(value) {
    var s = String(value === null || value === undefined ? '' : value);
    s = s.replace(/\s+/g, ' ').trim();
    if (s.length > MAX_TEXT) s = s.slice(0, MAX_TEXT).trim();
    return s;
  }

  function isHttpUrl(href) {
    if (typeof href !== 'string') return false;
    var h = href.trim().toLowerCase();
    return h.indexOf('http://') === 0 || h.indexOf('https://') === 0;
  }

  function absolutize(href, base) {
    try {
      if (typeof URL !== 'undefined') return new URL(href, base).toString();
    } catch (e) {
      /* fall through to manual fallback below */
    }
    /* Manual fallback for non-browser JS engines (tests): absolute
     * http(s) hrefs pass through; root-relative paths resolve against
     * the page origin. Never throws, never invents hosts. */
    var h = String(href || '').trim();
    if (/^https?:\/\//i.test(h)) return h;
    if (h.indexOf('/') === 0 && typeof base === 'string' && base) {
      var m = base.match(/^(https?:\/\/[^\/?#:]+)/i);
      if (m) return m[1] + h;
    }
    return null;
  }

  function emptyData(url) {
    return { url: String(url || ''), title: '', headings: [], links: [] };
  }

  /* Extract from a document-like: {title, URL, querySelectorAll}.
   * Accepts a real `document` in browsers, or a minimal stub in tests. */
  function extractPageData(rootDoc, opts) {
    var options = opts || {};
    var maxHeadings = options.maxHeadings || MAX_HEADINGS;
    var maxLinks = options.maxLinks || MAX_LINKS;
    var out = { url: '', title: '', headings: [], links: [] };
    if (!rootDoc) return out;
    try {
      out.url = String(rootDoc.URL || rootDoc.url || '');
    } catch (e) { out.url = ''; }
    try {
      out.title = cleanText(rootDoc.title || '');
    } catch (e) { out.title = ''; }
    var base = out.url || (typeof window !== 'undefined' && window.location
      ? String(window.location.href) : '');
    var seenLinks = {};
    try {
      var heads = rootDoc.querySelectorAll
        ? rootDoc.querySelectorAll('h1, h2, h3') : [];
      for (var i = 0; i < heads.length && out.headings.length < maxHeadings; i++) {
        var el = heads[i];
        if (!el) continue;
        var tag = 'h2';
        try {
          tag = String(el.tagName || 'h2').toLowerCase();
          if (tag !== 'h1' && tag !== 'h2' && tag !== 'h3') tag = 'h2';
        } catch (e2) { tag = 'h2'; }
        var text = '';
        try { text = cleanText(el.textContent || el.innerText || ''); }
        catch (e3) { text = ''; }
        if (text) out.headings.push({ level: tag, text: text });
      }
    } catch (e4) { /* best-effort: keep partial headings */ }
    try {
      var anchors = rootDoc.querySelectorAll
        ? rootDoc.querySelectorAll('a[href]') : [];
      for (var j = 0; j < anchors.length && out.links.length < maxLinks; j++) {
        var a = anchors[j];
        if (!a) continue;
        var raw = null;
        try {
          raw = typeof a.getAttribute === 'function'
            ? a.getAttribute('href') : a.href;
        } catch (e5) { raw = null; }
        if (typeof raw !== 'string' || !raw.trim()) continue;
        var abs = absolutize(raw.trim(), base);
        if (!abs || !isHttpUrl(abs) || abs.length > 2048) continue;
        if (seenLinks[abs]) continue;
        var label = '';
        try { label = cleanText(a.textContent || a.innerText || ''); }
        catch (e6) { label = ''; }
        seenLinks[abs] = true;
        out.links.push({ href: abs, text: label });
      }
    } catch (e7) { /* best-effort: keep partial links */ }
    return out;
  }

  /* ---- Live door: URL validation (pure, never fetches) ---- */

  function hostOf(url) {
    try {
      if (typeof URL !== 'undefined') return (new URL(url).hostname || '').toLowerCase();
    } catch (e) { /* fall through to regex */ }
    var m = String(url || '').match(/^https?:\/\/([^\/?#:]+)/i);
    return m ? m[1].toLowerCase() : '';
  }

  function isPrivateHost(host) {
    var h = String(host || '').toLowerCase().replace(/\.$/, '').replace(/^\[|\]$/g, '');
    if (!h) return false;
    if (h === 'localhost' || h === '::1') return true;
    if (h.indexOf('127.') === 0) return true;
    if (h === '0.0.0.0' || h === '::') return true;
    if (h.indexOf('10.') === 0) return true;
    if (h.indexOf('192.168.') === 0) return true;
    if (h.indexOf('169.254.') === 0) return true;
    var m172 = h.match(/^172\.(\d+)\./);
    if (m172) {
      var n = parseInt(m172[1], 10);
      if (n >= 16 && n <= 31) return true;
    }
    if (h.indexOf('fc') === 0 || h.indexOf('fd') === 0 || h.indexOf('fe80') === 0) return true;
    return false;
  }

  function validateUrl(input) {
    var text = (typeof input === 'string') ? input.trim() : '';
    if (!text) return { url: '', error: 'empty target: pass a public http(s) page URL' };
    if (text.length > 2048) return { url: text, error: 'rejected: URL over 2048 chars' };
    var low = text.toLowerCase();
    if (low.indexOf('http://') !== 0 && low.indexOf('https://') !== 0) {
      return { url: text, error: 'rejected: pass a public http(s) page URL (no ftp/data/javascript/bare-host input)' };
    }
    var host = hostOf(text);
    if (!host) return { url: text, error: 'rejected: malformed URL (no host)' };
    /* Credentialed URLs imply a login flow — out of scope, never fetched. */
    var afterScheme = text.replace(/^https?:\/\//i, '');
    var authority = afterScheme.split('/')[0] || '';
    /* Strip IPv6 brackets before userinfo check so colons inside
     * [::1]-style literals are not mistaken for credentials. */
    var authForCheck = authority.replace(/^\[[^\]]*\]/, '[v6]');
    if (authForCheck.indexOf('@') !== -1) {
      return { url: text, error: 'rejected: credentialed URLs are out of scope (no logins)' };
    }
    if (isPrivateHost(host)) {
      return { url: text, error: 'rejected: non-public host (loopback/private/reserved literals are never fetched)' };
    }
    return { url: text, error: null };
  }

  var WALL_MARKERS = [
    'log in to continue',
    'login to continue',
    'sign in to continue',
    'login required',
    'sign-in required',
    'please log in',
    'please sign in',
    'members only',
    'subscribe to continue',
    'subscription required',
    'for subscribers only',
    'this content is for subscribers',
    'paywall',
    'enter your password',
    'type your password'
  ];

  function detectWall(html) {
    var lowered = String(html || '').toLowerCase();
    for (var i = 0; i < WALL_MARKERS.length; i++) {
      if (lowered.indexOf(WALL_MARKERS[i]) !== -1) {
        return 'rejected: login-walled/paywalled page (matched ' + WALL_MARKERS[i] + '; no bypass, public sources only)';
      }
    }
    var hasPw = lowered.indexOf('type="password"') !== -1 || lowered.indexOf("type='password'") !== -1;
    if (hasPw && (lowered.indexOf('log in') !== -1 || lowered.indexOf('login') !== -1 ||
        lowered.indexOf('sign in') !== -1 || lowered.indexOf('account') !== -1)) {
      return 'rejected: login-walled page (password form; no bypass, public sources only)';
    }
    return null;
  }

  /* Parse an HTML string via DOMParser (no network). Never throws,
   * never invents: DOMParser-missing runtimes get base-URL-only shape. */
  function extractFromHtml(html, baseUrl, opts) {
    var base = String(baseUrl || '');
    if (typeof html !== 'string' || !html) return emptyData(base);
    if (typeof DOMParser === 'undefined') return emptyData(base);
    try {
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var data = extractPageData(doc, opts);
      data.url = base || data.url || '';
      return data;
    } catch (e) {
      return emptyData(base);
    }
  }

  function pageHost(url) {
    return hostOf(url).replace(/\.$/, '');
  }

  /* Map extraction to page_reader findings (title/heading/outbound_link).
   * Internal same-host navigation links are skipped (server parity:
   * only cross-host links become outbound_link findings). */
  function toFindings(data, opts) {
    var out = [];
    if (!data) return out;
    var maxLinks = (opts && opts.maxLinks) || MAX_LINKS;
    var maxHeadings = (opts && opts.maxHeadings) || MAX_HEADINGS;
    var pageUrl = String(data.url || '');
    var phost = pageHost(pageUrl);
    var title = String(data.title || '').trim();
    if (title) {
      var heads = Array.isArray(data.headings) ? data.headings : [];
      out.push({
        type: 'title',
        value: title.slice(0, 200),
        source: 'page_reader',
        confidence: heads.length ? 'medium' : 'low'
      });
    }
    var headings = Array.isArray(data.headings) ? data.headings : [];
    for (var i = 0; i < headings.length && out.length < (maxHeadings + 2); i++) {
      var h = headings[i] || {};
      var t = String(h.text || '').trim().slice(0, 200);
      if (!t) continue;
      out.push({ type: 'heading', value: t, source: 'page_reader', confidence: 'low' });
    }
    var seen = {};
    var links = Array.isArray(data.links) ? data.links : [];
    for (var j = 0; j < links.length; j++) {
      var href = links[j] && links[j].href ? String(links[j].href).trim() : '';
      if (!href || !isHttpUrl(href) || href.length > 2048) continue;
      if (seen[href]) continue;
      var lhost = pageHost(href);
      if (phost && lhost && lhost === phost) continue;
      seen[href] = true;
      out.push({ type: 'outbound_link', value: href, source: 'page_reader', confidence: 'low' });
      var nOutbound = 0;
      for (var k = 0; k < out.length; k++) if (out[k].type === 'outbound_link') nOutbound++;
      if (nOutbound >= maxLinks) break;
    }
    return out;
  }

  /* ONE user-initiated GET from the visitor browser (visitor IP egress).
   * Never called on page load — only from an explicit click handler.
   * Always resolves (never rejects with fake data):
   *   ok + findings | ok + [] (miss/degraded) | rejected + [] (bad/walled).
   */
  function fetchAndExtract(url, opts) {
    var v = validateUrl(url);
    if (v.error) {
      return Promise.resolve({ status: 'rejected', reason: v.error, findings: [], data: emptyData(String(url || '')) });
    }
    if (typeof fetch === 'undefined') {
      return Promise.resolve({ status: 'ok', reason: 'fetch unavailable in this browser (no hallucination)', findings: [], data: emptyData(v.url) });
    }
    var options = opts || {};
    var timeoutMs = options.timeoutMs || TIMEOUT_MS;
    var ctrl = null;
    var timer = null;
    try {
      if (typeof AbortController !== 'undefined') ctrl = new AbortController();
    } catch (e) { ctrl = null; }
    if (ctrl) {
      timer = setTimeout(function () { try { ctrl.abort(); } catch (e) {} }, timeoutMs);
    }
    var req = null;
    try {
      req = fetch(v.url, { redirect: 'follow', signal: ctrl ? ctrl.signal : undefined });
    } catch (e) {
      if (timer) clearTimeout(timer);
      return Promise.resolve({ status: 'ok', reason: 'fetch blocked (network) for ' + v.url + ' (no hallucination)', findings: [], data: emptyData(v.url) });
    }
    return req.then(function (resp) {
      if (timer) clearTimeout(timer);
      var status = 0;
      try { status = resp.status || 0; } catch (e) { status = 0; }
      if (status === 429) {
        return { status: 'rejected', reason: 'rejected: rate-limited (HTTP 429 from ' + v.url + '); backing off, no findings', findings: [], data: emptyData(v.url) };
      }
      if (status === 404 || status === 410) {
        return { status: 'ok', reason: 'page not found (HTTP ' + status + ') for ' + v.url + '; no hallucination', findings: [], data: emptyData(v.url) };
      }
      if (status === 403) {
        return { status: 'ok', reason: 'forbidden/bot-gate (HTTP 403) for ' + v.url + '; classified as error, not content', findings: [], data: emptyData(v.url) };
      }
      var okFlag = true;
      try { okFlag = resp.ok; } catch (e) { okFlag = status >= 200 && status < 300; }
      if (!okFlag) {
        return { status: 'ok', reason: 'unavailable (HTTP ' + status + ') for ' + v.url + '; no hallucination', findings: [], data: emptyData(v.url) };
      }
      var ctype = '';
      try { ctype = resp.headers ? (resp.headers.get('content-type') || '') : ''; } catch (e) { ctype = ''; }
      var cl = String(ctype || '').toLowerCase();
      if (cl && cl.indexOf('html') === -1 && cl.indexOf('text') === -1) {
        return { status: 'ok', reason: 'non-HTML content (' + ctype + ') for ' + v.url + '; text lane only', findings: [], data: emptyData(v.url) };
      }
      return resp.text().then(function (body) {
        if (!body || !String(body).trim()) {
          return { status: 'ok', reason: 'empty body for ' + v.url + ' (JS-shell? no JS rendering in v1)', findings: [], data: emptyData(v.url) };
        }
        var wall = detectWall(body);
        if (wall) return { status: 'rejected', reason: wall, findings: [], data: emptyData(v.url) };
        var html = String(body).slice(0, MAX_BODY_CHARS);
        var data = extractFromHtml(html, v.url, options);
        var findings = toFindings(data, options);
        if (!findings.length) {
          return { status: 'ok', reason: 'no readable text for ' + v.url + ' (JS-rendered shell? no JS rendering in v1)', findings: [], data: data };
        }
        return { status: 'ok', reason: 'page read for ' + v.url + ' (' + findings.length + ' finding(s), visitor-browser fetch)', findings: findings, data: data };
      });
    }).catch(function (err) {
      if (timer) clearTimeout(timer);
      var isTimeout = err && (err.name === 'AbortError' || err.name === 'TimeoutError');
      var why = isTimeout ? 'fetch timed out (10s)' : 'fetch blocked (CORS/network)';
      return { status: 'ok', reason: why + ' for ' + v.url + ' (no hallucination; the page may block cross-origin reads)', findings: [], data: emptyData(v.url) };
    });
  }

  return {
    extractPageData: extractPageData,
    extractFromHtml: extractFromHtml,
    toFindings: toFindings,
    fetchAndExtract: fetchAndExtract,
    validateUrl: validateUrl,
    MAX_HEADINGS: MAX_HEADINGS,
    MAX_LINKS: MAX_LINKS
  };
})();

/* UMD-ish export for future bundlers/tests; harmless in plain browsers. */
try {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = SherlockReader;
  } else if (typeof window !== 'undefined') {
    window.SherlockReader = SherlockReader;
  }
} catch (e) { /* non-fatal in locked-down contexts */ }

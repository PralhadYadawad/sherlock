"""exif_local adapter — metadata from user-supplied local files only.

Studied source: ExifTool docs/README only (interface pattern: tag names
such as Model / GPSLatitude / DateTimeOriginal and the IFD tag-directory
layout). Clean-room reimplementation in stdlib only — no ExifTool code,
no subprocess, no vendored tables. MIT (ours).

Contract: input is a LOCAL file path supplied by the user. URLs are
refused outright (no fetching, ever). Only the bytes the user already
provided are parsed.

Extracted fields (when present): camera model, GPS position, capture
timestamp. Each becomes a finding of type ``exif_model`` / ``exif_gps`` /
``exif_timestamp``.

Free cap / rate behavior: pure local compute, no keys, no network, no
rate limits. Guard: files over 25 MiB are refused (demo bound).

Failure taxonomy: URL input, missing/unreadable/oversize files, unknown
formats, and files with no EXIF fields all return clean results (zero
hallucinated fields) — ``rejected`` for bad input, ``ok`` with empty
findings when the file simply has no metadata.
"""

import os
import re
import struct

NAME = "exif_local"
LICENSE_NOTE = (
    "clean-room reimplementation, MIT (ours). Studied ExifTool docs only."
)

MAX_BYTES = 25 * 1024 * 1024

# TIFF field types we decode: (size-in-bytes-per-component, struct-code)
_TIFF_TYPES = {1: (1, "B"), 2: (1, "c"), 3: (2, "H"), 4: (4, "L"), 5: (8, None)}

# Tags of interest: IFD0 Model/Make, EXIF DateTime*, GPS IFD pointer.
_TAG_MODEL = 0x0110
_TAG_MAKE = 0x010F
_TAG_EXIF_IFD = 0x8769
_TAG_GPS_IFD = 0x8825
_TAG_DT_ORIGINAL = 0x9003
_TAG_DT_DIGITIZED = 0x9004
_TAG_GPS_LATREF = 0x0001
_TAG_GPS_LAT = 0x0002
_TAG_GPS_LONREF = 0x0003
_TAG_GPS_LON = 0x0004

_TEXT_MODEL_RE = re.compile(rb"MODEL\s*[:=]\s*([^\r\n]{1,64})", re.IGNORECASE)
_TEXT_GPS_RE = re.compile(
    rb"GPS\s*[:=]\s*([+-]?\d{1,3}(?:\.\d+)?\s*,\s*[+-]?\d{1,3}(?:\.\d+)?)",
    re.IGNORECASE,
)
_TEXT_TS_RE = re.compile(
    rb"(?:TIMESTAMP|DATETIMEORIGINAL|CREATEDATE)\s*[:=]\s*([^\r\n]{1,32})",
    re.IGNORECASE,
)
_TS_LIKE_RE = re.compile(r"^\d{4}[:\-/]\d{2}[:\-/]\d{2}[ T]\d{2}:\d{2}(:\d{2})?")


def _looks_like_url(text):
    lowered = text.strip().lower()
    return lowered.startswith(
        ("http://", "https://", "ftp://", "data:", "www.")
    )


def _rational_to_float(num, den):
    if not den:
        return None
    try:
        return num / den
    except Exception:
        return None


def _read_ifd(data, ifd_offset, endian, out):
    """Minimal TIFF IFD walk; fills out dict tag->python value."""
    if ifd_offset + 2 > len(data):
        return None
    try:
        (count,) = struct.unpack(endian + "H", data[ifd_offset:ifd_offset + 2])
    except struct.error:
        return None
    if count > 200 or ifd_offset + 2 + count * 12 > len(data):
        return None
    next_offset = None
    for i in range(count):
        entry = data[ifd_offset + 2 + i * 12: ifd_offset + 2 + (i + 1) * 12]
        try:
            tag, ftype, ncomp, val_or_off = struct.unpack(endian + "HHI4s", entry)
        except struct.error:
            continue
        if ftype not in _TIFF_TYPES or ncomp <= 0 or ncomp > 4096:
            continue
        size, code = _TIFF_TYPES[ftype]
        total = size * ncomp
        raw = val_or_off if total <= 4 else None
        if raw is None:
            (off,) = struct.unpack(endian + "L", val_or_off)
            if off + total > len(data):
                continue
            raw = data[off:off + total]
        else:
            raw = raw[:total]
        try:
            if ftype == 2:
                out[tag] = raw.split(b"\x00")[0].decode("ascii", "replace").strip()
            elif ftype == 5:
                vals = []
                for k in range(ncomp):
                    n, d = struct.unpack(endian + "LL", raw[k * 8:(k + 1) * 8])
                    f = _rational_to_float(n, d)
                    if f is None:
                        break
                    vals.append(f)
                else:
                    out[tag] = vals
                    continue
            else:
                vals = list(struct.unpack(endian + code * ncomp, raw))
                out[tag] = vals[0] if ncomp == 1 else vals
        except Exception:
            continue
    tail = ifd_offset + 2 + count * 12
    if tail + 4 <= len(data):
        try:
            (next_offset,) = struct.unpack(endian + "L", data[tail:tail + 4])
        except struct.error:
            next_offset = None
    return next_offset


def _tiff_fields(data, tiff_start):
    """Parse TIFF header at tiff_start; return tag dict or {}."""
    if tiff_start + 8 > len(data):
        return {}
    order = data[tiff_start:tiff_start + 2]
    if order == b"II":
        endian = "<"
    elif order == b"MM":
        endian = ">"
    else:
        return {}
    try:
        (magic, ifd0) = struct.unpack(endian + "HI", data[tiff_start + 2:tiff_start + 8])
    except struct.error:
        return {}
    if magic != 42:
        return {}
    base = data[tiff_start:]
    tags = {}
    if ifd0 < len(base):
        _read_ifd(base, ifd0, endian, tags)
    for ptr in (tags.get(_TAG_EXIF_IFD), tags.get(_TAG_GPS_IFD)):
        if isinstance(ptr, int) and 0 <= ptr < len(base):
            try:
                _read_ifd(base, ptr, endian, tags)
            except Exception:
                continue
    return tags


def _dms_to_deg(vals, ref):
    if not isinstance(vals, (list, tuple)) or len(vals) != 3:
        return None
    deg = vals[0] + vals[1] / 60.0 + vals[2] / 3600.0
    if str(ref).upper().startswith(("S", "W")):
        deg = -deg
    return round(deg, 6)


def parse_bytes(data: bytes):
    """Parse raw file bytes -> list of findings (pure function, no I/O)."""
    findings = []
    if not data:
        return findings
    model = None
    gps = None
    timestamp = None
    # 1) Real TIFF/EXIF path: bare TIFF header or JPEG APP1 Exif segment.
    tiff_starts = []
    if data[:2] in (b"II", b"MM"):
        tiff_starts.append(0)
    idx = data.find(b"Exif\x00\x00")
    if idx != -1:
        tiff_starts.append(idx + 6)
    for start in tiff_starts:
        try:
            tags = _tiff_fields(data, start)
        except Exception:
            continue
        if not tags:
            continue
        if model is None:
            for tag in (_TAG_MODEL, _TAG_MAKE):
                val = tags.get(tag)
                if isinstance(val, str) and val:
                    model = val[:64]
                    break
        lat = _dms_to_deg(tags.get(_TAG_GPS_LAT), tags.get(_TAG_GPS_LATREF, "N"))
        lon = _dms_to_deg(tags.get(_TAG_GPS_LON), tags.get(_TAG_GPS_LONREF, "E"))
        if gps is None and lat is not None and lon is not None:
            gps = "%s,%s" % (lat, lon)
        if timestamp is None:
            for tag in (_TAG_DT_ORIGINAL, _TAG_DT_DIGITIZED):
                val = tags.get(tag)
                if isinstance(val, str) and _TS_LIKE_RE.match(val.strip()):
                    timestamp = val.strip()[:32]
                    break
    # 2) Plain-text marker fallback (demo fixtures / sidecar notes).
    # Scans the whole buffered payload (bounded by MAX_BYTES at the
    # caller): markers may sit past any fixed window in large files.
    if model is None:
        m = _TEXT_MODEL_RE.search(data)
        if m:
            model = m.group(1).decode("latin1").strip()[:64] or None
    if gps is None:
        m = _TEXT_GPS_RE.search(data)
        if m:
            gps = m.group(1).decode("latin1").strip()
    if timestamp is None:
        m = _TEXT_TS_RE.search(data)
        if m:
            candidate = m.group(1).decode("latin1").strip()[:32]
            if candidate:
                timestamp = candidate
    if model:
        findings.append(
            {"type": "exif_model", "value": model, "source": NAME,
             "confidence": "high"}
        )
    if gps:
        findings.append(
            {"type": "exif_gps", "value": gps, "source": NAME,
             "confidence": "medium"}
        )
    if timestamp:
        findings.append(
            {"type": "exif_timestamp", "value": timestamp, "source": NAME,
             "confidence": "high"}
        )
    return findings


def run(target: str) -> dict:
    """-> {"status": "ok"|"rejected", "reason": str, "findings": [...]}."""
    if target is None or (isinstance(target, str) and not target.strip()):
        return {"status": "rejected",
                "reason": "empty target: pass a local file path", "findings": []}
    if not isinstance(target, str) or _looks_like_url(target):
        return {"status": "rejected",
                "reason": "refused: URLs are never fetched; "
                          "pass a user-supplied local file path",
                "findings": []}
    path = os.path.expanduser(target.strip())
    if not os.path.isfile(path):
        return {"status": "rejected",
                "reason": "rejected: file not found: %s" % target.strip(),
                "findings": []}
    try:
        size = os.path.getsize(path)
    except OSError:
        return {"status": "rejected",
                "reason": "rejected: unreadable file", "findings": []}
    if size > MAX_BYTES:
        return {"status": "rejected",
                "reason": "rejected: file over 25 MiB demo bound", "findings": []}
    try:
        with open(path, "rb") as fh:
            data = fh.read(MAX_BYTES + 1)
    except OSError:
        return {"status": "rejected",
                "reason": "rejected: unreadable file", "findings": []}
    try:
        findings = parse_bytes(data)
    except Exception as exc:
        return {"status": "rejected",
                "reason": "rejected: unparseable file (%s)" % type(exc).__name__,
                "findings": []}
    if findings:
        reason = "local EXIF: %d field(s) from user-supplied file" % len(findings)
    else:
        reason = "no EXIF fields found in user-supplied file"
    return {"status": "ok", "reason": reason, "findings": findings}

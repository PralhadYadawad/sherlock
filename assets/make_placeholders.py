#!/usr/bin/env python3
"""Regenerate theme-matched PNG placeholders with stdlib only (no external art).

New theme (matches redesigned sites/index.html design system):
  page      #06080d   surfaces #0e141e / #131b28
  accent    cyan #5ac8fa + violet #a78bfa
  lane hues username cyan/blue, domain emerald/teal, reel amber/rose
All art is procedural gradients + geometric motifs (ring, globe arcs, play
wedge). No network, no fonts, no external assets.
"""
import struct
import zlib
import os
import math

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 256


def png_chunk(ctype, data):
    c = struct.pack(">I", len(data)) + ctype + data
    c += struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)
    return c


def write_png(path, rgb_fn, size=SIZE):
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            raw += bytes(rgb_fn(x, y))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr)
           + png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + png_chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    print("wrote", path, len(png), "bytes")


def lerp(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def clamp01(v):
    return 0.0 if v < 0 else 1.0 if v > 1 else v


# Theme stops
BG0 = (6, 8, 13)
SURFACE = (14, 20, 30)
CYAN = (90, 200, 250)
VIOLET = (167, 139, 250)
EMERALD = (52, 211, 153)
AMBER = (251, 191, 36)
ROSE = (251, 113, 133)


def diagonal_glow(x, y, s, c1, c2):
    t = clamp01((x + y) / (2.0 * s))
    base = lerp(BG0, SURFACE, clamp01(y / s * 1.2))
    glow = lerp(c1, c2, t)
    d = abs(x - y) / s
    m = max(0.0, 1.0 - d * 3.0) * 0.35
    return lerp(base, glow, m * 0.6 + t * 0.12)


def ring_edge(x, y, cx, cy, r, w):
    d = math.hypot(x - cx, y - cy)
    return abs(d - r) <= w


def logo_px(x, y, s=SIZE):
    if x < 10 or y < 10 or x >= s - 10 or y >= s - 10:
        return lerp(CYAN, VIOLET, x / s)
    px = diagonal_glow(x, y, s, CYAN, VIOLET)
    # magnifier ring motif, centred slightly above middle
    cx, cy, r = s * 0.46, s * 0.44, s * 0.22
    if ring_edge(x, y, cx, cy, r, 7):
        return lerp(px, (230, 240, 250), 0.9)
    # handle beam to lower-right
    hx, hy = x - (cx + r * 0.7), y - (cy + r * 0.7)
    if 0 <= hx < s * 0.28 and 0 <= hy < s * 0.28 and abs(hx - hy) < 9 and hx > 0 and hy > 0:
        return lerp(px, VIOLET, 0.85)
    # faint dot grid
    if x % 32 < 2 and y % 32 < 2:
        return lerp(px, (148, 163, 184), 0.25)
    return px


def icon_px(x, y, s=SIZE):
    # rounded-square app tile: dark field, cyan top edge, violet beam
    rad, m = 48, 14
    ex = min(x - m, s - m - x)
    ey = min(y - m, s - m - y)
    if ex < 0 or ey < 0:
        return BG0
    if ex + ey < rad and (ex < rad - 6 or ey < rad - 6):
        # crude rounded corner cutout
        if math.hypot(rad - ex, rad - ey) > rad:
            return BG0
    px = diagonal_glow(x, y, s, EMERALD, CYAN)
    if y < m + 5:
        return lerp(px, CYAN, 0.7)
    cx, cy, r = s / 2, s * 0.46, s * 0.20
    if ring_edge(x, y, cx, cy, r, 8):
        return (235, 242, 250)
    if abs((x - cx) - (y - cy)) < 7 and x > cx + r * 0.6 and y > cy + r * 0.6 and x < cx + r * 1.9:
        return VIOLET
    return px


def shot_px(x, y, s=SIZE):
    # dashboard mock: hero bar + 3 lane-tinted card rows on dark field
    if y < 34:
        return lerp(SURFACE, (24, 33, 48), x / s)
    if x < 8 or y < 8 or x >= s - 8 or y >= s - 8:
        return (60, 72, 90)
    # card grid 2 cols x 3 rows
    gx, gy = (x - 20) // 108, (y - 52) // 60
    lx, ly = (x - 20) % 108, (y - 52) % 60
    if 0 <= gx < 2 and 0 <= gy < 3:
        if ly < 16:  # thumb strip tinted per lane row
            lane = [CYAN, EMERALD, AMBER][gy % 3]
            return lerp((16, 24, 36), lane, 0.55)
        if lx < 2 or ly < 2 or lx >= 106 or ly >= 58:
            return (90, 200, 250) if gx == 0 and gy == 0 else (55, 70, 90)
        return (17, 24, 35)
    return (9, 13, 20)


write_png(os.path.join(HERE, "logo.png"), logo_px)
write_png(os.path.join(HERE, "icon.png"), icon_px)
write_png(os.path.join(HERE, "screenshot.png"), shot_px)

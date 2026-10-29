#!/usr/bin/env python3
"""
sitrep_video.py v4 — Broadcast-quality SITREP video engine

Layout:  News broadcast — split screen (text left / Ken Burns image right)
Voice:   en-US-ChristopherNeural (deep, authoritative)
Effects: Ken Burns zoompan · xfade transitions · scrolling news ticker · intro sting
Sources: og:image thumbnails from confirmed news outlets (Al Jazeera, Reuters, etc.)

Usage:
  python3 /opt/conflict-monitor/sitrep_video.py
  python3 /opt/conflict-monitor/sitrep_video.py --out /path/to/output.mp4
"""

import argparse
import asyncio
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import json
import requests
from PIL import Image, ImageDraw, ImageFont

# Load .env so API keys are available when run directly (outside Docker)
_env_path = Path("/opt/conflict-monitor/.env")
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# ── Config ─────────────────────────────────────────────────────────────────────
API_BASE  = "http://localhost:8000"
VIDEO_DIR = Path("/opt/conflict-monitor/videos")
W, H      = 1280, 720
FPS       = 25
XFADE_DUR = 0.5          # seconds of cross-fade between segments
TTS_VOICE = "en-US-ChristopherNeural"   # fallback only

# ElevenLabs config — loaded from .env
ELEVENLABS_API_KEY  = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = "pqHfZKP75CvOlQylNhV4"   # Bill — deep, commanding American
ELEVENLABS_MODEL    = "eleven_multilingual_v2"  # highest quality
ELEVENLABS_SETTINGS = {                          # tuned for news broadcast
    "stability":          0.38,   # dynamic, expressive
    "similarity_boost":   0.82,   # faithful to voice character
    "style":              0.12,   # slight gravitas boost
    "use_speaker_boost":  True,
}

# Panel split: 44% text / 56% image
TEXT_W = 560
IMG_W  = W - TEXT_W       # 720

# Fonts — Open Sans for broadcast look
FONT_DIR    = "/usr/share/fonts/truetype/open-sans"
MONO_DIR    = "/usr/share/fonts/truetype/dejavu"
F_EXTRABOLD = f"{FONT_DIR}/OpenSans-ExtraBold.ttf"
F_BOLD      = f"{FONT_DIR}/OpenSans-Bold.ttf"
F_SEMIBOLD  = f"{FONT_DIR}/OpenSans-Semibold.ttf"
F_REGULAR   = f"{FONT_DIR}/OpenSans-Regular.ttf"
F_MONO      = f"{MONO_DIR}/DejaVuSansMono-Bold.ttf"

# Palette
BG        = (5, 9, 18)
BG_PANEL  = (8, 14, 26)
BG_DARK   = (3, 6, 12)
ACCENT    = (88, 166, 255)      # blue
RED       = (220, 38, 38)
ORANGE    = (234, 88, 12)
YELLOW    = (202, 138, 4)
GREEN     = (22, 163, 74)
PURPLE    = (147, 51, 234)
WHITE     = (240, 245, 255)
OFFWHITE  = (180, 195, 215)
DIM       = (60, 85, 120)
DARKGRAY  = (15, 22, 38)

_BLEND_BG = (10, 14, 25)  # matches BG constant

def blendc(color, alpha: float, bg=_BLEND_BG):
    """Pre-blend a color with the background (PIL 12 ignores RGBA on RGB images)."""
    return (
        int(bg[0] * (1 - alpha) + color[0] * alpha),
        int(bg[1] * (1 - alpha) + color[1] * alpha),
        int(bg[2] * (1 - alpha) + color[2] * alpha),
    )

LEVEL_COLORS = {
    "STABLE":     GREEN,
    "ELEVATED":   YELLOW,
    "ESCALATING": ORANGE,
    "CRITICAL":   RED,
    "WARTIME":    (255, 0, 68),
}

SOURCE_LABELS = {
    "aljazeera.com": "AL JAZEERA",
    "reuters.com": "REUTERS",
    "bbc.com": "BBC NEWS",
    "bbc.co.uk": "BBC NEWS",
    "timesofisrael.com": "TIMES OF ISRAEL",
    "haaretz.com": "HAARETZ",
    "iranintl.com": "IRAN INTERNATIONAL",
    "middleeasteye.net": "MIDDLE EAST EYE",
    "defensenews.com": "DEFENSE NEWS",
    "jpost.com": "JERUSALEM POST",
    "france24.com": "FRANCE 24",
    "apnews.com": "AP NEWS",
    "theguardian.com": "THE GUARDIAN",
    "washingtonpost.com": "WASHINGTON POST",
    "nbcnews.com": "NBC NEWS",
}


# ── Font helpers ───────────────────────────────────────────────────────────────
def fnt(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def text_w(draw, text: str, f) -> int:
    bb = draw.textbbox((0, 0), text, font=f)
    return bb[2] - bb[0]

def text_h(draw, text: str, f) -> int:
    bb = draw.textbbox((0, 0), text, font=f)
    return bb[3] - bb[1]

def wrap_text(draw, text: str, max_w: int, f) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if text_w(draw, test, f) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def draw_wrapped(draw, text: str, x: int, y: int, max_w: int, f,
                 color, spacing: int = 8) -> int:
    for line in wrap_text(draw, text, max_w, f):
        draw.text((x, y), line, font=f, fill=color)
        y += text_h(draw, line, f) + spacing
    return y


# ── Base frame builders ────────────────────────────────────────────────────────

def make_base(fill=BG) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), fill)
    draw = ImageDraw.Draw(img)
    return img, draw


def draw_topbar(draw, sitrep: dict):
    """Slim top bar: CONFLICT MONITOR branding + live badge + timestamp."""
    draw.rectangle([(0, 0), (W, 38)], fill=(4, 8, 18))
    draw.line([(0, 38), (W, 38)], fill=(20, 40, 70), width=1)

    f_label = fnt(F_MONO, 11)
    draw.text((12, 12), "◈ CONFLICT MONITOR  ·  SITREP", font=f_label, fill=ACCENT)

    lvl = sitrep.get("escalation_level", "STABLE")
    lc  = LEVEL_COLORS.get(lvl, GREEN)
    score = int((sitrep.get("escalation_score") or 50))
    lvl_f = fnt(F_BOLD, 11)
    score_f = fnt(F_MONO, 10)
    # Right side: IDX score badge + level + timestamp
    ts = sitrep.get("generated_at", "")[:16].replace("T", "  ") + " UTC"
    ts_f = fnt(F_REGULAR, 10)
    ts_w = text_w(draw, ts, ts_f)
    draw.text((W - 14 - ts_w, 14), ts, font=ts_f, fill=DIM)
    # Level badge
    lw = text_w(draw, f"● {lvl}", lvl_f)
    level_x = W - ts_w - lw - 28
    draw.text((level_x, 13), f"● {lvl}", font=lvl_f, fill=lc)
    # IDX score
    idx_label = f"IDX {score}/100"
    iw = text_w(draw, idx_label, score_f)
    idx_x = level_x - iw - 18
    draw.rectangle([(idx_x - 4, 10), (idx_x + iw + 4, 28)], fill=blendc(lc, 0.20))
    draw.text((idx_x, 13), idx_label, font=score_f, fill=lc)


def draw_bottombar(draw, sitrep: dict, extra: str = ""):
    """Thin bottom bar: truthevades.com + event count."""
    draw.rectangle([(0, H - 30), (W, H)], fill=(4, 8, 18))
    draw.line([(0, H - 30), (W, H - 30)], fill=(15, 30, 55), width=1)
    f = fnt(F_REGULAR, 10)
    left = f"truthevades.com  ·  {sitrep.get('events_analyzed', 0)} events analyzed"
    draw.text((12, H - 20), left, font=f, fill=DIM)
    if extra:
        draw.text((W - 12 - text_w(draw, extra, f), H - 20), extra, font=f, fill=DIM)


def draw_section_tag(draw, label: str, color, x: int, y: int) -> int:
    """Draw a colored section label pill, return new y."""
    f = fnt(F_EXTRABOLD, 11)
    tw = text_w(draw, label, f)
    draw.rectangle([(x, y), (x + tw + 14, y + 22)], fill=blendc(color, 0.20))
    draw.rectangle([(x, y), (x + 3, y + 22)], fill=color)
    draw.text((x + 10, y + 5), label, font=f, fill=color)
    return y + 30


# ── Full-width frame types ─────────────────────────────────────────────────────

def make_intro_frame(sitrep: dict) -> Image.Image:
    """Opening sting — full black with branding."""
    img, draw = make_base(BG_DARK)

    lvl = sitrep.get("escalation_level", "STABLE")
    lc  = LEVEL_COLORS.get(lvl, GREEN)

    # Horizontal accent line
    draw.rectangle([(0, H // 2 - 2), (W, H // 2 + 2)], fill=blendc(lc, 0.50))

    # CONFLICT MONITOR
    f_big = fnt(F_EXTRABOLD, 56)
    label = "CONFLICT MONITOR"
    lw = text_w(draw, label, f_big)
    draw.text(((W - lw) // 2, 200), label, font=f_big, fill=WHITE)

    # SITREP BRIEFING
    f_sub = fnt(F_SEMIBOLD, 22)
    sub = "STRATEGIC SITUATION REPORT"
    sw = text_w(draw, sub, f_sub)
    draw.text(((W - sw) // 2, 276), sub, font=f_sub, fill=DIM)

    # Escalation badge
    f_lvl = fnt(F_EXTRABOLD, 18)
    badge = f"STATUS:  {lvl}"
    bw = text_w(draw, badge, f_lvl) + 32
    bx = (W - bw) // 2
    draw.rectangle([(bx, 330), (bx + bw, 364)], fill=blendc(lc, 0.22), outline=lc)
    draw.text((bx + 16, 337), badge, font=f_lvl, fill=lc)

    # Date
    f_date = fnt(F_REGULAR, 14)
    date_str = datetime.now(timezone.utc).strftime("%d %B %Y").upper()
    dw = text_w(draw, date_str, f_date)
    draw.text(((W - dw) // 2, 385), date_str, font=f_date, fill=DIM)

    return img


def make_headline_frame(sitrep: dict) -> Image.Image:
    """Full-width headline card."""
    img, draw = make_base()
    draw_topbar(draw, sitrep)
    draw_bottombar(draw, sitrep)

    lvl = sitrep.get("escalation_level", "STABLE")
    lc  = LEVEL_COLORS.get(lvl, GREEN)
    headline = sitrep.get("headline", "")

    # Left accent bar
    draw.rectangle([(0, 38), (5, H - 30)], fill=blendc(lc, 0.80))

    # BREAKING / STATUS label
    y = 65
    y = draw_section_tag(draw, f"● {lvl}", lc, 30, y)

    # Big headline
    f_head = fnt(F_EXTRABOLD, 34)
    y += 8
    y = draw_wrapped(draw, headline, 30, y, W - 60, f_head, WHITE, spacing=12)

    # Divider
    y += 18
    draw.line([(30, y), (W - 30, y)], fill=blendc(lc, 0.40), width=1)
    y += 16

    # Subtext stats
    f_stat = fnt(F_SEMIBOLD, 15)
    evts = sitrep.get("events_analyzed", 0)
    trigger = (sitrep.get("trigger") or "auto").upper()
    draw.text((30, y), f"ANALYZING {evts} EVENTS  ·  TRIGGER: {trigger}  ·  PROFESSOR JIANG FRAMEWORK ACTIVE",
              font=f_stat, fill=DIM)

    return img


def make_endcard(sitrep: dict) -> Image.Image:
    img, draw = make_base(BG_DARK)
    lvl = sitrep.get("escalation_level", "STABLE")
    lc  = LEVEL_COLORS.get(lvl, GREEN)

    f_big  = fnt(F_EXTRABOLD, 42)
    f_med  = fnt(F_SEMIBOLD, 18)
    f_sm   = fnt(F_REGULAR, 13)

    label = "CONFLICT MONITOR"
    lw = text_w(draw, label, f_big)
    draw.text(((W - lw) // 2, 220), label, font=f_big, fill=WHITE)

    draw.line([(200, 285), (W - 200, 285)], fill=blendc(ACCENT, 0.50), width=1)

    sub = "LIVE INTELLIGENCE  ·  SITREP ENGINE  ·  PREDICTIVE HISTORY FRAMEWORKS"
    sw = text_w(draw, sub, f_sm)
    draw.text(((W - sw) // 2, 300), sub, font=f_sm, fill=DIM)

    url = "truthevades.com"
    uw = text_w(draw, url, f_med)
    draw.text(((W - uw) // 2, 345), url, font=f_med, fill=ACCENT)

    status = f"Current Status: {lvl}"
    stw = text_w(draw, status, f_sm)
    draw.text(((W - stw) // 2, 400), status, font=f_sm, fill=lc)

    return img


# ── Split-screen frame (text left + image right placeholder) ──────────────────

def make_text_panel(section_label: str, label_color,
                    bullets: list[str], sitrep: dict,
                    source_label: str = "") -> Image.Image:
    """Left text panel only (TEXT_W × H). Image added later via FFmpeg."""
    img = Image.new("RGB", (TEXT_W, H), BG_PANEL)
    draw = ImageDraw.Draw(img)

    lvl = sitrep.get("escalation_level", "STABLE")
    lc  = LEVEL_COLORS.get(lvl, GREEN)

    # Top micro-bar
    draw.rectangle([(0, 0), (TEXT_W, 38)], fill=(4, 8, 18))
    draw.line([(0, 38), (TEXT_W, 38)], fill=(15, 30, 55), width=1)
    f_label = fnt(F_MONO, 10)
    draw.text((10, 13), "◈ CONFLICT MONITOR  ·  SITREP", font=f_label, fill=ACCENT)

    # Vertical accent line
    draw.rectangle([(0, 38), (3, H - 26)], fill=label_color)

    # Section label tag
    y = 54
    y = draw_section_tag(draw, section_label, label_color, 16, y)

    # Bullets
    f_bullet_label = fnt(F_EXTRABOLD, 13)
    f_bullet_text  = fnt(F_REGULAR, 14)
    pad = 16

    for bullet in bullets[:4]:
        if y > H - 80:
            break
        bullet = bullet.strip().lstrip("•").strip()

        # Split "LABEL — text" into colored label + white text
        if " — " in bullet:
            blabel, btext = bullet.split(" — ", 1)
            blabel = blabel.strip()
            btext  = btext.strip()
            # Remove [src:...] citations
            btext = re.sub(r'\[src:[^\]]+\]', '', btext).strip()
            btext = re.sub(r'\[(CONFIRMED|REPORTED|CLAIMED)\]', '', btext).strip()

            draw.text((pad, y), blabel + " —", font=f_bullet_label, fill=label_color)
            y += text_h(draw, blabel, f_bullet_label) + 4
            y = draw_wrapped(draw, btext, pad + 8, y, TEXT_W - pad - 8,
                             f_bullet_text, OFFWHITE, spacing=5)
        else:
            bullet = re.sub(r'\[src:[^\]]+\]', '', bullet).strip()
            y = draw_wrapped(draw, bullet, pad, y, TEXT_W - pad - 8,
                             f_bullet_text, OFFWHITE, spacing=5)
        y += 14

    # Bottom source credit strip
    if source_label:
        draw.rectangle([(0, H - 26), (TEXT_W, H)], fill=(3, 6, 14))
        draw.line([(0, H - 26), (TEXT_W, H - 26)], fill=(15, 28, 50), width=1)
        f_src = fnt(F_REGULAR, 10)
        draw.text((10, H - 17), f"SOURCE: {source_label}", font=f_src, fill=DIM)

    return img


def make_fullwidth_text_frame(section_label: str, label_color,
                               bullets: list[str], sitrep: dict) -> Image.Image:
    """Full-width text frame for historical analogue and single-column content."""
    img, draw = make_base()
    draw_topbar(draw, sitrep)
    draw_bottombar(draw, sitrep)

    draw.rectangle([(0, 38), (4, H - 30)], fill=label_color)

    y = 55
    y = draw_section_tag(draw, section_label, label_color, 20, y)

    f_text = fnt(F_REGULAR, 16)
    f_bold = fnt(F_BOLD, 16)
    pad = 20

    for bullet in bullets[:5]:
        if y > H - 50:
            break
        bullet = bullet.strip().lstrip("•").strip()
        bullet = re.sub(r'\[src:[^\]]+\]', '', bullet).strip()
        bullet = re.sub(r'\[(CONFIRMED|REPORTED|CLAIMED)\]', '', bullet).strip()

        if " — " in bullet:
            blabel, btext = bullet.split(" — ", 1)
            draw.text((pad, y), blabel.strip() + " —", font=f_bold, fill=label_color)
            y += text_h(draw, blabel, f_bold) + 4
            y = draw_wrapped(draw, btext.strip(), pad + 12, y,
                             W - pad - 20, f_text, OFFWHITE, spacing=7)
        else:
            y = draw_wrapped(draw, bullet, pad, y, W - pad - 20, f_text, OFFWHITE, spacing=7)
        y += 16

    return img


# ── DB + API helpers ───────────────────────────────────────────────────────────

def psql(sql: str) -> list[list[str]]:
    cmd = [
        "docker", "exec",
        "-e", "PGPASSWORD=ConflictMon1t0r!",
        "conflict-monitor-db-1",
        "psql", "-U", "postgres", "-d", "conflict_monitor",
        "-t", "-A", "-F", "|||", "-c", sql,
    ]
    try:
        out = subprocess.check_output(cmd, text=True, timeout=12)
        rows = []
        for line in out.strip().splitlines():
            parts = line.split("|||")
            if any(p.strip() for p in parts):
                rows.append([p.strip() for p in parts])
        return rows
    except Exception as e:
        print(f"[db] query failed: {e}")
        return []


def get_ticker_events() -> str:
    """Fetch top events for the scrolling ticker."""
    rows = psql(
        "SELECT severity, "
        "REPLACE(REPLACE(LEFT(summary, 90), chr(10), ' '), '|||', ' ') "
        "FROM events "
        "WHERE severity >= 6 "
        "  AND timestamp > NOW() - INTERVAL '24 hours' "
        "  AND NOT summary LIKE '[MERGED%' "
        "ORDER BY severity DESC, timestamp DESC LIMIT 12"
    )
    parts = []
    for r in rows:
        if len(r) >= 2:
            parts.append(f"  ●  SEV{r[0]}: {r[1].upper()}")
    return ("  " + "   ·   ".join(parts) + "   ") * 3 if parts else ""


def get_sitrep_history(limit: int = 12) -> list[dict]:
    """Fetch recent sitrep escalation history for timeline chart."""
    rows = psql(
        f"SELECT id, escalation_level, escalation_score, generated_at "
        f"FROM sitreps "
        f"ORDER BY generated_at DESC LIMIT {limit}"
    )
    result = []
    for r in rows:
        if len(r) >= 4:
            result.append({"id": int(r[0]), "level": r[1], "score": int(r[2] or 50), "ts": r[3]})
        elif len(r) >= 3:
            result.append({"id": int(r[0]), "level": r[1], "score": 50, "ts": r[2]})
    return list(reversed(result))  # oldest first


def get_key_events_for_sitrep(key_ids: list[int]) -> list[dict]:
    """Fetch the key trigger events for this SITREP."""
    if not key_ids:
        return []
    ids_str = ",".join(str(i) for i in key_ids[:6])
    rows = psql(
        f"SELECT id, severity, event_type, location_name, source_url, channel_name, "
        f"REPLACE(REPLACE(LEFT(summary, 180), chr(10), ' '), '|||', ' '), source "
        f"FROM events WHERE id IN ({ids_str}) ORDER BY severity DESC"
    )
    result = []
    for r in rows:
        if len(r) >= 8:
            src = r[7]
            if "tg_" in src or "telegram" in src:
                net = "TELEGRAM"
            elif src.startswith("rss_x_"):
                net = "X / TWITTER"
            else:
                net = "RSS"
            result.append({
                "id": r[0], "severity": r[1], "event_type": r[2],
                "location": r[3], "source_url": r[4], "channel": r[5],
                "summary": r[6], "network": net,
            })
    return result


# ── New high-quality frame builders ───────────────────────────────────────────

def make_threat_dashboard_frame(sitrep: dict, history: list[dict]) -> Image.Image:
    """
    SITUATION ROOM dashboard — broadcast-quality status card.
    Left: escalation meter, score, delta, level. Right: top situation drivers.
    Far more watchable than a raw time-series chart.
    """
    img, draw = make_base()
    draw_topbar(draw, sitrep)
    draw_bottombar(draw, sitrep, "SITUATION ROOM  ·  LIVE THREAT ASSESSMENT")

    lvl = sitrep.get("escalation_level", "STABLE")
    lc  = LEVEL_COLORS.get(lvl, GREEN)
    cur_score = int(sitrep.get("escalation_score") or 50)

    # ── Section header ──────────────────────────────────────────────────────────
    y = 50
    y = draw_section_tag(draw, "◈ LIVE THREAT ASSESSMENT  ·  CONFLICT MONITOR FRAMEWORK", lc, 20, y)

    divider_x = W // 2 - 10
    content_y = y + 10

    # ═══ LEFT: THREAT METER ════════════════════════════════════════════════════

    # Big score circle
    cx, cy_c = 190, content_y + 100
    r_outer, r_inner = 95, 62
    # Outer glow ring
    draw.ellipse([(cx - r_outer - 8, cy_c - r_outer - 8),
                  (cx + r_outer + 8, cy_c + r_outer + 8)],
                 fill=blendc(lc, 0.12))
    # Colored outer ring
    draw.ellipse([(cx - r_outer, cy_c - r_outer), (cx + r_outer, cy_c + r_outer)],
                 fill=blendc(lc, 0.30), outline=lc)
    # Inner dark fill
    draw.ellipse([(cx - r_inner, cy_c - r_inner), (cx + r_inner, cy_c + r_inner)],
                 fill=(5, 9, 18))
    # Score number
    f_score_num = fnt(F_EXTRABOLD, 54)
    score_str = str(cur_score)
    sw = text_w(draw, score_str, f_score_num)
    draw.text((cx - sw // 2, cy_c - 34), score_str, font=f_score_num, fill=lc)
    # /100
    f_denom = fnt(F_MONO, 11)
    dw = text_w(draw, "/100", f_denom)
    draw.text((cx - dw // 2, cy_c + 22), "/100", font=f_denom, fill=blendc(lc, 0.60))

    # Level badge below circle
    f_lvl = fnt(F_EXTRABOLD, 16)
    lbl = f"▶  {lvl}"
    lw = text_w(draw, lbl, f_lvl) + 28
    lbx = cx - lw // 2
    lby = cy_c + r_outer + 14
    draw.rectangle([(lbx, lby), (lbx + lw, lby + 28)], fill=blendc(lc, 0.22), outline=lc)
    draw.text((lbx + 14, lby + 6), lbl, font=f_lvl, fill=lc)

    # Delta vs previous SITREP
    if len(history) >= 2:
        prev_score = int(history[-2].get("score") or 50)
        delta = cur_score - prev_score
        f_delta = fnt(F_BOLD, 14)
        if delta != 0:
            delta_str = f"{'▲' if delta > 0 else '▼'} {abs(delta):+d} FROM LAST SITREP"
            delta_color = RED if delta > 0 else GREEN
            dw2 = text_w(draw, delta_str, f_delta)
            draw.text((cx - dw2 // 2, lby + 42), delta_str, font=f_delta, fill=delta_color)
        else:
            f_nc = fnt(F_REGULAR, 13)
            nc_str = "◆  NO CHANGE FROM LAST SITREP"
            nw = text_w(draw, nc_str, f_nc)
            draw.text((cx - nw // 2, lby + 42), nc_str, font=f_nc, fill=DIM)

    # Compact history sparkline below delta (last 8 points)
    spark_y = lby + 72
    spark_h = 36
    spark_x0 = 30
    spark_x1 = divider_x - 20
    spark_w = spark_x1 - spark_x0
    recent = history[-8:] if len(history) >= 2 else []
    if len(recent) >= 2:
        min_s = min(int(h.get("score") or 50) for h in recent)
        max_s = max(int(h.get("score") or 50) for h in recent)
        rng = max(max_s - min_s, 5)
        pts = []
        for i, h in enumerate(recent):
            sc = int(h.get("score") or 50)
            px = spark_x0 + int(i / (len(recent) - 1) * spark_w)
            py = spark_y + spark_h - int((sc - min_s) / rng * spark_h)
            pts.append((px, py, sc, h.get("level", "STABLE")))
        for i in range(len(pts) - 1):
            px1, py1, _, lv1 = pts[i]
            px2, py2, _, lv2 = pts[i + 1]
            draw.line([(px1, py1), (px2, py2)], fill=blendc(LEVEL_COLORS.get(lv2, GREEN), 0.80), width=2)
        for px, py, sc, lv in pts:
            lcp = LEVEL_COLORS.get(lv, GREEN)
            draw.ellipse([(px - 3, py - 3), (px + 3, py + 3)], fill=lcp)
        f_spark = fnt(F_MONO, 8)
        draw.text((spark_x0, spark_y + spark_h + 3), "◀ HISTORY", font=f_spark, fill=DIM)
        draw.text((spark_x1 - 50, spark_y + spark_h + 3), "NOW ▶", font=f_spark, fill=blendc(lc, 0.70))

    # ── Vertical divider ────────────────────────────────────────────────────────
    draw.line([(divider_x, content_y), (divider_x, H - 36)], fill=blendc(DIM, 0.40), width=1)

    # ═══ RIGHT: STRATEGIC DRIVERS ══════════════════════════════════════════════
    rx = divider_x + 22
    ry = content_y

    f_sec = fnt(F_EXTRABOLD, 11)
    draw.text((rx, ry), "STRATEGIC DRIVERS", font=f_sec, fill=blendc(lc, 0.80))
    ry += 20
    draw.line([(rx, ry), (W - 20, ry)], fill=blendc(lc, 0.35), width=1)
    ry += 10

    esc_bullets = []
    esc_raw = sitrep.get("escalation_text") or ""
    for line in esc_raw.split("\n"):
        line = line.strip().lstrip("•").strip()
        line = re.sub(r'\[src:[^\]]+\]', '', line).strip()
        line = re.sub(r'\[(CONFIRMED|REPORTED|CLAIMED)\]\s*', '', line).strip()
        if line:
            esc_bullets.append(line)

    f_driver = fnt(F_REGULAR, 13)
    f_driver_bold = fnt(F_BOLD, 13)
    for bullet in esc_bullets[:3]:
        if ry > H - 50:
            break
        # Accent dot
        draw.ellipse([(rx, ry + 4), (rx + 6, ry + 10)], fill=lc)
        bx2 = rx + 14
        if " — " in bullet:
            tag, rest = bullet.split(" — ", 1)
            draw.text((bx2, ry), tag.strip()[:28] + " —", font=f_driver_bold, fill=lc)
            ry += 18
            ry = draw_wrapped(draw, rest.strip(), bx2, ry, W - bx2 - 20, f_driver, OFFWHITE, spacing=5)
        else:
            ry = draw_wrapped(draw, bullet[:220], bx2, ry, W - bx2 - 20, f_driver, OFFWHITE, spacing=5)
        ry += 14

    # Humanitarian / stakes line
    if ry < H - 80:
        hum = sitrep.get("humanitarian_ground") or ""
        hum_line = ""
        for ln in hum.split("\n"):
            ln = ln.strip().lstrip("•").strip()
            ln = re.sub(r'\[src:[^\]]+\]', '', ln).strip()
            if ln:
                hum_line = ln[:160]
                break
        if hum_line:
            ry += 4
            draw.line([(rx, ry), (W - 20, ry)], fill=blendc(DIM, 0.30), width=1)
            ry += 8
            f_hum_lbl = fnt(F_EXTRABOLD, 10)
            draw.text((rx, ry), "HUMANITARIAN", font=f_hum_lbl, fill=blendc(ORANGE, 0.80))
            ry += 16
            f_hum = fnt(F_REGULAR, 12)
            ry = draw_wrapped(draw, hum_line, rx, ry, W - rx - 20, f_hum, blendc(OFFWHITE, 0.80), spacing=4)

    return img


def make_escalation_chart_frame(sitrep: dict, history: list[dict]) -> Image.Image:
    """
    Full-width escalation index chart — 0-100 numeric score, broadcast data viz style.
    Shows last N sitrep escalation scores as a continuous time-series with
    colored threshold bands (STABLE/ELEVATED/ESCALATING/CRITICAL/WARTIME),
    gradient fill, score labels, and delta indicators.
    (LEGACY — kept as fallback, replaced by make_threat_dashboard_frame in pipeline)
    """
    img, draw = make_base()
    draw_topbar(draw, sitrep)
    draw_bottombar(draw, sitrep, "ESCALATION INDEX  ·  0 – 100")

    lvl = sitrep.get("escalation_level", "STABLE")
    lc  = LEVEL_COLORS.get(lvl, GREEN)
    cur_score = int((sitrep.get("escalation_score") or 50))

    # Section label
    y = 50
    y = draw_section_tag(draw, "◈ STRATEGIC ESCALATION INDEX  ·  CONFLICT MONITOR FRAMEWORK", lc, 20, y)

    if not history:
        draw.text((W // 2, H // 2), "NO HISTORY DATA", font=fnt(F_BOLD, 18), fill=DIM)
        return img

    # Chart area
    pad_l, pad_r = 96, 88
    pad_t, pad_b = y + 10, 60
    chart_x = pad_l
    chart_y = pad_t
    chart_w = W - pad_l - pad_r
    chart_h = H - pad_t - pad_b - 30

    def score_to_y(s):
        return chart_y + chart_h - int((s / 100) * chart_h)

    # Threshold band data: (threshold_score, label, color)
    WARTIME_COLOR = (255, 0, 68)
    THRESHOLDS = [
        (88, "WARTIME",    WARTIME_COLOR),
        (70, "CRITICAL",   RED),
        (52, "ESCALATING", ORANGE),
        (34, "ELEVATED",   YELLOW),
        (0,  "STABLE",     GREEN),
    ]

    # Draw threshold bands (subtle tinted backgrounds, pre-blended)
    band_tops    = [88, 70, 52, 34, 0]
    band_bottoms = [100, 88, 70, 52, 34]
    band_colors  = [WARTIME_COLOR, RED, ORANGE, YELLOW, GREEN]
    band_names   = ["WARTIME", "CRITICAL", "ESCALATING", "ELEVATED", "STABLE"]
    for top_score, bot_score, color, name in zip(band_tops, band_bottoms, band_colors, band_names):
        gy1 = score_to_y(bot_score)
        gy2 = score_to_y(top_score)
        draw.rectangle([(chart_x, gy1), (chart_x + chart_w, gy2)], fill=blendc(color, 0.18))

    # Draw threshold lines (more visible dividers)
    for thresh, name, color in THRESHOLDS:
        if thresh == 0:
            continue
        gy = score_to_y(thresh)
        draw.line([(chart_x, gy), (chart_x + chart_w, gy)], fill=blendc(color, 0.55), width=1)
        f_thresh = fnt(F_MONO, 8)
        t_label = f"{thresh}"
        draw.text((chart_x + chart_w + 4, gy - 5), t_label, font=f_thresh, fill=blendc(color, 0.75))
        f_band = fnt(F_MONO, 7)
        draw.text((chart_x + chart_w + 4, gy - 16), name, font=f_band, fill=blendc(color, 0.60))

    # Y-axis tick marks and labels (0, 25, 50, 75, 100)
    for tick in [0, 25, 50, 75, 100]:
        gy = score_to_y(tick)
        draw.line([(chart_x - 5, gy), (chart_x, gy)], fill=DIM, width=1)
        f_ytick = fnt(F_MONO, 9)
        t_label = str(tick)
        lw_t = text_w(draw, t_label, f_ytick)
        draw.text((chart_x - 8 - lw_t, gy - 5), t_label, font=f_ytick, fill=DIM)
        # Faint horizontal grid line
        if tick > 0:
            draw.line([(chart_x, gy), (chart_x + chart_w, gy)], fill=blendc(DIM, 0.25), width=1)

    # Y-axis label
    f_yaxis = fnt(F_MONO, 8)
    draw.text((6, chart_y + chart_h // 2 - 20), "ESCALATION", font=f_yaxis, fill=DIM)
    draw.text((6, chart_y + chart_h // 2 - 8),  "INDEX",      font=f_yaxis, fill=DIM)

    # Compute point positions using score
    n = len(history)
    points = []
    for i, h in enumerate(history):
        score = int(h.get("score") or 50)
        level = h.get("level", "STABLE")
        px = chart_x + int(i / max(n - 1, 1) * chart_w)
        py = score_to_y(score)
        points.append((px, py, score, level, h))

    # Draw filled area under the line (pre-blended per-level fill polygons)
    if len(points) >= 2:
        for seg_i in range(len(points) - 1):
            px1, py1, sc1, lv1, _ = points[seg_i]
            px2, py2, sc2, lv2, _ = points[seg_i + 1]
            lc1 = LEVEL_COLORS.get(lv1, GREEN)
            bottom = chart_y + chart_h
            fill_color = blendc(lc1, 0.28)
            # Draw trapezoid polygon for area fill
            poly = [(px1, py1), (px2, py2), (px2, bottom), (px1, bottom)]
            draw.polygon(poly, fill=fill_color)

    # Draw connecting line segments (full-bright, colored by destination level)
    for i in range(len(points) - 1):
        px1, py1, sc1, lv1, _ = points[i]
        px2, py2, sc2, lv2, _ = points[i + 1]
        lc2 = LEVEL_COLORS.get(lv2, GREEN)
        draw.line([(px1, py1), (px2, py2)], fill=lc2, width=3)

    # Draw dots and score labels
    for px, py, sc, lv, h in points:
        lc_pt = LEVEL_COLORS.get(lv, GREEN)
        is_current = (h.get("id") == sitrep.get("id"))
        dot_r = 9 if is_current else 5
        # Glow ring for current dot
        if is_current:
            draw.ellipse([(px - dot_r - 4, py - dot_r - 4), (px + dot_r + 4, py + dot_r + 4)],
                         fill=blendc(lc_pt, 0.35))
        draw.ellipse([(px - dot_r, py - dot_r), (px + dot_r, py + dot_r)],
                     fill=lc_pt, outline=(255, 255, 255) if is_current else lc_pt)

        # Score label above dot
        f_score = fnt(F_EXTRABOLD if is_current else F_MONO, 11 if is_current else 9)
        score_label = str(sc)
        sw2 = text_w(draw, score_label, f_score)
        label_y = py - dot_r - 16
        if is_current:
            draw.rectangle([(px - sw2 // 2 - 4, label_y - 2), (px + sw2 // 2 + 4, label_y + 13)],
                           fill=blendc(lc_pt, 0.30))
        draw.text((px - sw2 // 2, label_y), score_label, font=f_score, fill=lc_pt)

        # SITREP ID label below dot
        f_id = fnt(F_MONO, 7)
        id_label = f"#{h.get('id', '?')}"
        iw2 = text_w(draw, id_label, f_id)
        draw.text((px - iw2 // 2, py + dot_r + 3), id_label, font=f_id,
                  fill=blendc(lc_pt, 0.80))

    # Current score large badge — top right of chart
    f_score_big = fnt(F_EXTRABOLD, 36)
    f_score_sub = fnt(F_MONO, 12)
    f_score_lvl = fnt(F_BOLD, 14)

    score_str = str(cur_score)
    ssw = text_w(draw, score_str, f_score_big)
    slash_str = "/100"
    slw = text_w(draw, slash_str, f_score_sub)

    badge_pad = 16
    badge_w = ssw + slw + badge_pad * 2 + 6
    badge_h = 68
    bx = W - badge_w - 20
    by_pos = 50

    draw.rectangle([(bx, by_pos), (bx + badge_w, by_pos + badge_h)],
                   fill=blendc(lc, 0.18), outline=lc)
    draw.text((bx + badge_pad, by_pos + 8), score_str, font=f_score_big, fill=lc)
    draw.text((bx + badge_pad + ssw + 4, by_pos + 26), slash_str, font=f_score_sub, fill=blendc(lc, 0.60))

    # Level label below score
    lvl_label = f"▶ {lvl}"
    llw = text_w(draw, lvl_label, f_score_lvl)
    draw.text((bx + badge_pad, by_pos + badge_h - 22), lvl_label, font=f_score_lvl, fill=lc)

    # Delta indicator (score change from previous SITREP)
    if len(points) >= 2:
        prev_score = points[-2][2]
        delta = cur_score - prev_score
        if delta != 0:
            f_delta = fnt(F_BOLD, 13)
            delta_str = f"{'▲' if delta > 0 else '▼'}{abs(delta)}"
            delta_color = RED if delta > 0 else GREEN
            dw = text_w(draw, delta_str, f_delta)
            draw.text((bx + badge_w - dw - 10, by_pos + badge_h - 22),
                      delta_str, font=f_delta, fill=delta_color)

    # X-axis label
    f_xlabel = fnt(F_REGULAR, 10)
    xlabel = "← HISTORICAL SITREP SEQUENCE   (MOST RECENT →)"
    xw = text_w(draw, xlabel, f_xlabel)
    draw.text(((W - xw) // 2, chart_y + chart_h + 10), xlabel, font=f_xlabel, fill=DIM)

    return img


def make_event_cards_frame(sitrep: dict, key_events: list[dict]) -> Image.Image:
    """
    Full-width 'BREAKING INTEL' cards frame — shows the key trigger events
    that drove this SITREP with source attribution, severity badges, and summaries.
    Professional broadcast lower-third style layout.
    """
    img, draw = make_base()
    draw_topbar(draw, sitrep)
    draw_bottombar(draw, sitrep, "KEY INTELLIGENCE SOURCES")

    lvl = sitrep.get("escalation_level", "STABLE")
    lc  = LEVEL_COLORS.get(lvl, GREEN)

    y = 50
    y = draw_section_tag(draw, "◈ KEY TRIGGER EVENTS — SITREP INTELLIGENCE BASIS", lc, 20, y)

    if not key_events:
        f_nm = fnt(F_REGULAR, 14)
        nmw = text_w(draw, "NO KEY EVENTS DATA", f_nm)
        draw.text(((W - nmw) // 2, H // 2), "NO KEY EVENTS DATA", font=f_nm, fill=DIM)
        return img

    SEV_COLORS = {
        9: RED, 8: RED, 7: ORANGE, 6: YELLOW, 5: GREEN,
    }

    # Card layout: max 3 events per row, 2 rows if needed
    events_to_show = key_events[:4]  # Show max 4 events
    n = len(events_to_show)
    cols = min(n, 2)
    rows = (n + cols - 1) // cols

    card_margin = 18
    card_w = (W - card_margin * (cols + 1)) // cols
    card_h = (H - y - card_margin * (rows + 1) - 36) // rows

    for i, evt in enumerate(events_to_show):
        col = i % cols
        row = i // cols
        cx = card_margin + col * (card_w + card_margin)
        cy = y + card_margin + row * (card_h + card_margin)

        sev = int(evt.get("severity") or 5)
        sev_color = SEV_COLORS.get(sev, GREEN)
        net = evt.get("network", "RSS")
        channel = (evt.get("channel") or "").strip()[:30]
        location = (evt.get("location") or "").strip()[:40]
        summary = (evt.get("summary") or "").strip()
        evt_type = (evt.get("event_type") or "").upper()[:20]

        # Card background
        draw.rectangle([(cx, cy), (cx + card_w, cy + card_h)],
                       fill=(8, 14, 26), outline=(*sev_color, 60))
        # Left accent bar
        draw.rectangle([(cx, cy), (cx + 4, cy + card_h)], fill=sev_color)

        # Inner padding
        ix = cx + 14
        iy = cy + 10

        # Top row: SEV badge + network + event type
        f_badge = fnt(F_EXTRABOLD, 10)
        sev_label = f"SEV {sev}"
        sw = text_w(draw, sev_label, f_badge) + 14
        draw.rectangle([(ix, iy), (ix + sw, iy + 18)],
                       fill=blendc(sev_color, 0.22), outline=sev_color)
        draw.text((ix + 7, iy + 4), sev_label, font=f_badge, fill=sev_color)

        net_x = ix + sw + 8
        f_net = fnt(F_BOLD, 10)
        draw.text((net_x, iy + 4), net, font=f_net, fill=ACCENT)

        if evt_type:
            et_x = net_x + text_w(draw, net, f_net) + 10
            f_et = fnt(F_REGULAR, 9)
            draw.text((et_x, iy + 5), f"· {evt_type}", font=f_et, fill=DIM)

        iy += 24

        # Location
        if location:
            f_loc = fnt(F_BOLD, 11)
            draw.text((ix, iy), f"📍 {location}", font=f_loc, fill=OFFWHITE)
            iy += 18

        # Channel
        if channel:
            f_ch = fnt(F_REGULAR, 10)
            draw.text((ix, iy), channel.upper(), font=f_ch, fill=DIM)
            iy += 16

        # Summary — wrap to fit remaining space
        remaining_h = cy + card_h - iy - 14
        f_sum = fnt(F_REGULAR, 12)
        lines = wrap_text(draw, summary, card_w - 20, f_sum)
        for line in lines:
            if iy + 16 > cy + card_h - 14:
                # Last line — add ellipsis
                draw.text((ix, iy), "...", font=f_sum, fill=DIM)
                break
            draw.text((ix, iy), line, font=f_sum, fill=OFFWHITE)
            iy += text_h(draw, line, f_sum) + 4

    return img


def make_analyst_brief_frame(sitrep: dict) -> Image.Image:
    """
    ANALYST INTELLIGENCE BRIEF — shows the top 2 Q&A intel assessments as cards.
    Far more informative and broadcast-quality than a text-only location list.
    """
    img, draw = make_base()
    draw_topbar(draw, sitrep)
    draw_bottombar(draw, sitrep, "ANALYST INTELLIGENCE BRIEF  ·  SITREP FRAMEWORK")

    lvl = sitrep.get("escalation_level", "STABLE")
    lc  = LEVEL_COLORS.get(lvl, GREEN)

    y = 50
    y = draw_section_tag(draw, "◈ INTELLIGENCE ASSESSMENT  ·  PROFESSOR JIANG FRAMEWORK", lc, 20, y)

    kqs = sitrep.get("key_questions") or []
    if isinstance(kqs, str):
        try:
            kqs = json.loads(kqs)
        except Exception:
            kqs = []

    if not kqs:
        f_nm = fnt(F_REGULAR, 14)
        draw.text((W // 2, H // 2), "NO ANALYST DATA", font=f_nm, fill=DIM)
        return img

    # Show top 2 Q&As as stacked cards
    card_margin = 14
    n_cards = min(len(kqs), 2)
    card_h = (H - y - card_margin * (n_cards + 1) - 36) // n_cards

    for i, kq in enumerate(kqs[:n_cards]):
        q_str = str(kq.get("q", "")).strip()
        a_str = str(kq.get("a", "")).strip()
        w_str = str(kq.get("watch", "")).strip()

        # Clean [src:...] and status tags
        a_str = re.sub(r'\[src:[^\]]+\]', '', a_str).strip()
        a_str = re.sub(r'\[(CONFIRMED|REPORTED|CLAIMED)\]\s*', '', a_str).strip()
        w_str = re.sub(r'\[src:[^\]]+\]', '', w_str).strip()

        cx = card_margin
        cy = y + card_margin + i * (card_h + card_margin)
        cw = W - card_margin * 2

        # Card bg
        draw.rectangle([(cx, cy), (cx + cw, cy + card_h)],
                       fill=(8, 14, 26))
        # Left accent bar
        draw.rectangle([(cx, cy), (cx + 4, cy + card_h)], fill=lc)

        # Q number badge
        ix, iy = cx + 16, cy + 12
        f_num = fnt(F_EXTRABOLD, 10)
        q_badge = f"Q{i+1}"
        qbw = text_w(draw, q_badge, f_num) + 16
        draw.rectangle([(ix, iy), (ix + qbw, iy + 18)],
                       fill=blendc(lc, 0.22), outline=lc)
        draw.text((ix + 8, iy + 4), q_badge, font=f_num, fill=lc)

        # "ANALYST ASSESSMENT" label
        f_type = fnt(F_EXTRABOLD, 10)
        draw.text((ix + qbw + 10, iy + 4), "ANALYST ASSESSMENT", font=f_type, fill=blendc(ACCENT, 0.70))

        iy += 26

        # Question text
        f_q = fnt(F_BOLD, 13)
        iy = draw_wrapped(draw, q_str, ix, iy, cw - 30, f_q, OFFWHITE, spacing=5)
        iy += 8

        # Thin divider
        draw.line([(ix, iy), (cx + cw - 16, iy)], fill=blendc(DIM, 0.40), width=1)
        iy += 8

        # Answer text
        f_a = fnt(F_REGULAR, 12)
        remaining = cy + card_h - iy - (30 if w_str else 12)
        lines = wrap_text(draw, a_str, cw - 30, f_a)
        for line in lines:
            if iy + 16 > cy + card_h - (32 if w_str else 12):
                draw.text((ix, iy), "…", font=f_a, fill=DIM)
                break
            draw.text((ix, iy), line, font=f_a, fill=blendc(OFFWHITE, 0.90))
            iy += 17

        # Watch indicator at card bottom
        if w_str and iy < cy + card_h - 8:
            watch_y = cy + card_h - 28
            draw.rectangle([(cx + 4, watch_y), (cx + cw, watch_y + 24)],
                           fill=blendc(ORANGE, 0.10))
            f_watch_lbl = fnt(F_EXTRABOLD, 9)
            draw.text((ix, watch_y + 7), "WATCH:", font=f_watch_lbl, fill=ORANGE)
            f_watch = fnt(F_REGULAR, 11)
            w_short = w_str[:120]
            draw.text((ix + 54, watch_y + 6), w_short, font=f_watch, fill=blendc(OFFWHITE, 0.75))

    return img


def make_geographic_context_frame(sitrep: dict) -> Image.Image:
    """Legacy geo frame kept as fallback — replaced by make_analyst_brief_frame."""
    return make_analyst_brief_frame(sitrep)


def update_video_manifest(sid: int, video_filename: str):
    """Update /opt/conflict-monitor/videos/manifest.json with this video."""
    manifest_path = VIDEO_DIR / "manifest.json"
    try:
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
        else:
            manifest = {}

        manifest[str(sid)] = {
            "url": f"/videos/{video_filename}",
            "filename": video_filename,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"[manifest] Updated manifest.json for SITREP #{sid}")
    except Exception as e:
        print(f"[warn] Could not update manifest.json: {e}")




def fetch_tweet_media(tweet_url):
    """Fetch media from X/Twitter tweet via syndication API. Returns pbs.twimg.com URLs."""
    try:
        m = re.search(r'/status/(\d+)', tweet_url)
        if not m:
            return []
        tweet_id = m.group(1)
        api_url = (f'https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}'
                   '&lang=en&features=tfw_timeline_list%3A%3Btfw_follower_count_sunset%3Atrue&token=abc')
        hdrs = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://platform.twitter.com/',
            'Origin': 'https://platform.twitter.com',
        }
        r = requests.get(api_url, headers=hdrs, timeout=10)
        if r.status_code != 200:
            print(f'  syndication API {r.status_code} for {tweet_url[-40:]}')
            return []
        data = r.json()
        media_items = data.get('mediaDetails', [])
        urls = []
        for item in media_items:
            mtype = item.get('type', '')
            mu = item.get('media_url_https', '')
            if mu and mtype in ('photo', 'video', 'animated_gif'):
                urls.append(mu + '?format=jpg&name=large')
        if not urls:
            print(f'  no media in tweet {tweet_id} ({data.get("text","")[:50]})')
        return urls
    except Exception as e:
        print(f'  tweet_media error: {e}')
        return []


def fetch_og_image(url, summary, sev, seen, headers):
    """Fetch og/twitter image: X via syndication API, Telegram/news via og:image scrape."""
    try:
        is_x  = 'x.com' in url or 'twitter.com' in url
        is_tg = 't.me' in url
        domain = urlparse(url).netloc.replace('www.', '')
        label  = SOURCE_LABELS.get(domain, domain.upper()[:20])

        if is_x:
            user  = urlparse(url).path.strip('/').split('/')[0]
            label = f'X/{user[:14].upper()}'
            media_urls = fetch_tweet_media(url)
            for img_url in media_urls:
                if img_url not in seen:
                    seen.add(img_url)
                    try:
                        ph = requests.head(
                            img_url,
                            headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                                     'Referer': 'https://x.com/'},
                            timeout=6)
                        if ph.status_code == 200:
                            return {'image_url': img_url, 'source_label': label,
                                    'article_url': url, 'summary': summary[:140], 'severity': sev}
                    except Exception as he:
                        print(f'  head failed: {he}')
            return None

        # Telegram and news: scrape og:image
        try:
            resp = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        except Exception:
            return None
        if resp is None or resp.status_code != 200:
            return None
        html = resp.text
        img_url = ''
        og_pats = [
            r'property=["\x27]og:image["\x27]\s+content=["\x27]([^"\x27]+)["\x27]',
            r'content=["\x27]([^"\x27]+)["\x27]\s+property=["\x27]og:image["\x27]',
            r'name=["\x27]twitter:image["\x27\:src]*["\x27]\s+content=["\x27]([^"\x27]+)["\x27]',
            r'content=["\x27]([^"\x27]+)["\x27]\s+name=["\x27]twitter:image',
        ]
        for pat in og_pats:
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                if candidate.startswith('http'):
                    img_url = candidate
                    break
        if not img_url or img_url in seen:
            return None
        skip_kw = ('logo', 'default', 'placeholder', 'avatar', 'favicon', 'brand', 'icon', 'emoji')
        if any(k in img_url.lower() for k in skip_kw):
            return None
        seen.add(img_url)
        if is_tg:
            chan  = urlparse(url).path.strip('/').split('/')[0]
            label = f'TG/{chan[:14].upper()}'
        return {'image_url': img_url, 'source_label': label,
                'article_url': url, 'summary': summary[:140], 'severity': sev}
    except Exception as e:
        print(f'  x {url[:55]}: {e}')
        return None

def get_source_images(limit=8, key_ids=None):
    """Pull images from SITREP key event URLs (X, TG, news), then fill with recent high-sev events."""
    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    results, seen_imgs = [], set()

    # PASS 1: Images from exact events that drove this SITREP
    if key_ids:
        ids_str = ','.join(str(i) for i in key_ids[:12])
        rows = psql(
            f"SELECT channel_name, source_url, severity, "
            f"REPLACE(REPLACE(LEFT(summary,140),chr(10),' '),'|||',' ') "
            f"FROM events WHERE id IN ({ids_str}) "
            f"  AND source_url IS NOT NULL AND source_url != '' "
            f"ORDER BY severity DESC"
        )
        for r in rows:
            if len(results) >= limit or len(r) < 4 or not r[1]:
                continue
            img = fetch_og_image(r[1], r[3], r[2], seen_imgs, headers)
            if img:
                results.append(img)
                print(f"  + [KEY:{img['source_label']}] sev={r[2]}")

    # PASS 2: Fill from recent high-severity events if needed
    if len(results) < limit:
        needed = (limit - len(results)) + 4
        rows2 = psql(
            f"SELECT channel_name, source_url, severity, "
            f"REPLACE(REPLACE(LEFT(summary,140),chr(10),' '),'|||',' ') "
            f"FROM events WHERE severity >= 6 "
            f"  AND source_url IS NOT NULL AND source_url != '' "
            f"  AND timestamp > NOW() - INTERVAL '48 hours' "
            f"  AND NOT summary LIKE '[MERGED%' "
            f"ORDER BY severity DESC, timestamp DESC LIMIT {needed}"
        )
        for r in rows2:
            if len(results) >= limit or len(r) < 4 or not r[1]:
                continue
            img = fetch_og_image(r[1], r[3], r[2], seen_imgs, headers)
            if img:
                results.append(img)
                print(f"  + [FILL:{img['source_label']}] sev={r[2]}")

    return results


def download_image(url: str, min_w: int = 400, min_h: int = 220) -> str | None:
    """
    Download image to temp file, return path or None.
    Rejects images below min_w×min_h — filters out logos, avatars, thumbnails.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36", "Referer": "https://x.com/"}
        r = requests.get(url, headers=headers, timeout=8)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "")
        ext = ".jpg"
        if "png" in content_type or url.lower().endswith(".png"):
            ext = ".png"
        # Quality checks — reject tiny, too dark, or visually uniform images
        try:
            import numpy as _np
            check_img = Image.open(BytesIO(r.content))
            iw, ih = check_img.size
            if iw < min_w or ih < min_h:
                print(f"  ✗ image too small ({iw}×{ih}), skipping")
                return None
            # Convert to grayscale for brightness/uniformity checks
            gray = check_img.convert("L")
            pixels = _np.array(gray, dtype=_np.float32)
            mean_brightness = pixels.mean()
            std_brightness  = pixels.std()
            # Reject near-black images (night vision blobs, failed downloads)
            if mean_brightness < 18:
                print(f"  ✗ image too dark (mean={mean_brightness:.0f}), skipping")
                return None
            # Reject near-uniform images (solid color logos, flags, placeholder screens)
            if std_brightness < 22:
                print(f"  ✗ image too uniform (std={std_brightness:.1f}), skipping")
                return None
        except Exception:
            pass  # If checks fail, allow it through
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp.write(r.content)
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"  ✗ image download failed: {e}")
        return None

def get_wikipedia_location_images(locations: list[str], limit: int = 3) -> list[dict]:
    """
    Fetch representative images from Wikipedia for event locations.
    Gives us high-quality, relevant geographic imagery for free.
    """
    results = []
    headers = {"User-Agent": "ConflictMonitor/1.0 (intelligence@truthevades.com)"}
    seen = set()

    for loc in locations:
        if len(results) >= limit:
            break
        loc = loc.strip()
        if not loc or loc in seen:
            continue
        seen.add(loc)
        try:
            # Wikipedia REST API — page summary with thumbnail
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(loc)}"
            r = requests.get(url, headers=headers, timeout=6)
            if r.status_code != 200:
                continue
            data = r.json()
            img = data.get("originalimage") or data.get("thumbnail")
            if not img or not img.get("source"):
                continue
            img_url = img["source"]
            # Skip flag/emblem images — they're flat and visually boring as b-roll
            skip_keywords = ["Flag_of", "Coat_of_arms", "Emblem_of", "Seal_of",
                             "National_symbol", "flag_of", "coat_of_arms"]
            if any(kw in img_url for kw in skip_keywords):
                print(f"  ✗ [WIKIPEDIA] {loc}: skipping flag/emblem image")
                continue
            title   = data.get("title", loc)
            extract = (data.get("extract") or "")[:120]
            results.append({
                "image_url":    img_url,
                "source_label": f"WIKI: {title.upper()}",
                "article_url":  data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "summary":      extract,
                "severity":     7,
            })
            print(f"  ✓ [WIKIPEDIA] {title}")
        except Exception as e:
            print(f"  ✗ wikipedia {loc}: {e}")
    return results




# ── FFmpeg segment builders ────────────────────────────────────────────────────

def pil_to_mp4(img: Image.Image, duration: float, out: str):
    """Convert a PIL frame to a static MP4 clip — browser-safe H.264."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        img.save(f.name, "PNG")
        png = f.name
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(FPS), "-i", png,
        "-t", str(duration),
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-profile:v", "high", "-level:v", "4.0",
        "-pix_fmt", "yuv420p",
        "-g", str(FPS * 2),      # keyframe every 2s
        "-movflags", "+faststart",
        out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pil_to_mp4 failed: {result.stderr[-300:]}")
    os.unlink(png)


def make_fullbleed_image_clip(img_path: str, source_label: str, headline: str,
                               location: str, duration: float, out: str,
                               kb_style: int = 0, level_color_hex: str = "#58a6ff",
                               escalation_label: str = ""):
    """
    Full-bleed news broadcast clip — image fills the entire 1280×720 frame.
    Ken Burns motion keeps it alive. Lower-third overlay for source + headline only.
    This is what a real news broadcast looks like.
    """
    frames = max(2, int(duration * FPS))

    def esc(s: str) -> str:
        s = s.replace("\\", "\\\\").replace("'", "\u2019").replace(":", "\\:").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]").replace("%", "\\%")
        return s[:90]

    src_esc = esc(source_label.upper())
    head_esc = esc(headline[:72] + ("…" if len(headline) > 72 else ""))
    loc_esc  = esc(location.upper()[:40]) if location else ""

    # Ken Burns: 4 styles, all full-frame 1280×720
    kb = kb_style % 6
    OVS = 120
    if kb == 0:   # slow zoom in, center
        kb_f = (f"scale={W+OVS}:{H+OVS}:force_original_aspect_ratio=increase,"
                f"crop={W+OVS}:{H+OVS},"
                f"zoompan=z='min(zoom+0.0003\\,1.09)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',"
                f"scale={W}:{H},setsar=1")
    elif kb == 1: # pan left→right
        kb_f = (f"scale={W+OVS}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W+OVS}:{H},"
                f"zoompan=z='1.0':d={frames}:x='(iw-{W})*on/{frames}':y='0',"
                f"scale={W}:{H},setsar=1")
    elif kb == 2: # slow zoom out
        kb_f = (f"scale={W+OVS}:{H+OVS}:force_original_aspect_ratio=increase,"
                f"crop={W+OVS}:{H+OVS},"
                f"zoompan=z='max(zoom-0.0003\\,1.0)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',"
                f"scale={W}:{H},setsar=1")
    elif kb == 3: # pan right→left
        kb_f = (f"scale={W+OVS}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W+OVS}:{H},"
                f"zoompan=z='1.0':d={frames}:x='(iw-{W})*(1-on/{frames})':y='0',"
                f"scale={W}:{H},setsar=1")
    elif kb == 4: # zoom in top-left corner
        kb_f = (f"scale={W+OVS}:{H+OVS}:force_original_aspect_ratio=increase,"
                f"crop={W+OVS}:{H+OVS},"
                f"zoompan=z='min(zoom+0.0003\\,1.09)':d={frames}:x='0':y='0',"
                f"scale={W}:{H},setsar=1")
    else:         # slow drift down
        kb_f = (f"scale={W}:{H+OVS}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H+OVS},"
                f"zoompan=z='1.0':d={frames}:x='0':y='(ih-{H})*on/{frames}',"
                f"scale={W}:{H},setsar=1")

    # Bottom dark gradient bar (drawn via PIL separately then overlaid)
    bar_h = 90
    bar_img = Image.new("RGBA", (W, bar_h), (0, 0, 0, 0))
    bar_draw = ImageDraw.Draw(bar_img)
    for i in range(bar_h):
        alpha = int(210 * (i / bar_h))
        bar_draw.rectangle([(0, i), (W, i+1)], fill=(2, 5, 12, alpha))

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as bf:
        bar_img.save(bf.name, "PNG")
        bar_png = bf.name

    # Lower-third overlay via PIL (more control than drawtext)
    lt_h = 88
    lt_img = Image.new("RGBA", (W, lt_h), (0, 0, 0, 0))
    lt_draw = ImageDraw.Draw(lt_img)
    # Dark bg
    lt_draw.rectangle([(0, 0), (W, lt_h)], fill=(2, 5, 12, 210))
    # Accent left bar
    lhex = level_color_hex.lstrip("#")
    lr, lg, lb2 = int(lhex[0:2],16), int(lhex[2:4],16), int(lhex[4:6],16)
    lt_draw.rectangle([(0, 0), (5, lt_h)], fill=(lr, lg, lb2, 255))

    # Source badge
    f_src = fnt(F_EXTRABOLD, 11)
    src_badge_w = text_w(lt_draw, source_label.upper(), f_src) + 20
    lt_draw.rectangle([(12, 10), (12 + src_badge_w, 28)], fill=(lr, lg, lb2, 60))
    lt_draw.rectangle([(12, 10), (12 + src_badge_w, 28)], outline=(lr, lg, lb2, 200))
    lt_draw.text((22, 13), source_label.upper(), font=f_src, fill=(lr, lg, lb2, 255))

    # Location if present
    x_after_src = 12 + src_badge_w + 10
    if location:
        f_loc = fnt(F_SEMIBOLD, 11)
        lt_draw.text((x_after_src, 13), f"📍 {location.upper()[:35]}", font=f_loc, fill=(180, 200, 220, 220))

    # Headline
    f_head = fnt(F_BOLD, 15)
    lt_draw.text((12, 36), headline[:90], font=f_head, fill=(235, 240, 250, 255))

    # Escalation label top-right
    if escalation_label:
        f_esc_lbl = fnt(F_EXTRABOLD, 11)
        elw = text_w(lt_draw, escalation_label, f_esc_lbl)
        lt_draw.text((W - elw - 14, 13), escalation_label, font=f_esc_lbl, fill=(lr, lg, lb2, 255))

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as lf:
        lt_img.save(lf.name, "PNG")
        lt_png = lf.name

    # FFmpeg: image → Ken Burns → overlay lower-third PNG at bottom
    fc = (
        f"[0:v]format=yuv420p,{kb_f}[base];"
        f"[1:v]format=rgba[lt];"
        f"[base][lt]overlay=x=0:y={H - lt_h}[vout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(FPS), "-i", img_path,
        "-loop", "1", "-framerate", str(FPS), "-i", lt_png,
        "-filter_complex", fc,
        "-map", "[vout]",
        "-t", str(duration), "-r", str(FPS),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-profile:v", "high", "-level:v", "4.0",
        "-pix_fmt", "yuv420p",
        "-g", str(FPS * 2), "-movflags", "+faststart",
        out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    os.unlink(lt_png)
    os.unlink(bar_png)
    if result.returncode != 0:
        print(f"[ffmpeg image] error: {result.stderr[-400:]}")
        raise RuntimeError("fullbleed image clip failed")


def make_split_clip(text_panel: Image.Image, img_path: str,
                    source_label: str, summary: str,
                    duration: float, out: str, kb_style: int = 0):
    """Legacy — routes to fullbleed image clip (text panel ignored)."""
    raise RuntimeError("split clip deprecated — use fullbleed")


def make_fullwidth_clip(img: Image.Image, duration: float, out: str):
    """Full-width clip from PIL image."""
    pil_to_mp4(img, duration, out)


def chain_clips_xfade(clips: list[tuple[str, float]], out: str):
    """
    Chain clips with xfade transitions.
    - ≤8 clips: pairwise xfade (smooth crossfades)
    - >8 clips: concat demuxer (fast, no re-encode penalty)
    """
    if len(clips) == 1:
        subprocess.run(["cp", clips[0][0], out], check=True)
        return

    # For long chains use fast concat to avoid O(n²) re-encoding
    if len(clips) > 8:
        _chain_concat(clips, out)
        return

    ENCODE_FLAGS = [
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-profile:v", "high", "-level:v", "4.0",
        "-pix_fmt", "yuv420p",
        "-g", str(FPS * 2),
        "-movflags", "+faststart",
    ]

    def xfade_two(in_a: str, dur_a: float, in_b: str, out_path: str):
        """Crossfade two clips together."""
        offset = max(0.1, dur_a - XFADE_DUR)
        fc = (
            f"[0:v]fps={FPS},format=yuv420p,setpts=PTS-STARTPTS[v0];"
            f"[1:v]fps={FPS},format=yuv420p,setpts=PTS-STARTPTS[v1];"
            f"[v0][v1]xfade=transition=fade:duration={XFADE_DUR}:offset={offset:.4f}[vout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", in_a, "-i", in_b,
            "-filter_complex", fc,
            "-map", "[vout]",
        ] + ENCODE_FLAGS + [out_path]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"xfade_two failed: {r.stderr[-400:]}")

    with tempfile.TemporaryDirectory() as td:
        # Start with first clip
        prev_path = clips[0][0]
        prev_dur  = clips[0][1]

        for i, (next_path, next_dur) in enumerate(clips[1:]):
            is_last = (i == len(clips) - 2)
            tmp_out = out if is_last else os.path.join(td, f"chain_{i:02d}.mp4")
            xfade_two(prev_path, prev_dur, next_path, tmp_out)
            # Duration of combined clip
            prev_dur  = prev_dur + next_dur - XFADE_DUR
            prev_path = tmp_out

    print(f"[chain] {len(clips)} clips chained OK (xfade)")


def _chain_concat(clips: list[tuple[str, float]], out: str):
    """
    Fast concat using ffmpeg concat demuxer — no re-encode, handles any clip count.
    Each clip must have matching codec/resolution (guaranteed by our pipeline).
    """
    with tempfile.TemporaryDirectory() as td:
        list_path = os.path.join(td, "concat.txt")
        with open(list_path, "w") as f:
            for path, _ in clips:
                f.write(f"file '{path}'\n")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-profile:v", "high", "-level:v", "4.0",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"concat failed: {r.stderr[-400:]}")
    print(f"[chain] {len(clips)} clips chained OK (concat)")


def add_ticker_and_audio(video_in: str, audio_in: str,
                          ticker_text: str, out: str):
    """Mux audio onto video. Ticker removed — was covering source text."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_in, "-i", audio_in,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-shortest", "-movflags", "+faststart",
        out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        cmd2 = [
            "ffmpeg", "-y", "-i", video_in, "-i", audio_in,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-profile:v", "high", "-level:v", "4.0", "-pix_fmt", "yuv420p",
            "-g", str(FPS * 2),
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-shortest", "-movflags", "+faststart", out,
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True)
        if r2.returncode != 0:
            raise RuntimeError(f"audio mux failed: {r2.stderr[-400:]}")


# ── TTS ────────────────────────────────────────────────────────────────────────

def _clean_bullet(raw: str) -> str:
    """Strip structural notation from a SITREP bullet, leaving clean spoken text."""
    t = raw.strip().lstrip("•").strip()
    # Remove source citations: [src:1234,5678]
    t = re.sub(r'\[src:[^\]]+\]', '', t)
    # Remove confidence markers: [CONFIRMED], [REPORTED], [CLAIMED], [UNVERIFIED]
    t = re.sub(r'\[(CONFIRMED|REPORTED|CLAIMED|UNVERIFIED)\]', '', t)
    # Remove structural category labels safely.
    # Bullets look like: "MILITARY — text" or "[APPLY PAX JUDAICA — GT#16] — text"
    # Strategy: split on ALL " — " and take the last segment (actual content).
    # Guard: only do this if the first part looks like a label, not content.
    parts = t.split(" — ")
    if len(parts) >= 2:
        prefix = parts[0].strip()
        # Strip if prefix is a category label: all-caps, short, or contains brackets/codes
        if (len(prefix) < 70 and
            (prefix.upper() == prefix or          # all caps label
             re.search(r'[\[\]#]', prefix) or      # contains bracket/hash (code reference)
             prefix.lower().startswith("bullet:"))):
            t = " — ".join(parts[1:]).strip()      # join remaining (content may have —)
    # Remove any leftover bracket residue at start: "GT#16] — " or "[GT#3]"
    t = re.sub(r'^[\w#]+\]\s*—?\s*', '', t)
    t = t.strip()
    # Ensure sentence ends properly
    if t and not t[-1] in '.?!':
        t += '.'
    return t


def _top_bullets(sitrep: dict, field: str, n: int) -> list[str]:
    """Extract and clean the top n bullets from a SITREP field."""
    raw = sitrep.get(field) or ""
    lines = [l for l in raw.split("\n") if l.strip().lstrip("•").strip()]
    cleaned = []
    for line in lines[:n]:
        c = _clean_bullet(line)
        if c and len(c) > 20:
            cleaned.append(c)
    return cleaned


def _build_script_llm(sitrep: dict) -> "str | None":
    """
    Use Claude Haiku to rewrite SITREP data as a broadcast-quality narration.
    ~190-230 words. Returns None on any failure so caller falls back to rule-based.
    Includes: situation, escalation, key analyst question, economic exposure,
    game theory insight, satellite confirmation note, historical parallel.
    Cost: ~$0.0005 per call — negligible.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic as _anthropic
    except ImportError:
        return None

    lvl      = sitrep.get("escalation_level", "STABLE")
    score    = sitrep.get("escalation_score", 50) or 50
    headline = sitrep.get("headline", "")
    evts     = sitrep.get("events_analyzed", 0)
    gen_at   = (sitrep.get("generated_at") or "")[:10]

    sit_text = " ".join(_top_bullets(sitrep, "situation", 3))
    esc_text = " ".join(_top_bullets(sitrep, "escalation_text", 2))
    gt_text  = " ".join(_top_bullets(sitrep, "game_theory", 2))
    analogue = _clean_bullet((sitrep.get("historical_analogue") or "")[:350])

    # ── All analyst intelligence Q&A pairs ───────────────────────────────────
    kqs = sitrep.get("key_questions") or []
    if isinstance(kqs, str):
        try:
            import json as _json
            kqs = _json.loads(kqs)
        except Exception:
            kqs = []
    analyst_qas = []  # list of (q, a, watch) tuples, cleaned
    for kq in (kqs if isinstance(kqs, list) else []):
        q_str = _clean_bullet(str(kq.get("q", "")))
        a_str = _clean_bullet(str(kq.get("a", "")))
        # Strip [src:ID] citation codes — not suitable for spoken narration
        a_str = re.sub(r'\[src:[^\]]+\]', "", a_str).strip()
        w_str = _clean_bullet(str(kq.get("watch", "")))
        if q_str and a_str:
            analyst_qas.append((q_str, a_str, w_str))

    # ── Economic/energy exposure (top bullet) ────────────────────────────────
    econ_bullets = _top_bullets(sitrep, "economic_exposure", 1)
    econ_note    = econ_bullets[0] if econ_bullets else ""

    # ── Humanitarian context (top bullet) ────────────────────────────────────
    human_bullets = _top_bullets(sitrep, "humanitarian_ground", 1)
    human_note    = human_bullets[0] if human_bullets else ""

    # ── Satellite intelligence note ───────────────────────────────────────────
    # Primary: query DB for satellite-confirmed events in key event IDs
    sat_note = ""
    key_ids_raw = sitrep.get("key_event_ids", []) or []
    if isinstance(key_ids_raw, str):
        key_ids_list = [x.strip() for x in key_ids_raw.split(",") if x.strip().isdigit()]
    else:
        key_ids_list = [str(x) for x in key_ids_raw if str(x).isdigit()]

    if key_ids_list:
        ids_str = ",".join(key_ids_list[:30])
        try:
            sat_rows = psql(
                f"SELECT id, location_name, confirmed_networks FROM events "
                f"WHERE id IN ({ids_str}) AND confirmed_networks ILIKE '%SATELLITE%' "
                f"ORDER BY severity DESC LIMIT 3"
            )
            if sat_rows:
                locs = list(dict.fromkeys(r[1] for r in sat_rows if r[1]))[:2]
                if locs:
                    loc_str = " and ".join(locs)
                    sat_note = (
                        f"Independent NASA VIIRS orbital sensors have cross-confirmed "
                        f"thermal anomalies at {loc_str}, providing physical ground truth "
                        f"independent of all human reporting."
                    )
                else:
                    sat_note = (
                        "Independent NASA VIIRS orbital sensors have cross-confirmed "
                        "thermal anomalies at this location, providing physical ground truth "
                        "independent of all human reporting."
                    )
        except Exception:
            pass

    # Fallback: keyword scan of key_questions answers
    if not sat_note:
        kq_text = " ".join(
            str(kq.get("a", "")) for kq in (kqs if isinstance(kqs, list) else [])
        ).lower()
        if any(kw in kq_text for kw in ("nasa viirs", "satellite", "thermal anomaly", "sat-verified", "[satellite confirmed]")):
            sat_note = "Independent NASA VIIRS orbital sensor data is cross-referencing ground reports."

    # ── Assemble data context block ───────────────────────────────────────────
    data_ctx  = f"Date: {gen_at}\n"
    data_ctx += f"Threat Level: {lvl} — Escalation Index {score} out of 100\n"
    data_ctx += f"Headline: {headline}\n\n"
    data_ctx += f"Ground situation: {sit_text}\n\n"
    data_ctx += f"Strategic trajectory: {esc_text}\n\n"
    if econ_note:
        data_ctx += f"Economic/energy exposure: {econ_note}\n\n"
    if human_note:
        data_ctx += f"Humanitarian situation: {human_note}\n\n"
    if sat_note:
        data_ctx += f"Satellite intelligence: {sat_note}\n\n"
    data_ctx += f"Key strategic dynamic: {gt_text}\n\n"
    if analogue:
        data_ctx += f"Historical parallel: {analogue}\n\n"
    # ── All analyst Q&A pairs — primary intelligence content ─────────────────
    if analyst_qas:
        data_ctx += f"ANALYST INTELLIGENCE QUESTIONS ({len(analyst_qas)} total):\n"
        for i, (q, a, w) in enumerate(analyst_qas, 1):
            data_ctx += f"[Q{i}] {q}\n"
            data_ctx += f"  Assessment: {a}\n"
            if w:
                data_ctx += f"  Watch indicator: {w}\n"
            data_ctx += "\n"

    final_sentence = (
        f"This briefing covered {evts} intelligence events. "
        "Full live coverage at truthevades dot com."
    )
    prompt = (
        "You are a senior broadcast writer for a geopolitical intelligence service. "
        f"Write a spoken narration script of EXACTLY 260-300 words for a video intelligence briefing "
        "in the style of BBC World Service or Al Jazeera English — authoritative, precise, "
        "and never sensationalist. HARD LIMIT: stop writing before reaching 300 words.\n\n"
        "STRUCTURE (follow this arc — each section gets 2-3 sentences max):\n"
        "1. Open: the single most urgent on-the-ground development (2-3 sentences)\n"
        "2. Stakes: strategic and economic consequences (2 sentences)\n"
        "3. Top 2 analyst intelligence questions as flowing narrative — "
        "   one sentence per question covering: the core uncertainty, current assessment, "
        "   and what to watch for. Pick only the 2 most critical Q&As.\n"
        "4. Close: single most critical watch indicator (1 sentence)\n"
        f"5. LAST sentence must be word-for-word: \"{final_sentence}\"\n\n"
        "STRICT RULES:\n"
        "- 260-300 words total (including the final sentence). Count carefully.\n"
        "- Spoken prose only — no bullets, brackets, citation codes, or section headers\n"
        "- Convert all [CONFIRMED]/[REPORTED]/[CLAIMED] labels to natural spoken qualifiers\n"
        "- Use specific named actors, locations, weapons, and units — never vague\n"
        "- Mention satellite confirmation naturally if data includes it\n"
        "- Active voice throughout. Short declarative sentences.\n"
        "- Do not fabricate facts not present in the data\n"
        "- No meta-commentary, no self-reference\n\n"
        "SITREP INTELLIGENCE DATA:\n"
        + data_ctx +
        "\nWrite ONLY the narration — start immediately with the opening sentence, "
        "no title, no header, no preamble."
    )

    def _truncate_to_target(text: str, max_words: int, final_sent: str) -> str:
        """Truncate script to max_words at a sentence boundary, re-appending final sentence."""
        # Remove any existing copy of the final sentence
        clean = text.replace(final_sent, "").strip()
        sentences = re.split(r'(?<=[.!?])\s+', clean)
        kept, count = [], 0
        budget = max_words - len(final_sent.split())  # leave room for final sentence
        for s in sentences:
            wc = len(s.split())
            if count + wc > budget:
                break
            kept.append(s)
            count += wc
        return " ".join(kept) + " " + final_sent

    try:
        client = _anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        script = msg.content[0].text.strip()
        # Strip any accidental markdown headers (# Title lines)
        script = re.sub(r"^#+\s+[^\n]+\n+", "", script).strip()
        word_count = len(script.split())
        # Enforce hard ceiling at 420 words — truncate at sentence boundary
        if word_count > 420:
            script = _truncate_to_target(script, 400, final_sentence)
            word_count = len(script.split())
            print(f"[script] Truncated to {word_count} words")
        if 80 < word_count < 500:
            print(f"[script] LLM narration: {word_count} words")
            return script
        print(f"[script] LLM output unexpected length ({word_count} words), using fallback")
        return None
    except Exception as e:
        print(f"[script] LLM call failed ({e}), using rule-based fallback")
        return None


def build_script(sitrep: dict) -> str:
    """
    Generate spoken narration for the SITREP video.
    Primary:  Claude Haiku — natural broadcast-quality prose (~160-200 words).
    Fallback: Improved rule-based assembly when API unavailable.
    """
    # --- Primary: LLM rewrite ---
    llm_result = _build_script_llm(sitrep)
    if llm_result:
        return llm_result

    # --- Fallback: improved rule-based ---
    lvl      = sitrep.get("escalation_level", "STABLE")
    score    = sitrep.get("escalation_score", 50) or 50
    headline = sitrep.get("headline", "")
    evts     = sitrep.get("events_analyzed", 0)
    gen_at   = (sitrep.get("generated_at") or "")[:10]

    sit      = _top_bullets(sitrep, "situation", 2)
    esc      = _top_bullets(sitrep, "escalation_text", 1)
    gt       = _top_bullets(sitrep, "game_theory", 1)
    econ     = _top_bullets(sitrep, "economic_exposure", 1)
    analogue = _clean_bullet((sitrep.get("historical_analogue") or "")[:300])

    # Check for satellite confirmation via key_event_ids
    fallback_sat_note = ""
    key_ids_raw = sitrep.get("key_event_ids", []) or []
    if isinstance(key_ids_raw, str):
        key_ids_list = [x.strip() for x in key_ids_raw.split(",") if x.strip().isdigit()]
    else:
        key_ids_list = [str(x) for x in key_ids_raw if str(x).isdigit()]
    if key_ids_list:
        try:
            sat_rows = psql(
                f"SELECT location_name FROM events "
                f"WHERE id IN ({','.join(key_ids_list[:30])}) "
                f"AND confirmed_networks ILIKE '%SATELLITE%' LIMIT 2"
            )
            if sat_rows:
                locs = [r[0] for r in sat_rows if r[0]]
                if locs:
                    fallback_sat_note = f"Orbital sensors have independently confirmed activity at {' and '.join(locs)}."
                else:
                    fallback_sat_note = "NASA orbital sensors have independently confirmed key events."
        except Exception:
            pass

    level_phrase = {
        "STABLE":     "The situation remains stable",
        "ELEVATED":   "Tensions are elevated across the region",
        "ESCALATING": "The situation is rapidly escalating",
        "CRITICAL":   "Conditions are critical",
        "WARTIME":    "Active wartime conditions are reported across the theater",
    }.get(lvl, f"Threat level is assessed as {lvl.lower()}")

    # Pull Q&A pairs for fallback narration
    fallback_kqs = sitrep.get("key_questions") or []
    if isinstance(fallback_kqs, str):
        try:
            import json as _json2
            fallback_kqs = _json2.loads(fallback_kqs)
        except Exception:
            fallback_kqs = []

    parts = [
        f"Conflict Monitor Intelligence. {gen_at}.",
        f"{level_phrase} — escalation index {score} out of 100.",
        headline,
    ]
    parts.extend(sit)
    if fallback_sat_note:
        parts.append(fallback_sat_note)
    parts.extend(esc)
    if econ:
        parts.extend(econ)
    parts.extend(gt)
    # Include top 2 Q&A pairs in fallback narration
    for kq in (fallback_kqs[:2] if isinstance(fallback_kqs, list) else []):
        q_str = _clean_bullet(str(kq.get("q", "")))
        a_str = _clean_bullet(re.sub(r'\[src:[^\]]+\]', "", str(kq.get("a", ""))).strip())
        if q_str and a_str:
            parts.append(f"Analysts ask: {q_str}")
            parts.append(f"Current assessment: {a_str[:250]}")
    if analogue and len(analogue) > 30:
        parts.append(f"Analysts draw comparisons to {analogue}")
    parts.append(
        f"This briefing covered {evts} intelligence events. "
        f"Full live report at truthevades dot com."
    )
    return " ".join(p for p in parts if p and p.strip())


# ── Kokoro TTS config ──────────────────────────────────────────────────────────
KOKORO_VOICE   = "bm_lewis"   # British male — deep, authoritative broadcast voice
KOKORO_SPEED   = 0.97         # Slight slowdown for gravitas
_kokoro_pipeline = None       # Module-level cache — load once, reuse across videos

def _get_kokoro_pipeline():
    """Lazy-load Kokoro pipeline and cache it for the process lifetime."""
    global _kokoro_pipeline
    if _kokoro_pipeline is None:
        from kokoro import KPipeline
        print("[tts] Loading Kokoro-82M pipeline (first call)...")
        _kokoro_pipeline = KPipeline(lang_code='b', repo_id='hexgrad/Kokoro-82M')
        print("[tts] Kokoro pipeline ready")
    return _kokoro_pipeline


def tts_kokoro(script: str, wav_path: str) -> list:
    """
    Generate narration with Kokoro-82M (bm_lewis — British male anchor).
    Returns word-timing list: [(word, start_sec, end_sec), ...] for caption burn-in.
    Audio saved as 24kHz WAV at wav_path.
    """
    import numpy as np
    import soundfile as sf

    pipeline = _get_kokoro_pipeline()
    chunks_audio = []
    chunks_text  = []
    for gs, ps, audio in pipeline(script, voice=KOKORO_VOICE, speed=KOKORO_SPEED,
                                  split_pattern=r'(?<=[.!?])\s+'):
        chunks_audio.append(audio)
        chunks_text.append(gs)

    full_audio = np.concatenate(chunks_audio)
    sf.write(wav_path, full_audio, 24000)
    total_dur = len(full_audio) / 24000.0

    # ── Word-level timing (character-weight proportional distribution) ────────
    # We know the total audio duration and the full text. Assign each word a
    # duration proportional to its character count (plus a fixed inter-word gap).
    words = script.split()
    total_chars = sum(len(w) for w in words)
    inter_word  = 0.045  # ~45ms gap between words
    speech_time = max(0, total_dur - inter_word * len(words))
    word_timings = []
    cursor = 0.0
    for w in words:
        frac     = len(w) / total_chars if total_chars else 1 / len(words)
        duration = speech_time * frac
        word_timings.append((w, round(cursor, 3), round(cursor + duration, 3)))
        cursor  += duration + inter_word

    return word_timings


def build_caption_filter(word_timings: list, video_w: int = 1280, video_h: int = 720,
                          font_size: int = 26) -> str:
    """
    Build an FFmpeg drawtext filter string that burns word-synced captions
    into the lower third of the video. Words appear in groups of ~8 and
    fade in/out as each group's time window spans the audio.
    """
    if not word_timings:
        return ""

    GROUP_SIZE = 8
    groups = []
    for i in range(0, len(word_timings), GROUP_SIZE):
        grp = word_timings[i:i + GROUP_SIZE]
        text  = " ".join(w for w, _, _ in grp)
        start = grp[0][1]
        end   = grp[-1][2] + 0.15   # slight tail
        groups.append((text, start, end))

    def esc(t: str) -> str:
        return (t.replace("\\", "\\\\").replace("'", "\u2019")
                 .replace(":", "\\:").replace("%", "\\%"))

    y_pos    = video_h - 90
    filters  = []
    for text, start, end in groups:
        et = esc(text)
        # Semi-transparent black backdrop line + white caption text
        filters.append(
            f"drawtext=text='{et}'"
            f":fontsize={font_size}:fontcolor=white:font='DejaVu Sans Bold'"
            f":x=(w-text_w)/2:y={y_pos}"
            f":box=1:boxcolor=black@0.62:boxborderw=10"
            f":enable='between(t,{start:.3f},{end:.3f})'"
        )
    return ",".join(filters)


async def tts(script: str, path: str) -> list:
    """
    TTS: Kokoro primary (free, broadcast quality) → ElevenLabs → edge-tts.
    Returns word_timings list from Kokoro, or [] for fallbacks.
    Audio written to `path` (mp3 or wav).
    """
    # ── Primary: Kokoro-82M (free, self-hosted) ───────────────────────────────
    try:
        import time
        t0 = time.time()
        wav_path = path.replace(".mp3", ".wav")
        word_timings = tts_kokoro(script, wav_path)
        dur = len(script.split()) / 2.5  # rough sanity check
        elapsed = time.time() - t0
        print(f"[tts] Kokoro bm_lewis | {elapsed:.1f}s gen | captions: {len(word_timings)} words")
        # Convert to MP3 for compatibility with rest of pipeline
        if path.endswith(".mp3"):
            subprocess.run([
                "ffmpeg", "-y", "-i", wav_path,
                "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", path,
            ], capture_output=True, check=True)
        else:
            import shutil
            shutil.copy(wav_path, path)
        return word_timings
    except Exception as e:
        print(f"[tts] Kokoro failed ({e}), trying ElevenLabs...")

    # ── Secondary: ElevenLabs (if API key present and has credits) ────────────
    api_key = os.environ.get("ELEVENLABS_API_KEY", ELEVENLABS_API_KEY)
    if api_key:
        try:
            from elevenlabs.client import ElevenLabs
            from elevenlabs import VoiceSettings
            client = ElevenLabs(api_key=api_key)
            audio_gen = client.text_to_speech.convert(
                voice_id=ELEVENLABS_VOICE_ID,
                text=script,
                model_id=ELEVENLABS_MODEL,
                voice_settings=VoiceSettings(**ELEVENLABS_SETTINGS),
                output_format="mp3_44100_192",
            )
            with open(path, "wb") as f:
                for chunk in audio_gen:
                    if chunk:
                        f.write(chunk)
            print(f"[tts] ElevenLabs Bill voice ({ELEVENLABS_MODEL})")
            return []
        except Exception as e:
            print(f"[tts] ElevenLabs failed ({e}), falling back to edge-tts")

    # ── Tertiary: edge-tts (always available, free) ───────────────────────────
    import edge_tts
    comm = edge_tts.Communicate(script, TTS_VOICE, rate="-5%")
    await comm.save(path)
    print(f"[tts] edge-tts fallback ({TTS_VOICE})")
    return []


def audio_dur(path: str) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ], text=True).strip()
    return float(out)


# ── Main ───────────────────────────────────────────────────────────────────────

def parse_bullets(field_text: str) -> list[str]:
    lines = [l.strip() for l in (field_text or "").split("\n") if l.strip()]
    return [l.lstrip("•").strip() for l in lines if l.lstrip("•").strip()]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--api", default=API_BASE)
    args = parser.parse_args()

    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    ts  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    # 1. Fetch SITREP
    print("[api] Fetching SITREP...")
    resp = requests.get(f"{args.api}/sitreps/latest", timeout=10)
    resp.raise_for_status()
    sitrep = resp.json().get("sitrep")
    if not sitrep:
        print("ERROR: no SITREP available")
        sys.exit(1)
    sid = sitrep.get("id", "?")
    lvl = sitrep.get("escalation_level", "STABLE")
    lc  = LEVEL_COLORS.get(lvl, GREEN)
    print(f"[sitrep] #{sid} | {lvl} | {sitrep.get('headline','')[:60]}")

    # 2. Fetch source images
    print("[media] Fetching images from key event URLs (X, TG, news)...")
    _raw = sitrep.get("key_event_ids", []) or []
    _kids = [int(x) for x in (_raw if isinstance(_raw,list) else str(_raw).split(",")) if str(x).strip().isdigit()]
    source_imgs = get_source_images(limit=8, key_ids=_kids)
    print(f"[media] Got {len(source_imgs)} images")

    # 2b. Fetch escalation history + key events for new frames
    print("[intel] Fetching escalation history...")
    sitrep_history = get_sitrep_history(limit=12)
    print(f"[intel] Got {len(sitrep_history)} history points")

    print("[intel] Fetching key trigger events...")
    key_ids_raw = sitrep.get("key_event_ids", []) or []
    if isinstance(key_ids_raw, str):
        key_ids = [int(x) for x in key_ids_raw.split(",") if x.strip().isdigit()]
    else:
        key_ids = [int(x) for x in key_ids_raw if str(x).isdigit()]
    key_events = get_key_events_for_sitrep(key_ids)
    print(f"[intel] Got {len(key_events)} key events")

    # Ticker removed — was covering source text
    ticker_text = ""

    # 4. TTS
    script   = build_script(sitrep)
    audio_path = str(VIDEO_DIR / f"sitrep_{sid}_{ts}.mp3")
    print(f"[tts] Generating narration ({len(script)} chars)...")
    word_timings = await tts(script, audio_path)
    caption_filter = build_caption_filter(word_timings) if word_timings else ""
    if caption_filter:
        print(f"[captions] {len(word_timings)} words → burn-in captions ready")
    total_audio = audio_dur(audio_path)
    print(f"[tts] Duration: {total_audio:.1f}s")

    # 5. Download images to temp files — news og:images + Wikipedia location images
    # Extract top locations from key events for Wikipedia lookup
    wiki_locations = list(dict.fromkeys(
        e.get("location", "") for e in key_events if e.get("location")
    ))[:4]
    if wiki_locations:
        print(f"[wiki] Fetching location images for: {wiki_locations[:3]}")
        wiki_imgs = get_wikipedia_location_images(wiki_locations, limit=3)
    else:
        wiki_imgs = []

    # Interleave news images + wiki images for variety
    all_imgs = []
    news_q, wiki_q = list(source_imgs), list(wiki_imgs)
    while news_q or wiki_q:
        if news_q: all_imgs.append(news_q.pop(0))
        if wiki_q: all_imgs.append(wiki_q.pop(0))

    img_files = []
    for si in all_imgs:
        p = download_image(si["image_url"])
        if p:
            img_files.append((p, si["source_label"], si["summary"]))
    print(f"[images] {len(img_files)} scraped ({len(source_imgs)} news + {len(wiki_imgs)} wiki)")

    # ── Flux Schnell AI image augmentation ─────────────────────────────────────
    # Fill gaps (< 8 images) with cinematic AI-generated conflict imagery.
    # Cost: $0.003/image via Replicate — 6 images = $0.018/video.
    REPLICATE_KEY = os.environ.get("REPLICATE_API_TOKEN", "")
    TARGET_IMAGES = 12  # aim for at least this many images per video
    if REPLICATE_KEY and len(img_files) < TARGET_IMAGES:
        needed = TARGET_IMAGES - len(img_files)
        # Build prompts from SITREP headline + key locations
        locations = list(dict.fromkeys(
            e.get("location", "") for e in key_events if e.get("location")
        ))[:4]
        loc_str = ", ".join(locations[:2]) if locations else "conflict zone"
        level_str = sitrep.get("escalation_level", "CRITICAL")
        # Pull headline keywords for more specific Flux prompts
        headline = sitrep.get("headline", "")
        headline_lower = headline.lower()
        base_prompts = [
            f"Cinematic wide-angle aerial photograph of {loc_str} at dusk, "
            "smoke columns rising from burning structures, AP wire photograph style, "
            "dramatic storm light, no text, no logos, ultra-sharp",

            f"Low-altitude military reconnaissance photograph of {loc_str}, "
            "missile strike craters, industrial damage, overcast dramatic sky, "
            "photojournalism, no people in foreground",

            f"Dramatic photojournalism at golden hour: military vehicles and equipment "
            f"near {loc_str}, dust haze, long shadows, Reuters style, sharp focus, "
            "cinematic widescreen composition",

            f"Oil refinery or industrial facility engulfed in fire and black smoke at night, "
            f"{loc_str} region, emergency lighting, dramatic flames, photorealistic news photography",

            f"Naval warships at high speed in Mediterranean Sea, grey overcast sky, "
            "white wake, military formation, photorealistic, cinematic wide shot",

            f"Empty urban street in {loc_str} at dawn, barricades, tension, military checkpoint, "
            "documentary style, subdued colors, photorealistic",

            f"Satellite-view style photograph of strategic port or airbase in {loc_str}, "
            "high altitude, sharp detail, intelligence imagery aesthetic, no labels",

            f"Dramatic wide establishing shot of ancient city skyline in Middle East, "
            "military helicopters visible in sky, smoke on horizon, photorealistic, cinematic",
        ]
        prompts = base_prompts[:needed]
        print(f"[flux] Generating {len(prompts)} AI images via Flux Schnell (~${len(prompts)*0.003:.3f})...")
        try:
            import replicate as _replicate
            import time as _time
            _replicate_client = _replicate.Client(api_token=REPLICATE_KEY)
            for i, prompt in enumerate(prompts):
                if i > 0:
                    _time.sleep(10)  # Replicate: 6 req/min cap even on paid tier
                for attempt in range(2):
                    try:
                        output = _replicate_client.run(
                            "black-forest-labs/flux-schnell",
                            input={
                                "prompt": prompt,
                                "num_outputs": 1,
                                "aspect_ratio": "16:9",
                                "output_format": "jpg",
                                "output_quality": 90,
                                "num_inference_steps": 4,
                                "go_fast": True,
                            }
                        )
                        img_url = str(output[0]) if output else None
                        if img_url:
                            p = download_image(img_url)
                            if p:
                                img_files.append((p, "AI IMAGERY", loc_str))
                                print(f"[flux] Image {i+1}/{len(prompts)} OK")
                        break
                    except Exception as e_img:
                        if "429" in str(e_img) and attempt == 0:
                            print(f"[flux] Rate limited — waiting 15s before retry...")
                            _time.sleep(15)
                        else:
                            print(f"[flux] Image {i+1} failed: {e_img}")
                            break
        except Exception as e_flux:
            print(f"[flux] Replicate unavailable ({e_flux}), using scraped images only")
    elif not REPLICATE_KEY:
        print("[flux] No REPLICATE_API_TOKEN set — skipping AI image generation")

    print(f"[images] Final pool: {len(img_files)} images")

    # 6. Plan segments
    sit_bullets  = parse_bullets(sitrep.get("situation", ""))
    esc_bullets  = parse_bullets(sitrep.get("escalation_text", ""))
    econ_bullets = parse_bullets(sitrep.get("economic_exposure", ""))
    gt_bullets   = parse_bullets(sitrep.get("game_theory", ""))
    analogue     = sitrep.get("historical_analogue", "") or ""

    # ── Segment plan — FULL BLEED BROADCAST ───────────────────────────────────
    # Philosophy: images fill the entire frame. Text only as lower-thirds.
    # Structure:  Sting → Headline → [Image clips cycling through all footage] → Score card → Endcard
    # Types: intro, headline, image, scorecard, endcard
    lc_hex = {
        "STABLE": "#16a34a", "ELEVATED": "#ca8a04",
        "ESCALATING": "#ea580c", "CRITICAL": "#dc2626", "WARTIME": "#ff0044",
    }.get(lvl, "#58a6ff")
    esc_label = f"{lvl}  ·  {cur_score if (cur_score := int(sitrep.get('escalation_score') or 50)) else '?'}/100"

    plan = [
        ("intro",     None, None, 2.5),   # 2.5s branding sting
        ("headline",  None, None, 4.5),   # 4.5s headline frame
    ]

    img_idx = 0
    kb_idx  = 0

    def next_img():
        nonlocal img_idx
        if img_idx < len(img_files):
            r = img_files[img_idx]; img_idx += 1; return r
        # Cycle back through images if we run out
        if img_files:
            img_idx2 = img_idx % len(img_files); img_idx += 1; return img_files[img_idx2]
        return None

    # Extract short headline snippets for lower-thirds (vary per image)
    headline_full = sitrep.get("headline", "")
    # Pull the top event summaries for per-image lower-thirds
    event_summaries = [e.get("summary", "")[:80] for e in key_events[:8]] if key_events else []
    sit_lines = []
    for line in (sitrep.get("situation") or "").split("\n"):
        line = line.strip().lstrip("•").strip()
        line = re.sub(r'\[src:[^\]]+\]|\[(CONFIRMED|REPORTED|CLAIMED)\]\s*', '', line).strip()
        if " — " in line:
            _, rest = line.split(" — ", 1)
            line = rest.strip()
        if len(line) > 20:
            sit_lines.append(line[:80])
    lower_thirds = (event_summaries + sit_lines + [headline_full] * 3)

    # Score card (threat dashboard) — brief, ~5s, right after intro/headline
    plan.append(("scorecard", None, None, 5.0))

    # Main body: pure image clips — each image gets its own segment with lower-third
    # Target ~8–10 image segments to fill the audio duration
    target_img_segs = max(6, len(img_files))
    for i in range(target_img_segs):
        img_info = next_img()
        if not img_info:
            break
        img_path_i, src_label_i, summary_i = img_info
        lower = lower_thirds[i % len(lower_thirds)] if lower_thirds else summary_i
        # Vary location from key events
        location_i = key_events[i % len(key_events)].get("location", "") if key_events else ""
        plan.append(("image", {
            "img_path": img_path_i,
            "source_label": src_label_i,
            "headline": lower,
            "location": location_i,
            "kb_style": kb_idx,
        }, None, 14.0))
        kb_idx += 1

    plan.append(("endcard", None, None, 3.5))

    # Scale all durations proportionally so total ≈ audio length (minus xfade overlap)
    total_xfade_overlap = XFADE_DUR * (len(plan) - 1)
    visual_target = total_audio + total_xfade_overlap
    current_total = sum(p[3] for p in plan)
    scale = visual_target / current_total
    plan = [(t, c, i, d * scale) for t, c, i, d in plan]

    # 7. Build individual clips
    print(f"[video] Building {len(plan)} segments...")
    clip_files: list[tuple[str, float]] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for seg_idx, (seg_type, content, img_info, dur) in enumerate(plan):
            out_clip = os.path.join(tmpdir, f"seg_{seg_idx:02d}.mp4")

            if seg_type == "intro":
                make_fullwidth_clip(make_intro_frame(sitrep), dur, out_clip)

            elif seg_type == "headline":
                make_fullwidth_clip(make_headline_frame(sitrep), dur, out_clip)

            elif seg_type == "endcard":
                make_fullwidth_clip(make_endcard(sitrep), dur, out_clip)

            elif seg_type == "scorecard":
                # Brief threat score card — 5s, right after headline
                frame = make_threat_dashboard_frame(sitrep, sitrep_history)
                make_fullwidth_clip(frame, dur, out_clip)

            elif seg_type == "image":
                # Full-bleed news image with Ken Burns + lower-third — the meat of the video
                d = content
                try:
                    make_fullbleed_image_clip(
                        img_path=d["img_path"],
                        source_label=d["source_label"],
                        headline=d["headline"],
                        location=d["location"],
                        duration=dur,
                        out=out_clip,
                        kb_style=d["kb_style"],
                        level_color_hex=lc_hex,
                        escalation_label=esc_label,
                    )
                except Exception as e:
                    print(f"  ✗ image clip failed ({e}), using headline frame")
                    make_fullwidth_clip(make_headline_frame(sitrep), dur, out_clip)

            # ── Legacy segment types (kept for backwards compat) ──────────────
            elif seg_type in ("chart", "dashboard"):
                frame = make_threat_dashboard_frame(sitrep, sitrep_history)
                make_fullwidth_clip(frame, dur, out_clip)
            elif seg_type in ("cards", "analyst", "geo"):
                frame = make_event_cards_frame(sitrep, key_events)
                make_fullwidth_clip(frame, dur, out_clip)
            elif seg_type == "full":
                section_label, color, bullets = content
                frame = make_fullwidth_text_frame(section_label, color, bullets, sitrep)
                make_fullwidth_clip(frame, dur, out_clip)
            elif seg_type == "split":
                # Legacy split → fullbleed image fallback
                if img_info:
                    img_path_s, src_label_s, summary_s = img_info
                    try:
                        make_fullbleed_image_clip(img_path_s, src_label_s, summary_s[:72],
                                                  "", dur, out_clip, kb_style=0,
                                                  level_color_hex=lc_hex, escalation_label=esc_label)
                    except Exception:
                        make_fullwidth_clip(make_headline_frame(sitrep), dur, out_clip)
                else:
                    make_fullwidth_clip(make_headline_frame(sitrep), dur, out_clip)

            print(f"  ✓ seg {seg_idx+1}/{len(plan)}: {seg_type} ({dur:.1f}s)")
            clip_files.append((out_clip, dur))

        # 8. Chain with xfade
        chained = os.path.join(tmpdir, "chained.mp4")
        print(f"[video] Chaining {len(clip_files)} clips with xfade...")
        chain_clips_xfade(clip_files, chained)

        # 9. Add ticker + audio (+ burn-in captions if Kokoro provided timings)
        out_path = args.out or str(VIDEO_DIR / f"sitrep_{sid}_{ts}.mp4")
        if caption_filter:
            # Burn captions then mux audio
            captioned_path = os.path.join(tmpdir, "captioned.mp4")
            print("[video] Burning word-synced captions...")
            cap_cmd = [
                "ffmpeg", "-y", "-i", chained,
                "-vf", caption_filter,
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-profile:v", "high", "-level:v", "4.0", "-pix_fmt", "yuv420p",
                captioned_path,
            ]
            cap_res = subprocess.run(cap_cmd, capture_output=True, text=True)
            if cap_res.returncode == 0:
                print("[video] Captions burned. Adding audio...")
                add_ticker_and_audio(captioned_path, audio_path, ticker_text, out_path)
            else:
                print(f"[captions] Burn failed ({cap_res.stderr[-200:]}), skipping")
                add_ticker_and_audio(chained, audio_path, ticker_text, out_path)
        else:
            print("[video] Adding audio (no caption data)...")
            add_ticker_and_audio(chained, audio_path, ticker_text, out_path)

    # 10. Cleanup downloaded images
    for p, _, _ in img_files:
        try:
            os.unlink(p)
        except Exception:
            pass

    size_mb = os.path.getsize(out_path) / 1024 / 1024

    # Only update manifest + symlink if output is inside VIDEO_DIR
    # (--out /tmp/test.mp4 is a dev test run — don't corrupt the live manifest)
    out_in_video_dir = Path(out_path).resolve().parent == VIDEO_DIR.resolve()
    if out_in_video_dir:
        latest_link = os.path.join(VIDEO_DIR, "latest.mp4")
        try:
            if os.path.lexists(latest_link):
                os.unlink(latest_link)
            os.symlink(os.path.basename(out_path), latest_link)
        except Exception as e:
            print(f"[warn] Could not update latest.mp4 symlink: {e}")
        video_basename = os.path.basename(out_path)
        update_video_manifest(sid, video_basename)
    else:
        print(f"[manifest] Skipped (--out is outside VIDEO_DIR — test run)")

    print(f"\n✅ SITREP VIDEO COMPLETE")
    print(f"   Output:  {out_path}")
    print(f"   URL:     /videos/latest.mp4")
    print(f"   Size:    {size_mb:.1f} MB")
    print(f"   SITREP:  #{sid} | {lvl}")
    print(f"   Voice:   ElevenLabs Bill ({ELEVENLABS_MODEL})")
    print(f"   Dur:     {total_audio:.1f}s narration")


if __name__ == "__main__":
    asyncio.run(main())

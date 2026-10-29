"""Historical March 2026 channel registry recovered with the application.

The entries, scores, affiliation labels, notes and cited references below are
unverified historical editorial metadata. They are preserved for continuity,
not calibrated accuracy/speed measurements, ground truth, current identity or
funding determinations, or evidence of independent origin. Revalidate specific
claims with dated primary sources before using these priors in an assessment.
Repeated records or publisher group labels do not confirm a reported claim.
"""

from typing import TypedDict


class ChannelMeta(TypedDict):
    display_name: str
    reliability: int           # Historical uncalibrated editorial prior (March 2026)
    affiliation: str           # Inherited unverified historical label
    flag: str
    bias_notes: str
    languages: list


# ── Full registry ─────────────────────────────────────────────────────────────

CHANNEL_REGISTRY: dict[str, ChannelMeta] = {

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  5/5 — Systematic verification, explicit methodology, corrects errors   ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    "CIG_telegram": {
        "display_name": "Conflict Intelligence Group",
        "reliability": 5,
        "affiliation": "independent-research",
        "flag": "🔍",
        "bias_notes": (
            "UK-based open-source research group. Systematic geolocation of conflict "
            "imagery with explicit methodology published. Corrects errors publicly. "
            "No state funding or known political alignment. Used by multiple live "
            "conflict trackers as primary source. Gold standard."
        ),
        "languages": ["en"],
    },
    "GeoConfirmed": {
        "display_name": "GeoConfirmed",
        "reliability": 5,
        "affiliation": "independent-research",
        "flag": "📍",
        "bias_notes": (
            "Specialist geolocation and visual verification. Publishes coordinates "
            "with explicit confidence ratings. Publicly corrected and deleted posts "
            "when challenged by other OSINT experts — rare intellectual honesty. "
            "No known state ties or political alignment."
        ),
        "languages": ["en"],
    },

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  4/5 — Cross-verifies, accurate, no state funding documented            ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    "AuroraIntel": {
        "display_name": "Aurora Intel",
        "reliability": 4,
        "affiliation": "independent-western",
        "flag": "🌐",
        "bias_notes": (
            "UK-based OSINT collective. Methodical cross-verification before posting. "
            "Good track record. Slight pro-Western framing on geopolitical narratives "
            "but factual on military events. Not state-funded. Minor framing lean "
            "does not materially distort reported facts."
        ),
        "languages": ["en"],
    },
    "OSINTdefender": {
        "display_name": "OSINT Defender",
        "reliability": 4,
        "affiliation": "independent-western",
        "flag": "🌐",
        "bias_notes": (
            "US-based independent analyst. Generally accurate with good source "
            "attribution. Pro-Western geopolitical framing on context, but the "
            "underlying event data is usually accurate. Not state-funded. "
            "Occasionally rapid-posts without full verification on breaking events."
        ),
        "languages": ["en"],
    },
    "OSINTWarfare": {
        "display_name": "OSINT Warfare",
        "reliability": 4,
        "affiliation": "independent",
        "flag": "🗺️",
        "bias_notes": (
            "~95K followers. Real-time global conflict maps and analysis. "
            "No known state ties, no documented political alignment. "
            "Listed by iranwarlive.com and erkansaka.net as a primary source. "
            "Speed is high but verification appears reasonably consistent."
        ),
        "languages": ["en"],
    },
    "ourwarstoday": {
        "display_name": "Our Wars Today",
        "reliability": 4,
        "affiliation": "independent",
        "flag": "⚖️",
        "bias_notes": (
            "~48K followers. Grokipedia's US-Iran conflict channel analysis assesses "
            "this as 'relatively neutral, factual reporting approach'. No documented "
            "state ties or political affiliation. Good cross-check source."
        ),
        "languages": ["en"],
    },
    "ELINTNews": {
        "display_name": "ELINT News",
        "reliability": 4,
        "affiliation": "independent-technical",
        "flag": "📡",
        "bias_notes": (
            "Electronic intelligence and military monitoring. Covers signals, "
            "radar intercepts, and electronic warfare events in the Middle East. "
            "Cross-verifies before posting. No documented political alignment or "
            "state funding. Complements MATA and IntelSky with signals focus."
        ),
        "languages": ["en"],
    },
    "dropsitenews": {
        "display_name": "Drop Site News",
        "reliability": 4,
        "affiliation": "independent",
        "flag": "📰",
        "bias_notes": (
            "Independent investigative outlet founded by Ryan Grim and Ken Klippenstein. "
            "Both have a strong track record on national security leaks and conflict "
            "reporting. No state funding documented. Progressive editorial lean on "
            "context; factual on events. Often breaks stories the wire services miss. "
            "4/5 for editorial independence and consistent verification standards."
        ),
        "languages": ["en"],
    },
    "lourage_america": {
        "display_name": "Lourage America",
        "reliability": 4,
        "affiliation": "independent",
        "flag": "🇺🇸",
        "bias_notes": (
            "Independent breaking news OSINT analyst on X. Vetted by operators "
            "of this instance for strong track record on conflict breaking news. "
            "No documented state funding or political coordination."
        ),
        "languages": ["en"],
    },
    "Osint613": {
        "display_name": "Osint613",
        "reliability": 3,
        "affiliation": "independent",
        "flag": "🔎",
        "bias_notes": (
            "Middle East OSINT specialist. Active Iran-Israel conflict coverage "
            "with a focus on military events and geolocation. Speed is good; "
            "verification depth is variable. No documented political alignment or "
            "state ties. Score of 3 reflects inconsistent cross-verification."
        ),
        "languages": ["en"],
    },
    "OSINT_Insider": {
        "display_name": "OSINT Insider",
        "reliability": 4,
        "affiliation": "independent-western",
        "flag": "🕵️",
        "bias_notes": (
            "~130K followers. Focuses on defense, diplomacy, and global conflict "
            "analysis. Listed by erkansaka.net 2026 US-Iran OSINT guide as a "
            "primary monitoring source. Strong track record on military deployments "
            "and diplomatic escalation signals. Minor pro-Western geopolitical "
            "framing on narrative context; factual on underlying events. "
            "Not state-funded."
        ),
        "languages": ["en"],
    },

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  3/5 — Useful but identifiable editorial perspective on one side,       ║
    # ║  OR variable verification. Applies equally to ALL political alignments. ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    "MATA_osint": {
        "display_name": "MATA (Military Air Tracking Alliance)",
        "reliability": 3,
        "affiliation": "independent-technical",
        "flag": "✈️",
        "bias_notes": (
            "~21K followers. Coordinated network of ~30 flight trackers. "
            "Purely technical — callsigns, routes, unusual military maneuvers. "
            "No political bias documented. Score of 3 reflects variable verification "
            "depth rather than any political lean. Directly complements ADS-B data."
        ),
        "languages": ["en"],
    },
    "Intel_Sky": {
        "display_name": "IntelSky",
        "reliability": 3,
        "affiliation": "independent-technical",
        "flag": "🛰️",
        "bias_notes": (
            "~51K followers. Middle East military air/land/sea tracking. "
            "Operates intelsky.org radar (100k+ ADS-B records/day). "
            "No documented political bias — purely technical. Score of 3 reflects "
            "that verification depth on non-aviation claims is inconsistent."
        ),
        "languages": ["en"],
    },
    "MilitaryOSINT": {
        "display_name": "Military OSINT",
        "reliability": 3,
        "affiliation": "independent",
        "flag": "🎖️",
        "bias_notes": (
            "Military hardware, deployments, and order-of-battle coverage. "
            "Speed and verification quality varies significantly. "
            "No strong political alignment documented. Cross-reference before citing."
        ),
        "languages": ["en"],
    },
    "inabornintel": {
        "display_name": "In A Born Intel",
        "reliability": 3,
        "affiliation": "independent",
        "flag": "📡",
        "bias_notes": (
            "Independent aggregator. Reliable on major confirmed events, "
            "variable on fast-developing situations. No documented political lean."
        ),
        "languages": ["en"],
    },

    # The following channels all score 3/5 for the same reason: accurate-enough
    # on raw events but with a clear editorial perspective from one side of the
    # conflict. They are equally useful and equally partial. None is "better"
    # than the others from a facts standpoint — they just serve different
    # narrative contexts. Use multiple in combination; dedup handles it.

    "IranIntl_En": {
        "display_name": "Iran International (EN)",
        "reliability": 3,
        "affiliation": "anti-regime",
        "flag": "📰",
        "bias_notes": (
            "London-based satellite channel, 1M+ subscribers. Credible journalism "
            "but editorially and financially opposed to the Islamic Republic "
            "(funded via Saudi/opposition-aligned sources per CPJ research). "
            "Will amplify Iranian military failures and downplay Iranian government "
            "context. Apply same scrutiny as you would to any state-aligned source "
            "from the other side. Facts usually accurate; framing is one-sided."
        ),
        "languages": ["en", "fa"],
    },
    "IsraelRadar_com": {
        "display_name": "Israel Radar",
        "reliability": 3,
        "affiliation": "israeli-perspective",
        "flag": "📰",
        "bias_notes": (
            "Israeli-perspective channel. Fast on events from the Israeli side. "
            "IMPORTANT: Israel's military censorship apparatus (IDF censor) actively "
            "restricts what can be reported about strikes on Israeli territory "
            "(CPJ + RSF documented March 2026). Events favourable to Iran may be "
            "delayed, minimised, or absent. Equally biased to QudsNen, just opposite."
        ),
        "languages": ["en", "he"],
    },
    "QudsNen": {
        "display_name": "Quds News Network",
        "reliability": 3,
        "affiliation": "resistance-perspective",
        "flag": "📰",
        "bias_notes": (
            "Axis of Resistance / pro-resistance viewpoint. Fast on events from "
            "Iranian-aligned forces. Will amplify Iranian/Hezbollah/Houthi actions "
            "and downplay losses on that side. Equally biased to IsraelRadar, "
            "just opposite direction. Use together to triangulate what both sides "
            "are claiming — truth often lies between the two narratives."
        ),
        "languages": ["en", "ar"],
    },
    "Middle_East_Spectator": {
        "display_name": "Middle East Spectator",
        "reliability": 3,
        "affiliation": "resistance-perspective",
        "flag": "🌍",
        "bias_notes": (
            "Aggregates broadly but with documented Axis of Resistance framing "
            "(grokipedia US-Iran analysis). Mirrors IsraelRadar in reliability — "
            "both are 3/5, both have a side. Neither is 'better' as a facts source; "
            "they're complementary if treated as perspective-windows."
        ),
        "languages": ["en"],
    },
    "alibk3": {
        "display_name": "Ali Bk",
        "reliability": 3,
        "affiliation": "resistance-perspective",
        "flag": "📡",
        "bias_notes": (
            "129K subscribers. Arabic-language real-time conflict reporting covering "
            "missile launches, Gulf state strikes, and ground conflict media. "
            "Very high posting frequency during active conflict periods. "
            "Uses 'إعلام العدو' (enemy media) to refer to Israeli outlets — "
            "clear resistance-aligned framing. Scores 3/5: fast and accurate on events "
            "but editorially one-sided, same tier as QudsNen. Valuable for Arabic-language "
            "coverage and Gulf-state event alerts (Bahrain, Kuwait, UAE) not well covered "
            "by English-language channels."
        ),
        "languages": ["ar"],
    },

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  2/5 — Speed-over-accuracy OR documented amplification of unverified    ║
    # ║  content regardless of political direction                              ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    "warmonitors": {
        "display_name": "War Monitors",
        "reliability": 2,
        "affiliation": "aggregator",
        "flag": "⚡",
        "bias_notes": (
            "High-speed breaking-news aggregator. Posts extremely rapidly without "
            "independent verification. High false-positive rate on early reports. "
            "Score of 2 is about methodology (speed > accuracy), not politics. "
            "Use as first-alert trigger only — always corroborate."
        ),
        "languages": ["en"],
    },
    "Qassam1brigades": {
        "display_name": "Qassam Brigades (Hamas)",
        "reliability": 2,
        "affiliation": "resistance-military",
        "flag": "⚠️",
        "bias_notes": (
            "Official military communiques from the Izz ad-Din al-Qassam Brigades — "
            "the military wing of Hamas. Primary source for Hamas operational claims "
            "including rocket launches, tunnel operations, and hostage status. "
            "Score of 2: official armed-group channel. Events reported are often "
            "real but heavily framed. No independent verification. The same standard "
            "applied here would apply to an official IDF Spokesperson channel. "
            "In registry for documentation and primary-source reference only — "
            "excluded from DEFAULT_CHANNELS by reliability threshold."
        ),
        "languages": ["ar", "en"],
    },
    "Ansarallah_MC": {
        "display_name": "Ansarallah (Houthi) Media",
        "reliability": 2,
        "affiliation": "houthi-official",
        "flag": "⚠️",
        "bias_notes": (
            "Official Ansarallah (Houthi movement) media channel. Primary source "
            "for Houthi operational claims: Red Sea shipping attacks, ballistic "
            "missile launches toward Israel, drone operations. "
            "Score of 2: official armed-group channel, no independent verification. "
            "Events are often real but framing is one-sided. "
            "In registry for documentation and primary-source reference — "
            "excluded from DEFAULT_CHANNELS by reliability threshold. "
            "Use alongside Haaretz/Times of Israel to triangulate Red Sea events."
        ),
        "languages": ["ar"],
    },
    "IntelSlava": {
        "display_name": "Intel Slava Z",
        "reliability": 1,
        "affiliation": "russian-state",
        "flag": "🚫",
        "bias_notes": (
            "RECLASSIFIED to 1/5: Russian state information operation. "
            "The 'Z' is an explicit symbol of Russian pro-invasion ideology — this "
            "is not a framing preference, it is an active propaganda identifier. "
            "Russian information operations around the Iran-Israel conflict are "
            "documented (Russian and Iranian strategic interests align). "
            "Same scoring as PressTV/IRNA applied consistently — the nationality "
            "of the state does not affect the classification. "
            "IN REGISTRY ONLY for documentation. Never actively monitored."
        ),
        "languages": ["en", "ru"],
    },
    "SentDefender": {
        "display_name": "Sentinel Defender",
        "reliability": 2,
        "affiliation": "western-aggregator",
        "flag": "⚡",
        "bias_notes": (
            "Large following, amplified by high-profile accounts. University of "
            "Washington study flagged for spreading unverified content during "
            "conflict events without adequate editorial safeguards. "
            "Score of 2 is about documented accuracy issues, not political alignment. "
            "Use as first-alert signal only."
        ),
        "languages": ["en"],
    },

    # ╔══════════════════════════════════════════════════════════════════════════╗
    # ║  1/5 — Confirmed state broadcaster. Official government narrative only. ║
    # ║  Applies to ALL governments equally. Not actively monitored.            ║
    # ╚══════════════════════════════════════════════════════════════════════════╝

    "PressTV": {
        "display_name": "Press TV",
        "reliability": 1,
        "affiliation": "iranian-state",
        "flag": "📺",
        "bias_notes": (
            "Iranian state broadcaster. Official Islamic Republic messaging. "
            "Factnameh study: >95% word-similarity with IRGC channels = coordinated "
            "state narrative. Score of 1 applies to ALL state broadcasters equally — "
            "same standard would apply to Israeli Kan, US VOA, or RT if monitored."
        ),
        "languages": ["en", "fa"],
    },
    "IRNA_En": {
        "display_name": "IRNA (Islamic Republic News Agency)",
        "reliability": 1,
        "affiliation": "iranian-state",
        "flag": "📺",
        "bias_notes": (
            "Official Iranian state news agency. Government official narrative only. "
            "Identical scoring rationale as PressTV. In registry for completeness "
            "and scoring reference if encountered — not actively monitored."
        ),
        "languages": ["en", "fa"],
    },
}


# ── Convenience exports ───────────────────────────────────────────────────────

# ── Channels we actively monitor ─────────────────────────────────────────────
# Criteria:
#   • reliability >= 3 (cross-verifies, factual on events, no systematic accuracy failures)
#   • NOT a confirmed state broadcaster (applies to ALL governments equally)
#
# Explicitly excluded affiliations regardless of reliability score:
#   "iranian-state"       — IRGC/government mouthpieces (PressTV, IRNA)
#   "russian-state"       — Russian state/pro-invasion info ops (Intel Slava Z)
#   "russian-state-adjacent" — Channels with documented Kremlin coordination
#
# Note: 2/5 channels (warmonitors, SentDefender) are excluded by the reliability
# threshold, not by affiliation. They remain in the registry for documentation.

# Affiliations that are NEVER monitored regardless of claimed reliability score
_EXCLUDED_AFFILIATIONS = {"iranian-state", "russian-state", "russian-state-adjacent"}

DEFAULT_CHANNELS = [
    k for k, v in CHANNEL_REGISTRY.items()
    if v["reliability"] >= 3 and v["affiliation"] not in _EXCLUDED_AFFILIATIONS
]


def get_reliability(channel_name: str) -> int | None:
    """Return reliability score (1-5) for a channel handle. None if unknown."""
    meta = CHANNEL_REGISTRY.get(channel_name)
    return meta["reliability"] if meta else None


def get_channel_meta(channel_name: str) -> ChannelMeta | None:
    """Return full metadata dict for a channel handle."""
    return CHANNEL_REGISTRY.get(channel_name)


def get_all_channels() -> dict[str, ChannelMeta]:
    """Return the full channel registry."""
    return CHANNEL_REGISTRY

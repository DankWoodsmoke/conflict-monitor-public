"""Descriptive source-network labels, never an independence or truth test.

Different editorial perspectives can repeat the same underlying report. Network
membership cannot establish independence, agreement, or confirmation. The legacy
confirmation helper is retained for API compatibility and deliberately fails closed.
"""
from app.services.evidence import canonical_source, parse_channels

CHANNEL_NETWORK: dict[str, str] = {
    "bbc_mideast":      "WEST_PRESS",
    "the_war_zone":     "WEST_PRESS",
    "defense_one":      "WEST_PRESS",
    "guardian_mideast": "WEST_PRESS",
    "dw_world":         "WEST_PRESS",
    "aljazeera":       "MIDEAST_PRESS",
    "rfi":             "MIDEAST_PRESS",
    "middle_east_eye": "MIDEAST_PRESS",
    "QudsNen":              "TG",
    "Middle_East_Spectator":"TG",
    "alibk3":               "TG",
    "times_of_israel": "IL_PRESS",
    "jpost":           "IL_PRESS",
    "x_elintnews":       "X_OSINT",
    "x_dropsitenews":    "X_OSINT",
    "x_osint613":        "X_OSINT",
    "x_osintwarfare":    "X_OSINT",
    "x_geoconfirmed":    "X_OSINT",
    "x_lourage_america": "X_OSINT",
    "x_truthtellerftm":  "X_OSINT",
    "x_auroraintel":     "X_OSINT",
    "x_osintdefender":   "X_OSINT",
    "x_intelsky":        "X_OSINT",
    "elintnews":       "X_OSINT",
    "dropsitenews":    "X_OSINT",
    "osint613":        "X_OSINT",
    "osintwarfare":    "X_OSINT",
    "geoconfirmed":    "X_OSINT",
    "lourage_america": "X_OSINT",
    "truthtellerftm":  "X_OSINT",
    "auroraintel":     "X_OSINT",
    "osintdefender":   "X_OSINT",
    "intelsky":        "X_OSINT",
    "x_iranintl":     "WEST_PRESS",
    "x_ajebreaking":  "MIDEAST_PRESS",
    "x_haaretz":      "IL_PRESS",
    "iranintl":       "WEST_PRESS",
    "ajenews":        "MIDEAST_PRESS",
    "haaretzcom":     "IL_PRESS",
    "x_ukmto":           "MARITIME_SEC",
    "x_us5thfleet":      "MARITIME_SEC",
    "x_cmf":             "MARITIME_SEC",
    "x_tankertrackers":  "MARITIME_SEC",
    "ukmto":             "MARITIME_SEC",
    "us5thfleet":        "MARITIME_SEC",
    "cmf_bahrain":       "MARITIME_SEC",
    "tankertrackers":    "MARITIME_SEC",
    "x_safety4sea":       "WEST_PRESS",
    "hellenic_shipping":  "WEST_PRESS",
    "splash247":          "WEST_PRESS",
    "safety4sea":         "WEST_PRESS",
    "x_chrismartenson":   "ANALYSIS",
    "x_lynalden":         "ANALYSIS",
    "x_lukegromen":       "ANALYSIS",
    "x_ianbremmer":       "ANALYSIS",
    "x_michaelpettis":    "ANALYSIS",
    "war_on_rocks":       "ANALYSIS",
    "oilprice":           "ANALYSIS",
    "freightwaves":       "ANALYSIS",
    "x_raoulpal":         "ANALYSIS",
    "x_tavicosta":        "ANALYSIS",
    "x_eurasiagroup":     "ANALYSIS",
    "x_gzeromedia":       "ANALYSIS",
    "x_csis":             "ANALYSIS",
    "x_freightwaves":     "ANALYSIS",
    "x_warontherocks":    "ANALYSIS",
    "satellite_firms":    "SATELLITE",
    "nasa firms viirs-noaa20": "SATELLITE",
    "nasa firms":         "SATELLITE",
}
# Normalize legacy casing and transport aliases once.
CHANNEL_NETWORK = {canonical_source(k): v for k, v in CHANNEL_NETWORK.items()}

# No political/network pair supplies a valid factual-confirmation rule.
VALID_CONFIRMATION_PAIRS: frozenset[frozenset[str]] = frozenset()


def get_channel_network(channel: str) -> str:
    return CHANNEL_NETWORK.get(canonical_source(channel), "UNKNOWN")


def compute_confirmed_networks(reporting_channels: str) -> list[str]:
    """Legacy name: returns descriptive networks only, not confirmed networks."""
    return sorted({get_channel_network(c) for c in parse_channels(reporting_channels)})


def is_cross_network_confirmed(reporting_channels: str) -> bool:
    """Channel names alone cannot demonstrate independent factual corroboration."""
    return False


def is_viral_amplification(reporting_channels: str, report_count: int) -> bool:
    """Heuristic review flag for concentrated repetition, not a misinformation verdict."""
    if report_count < 4:
        return False
    networks = set(compute_confirmed_networks(reporting_channels))
    return bool(networks) and (len(networks) == 1 or networks <= {"TG", "X_OSINT"})

"""Anomaly scoring — identifies high-severity, strategically significant events.

Uses rules-based severity thresholds only — no AI API calls.
This keeps costs zero while still surfacing events that matter most.

Score = event severity (0-10). Events with score >= 7 show in ANOMALY ALERTS.
The classifier already does the hard work of assigning a meaningful severity score.
"""

import logging

logger = logging.getLogger(__name__)


async def analyze_anomaly(summary: str, event_type: str, severity: int,
                          location_name: str, raw_text: str) -> dict:
    """Return anomaly score based on severity — no API call needed."""
    # Directly use the classifier's severity score as the anomaly indicator.
    # severity >= 9: nuclear/capital strikes, major power involvement
    # severity >= 7: escalatory threshold crossings, first-use events
    # severity >= 5: notable, show in anomaly panel
    # < 5: routine conflict activity, not shown
    score = severity if severity >= 5 else 0
    is_anomaly = score >= 7

    if is_anomaly:
        logger.info(
            "High-severity event flagged (score=%d): %s @ %s",
            score, summary[:80], location_name,
        )

    return {
        "is_anomaly": is_anomaly,
        "anomaly_score": score,
        "analysis": "",  # No AI-generated text — analysis is in the source article
    }

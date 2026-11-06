"""Anomaly assessment remains unavailable without an independent baseline."""


async def analyze_anomaly(summary: str, event_type: str, severity: int,
                          location_name: str, raw_text: str) -> dict:
    """Retain compatibility fields without turning impact into anomaly evidence."""
    return {"is_anomaly":False,"anomaly_score":0,"analysis":"",
            "assessment_status":"unassessed","basis":"no_qualified_anomaly_baseline"}

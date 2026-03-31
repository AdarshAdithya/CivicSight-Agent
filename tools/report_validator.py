"""
report_validator.py
-------------------
ADK tool that accepts extracted civic issue details and returns a simulated
Government Tracking ID. In production this would POST to a real GovAPI.
"""
import hashlib
import time
import json


def report_validator(
    category: str,
    severity: str,
    location: str,
    description: str,
) -> dict:
    """Registers a civic issue and returns a Government Tracking ID.

    Args:
        category: Type of civic issue (e.g. "Pothole", "Broken Streetlight").
        severity: Severity level — "Low", "Medium", "High", or "Critical".
        location: Street address or landmark where the issue was observed.
        description: Short human-readable summary of the problem.

    Returns:
        A dict containing the tracking ID, status, and estimated resolution time.
    """
    # --- Simulate ID generation (deterministic from content) ---
    payload = f"{category}|{severity}|{location}|{description}|{time.time()}"
    short_hash = hashlib.sha1(payload.encode()).hexdigest()[:8].upper()
    tracking_id = f"GOV-{short_hash}"

    resolution_days = {"Low": 14, "Medium": 7, "High": 3, "Critical": 1}.get(
        severity, 7
    )

    result = {
        "tracking_id": tracking_id,
        "status": "Registered",
        "category": category,
        "severity": severity,
        "location": location,
        "description": description,
        "estimated_resolution_days": resolution_days,
        "message": (
            f"Issue '{category}' at '{location}' has been registered with the "
            f"civic authority. Tracking ID: {tracking_id}. "
            f"Estimated resolution: {resolution_days} day(s)."
        ),
    }

    print(f"[report_validator] Registered issue → {json.dumps(result, indent=2)}")
    return result

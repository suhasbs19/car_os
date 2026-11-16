"""
Vehicle health assessment service.
Implements a deterministic rule-based health score formula.

DISCLAIMER: Health score is a rule-based estimate, not a professional
mechanical diagnosis. It cannot verify actual tyre, brake, suspension,
engine, or battery condition.
"""
from datetime import date


HEALTH_DISCLAIMER = (
    "Health score is a rule-based estimate, not a professional mechanical diagnosis. "
    "It cannot verify actual tyre, brake, suspension, engine, or battery condition."
)


def calculate_health_score(manufacturing_year: int, odometer_km: float,
                            service_history: str, reported_issues: int,
                            obd_record=None) -> dict:
    """
    Calculate vehicle health score using the deterministic formula.
    Optionally incorporates advisory OBD-II DTC penalties when diagnostic data is present.

    Returns a dict with:
        score (float): 0–100
        status (str): Healthy | Attention | Critical
        breakdown (dict): individual penalty components
    """
    current_year = date.today().year
    age = max(0, current_year - manufacturing_year)

    age_penalty = min(age * 3, 30)
    mileage_penalty = min((odometer_km // 10000) * 2, 30)

    service_history_map = {
        "Full": 0,
        "Partial": 10,
        "None": 20,
        "Unknown": 10,
    }
    service_penalty = service_history_map.get(service_history, 10)

    issues_penalty = min(reported_issues * 10, 40)

    # Optional OBD-II advisory diagnostic penalty (capped at 15 to avoid dominating health score)
    obd_penalty = 0
    obd_advisory_notes = []
    if obd_record:
        dtcs = getattr(obd_record, "dtc_list", [])
        if dtcs:
            dtc_pen = min(len(dtcs) * 5, 10)
            obd_penalty += dtc_pen
            obd_advisory_notes.append(f"{len(dtcs)} active DTC code(s) detected ({', '.join(dtcs)})")
        if getattr(obd_record, "coolant_temp_c", None) and obd_record.coolant_temp_c >= 105:
            obd_penalty += 5
            obd_advisory_notes.append(f"Elevated coolant temperature ({obd_record.coolant_temp_c}°C)")
        if getattr(obd_record, "battery_voltage", None) and obd_record.battery_voltage < 11.8:
            obd_penalty += 5
            obd_advisory_notes.append(f"Low battery voltage ({obd_record.battery_voltage}V)")
        obd_penalty = min(obd_penalty, 15)

    # Diagnostic presence distinction
    if obd_record is None:
        diagnostic_status = "No diagnostic data recorded"
    else:
        dtcs = getattr(obd_record, "dtc_list", [])
        if dtcs:
            diagnostic_status = f"{len(dtcs)} active fault code(s) recorded"
        else:
            diagnostic_status = "No diagnostic faults detected"

    raw_score = 100 - age_penalty - mileage_penalty - service_penalty - issues_penalty - obd_penalty
    health_score = float(max(0, min(100, raw_score)))

    if health_score >= 80:
        status = "Healthy"
    elif health_score >= 50:
        status = "Attention"
    else:
        status = "Critical"

    return {
        "score": round(health_score, 1),
        "status": status,
        "score_label": f"{round(health_score, 1)} / 100 Health Index",
        "diagnostic_status": diagnostic_status,
        "breakdown": {
            "age_years": age,
            "age_penalty": age_penalty,
            "mileage_penalty": mileage_penalty,
            "service_penalty": service_penalty,
            "issues_penalty": issues_penalty,
            "obd_penalty": obd_penalty,
            "obd_advisory_notes": obd_advisory_notes,
            "raw_score": raw_score,
            "diagnostic_status": diagnostic_status,
        },
        "disclaimer": HEALTH_DISCLAIMER,
    }


def get_status_color(status: str) -> str:
    """Return a CSS class name for the given health status."""
    return {
        "Healthy": "status-healthy",
        "Attention": "status-attention",
        "Critical": "status-critical",
    }.get(status, "status-unknown")

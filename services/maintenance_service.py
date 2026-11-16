"""
Maintenance service: reminder logic and status classification.

Rule-based reminders are labelled as rule-based, not ML predictions.
"""
from datetime import date, timedelta


def classify_maintenance_status(service_date, next_service_date, next_service_odometer,
                                 current_odometer):
    """
    Determine if a maintenance item is Overdue, Upcoming, or OK.
    Returns a dict with status and reason.
    """
    today = date.today()
    reasons = []
    status = "OK"

    if next_service_date:
        days_until = (next_service_date - today).days
        if days_until < 0:
            status = "Overdue"
            reasons.append(f"Service date was {abs(days_until)} day(s) ago")
        elif days_until <= 30:
            status = "Upcoming"
            reasons.append(f"Service due in {days_until} day(s)")

    if next_service_odometer and current_odometer:
        km_remaining = next_service_odometer - current_odometer
        if km_remaining <= 0:
            status = "Overdue"
            reasons.append(f"Odometer target exceeded by {abs(km_remaining):.0f} km")
        elif km_remaining <= 1000:
            if status != "Overdue":
                status = "Upcoming"
            reasons.append(f"{km_remaining:.0f} km until next service")

    return {
        "status": status,
        "reasons": reasons,
        "reminder_type": "Rule-based reminder (not an ML prediction)",
    }


def get_upcoming_maintenance(vehicle_id, maintenance_records, current_odometer, obd_record=None):
    """
    Return list of upcoming/overdue maintenance items for a vehicle.
    Incorporates OBD-II trouble codes and serious condition alerts if available.
    """
    results = []
    today = date.today()
    for record in maintenance_records:
        info = classify_maintenance_status(
            record.service_date,
            record.next_service_date,
            record.next_service_odometer,
            current_odometer,
        )
        if info["status"] in ("Overdue", "Upcoming"):
            results.append({
                "record_id": record.id,
                "component": record.component_name,
                "category": record.service_category,
                "status": info["status"],
                "reasons": info["reasons"],
            })

    # Integrate active OBD-II diagnostic recommendations
    if obd_record:
        from services.obd_service import analyze_obd_record
        analysis = analyze_obd_record(obd_record)
        for flag in analysis.get("critical_flags", []):
            results.append({
                "record_id": None,
                "component": flag["type"],
                "category": "OBD-II Diagnostic Telemetry",
                "status": "Overdue",
                "reasons": [flag["message"], "Direct OBD parameter trigger; technician verification advised."],
            })
        for dtc in analysis.get("dtc_explanations", []):
            if dtc["severity"] != "Critical":
                results.append({
                    "record_id": None,
                    "component": f"DTC {dtc['code']}: {dtc['title']}",
                    "category": "OBD-II Diagnostic Advisory",
                    "status": "Upcoming",
                    "reasons": [dtc["explanation"], dtc["recommendation"]],
                })

    return results


def calculate_maintenance_stats(maintenance_records):
    """
    Calculate aggregated maintenance statistics.
    """
    total_cost = sum(r.cost for r in maintenance_records)
    total_records = len(maintenance_records)
    categories = {}
    for r in maintenance_records:
        categories[r.service_category] = categories.get(r.service_category, 0) + r.cost

    return {
        "total_cost": total_cost,
        "total_records": total_records,
        "cost_by_category": categories,
    }

"""
Fuel and energy analysis service.
Keeps litres (ICE/CNG/Hybrid) and kWh (Electric) strictly separate.
"""


FUEL_UNIT_MAP = {
    "Petrol": "L",
    "Diesel": "L",
    "CNG": "kg",
    "Hybrid": "L",
    "Electric": "kWh",
}

EFFICIENCY_LABEL_MAP = {
    "Petrol": "km/L",
    "Diesel": "km/L",
    "CNG": "km/kg",
    "Hybrid": "km/L",
    "Electric": "km/kWh",
}

# Indian fuel price benchmarks (Metro 2026 indicative averages)
INDIAN_FUEL_BENCHMARKS = {
    "Petrol": {"price_per_unit": 103.50, "unit": "L", "region": "Metro Average (INR/L)", "currency": "₹"},
    "Diesel": {"price_per_unit": 90.00, "unit": "L", "region": "Metro Average (INR/L)", "currency": "₹"},
    "CNG": {"price_per_unit": 86.00, "unit": "kg", "region": "Metro Average (INR/kg)", "currency": "₹"},
    "Electric": {"price_per_unit": 9.00, "unit": "kWh", "region": "Domestic/EV Tariff (INR/kWh)", "currency": "₹"},
}


def calculate_fuel_efficiency(distance_km: float, quantity: float, fuel_type: str, cost: float | None = None) -> dict:
    """
    Calculate fuel/energy efficiency for a single fill-up or charging event.
    Returns efficiency value (km/L or km/kWh), unit label, and cost per km.
    """
    if quantity <= 0 or distance_km <= 0:
        return {"efficiency": None, "unit": EFFICIENCY_LABEL_MAP.get(fuel_type, "km/unit"),
                "cost_per_km": None, "error": "Distance and quantity must be positive"}

    efficiency = distance_km / quantity
    unit = EFFICIENCY_LABEL_MAP.get(fuel_type, "km/unit")
    cost_per_km = round(cost / distance_km, 2) if (cost is not None and cost >= 0) else None

    return {
        "efficiency": round(efficiency, 2),
        "unit": unit,
        "cost_per_km": cost_per_km,
    }


def calculate_cost_per_km(distance_km: float, cost: float) -> float | None:
    """Calculate cost per kilometre. Returns None if distance is zero or invalid."""
    if distance_km and distance_km > 0 and cost is not None and cost >= 0:
        return round(cost / distance_km, 2)
    return None


def aggregate_fuel_records(fuel_records, fuel_type: str | None = None) -> dict:
    """
    Aggregate multiple fuel records into summary statistics.
    Keeps ICE (Litres), CNG (Kilograms), and Electric (kWh) units strictly segregated.
    When multiple fuel types are present in a mixed fleet query, total quantity and
    mixed economy are not blended into invalid single numbers; instead a structured
    per-powertrain breakdown is provided alongside fleet distance and total spend.
    """
    records = list(fuel_records)
    if not records:
        unit = EFFICIENCY_LABEL_MAP.get(fuel_type, "km/unit") if fuel_type else "km/unit"
        qty_unit = FUEL_UNIT_MAP.get(fuel_type, "unit") if fuel_type else "unit"
        return {
            "total_records": 0,
            "total_distance_km": 0.0,
            "total_quantity": 0.0,
            "total_cost": 0.0,
            "average_efficiency": None,
            "average_cost_per_km": None,
            "unit": unit,
            "quantity_unit": qty_unit,
            "is_mixed": False,
            "by_fuel_type": {},
        }

    total_distance = sum(r.distance_km for r in records)
    total_cost = sum(r.cost for r in records)
    avg_cost_per_km = calculate_cost_per_km(total_distance, total_cost)

    distinct_types = sorted(list(set(r.fuel_type for r in records if r.fuel_type)))
    is_mixed = len(distinct_types) > 1

    by_fuel = {}
    for ft in distinct_types:
        ft_recs = [r for r in records if r.fuel_type == ft]
        ft_dist = sum(r.distance_km for r in ft_recs)
        ft_qty = sum(r.quantity for r in ft_recs)
        ft_cost = sum(r.cost for r in ft_recs)
        ft_eff = round(ft_dist / ft_qty, 2) if (ft_qty > 0 and ft_dist > 0) else None
        ft_cpk = calculate_cost_per_km(ft_dist, ft_cost)
        by_fuel[ft] = {
            "total_records": len(ft_recs),
            "total_distance_km": round(ft_dist, 1),
            "total_quantity": round(ft_qty, 2),
            "total_cost": round(ft_cost, 2),
            "average_efficiency": ft_eff,
            "average_cost_per_km": ft_cpk,
            "unit": EFFICIENCY_LABEL_MAP.get(ft, "km/unit"),
            "quantity_unit": FUEL_UNIT_MAP.get(ft, "unit"),
        }

    if is_mixed:
        return {
            "total_records": len(records),
            "total_distance_km": round(total_distance, 1),
            "total_quantity": None,
            "total_cost": round(total_cost, 2),
            "average_efficiency": None,
            "average_cost_per_km": avg_cost_per_km,
            "unit": "Mixed Units",
            "quantity_unit": "Mixed",
            "is_mixed": True,
            "by_fuel_type": by_fuel,
        }
    else:
        ft = distinct_types[0] if distinct_types else (fuel_type or "Petrol")
        total_quantity = sum(r.quantity for r in records)
        avg_efficiency = round(total_distance / total_quantity, 2) if (total_quantity > 0 and total_distance > 0) else None
        return {
            "total_records": len(records),
            "total_distance_km": round(total_distance, 1),
            "total_quantity": round(total_quantity, 2),
            "total_cost": round(total_cost, 2),
            "average_efficiency": avg_efficiency,
            "average_cost_per_km": avg_cost_per_km,
            "unit": EFFICIENCY_LABEL_MAP.get(ft, "km/unit"),
            "quantity_unit": FUEL_UNIT_MAP.get(ft, "unit"),
            "is_mixed": False,
            "by_fuel_type": by_fuel,
        }


def monthly_fuel_trend(fuel_records) -> list:
    """Return monthly aggregated fuel cost and distance for charting."""
    from collections import defaultdict
    monthly = defaultdict(lambda: {"cost": 0.0, "distance": 0.0, "quantity": 0.0})
    for r in fuel_records:
        key = r.date.strftime("%Y-%m")
        monthly[key]["cost"] += r.cost
        monthly[key]["distance"] += r.distance_km
        monthly[key]["quantity"] += r.quantity

    return [
        {"month": k, "cost": round(v["cost"], 2),
         "distance": round(v["distance"], 1),
         "quantity": round(v["quantity"], 2)}
        for k, v in sorted(monthly.items())
    ]

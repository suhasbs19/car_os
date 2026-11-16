"""
CAR OS - Powertrain-Differentiated OBD Reference Service
========================================================
Manages documented OBD-II parameter ranges, PID applicability, and diagnostic
condition assessment across distinct powertrains:
  - Petrol
  - CNG
  - Diesel
  - Hybrid
  - Electric (EV)

Key Safeguards:
1. Distinguishes powertrain-specific PID applicability (e.g. Engine RPM and Coolant Temp are N/A for EVs).
2. Clarifies that 12V auxiliary voltage is NOT High-Voltage traction battery State of Charge/Health.
3. Treats values as reference indicator ranges, NOT conclusive proof of mechanical component failure.
4. Complies with Section D mandates of CAR OS.
"""

import os
import json
from typing import Optional, Dict, Any, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_JSON_PATH = os.path.join(BASE_DIR, "data", "obd_reference_parameters.json")

_REFERENCE_CACHE: Optional[Dict[str, Any]] = None

OBD_REFERENCE_DISCLAIMER = (
    "OBD-II readings and reference ranges indicate electronic sensor parameters and circuit conditions. "
    "Deviations represent diagnostic indicators requiring physical verification by a certified technician, "
    "not conclusive proof of mechanical component failure."
)


def load_obd_reference_data(filepath: str = REF_JSON_PATH) -> Dict[str, Any]:
    """Load and cache the powertrain-differentiated OBD reference parameter dataset."""
    global _REFERENCE_CACHE
    if _REFERENCE_CACHE is not None:
        return _REFERENCE_CACHE

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"OBD reference dataset not found at: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        _REFERENCE_CACHE = json.load(f)

    return _REFERENCE_CACHE


def normalize_fuel_type(fuel_type: Optional[str]) -> str:
    """Normalize input fuel type into standard powertrain category."""
    if not fuel_type:
        return "Petrol"
    f = str(fuel_type).strip().title()
    if "Electric" in f or "Ev" in f.upper():
        return "Electric"
    if "Hybrid" in f:
        return "Hybrid"
    if "Diesel" in f:
        return "Diesel"
    if "Cng" in f.upper() or "Lpg" in f.upper():
        return "CNG"
    return "Petrol"


def check_parameter_applicability(param_name: str, fuel_type: str) -> Tuple[bool, str]:
    """
    Determine if a standard OBD parameter is applicable to the given powertrain.
    
    Returns:
        (is_applicable: bool, note: str)
    """
    ref_data = load_obd_reference_data()
    params = ref_data.get("parameters", {})
    p_info = params.get(param_name)

    if not p_info:
        return True, "Standard OBD-II parameter"

    norm_fuel = normalize_fuel_type(fuel_type)
    applicability = p_info.get("applicability", {})
    is_app = applicability.get(norm_fuel, True)

    if not is_app:
        if norm_fuel == "Electric" and p_info.get("ev_note"):
            return False, p_info["ev_note"]
        if norm_fuel == "Diesel" and p_info.get("diesel_note"):
            return False, p_info["diesel_note"]
        return False, f"Parameter '{param_name}' is not applicable to {norm_fuel} powertrains."

    if norm_fuel == "Hybrid" and p_info.get("hybrid_note"):
        return True, p_info["hybrid_note"]
    if norm_fuel == "Electric" and p_info.get("ev_note"):
        return True, p_info["ev_note"]

    return True, f"Standard parameter for {norm_fuel} powertrain"


def evaluate_obd_reading(
    param_name: str,
    value: Optional[float],
    fuel_type: str = "Petrol",
    vehicle_state: str = "running",
) -> Dict[str, Any]:
    """
    Evaluate a specific telemetry reading against documented reference ranges.
    
    Returns:
        dict:
            parameter: str
            value: float | None
            fuel_type: str
            is_applicable: bool
            status: "normal" | "advisory" | "critical" | "not_applicable" | "no_data"
            message: str
            reference_range: dict | None
            disclaimer: str
    """
    norm_fuel = normalize_fuel_type(fuel_type)
    is_applicable, applicability_note = check_parameter_applicability(param_name, norm_fuel)

    if not is_applicable:
        return {
            "parameter": param_name,
            "value": value,
            "fuel_type": norm_fuel,
            "is_applicable": False,
            "status": "not_applicable",
            "message": applicability_note,
            "reference_range": None,
            "disclaimer": OBD_REFERENCE_DISCLAIMER,
        }

    if value is None:
        return {
            "parameter": param_name,
            "value": None,
            "fuel_type": norm_fuel,
            "is_applicable": True,
            "status": "no_data",
            "message": "No reading provided for evaluation.",
            "reference_range": None,
            "disclaimer": OBD_REFERENCE_DISCLAIMER,
        }

    ref_data = load_obd_reference_data()
    p_info = ref_data.get("parameters", {}).get(param_name, {})
    ranges_by_fuel = p_info.get("ranges", {})
    ranges = ranges_by_fuel.get(norm_fuel)

    status = "normal"
    msg = f"{p_info.get('name', param_name)} reading ({value} {p_info.get('unit', '')}) is within normal operating reference."

    # Engine Coolant Temp evaluation
    if param_name == "coolant_temp_c" and ranges:
        if value >= ranges.get("critical_high", 115):
            status = "critical"
            msg = f"Elevated coolant temperature ({value}°C). Operating above {ranges.get('warning_high', 105)}°C indicates severe thermal stress; immediate inspection recommended."
        elif value >= ranges.get("warning_high", 105):
            status = "advisory"
            msg = f"Elevated coolant temperature ({value}°C) approaching high thermal threshold. Verify radiator airflow and coolant level."
        elif value < ranges.get("operating_min", 80) and vehicle_state == "running":
            status = "advisory"
            msg = f"Coolant temperature ({value}°C) below normal warmed-up operating range ({ranges.get('operating_min', 80)}-{ranges.get('operating_max', 95)}°C). Thermostat may be sluggish or stuck open."

    # Auxiliary / Battery Voltage evaluation
    elif param_name == "battery_voltage" and ranges:
        if value < ranges.get("critical_low", 11.6):
            status = "critical"
            msg = f"Low auxiliary battery voltage ({value}V). Risk of ECU brownout or failed engine start/contactor closure."
        elif value > ranges.get("overvoltage", 15.2):
            status = "critical"
            msg = f"High electrical bus voltage ({value}V). Alternator regulator or DC-DC converter output voltage exceeds safe charging limits."
        elif value < ranges.get("resting_min", 12.2) and vehicle_state != "running":
            status = "advisory"
            msg = f"Battery resting voltage ({value}V) indicates partial discharge or battery aging."

    # Engine RPM evaluation
    elif param_name == "engine_rpm" and ranges:
        if ranges.get("redline") and value > ranges["redline"]:
            status = "critical"
            msg = f"Engine RPM ({value}) exceeds manufacturer redline threshold ({ranges['redline']} RPM)."
        elif vehicle_state == "idle" and (value < ranges.get("idle_min", 600) or value > ranges.get("idle_max", 1000)):
            status = "advisory"
            msg = f"Idle RPM ({value}) deviates from expected idle range ({ranges.get('idle_min', 650)}-{ranges.get('idle_max', 900)} RPM)."

    return {
        "parameter": param_name,
        "value": value,
        "fuel_type": norm_fuel,
        "is_applicable": True,
        "status": status,
        "message": msg,
        "reference_range": ranges,
        "disclaimer": OBD_REFERENCE_DISCLAIMER,
    }


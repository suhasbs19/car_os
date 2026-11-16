"""
CAR OS - OBD-II Diagnostic Telemetry & DTC Analysis Service
Handles validation, structured storage, condition checking, and explainable
fault code analysis for vehicle onboard diagnostics.
"""
import re
import json
from datetime import datetime, timezone

DTC_PATTERN = re.compile(r"^[PCBU][0-9A-Fa-f]{4}$")

OBD_DISCLAIMER = (
    "OBD-II readings and diagnostic trouble codes (DTCs) indicate electronic parameters and "
    "detected circuit conditions. They do not independently prove complete mechanical component failure. "
    "A physical diagnostic verification by a certified technician is recommended."
)

# Knowledge base of common automotive OBD-II DTC trouble codes
DTC_KNOWLEDGE_BASE = {
    "P0420": {
        "title": "Catalyst System Efficiency Below Threshold (Bank 1)",
        "subsystem": "Powertrain / Emissions",
        "severity": "Moderate",
        "explanation": "The Engine Control Module (ECM) detected that catalyst oxygen storage capacity has dropped below calibrated threshold, or the downstream O2 sensor response is slow.",
        "recommendation": "Inspect exhaust pipe for leaks before the catalytic converter; verify upstream and downstream O2 sensor voltage switching before replacing catalytic converter.",
    },
    "P0300": {
        "title": "Random / Multiple Cylinder Misfire Detected",
        "subsystem": "Powertrain / Ignition & Combustion",
        "severity": "Critical",
        "explanation": "The crankshaft position sensor detected rotational speed fluctuations indicating multiple engine cylinders are misfiring during combustion.",
        "recommendation": "Inspect spark plugs, ignition coil packs, fuel injector spray patterns, and check for vacuum intake leaks. Avoid heavy load driving.",
    },
    "P0301": {"title": "Cylinder 1 Misfire Detected", "subsystem": "Powertrain", "severity": "Critical", "explanation": "Combustion failure isolated to cylinder 1.", "recommendation": "Swap cylinder 1 spark plug/coil to test if misfire moves to another cylinder."},
    "P0302": {"title": "Cylinder 2 Misfire Detected", "subsystem": "Powertrain", "severity": "Critical", "explanation": "Combustion failure isolated to cylinder 2.", "recommendation": "Inspect cylinder 2 ignition and fuel delivery."},
    "P0303": {"title": "Cylinder 3 Misfire Detected", "subsystem": "Powertrain", "severity": "Critical", "explanation": "Combustion failure isolated to cylinder 3.", "recommendation": "Inspect cylinder 3 ignition and fuel delivery."},
    "P0304": {"title": "Cylinder 4 Misfire Detected", "subsystem": "Powertrain", "severity": "Critical", "explanation": "Combustion failure isolated to cylinder 4.", "recommendation": "Inspect cylinder 4 ignition and fuel delivery."},
    "P0101": {
        "title": "Mass Air Flow (MAF) Sensor Circuit Range/Performance",
        "subsystem": "Powertrain / Fuel & Air Metering",
        "severity": "Moderate",
        "explanation": "Intake air flow signal does not correlate with calculated engine speed and throttle angle.",
        "recommendation": "Inspect air filter housing for dirt accumulation and clean MAF sensor sensing wire with approved electronics cleaner.",
    },
    "P0171": {
        "title": "System Too Lean (Bank 1)",
        "subsystem": "Powertrain / Fuel Trim",
        "severity": "Moderate",
        "explanation": "Air-fuel mixture has excess oxygen or insufficient fuel delivery. Short/long-term fuel trim reached positive correction limit.",
        "recommendation": "Inspect for intake boot tears, PCV hose vacuum leaks, low fuel pressure, or dirty fuel injectors.",
    },
    "P0172": {
        "title": "System Too Rich (Bank 1)",
        "subsystem": "Powertrain / Fuel Trim",
        "severity": "Moderate",
        "explanation": "Air-fuel mixture has excess unburned fuel. Negative fuel trim limit reached.",
        "recommendation": "Check fuel pressure regulator, inspect for dripping fuel injectors, and verify engine oil is not contaminated with fuel.",
    },
    "P0113": {
        "title": "Intake Air Temperature (IAT) Sensor Circuit High",
        "subsystem": "Powertrain / Air Metering",
        "severity": "Low",
        "explanation": "IAT sensor circuit voltage is near 5V reference, typically indicating an open circuit or unplugged sensor.",
        "recommendation": "Inspect IAT harness connector and wiring for pin corrosion or disconnection.",
    },
    "P0128": {
        "title": "Coolant Thermostat (Coolant Temp Below Regulating Temp)",
        "subsystem": "Powertrain / Cooling System",
        "severity": "Moderate",
        "explanation": "Engine took longer than expected to reach normal operating temperature (typically 80°C–90°C).",
        "recommendation": "Check engine coolant level; thermostat is likely stuck open and needs replacement.",
    },
    "P0500": {
        "title": "Vehicle Speed Sensor (VSS) Malfunction",
        "subsystem": "Chassis / Speed Sensing",
        "severity": "Moderate",
        "explanation": "Transmission speed sensor or ABS wheel speed signal is erratic or missing.",
        "recommendation": "Inspect wheel speed sensor wiring harnesses and ABS tone rings for road debris damage.",
    },
    "P0700": {
        "title": "Transmission Control System (MIL Request)",
        "subsystem": "Powertrain / Automatic Transmission",
        "severity": "Critical",
        "explanation": "Transmission Control Module (TCM) detected a hydraulic, clutch, or solenoid fault and requested the Check Engine light.",
        "recommendation": "Connect dedicated transmission scan tool to retrieve TCM-specific sub-codes; check transmission fluid level and condition.",
    },
    "C0035": {
        "title": "Left Front Wheel Speed Circuit Malfunction",
        "subsystem": "Chassis / ABS & Traction",
        "severity": "Moderate",
        "explanation": "ABS module lost signal from left-front wheel speed sensor.",
        "recommendation": "Inspect left-front hub sensor harness and connector integrity.",
    },
    "B0001": {
        "title": "Driver Airbag Stage 1 Deployment Control",
        "subsystem": "Body / Supplemental Restraint System",
        "severity": "Critical",
        "explanation": "SRS module detected high or low resistance in the driver steering wheel clockspring circuit.",
        "recommendation": "Do not probe with standard multimeter. Service steering column clockspring through authorized safety technician.",
    },
    "U0100": {
        "title": "Lost Communication With ECM / PCM",
        "subsystem": "Network & Communication / CAN-Bus",
        "severity": "Critical",
        "explanation": "Controller Area Network (CAN-bus) nodes failed to receive periodic heartbeat message from engine computer.",
        "recommendation": "Check battery voltage, engine ground straps, ECM power relay, and high/low CAN-bus terminating resistance.",
    },
}


def explain_dtc(code: str) -> dict:
    """Return an explainable breakdown of a single Diagnostic Trouble Code."""
    normalized = code.strip().upper()
    if normalized in DTC_KNOWLEDGE_BASE:
        info = DTC_KNOWLEDGE_BASE[normalized]
        return {
            "code": normalized,
            "title": info["title"],
            "subsystem": info["subsystem"],
            "severity": info["severity"],
            "explanation": info["explanation"],
            "recommendation": info["recommendation"],
            "known": True,
        }

    # Fallback explanation by prefix
    prefix = normalized[0] if normalized else ""
    prefix_map = {
        "P": ("Powertrain", "Engine, transmission, and emissions control systems"),
        "C": ("Chassis", "Braking, steering, suspension, and ABS systems"),
        "B": ("Body", "Airbags, climate control, lighting, and interior electronics"),
        "U": ("Network & Communication", "CAN-bus communication lines and inter-ECU links"),
    }
    system, desc = prefix_map.get(prefix, ("General Vehicle Electronics", "Vehicle electronic controller system"))

    return {
        "code": normalized,
        "title": f"Manufacturer Diagnostic Trouble Code ({normalized})",
        "subsystem": system,
        "severity": "Moderate",
        "explanation": f"The onboard electronic control unit recorded fault code {normalized} within the {desc}. Parameter deviations or sensor circuit anomalies have been recorded.",
        "recommendation": "Scan vehicle with a dedicated professional OBD-II scanner to read live freeze-frame data and sensor circuit voltages.",
        "known": False,
    }


def parse_and_validate_dtcs(raw_dtcs: str) -> tuple[list[str], list[str]]:
    """
    Parse a string containing one or more DTC codes.
    Returns (valid_dtc_list, error_messages).
    """
    if not raw_dtcs or not raw_dtcs.strip():
        return [], []

    # Split by comma, semicolon, newline, or whitespace
    tokens = re.split(r"[,;\s]+", raw_dtcs.strip())
    valid_codes = []
    errors = []

    for token in tokens:
        clean = token.strip().upper()
        if not clean:
            continue
        if DTC_PATTERN.match(clean):
            if clean not in valid_codes:
                valid_codes.append(clean)
        else:
            errors.append(
                f"Invalid DTC code '{token}'. OBD-II codes must consist of P, C, B, or U "
                f"followed by 4 hexadecimal characters (e.g. P0420, P0300)."
            )

    return valid_codes, errors


def validate_obd_data(form_data: dict) -> tuple[bool, dict, list[str]]:
    """
    Validate OBD-II diagnostic data submitted via form.

    Returns:
        (has_data, cleaned_data, errors)
        - has_data (bool): True if at least one OBD field had meaningful input.
        - cleaned_data (dict): Validated values with None for omitted fields.
        - errors (list[str]): List of human-readable error messages.
    """
    errors = []
    cleaned = {
        "connection_status": "Not connected",
        "data_source": "Manual",
        "engine_rpm": None,
        "vehicle_speed_kmh": None,
        "coolant_temp_c": None,
        "engine_load_pct": None,
        "throttle_pos_pct": None,
        "fuel_system_status": None,
        "battery_voltage": None,
        "dtc_codes": [],
        "notes": None,
    }

    # Extract raw inputs
    conn_status = form_data.get("obd_connection_status", "").strip()
    data_source = form_data.get("obd_data_source", "").strip()
    rpm_str = form_data.get("engine_rpm", "").strip()
    speed_str = form_data.get("vehicle_speed_kmh", "").strip()
    coolant_str = form_data.get("coolant_temp_c", "").strip()
    load_str = form_data.get("engine_load_pct", "").strip()
    throttle_str = form_data.get("throttle_pos_pct", "").strip()
    fuel_status = form_data.get("fuel_system_status", "").strip()
    voltage_str = form_data.get("battery_voltage", "").strip()
    dtc_str = form_data.get("dtc_codes", "").strip()
    notes = form_data.get("obd_notes", "").strip()

    # Determine if user attempted to enter any OBD information
    has_data = any([
        rpm_str, speed_str, coolant_str, load_str, throttle_str,
        fuel_status, voltage_str, dtc_str, notes,
        conn_status in ("Connected", "Not connected") and (conn_status == "Connected" or any([rpm_str, speed_str, coolant_str, dtc_str])),
    ])

    if not has_data:
        return False, cleaned, []

    # Connection status
    if conn_status in ("Connected", "Not connected"):
        cleaned["connection_status"] = conn_status
    else:
        cleaned["connection_status"] = "Not connected"

    # Data source
    if data_source in ("Manual", "Live OBD"):
        cleaned["data_source"] = data_source
    else:
        cleaned["data_source"] = "Manual"

    # Engine RPM: [0, 15000]
    if rpm_str:
        try:
            rpm = float(rpm_str)
            if rpm < 0 or rpm > 15000:
                errors.append("Engine RPM must be between 0 and 15,000 RPM.")
            else:
                cleaned["engine_rpm"] = round(rpm, 1)
        except ValueError:
            errors.append("Engine RPM must be a valid number.")

    # Vehicle Speed: [0, 400] km/h
    if speed_str:
        try:
            speed = float(speed_str)
            if speed < 0 or speed > 400:
                errors.append("Vehicle speed must be between 0 and 400 km/h.")
            else:
                cleaned["vehicle_speed_kmh"] = round(speed, 1)
        except ValueError:
            errors.append("Vehicle speed must be a valid number.")

    # Coolant Temperature: [-40, 150] °C
    if coolant_str:
        try:
            coolant = float(coolant_str)
            if coolant < -40 or coolant > 150:
                errors.append("Engine coolant temperature must be between -40°C and 150°C.")
            else:
                cleaned["coolant_temp_c"] = round(coolant, 1)
        except ValueError:
            errors.append("Engine coolant temperature must be a valid number.")

    # Engine Load: [0, 100] %
    if load_str:
        try:
            load = float(load_str)
            if load < 0 or load > 100:
                errors.append("Engine load must be between 0% and 100%.")
            else:
                cleaned["engine_load_pct"] = round(load, 1)
        except ValueError:
            errors.append("Engine load must be a valid number.")

    # Throttle Position: [0, 100] %
    if throttle_str:
        try:
            throttle = float(throttle_str)
            if throttle < 0 or throttle > 100:
                errors.append("Throttle position must be between 0% and 100%.")
            else:
                cleaned["throttle_pos_pct"] = round(throttle, 1)
        except ValueError:
            errors.append("Throttle position must be a valid number.")

    # Battery Voltage: [0, 30] V
    if voltage_str:
        try:
            voltage = float(voltage_str)
            if voltage < 0 or voltage > 30:
                errors.append("Battery voltage must be between 0V and 30V.")
            else:
                cleaned["battery_voltage"] = round(voltage, 2)
        except ValueError:
            errors.append("Battery voltage must be a valid number.")

    # Fuel System Status
    if fuel_status:
        cleaned["fuel_system_status"] = fuel_status[:100]

    # Diagnostic Trouble Codes (DTCs)
    if dtc_str:
        valid_dtcs, dtc_errors = parse_and_validate_dtcs(dtc_str)
        if dtc_errors:
            errors.extend(dtc_errors)
        cleaned["dtc_codes"] = valid_dtcs

    # Notes
    if notes:
        cleaned["notes"] = notes

    return has_data, cleaned, errors


def analyze_obd_record(record) -> dict:
    """
    Perform diagnostic condition analysis on an OBDRecord.

    Returns:
        dict containing:
            dtc_explanations: list of dicts from explain_dtc()
            critical_flags: list of high-priority condition alerts
            advisories: list of moderate/informative condition notes
            disclaimer: standard safety/diagnostic disclaimer
    """
    if record is None:
        return {
            "has_data": False,
            "dtc_explanations": [],
            "critical_flags": [],
            "advisories": [],
            "disclaimer": OBD_DISCLAIMER,
        }

    dtc_list = record.dtc_list if hasattr(record, "dtc_list") else []
    dtc_explanations = [explain_dtc(code) for code in dtc_list]

    critical_flags = []
    advisories = []

    # Check for critical DTCs
    critical_dtcs = [d for d in dtc_explanations if d["severity"] == "Critical"]
    if critical_dtcs:
        codes_str = ", ".join(d["code"] for d in critical_dtcs)
        critical_flags.append({
            "type": "Critical DTC",
            "message": f"Critical diagnostic trouble codes recorded ({codes_str}). Immediate engine/safety inspection recommended.",
        })

    # Coolant temperature checks
    if record.coolant_temp_c is not None:
        if record.coolant_temp_c >= 105:
            critical_flags.append({
                "type": "Engine Overheating",
                "message": f"Elevated engine coolant temperature ({record.coolant_temp_c}°C). Operating above 105°C risks cylinder head warping or blown head gasket.",
            })
        elif record.coolant_temp_c < 65 and record.engine_rpm and record.engine_rpm > 1200:
            advisories.append({
                "type": "Low Operating Temperature",
                "message": f"Engine coolant temperature ({record.coolant_temp_c}°C) is below optimal 80°C–90°C while vehicle is running. Thermostat may be stuck open.",
            })

    # Battery voltage checks
    if record.battery_voltage is not None:
        if record.battery_voltage < 11.8:
            critical_flags.append({
                "type": "Low Battery Voltage",
                "message": f"Low electrical system voltage ({record.battery_voltage}V). Deep discharge or alternator undercharging detected.",
            })
        elif record.battery_voltage > 15.0:
            critical_flags.append({
                "type": "Overvoltage Warning",
                "message": f"Alternator voltage regulator warning: {record.battery_voltage}V exceeds safe 14.8V charging threshold.",
            })
        elif record.battery_voltage < 12.2:
            advisories.append({
                "type": "Weak Battery",
                "message": f"Battery resting voltage ({record.battery_voltage}V) indicates partial charge or impending battery aging.",
            })

    # Engine load at idle
    if record.engine_rpm is not None and record.engine_load_pct is not None:
        if record.engine_rpm < 1000 and record.engine_load_pct > 45:
            advisories.append({
                "type": "High Idle Engine Load",
                "message": f"Engine load is unusually high ({record.engine_load_pct}%) at idle ({record.engine_rpm} RPM). Check AC compressor drag or accessory belt resistance.",
            })

    # Electric Vehicle (EV) specific safeguards & SOH/SOC distinction
    is_ev = False
    vehicle_obj = getattr(record, "vehicle", None)
    if vehicle_obj and getattr(vehicle_obj, "fuel_type", "") == "Electric":
        is_ev = True

    if is_ev:
        advisories.append({
            "type": "EV High-Voltage Traction Battery Safeguard",
            "message": (
                "Auxiliary voltage reflects the 12V low-voltage accessory system, NOT the "
                "High-Voltage (HV) Traction Battery State of Health (SOH) or State of Charge (SOC). "
                "Per literature survey guidelines (Haraz et al., Lanubile et al.), EV traction battery "
                "degradation cannot be inferred from 12V auxiliary readings alone."
            ),
        })

    return {
        "has_data": True,
        "record": record,
        "is_ev": is_ev,
        "dtc_explanations": dtc_explanations,
        "critical_flags": critical_flags,
        "advisories": advisories,
        "disclaimer": OBD_DISCLAIMER,
    }

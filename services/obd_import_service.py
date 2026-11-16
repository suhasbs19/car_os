"""
CAR OS - OBD-II Data File Import & Ingestion Service
Handles secure upload, inspection, column mapping, validation, duplicate prevention,
and ingestion of OBD-II CSV telemetry records.

Supports standard OBD telematics headers and Toyota Etios research CSV formats.
Safely detects and handles trailing commas and CSV formula injection.
"""
import os
import re
import csv
import json
import hashlib
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple, Optional, Any
from werkzeug.utils import secure_filename
from models import db, Vehicle, OBDRecord
from services.health_service import calculate_health_score
from services.valuation_service import calculate_resale_value
from services.obd_service import DTC_PATTERN, parse_and_validate_dtcs

# Configurable limits
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ROW_COUNT = 5000                   # 5,000 rows max per import

# Temporary directory for error reports and preview sessions
IMPORT_TEMP_DIR = os.path.join(tempfile.gettempdir(), "caros_obd_imports")
os.makedirs(IMPORT_TEMP_DIR, exist_ok=True)

# Parameter definitions with metadata and alias rules
SUPPORTED_PARAMETERS = {
    "timestamp": {
        "label": "Timestamp / Date-Time",
        "aliases": [
            "timestamp", "time", "datetime", "date_time", "date", "utc_time",
            "log_time", "timestamp_utc", "time_stamp", "time (s)", "engine_run_tine ()",
            "engine_run_time ()", "engine_run_time", "run_time",
        ],
        "type": "datetime",
    },
    "engine_rpm": {
        "label": "Engine RPM",
        "aliases": [
            "engine_rpm ()", "engine_rpm", "rpm", "enginespeed", "engine speed",
            "rpm (rpm)", "enginerpm", "engine_speed_rpm", "engine_speed",
        ],
        "type": "float",
        "min": 0.0,
        "max": 15000.0,
        "unit": "RPM",
    },
    "vehicle_speed_kmh": {
        "label": "Vehicle Speed (km/h)",
        "aliases": [
            "vehicle_speed ()", "vehicle_speed", "speed", "speed_kmh",
            "vehicle_speed_kmh", "vehicle speed (km/h)", "speed (km/h)", "veh_speed",
        ],
        "type": "float",
        "min": 0.0,
        "max": 400.0,
        "unit": "km/h",
    },
    "coolant_temp_c": {
        "label": "Engine Coolant Temp (°C)",
        "aliases": [
            "coolant_temperature ()", "coolant_temperature", "coolant_temp",
            "coolant_temp_c", "coolant", "engine_coolant_temp", "engine coolant temp (°c)",
            "coolant temp", "temp_coolant",
        ],
        "type": "float",
        "min": -40.0,
        "max": 150.0,
        "unit": "°C",
    },
    "engine_load_pct": {
        "label": "Engine Load (%)",
        "aliases": [
            "engine_load ()", "engine_load", "calculated_load", "load",
            "engine_load_pct", "engine load (%)", "calculated engine load (%)",
            "eng_load", "load_pct",
        ],
        "type": "float",
        "min": 0.0,
        "max": 100.0,
        "unit": "%",
    },
    "throttle_pos_pct": {
        "label": "Throttle Position (%)",
        "aliases": [
            "throttle ()", "relative_throttle_position ()", "absolute_throttle_b ()",
            "throttle_pos", "throttle_position", "throttle_pos_pct", "throttle (%)",
            "throttle_position (%)", "rel_throttle", "abs_throttle",
        ],
        "type": "float",
        "min": 0.0,
        "max": 100.0,
        "unit": "%",
    },
    "battery_voltage": {
        "label": "Battery / Control Module Voltage (V)",
        "aliases": [
            "control_module_voltage ()", "control_module_voltage", "battery_voltage",
            "voltage", "battery", "module_voltage", "battery (v)", "ecu_voltage",
            "control_voltage", "voltage (v)", "volts",
        ],
        "type": "float",
        "min": 0.0,
        "max": 30.0,
        "unit": "V",
    },
    "fuel_system_status": {
        "label": "Fuel-System Status",
        "aliases": [
            "fuel_system_status", "fuel_system", "fuel_status", "fuelsystemstatus",
            "fuel system status", "fuel_sys_status",
        ],
        "type": "string",
    },
    "dtc_codes": {
        "label": "Diagnostic Trouble Codes (DTCs)",
        "aliases": [
            "dtc_codes", "dtc", "dtcs", "trouble_codes", "fault_codes",
            "diagnostic_trouble_codes", "dtc_code", "trouble_code",
        ],
        "type": "dtc",
    },
}


def sanitize_csv_cell(val: Any) -> str:
    """
    Sanitize text against CSV Formula Injection (Excel / LibreOffice DDE execution).
    Prepends a single quote if string begins with =, +, -, @, tab, or carriage return.
    """
    if val is None:
        return ""
    s = str(val).strip()
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{s}"
    return s


def normalize_header_token(token: str) -> str:
    """Normalize a CSV header string for comparison."""
    if not token:
        return ""
    # Strip whitespace, lower
    clean = token.strip().lower()
    # Normalize empty parens e.g. " ()"
    clean = re.sub(r"\s*\(\s*\)", " ()", clean)
    return clean


def safe_read_csv(file_stream_or_content: Any) -> Tuple[List[str], List[List[str]], bool, Optional[str]]:
    """
    Safely parse CSV content with trailing-comma detection and normalization.
    Returns:
        (headers, rows, has_trailing_comma, error_message)
    """
    try:
        if isinstance(file_stream_or_content, (bytes, bytearray)):
            text = file_stream_or_content.decode("utf-8-sig", errors="replace")
        elif isinstance(file_stream_or_content, str):
            text = file_stream_or_content
        elif hasattr(file_stream_or_content, "read"):
            raw = file_stream_or_content.read()
            if isinstance(raw, bytes):
                text = raw.decode("utf-8-sig", errors="replace")
            else:
                text = str(raw)
        else:
            return [], [], False, "Invalid file stream."
    except Exception as e:
        return [], [], False, f"Could not decode file content: {str(e)}"

    if not text.strip():
        return [], [], False, "The uploaded file is empty."

    lines = text.splitlines()
    if not lines:
        return [], [], False, "No data rows found in CSV."

    # Parse using csv.reader
    reader = csv.reader(lines)
    raw_header = next(reader, None)
    if not raw_header:
        return [], [], False, "Could not read CSV header."

    # Detect trailing comma in header
    has_trailing_comma = False
    if raw_header and raw_header[-1] == "":
        has_trailing_comma = True
        raw_header = raw_header[:-1]

    headers = [h.strip() for h in raw_header]
    if not headers or all(h == "" for h in headers):
        return [], [], False, "CSV header is empty or invalid."

    expected_cols = len(headers)
    clean_rows = []

    for line_idx, row in enumerate(reader, start=2):
        if not row:
            continue
        # If row has exactly expected_cols + 1 and the last element is empty, trailing comma detected
        if len(row) == expected_cols + 1 and row[-1].strip() == "":
            has_trailing_comma = True
            row = row[:-1]
        elif len(row) > expected_cols and all(c.strip() == "" for c in row[expected_cols:]):
            has_trailing_comma = True
            row = row[:expected_cols]

        # Pad with empty strings if row is shorter than header
        if len(row) < expected_cols:
            row = row + [""] * (expected_cols - len(row))

        clean_rows.append(row)

        if len(clean_rows) > MAX_ROW_COUNT:
            return headers, clean_rows, has_trailing_comma, f"File exceeds maximum allowed limit of {MAX_ROW_COUNT} rows."

    return headers, clean_rows, has_trailing_comma, None


def detect_column_mappings(headers: List[str]) -> Dict[str, Optional[str]]:
    """
    Automatically map CSV column headers to supported OBD-II parameters.
    Returns:
        dict: {param_name: matched_header_or_None}
    """
    mapping = {p: None for p in SUPPORTED_PARAMETERS}
    normalized_headers = {normalize_header_token(h): h for h in headers}

    # 1. Check exact / alias matches
    for param, meta in SUPPORTED_PARAMETERS.items():
        aliases = meta["aliases"]
        matched_header = None
        for alias in aliases:
            norm_alias = normalize_header_token(alias)
            if norm_alias in normalized_headers:
                matched_header = normalized_headers[norm_alias]
                break

        # 2. If not found by direct alias, try substring match (excluding counter/timer columns)
        if not matched_header:
            for norm_h, original_h in normalized_headers.items():
                if param == "dtc_codes" and any(neg in norm_h for neg in ["time", "distance", "warm_up", "since", "cleared"]):
                    continue
                # Strip non-alphanumeric
                h_slug = re.sub(r"[^a-z0-9]", "", norm_h)
                for alias in aliases:
                    alias_slug = re.sub(r"[^a-z0-9]", "", alias)
                    if alias_slug and (alias_slug == h_slug or alias_slug in h_slug):
                        matched_header = original_h
                        break
                if matched_header:
                    break

        mapping[param] = matched_header

    return mapping


def compute_obd_fingerprint(
    vehicle_id: int,
    timestamp_val: Any,
    engine_rpm: Optional[float],
    vehicle_speed_kmh: Optional[float],
    coolant_temp_c: Optional[float],
    engine_load_pct: Optional[float],
    throttle_pos_pct: Optional[float],
    battery_voltage: Optional[float],
    fuel_system_status: Optional[str],
    dtc_codes: List[str]
) -> str:
    """
    Compute a stable SHA-256 fingerprint for OBD records to prevent duplicate imports.
    """
    ts_str = timestamp_val.isoformat() if hasattr(timestamp_val, "isoformat") else str(timestamp_val or "")
    dtc_str = ",".join(sorted(dtc_codes)) if dtc_codes else ""
    rpm_str = f"{engine_rpm:.1f}" if engine_rpm is not None else ""
    speed_str = f"{vehicle_speed_kmh:.1f}" if vehicle_speed_kmh is not None else ""
    coolant_str = f"{coolant_temp_c:.1f}" if coolant_temp_c is not None else ""
    load_str = f"{engine_load_pct:.1f}" if engine_load_pct is not None else ""
    throttle_str = f"{throttle_pos_pct:.1f}" if throttle_pos_pct is not None else ""
    voltage_str = f"{battery_voltage:.2f}" if battery_voltage is not None else ""
    fuel_str = (fuel_system_status or "").strip().lower()

    raw = f"{vehicle_id}|{ts_str}|{rpm_str}|{speed_str}|{coolant_str}|{load_str}|{throttle_str}|{voltage_str}|{fuel_str}|{dtc_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_existing_vehicle_fingerprints(vehicle_id: int) -> set:
    """Retrieve stable fingerprints for all existing OBD records of a vehicle."""
    records = OBDRecord.query.filter_by(vehicle_id=vehicle_id).all()
    fingerprints = set()
    for r in records:
        fp = compute_obd_fingerprint(
            vehicle_id=r.vehicle_id,
            timestamp_val=r.timestamp,
            engine_rpm=r.engine_rpm,
            vehicle_speed_kmh=r.vehicle_speed_kmh,
            coolant_temp_c=r.coolant_temp_c,
            engine_load_pct=r.engine_load_pct,
            throttle_pos_pct=r.throttle_pos_pct,
            battery_voltage=r.battery_voltage,
            fuel_system_status=r.fuel_system_status,
            dtc_codes=r.dtc_list,
        )
        fingerprints.add(fp)
    return fingerprints


def parse_timestamp_value(raw_val: str, base_time: Optional[datetime] = None) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Parse a timestamp string in multiple standard formats.
    Returns:
        (datetime_obj, error_msg)
    """
    if not raw_val or not str(raw_val).strip():
        return None, None

    s = str(raw_val).strip()

    # Try ISO formats
    for iso_fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(s, iso_fmt), None
        except ValueError:
            pass

    # Try ISO fromisoformat
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None), None
    except ValueError:
        pass

    # Try unix timestamp or numeric relative seconds (e.g. ENGINE_RUN_TINE 0.0, 10.5)
    try:
        val_f = float(s)
        # Epoch timestamp (> 1 billion)
        if val_f > 1_000_000_000:
            if val_f > 1_000_000_000_000:  # milliseconds
                val_f = val_f / 1000.0
            return datetime.fromtimestamp(val_f, tz=timezone.utc).replace(tzinfo=None), None
        elif base_time is not None:
            # Relative run time in seconds from session base
            return base_time + timedelta(seconds=val_f), None
    except (ValueError, OverflowError):
        pass

    return None, f"Invalid timestamp format '{s}'. Expected ISO 8601 (e.g. YYYY-MM-DD HH:MM:SS) or Unix epoch."


def preview_obd_csv(
    file_content: Any,
    filename: str,
    vehicle_id: int
) -> Dict[str, Any]:
    """
    Validate and generate a preview of the uploaded OBD CSV file.
    """
    # Verify vehicle
    vehicle = Vehicle.query.get(vehicle_id)
    if not vehicle:
        return {
            "success": False,
            "error": f"Vehicle ID {vehicle_id} not found.",
        }

    # Safe CSV parsing
    headers, rows, has_trailing_comma, error = safe_read_csv(file_content)
    if error:
        return {"success": False, "error": error}

    total_rows = len(rows)
    if total_rows == 0:
        return {"success": False, "error": "CSV contains no data rows."}

    # Auto-detect column mappings
    mapping = detect_column_mappings(headers)
    has_dtc_column = bool(mapping.get("dtc_codes"))

    # Prepare preview rows (up to 8 sample rows)
    preview_sample = []
    for r in rows[:8]:
        row_dict = {}
        for h, val in zip(headers, r):
            row_dict[h] = sanitize_csv_cell(val)
        preview_sample.append(row_dict)

    is_ev = (vehicle.fuel_type == "Electric")

    # Save content to secure temporary file for subsequent execution
    token = str(uuid.uuid4())
    temp_path = os.path.join(IMPORT_TEMP_DIR, f"{token}.csv")
    with open(temp_path, "w", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    return {
        "success": True,
        "token": token,
        "filename": secure_filename(filename) or "obd_data.csv",
        "vehicle_id": vehicle.id,
        "vehicle_display": f"{vehicle.registration_number} ({vehicle.make} {vehicle.model})",
        "vehicle_fuel_type": vehicle.fuel_type,
        "is_ev": is_ev,
        "total_rows": total_rows,
        "headers": headers,
        "detected_mapping": mapping,
        "supported_parameters": {
            k: {"label": v["label"], "unit": v.get("unit")}
            for k, v in SUPPORTED_PARAMETERS.items()
        },
        "has_dtc_column": has_dtc_column,
        "has_trailing_comma": has_trailing_comma,
        "preview_rows": preview_sample,
    }


def execute_obd_import(
    token: str,
    vehicle_id: int,
    column_mapping: Dict[str, str],
    custom_notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute validation and database ingestion for a previewed CSV file.
    """
    temp_path = os.path.join(IMPORT_TEMP_DIR, f"{token}.csv")
    if not os.path.exists(temp_path):
        return {
            "success": False,
            "error": "Upload session expired or temporary file not found. Please re-upload your file.",
        }

    vehicle = Vehicle.query.get(vehicle_id)
    if not vehicle:
        return {
            "success": False,
            "error": f"Vehicle ID {vehicle_id} not found.",
        }

    is_ev = (vehicle.fuel_type == "Electric")

    # Read the temporary CSV file
    try:
        with open(temp_path, "r", encoding="utf-8") as f:
            headers, rows, _, error = safe_read_csv(f)
            if error:
                return {"success": False, "error": error}
    except Exception as e:
        return {"success": False, "error": f"Error reading temporary file: {str(e)}"}

    header_indices = {h: idx for idx, h in enumerate(headers)}

    # Existing fingerprints to prevent duplicates against DB
    existing_fps = get_existing_vehicle_fingerprints(vehicle.id)
    file_fps = set()

    accepted_records = []
    rejected_rows = []
    duplicate_count = 0
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    base_session_time = now_utc

    has_dtc_col = bool(column_mapping.get("dtc_codes") and column_mapping["dtc_codes"] in header_indices)

    for row_idx, row in enumerate(rows, start=1):
        row_errors = []
        cleaned_values = {
            "engine_rpm": None,
            "vehicle_speed_kmh": None,
            "coolant_temp_c": None,
            "engine_load_pct": None,
            "throttle_pos_pct": None,
            "battery_voltage": None,
            "fuel_system_status": None,
            "dtc_codes": [],
            "timestamp": None,
        }

        # 1. Parse timestamp
        ts_col = column_mapping.get("timestamp")
        if ts_col and ts_col in header_indices:
            raw_ts = row[header_indices[ts_col]].strip()
            parsed_dt, ts_err = parse_timestamp_value(raw_ts, base_time=base_session_time)
            if ts_err:
                row_errors.append(ts_err)
            else:
                cleaned_values["timestamp"] = parsed_dt

        if cleaned_values["timestamp"] is None:
            # Fallback: sequential UTC timestamp based on import time
            cleaned_values["timestamp"] = now_utc + timedelta(milliseconds=row_idx * 100)

        # 2. Parse numeric parameters
        numeric_specs = [
            ("engine_rpm", 0.0, 15000.0, "RPM"),
            ("vehicle_speed_kmh", 0.0, 400.0, "km/h"),
            ("coolant_temp_c", -40.0, 150.0, "°C"),
            ("engine_load_pct", 0.0, 100.0, "%"),
            ("throttle_pos_pct", 0.0, 100.0, "%"),
            ("battery_voltage", 0.0, 30.0, "V"),
        ]

        has_sensor_data = False
        for param_key, min_val, max_val, unit in numeric_specs:
            col_name = column_mapping.get(param_key)
            if col_name and col_name in header_indices:
                raw_v = row[header_indices[col_name]].strip()
                if raw_v != "":
                    try:
                        val_f = float(raw_v)
                        if val_f < min_val or val_f > max_val:
                            row_errors.append(
                                f"{SUPPORTED_PARAMETERS[param_key]['label']} value {val_f} is out of allowable range [{min_val}, {max_val}] {unit}."
                            )
                        else:
                            cleaned_values[param_key] = round(val_f, 2)
                            has_sensor_data = True
                    except ValueError:
                        row_errors.append(
                            f"Invalid numeric value '{raw_v}' for {SUPPORTED_PARAMETERS[param_key]['label']}."
                        )

        # 3. Fuel system status
        fuel_col = column_mapping.get("fuel_system_status")
        if fuel_col and fuel_col in header_indices:
            raw_fuel = row[header_indices[fuel_col]].strip()
            if raw_fuel:
                cleaned_values["fuel_system_status"] = sanitize_csv_cell(raw_fuel)[:100]
                has_sensor_data = True

        # 4. DTC codes
        dtc_col = column_mapping.get("dtc_codes")
        if dtc_col and dtc_col in header_indices:
            raw_dtc = row[header_indices[dtc_col]].strip()
            if raw_dtc:
                valid_dtcs, dtc_errs = parse_and_validate_dtcs(raw_dtc)
                if dtc_errs:
                    row_errors.extend(dtc_errs)
                else:
                    cleaned_values["dtc_codes"] = valid_dtcs
                    has_sensor_data = True

        # Check if row had any valid sensor information
        if not has_sensor_data:
            row_errors.append("Row contains no mapped sensor telemetry or DTC codes.")

        # If errors encountered in row, record rejection
        if row_errors:
            rejected_rows.append({
                "row_number": row_idx,
                "reasons": row_errors,
                "raw_values": {
                    headers[i]: sanitize_csv_cell(row[i]) for i in range(min(len(headers), len(row)))
                },
            })
            continue

        # 5. Duplicate check using stable fingerprint
        fp = compute_obd_fingerprint(
            vehicle_id=vehicle.id,
            timestamp_val=cleaned_values["timestamp"],
            engine_rpm=cleaned_values["engine_rpm"],
            vehicle_speed_kmh=cleaned_values["vehicle_speed_kmh"],
            coolant_temp_c=cleaned_values["coolant_temp_c"],
            engine_load_pct=cleaned_values["engine_load_pct"],
            throttle_pos_pct=cleaned_values["throttle_pos_pct"],
            battery_voltage=cleaned_values["battery_voltage"],
            fuel_system_status=cleaned_values["fuel_system_status"],
            dtc_codes=cleaned_values["dtc_codes"],
        )

        if fp in existing_fps or fp in file_fps:
            duplicate_count += 1
            continue

        file_fps.add(fp)

        # Build note
        note_parts = []
        if custom_notes:
            note_parts.append(custom_notes.strip())
        if not has_dtc_col:
            note_parts.append("File contains no DTC information; absence of DTCs does not confirm mechanical health.")
        if is_ev and cleaned_values["battery_voltage"] is not None:
            note_parts.append("12V auxiliary reading; does not reflect High-Voltage traction battery SOH/SOC.")
        combined_notes = " | ".join(note_parts) if note_parts else None

        obd_entry = OBDRecord(
            vehicle_id=vehicle.id,
            timestamp=cleaned_values["timestamp"],
            data_source="Imported CSV",
            connection_status="Connected",
            engine_rpm=cleaned_values["engine_rpm"],
            vehicle_speed_kmh=cleaned_values["vehicle_speed_kmh"],
            coolant_temp_c=cleaned_values["coolant_temp_c"],
            engine_load_pct=cleaned_values["engine_load_pct"],
            throttle_pos_pct=cleaned_values["throttle_pos_pct"],
            fuel_system_status=cleaned_values["fuel_system_status"],
            battery_voltage=cleaned_values["battery_voltage"],
            dtc_codes=json.dumps(cleaned_values["dtc_codes"]) if cleaned_values["dtc_codes"] else None,
            notes=combined_notes,
        )
        accepted_records.append(obd_entry)

    # Database commit
    if accepted_records:
        try:
            for rec in accepted_records:
                db.session.add(rec)
            db.session.flush()

            # Recalculate vehicle health and resale scores
            from routes.vehicle_routes import _compute_vehicle_scores
            _compute_vehicle_scores(vehicle)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return {
                "success": False,
                "error": f"Database commit error: {str(e)}",
            }

    # Generate error report if there are rejected rows
    error_report_token = None
    if rejected_rows:
        error_report_token = str(uuid.uuid4())
        error_csv_path = os.path.join(IMPORT_TEMP_DIR, f"err_{error_report_token}.csv")
        try:
            with open(error_csv_path, "w", encoding="utf-8", newline="") as ef:
                ewriter = csv.writer(ef)
                ewriter.writerow(["Row_Number", "Rejection_Reasons", "Raw_Data_Sample"])
                for rej in rejected_rows:
                    ewriter.writerow([
                        rej["row_number"],
                        "; ".join(rej["reasons"]),
                        json.dumps(rej["raw_values"]),
                    ])
        except Exception:
            pass

    # Clean up temporary CSV file
    try:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception:
        pass

    return {
        "success": True,
        "vehicle_id": vehicle.id,
        "vehicle_reg": vehicle.registration_number,
        "total_rows": len(rows),
        "accepted_count": len(accepted_records),
        "duplicate_count": duplicate_count,
        "rejected_count": len(rejected_rows),
        "rejected_sample": rejected_rows[:10],
        "has_dtc_column": has_dtc_col,
        "is_ev": is_ev,
        "error_report_token": error_report_token,
    }

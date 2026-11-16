"""
CAR OS - Service History Dataset Ingestion Service
Handles validation, preview, safe vehicle mapping, deduplication, and
idempotent ingestion of vehicle service records from Excel workbooks.

Maintains complete traceability and prevents duplicate expense counting.
"""
import os
import openpyxl
import pandas as pd
from datetime import date, datetime
from models import db, Vehicle, MaintenanceRecord, ExpenseRecord
from services.health_service import calculate_health_score
from services.valuation_service import calculate_resale_value


EXPECTED_SERVICE_HISTORY_COLUMNS = [
    "Service_Record_ID",
    "Vehicle_ID",
    "Service_Date",
    "Odometer_at_Service_km",
    "Service_Type",
    "Component_or_System",
    "Work_Performed",
    "Service_Cost_INR",
    "Parts_Cost_INR",
    "Labour_Cost_INR",
    "Next_Service_Due_km",
    "Diagnostic_Trouble_Code",
    "Workshop_or_Source",
    "Evidence_Status",
]


def inspect_dataset_workbook(file_path: str) -> dict:
    """
    Inspect the Excel workbook and return metadata, sheet summaries, and data profiles.
    Does not modify the database or source file.
    """
    if not os.path.exists(file_path):
        return {"valid": False, "error": f"File not found: {file_path}"}

    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet_names = wb.sheetnames
        sheets_info = {}

        for name in sheet_names:
            ws = wb[name]
            sheets_info[name] = {
                "max_row": ws.max_row,
                "max_column": ws.max_column,
            }

        # Check Service_History sheet
        has_service_history = "Service_History" in sheet_names
        service_history_summary = {}
        if has_service_history:
            df_sh = pd.read_excel(file_path, sheet_name="Service_History")
            service_history_summary = {
                "total_records": len(df_sh),
                "columns": df_sh.columns.tolist(),
                "vehicle_ids": sorted(df_sh["Vehicle_ID"].dropna().unique().tolist()) if "Vehicle_ID" in df_sh.columns else [],
                "missing_values": {k: int(v) for k, v in df_sh.isnull().sum().items()},
                "service_types": df_sh["Service_Type"].value_counts().to_dict() if "Service_Type" in df_sh.columns else {},
                "evidence_status": df_sh["Evidence_Status"].value_counts().to_dict() if "Evidence_Status" in df_sh.columns else {},
            }

        # Check Vehicle_Profile_Demo sheet
        has_profile_demo = "Vehicle_Profile_Demo" in sheet_names
        profile_demo_vehicles = []
        if has_profile_demo:
            df_vp = pd.read_excel(file_path, sheet_name="Vehicle_Profile_Demo")
            for _, row in df_vp.iterrows():
                profile_demo_vehicles.append({
                    "vehicle_id": str(row.get("Vehicle_ID", "")),
                    "make": str(row.get("Make", "")),
                    "model": str(row.get("Model", "")),
                    "fuel_type": str(row.get("Fuel_Type", "")),
                    "powertrain": str(row.get("Powertrain", "")),
                    "model_year": int(row.get("Model_Year", 0)) if pd.notnull(row.get("Model_Year")) else None,
                    "odometer_km": float(row.get("Odometer_km", 0)) if pd.notnull(row.get("Odometer_km")) else None,
                    "cumulative_repair_cost": float(row.get("Cumulative_Repair_Cost_INR", 0)) if pd.notnull(row.get("Cumulative_Repair_Cost_INR")) else 0,
                    "record_status": str(row.get("Record_Status", "")),
                })

        return {
            "valid": True,
            "sheet_names": sheet_names,
            "sheets_info": sheets_info,
            "has_service_history": has_service_history,
            "service_history_summary": service_history_summary,
            "has_profile_demo": has_profile_demo,
            "profile_demo_vehicles": profile_demo_vehicles,
        }
    except Exception as e:
        return {"valid": False, "error": f"Error parsing workbook: {str(e)}"}


def suggest_candidate_mappings(file_path: str) -> list[dict]:
    """
    Generate non-authoritative candidate mappings between dataset Vehicle_IDs
    and currently registered database vehicles based on Make, Model, and Fuel Type.
    These are suggestions only; human confirmation is mandatory.
    """
    inspection = inspect_dataset_workbook(file_path)
    if not inspection.get("valid"):
        return []

    demo_vehicles = inspection.get("profile_demo_vehicles", [])
    registered_vehicles = Vehicle.query.all()
    candidates = []

    for demo in demo_vehicles:
        d_vid = demo["vehicle_id"]
        d_make = demo["make"].lower().strip()
        d_model = demo["model"].lower().strip()
        d_fuel = demo["fuel_type"].lower().strip()

        matched_vehicle = None
        match_type = "None"

        for reg_v in registered_vehicles:
            r_make = reg_v.make.lower().strip()
            r_model = reg_v.model.lower().strip()
            r_fuel = reg_v.fuel_type.lower().strip()

            # Exact Make and Model match
            if (d_make in r_make or r_make in d_make) and (d_model in r_model or r_model in d_model):
                if d_fuel == r_fuel or (d_fuel == "petrol" and r_fuel == "petrol") or ("ev" in d_model and reg_v.fuel_type == "Electric"):
                    matched_vehicle = reg_v
                    match_type = "High Confidence (Make + Model + Fuel)"
                    break
                elif not matched_vehicle:
                    matched_vehicle = reg_v
                    match_type = "Partial (Make + Model)"

        candidates.append({
            "dataset_vehicle_id": d_vid,
            "dataset_spec": f"{demo['make']} {demo['model']} ({demo['fuel_type']}, {demo['model_year']})",
            "candidate_vehicle_id": matched_vehicle.id if matched_vehicle else None,
            "candidate_registration": matched_vehicle.registration_number if matched_vehicle else None,
            "candidate_spec": f"{matched_vehicle.make} {matched_vehicle.model} ({matched_vehicle.registration_number})" if matched_vehicle else "No match",
            "match_confidence": match_type,
        })

    return candidates


def parse_service_date(date_val) -> date | None:
    """Parse various date formats from Excel (Timestamp, date, or ISO string)."""
    if pd.isnull(date_val):
        return None
    if isinstance(date_val, (datetime, pd.Timestamp)):
        return date_val.date()
    if isinstance(date_val, date):
        return date_val
    try:
        dt = pd.to_datetime(date_val)
        return dt.date()
    except Exception:
        pass
    try:
        return date.fromisoformat(str(date_val).strip())
    except Exception:
        return None


def preview_or_import_service_history(
    file_path: str,
    vehicle_mapping: dict[str, int],
    dry_run: bool = True,
    create_expense_records: bool = False,
) -> dict:
    """
    Preview or execute the ingestion of the Service_History sheet.

    Args:
        file_path: Absolute or relative path to the Excel workbook.
        vehicle_mapping: Dict mapping dataset Vehicle_ID (e.g. 'V001') to target DB Vehicle.id (int).
        dry_run: If True, validates without committing changes to DB.
        create_expense_records: If True, creates linked ExpenseRecord to track expenditure,
                                safely linked via linked_maintenance_id / expense_id to prevent double-counting.

    Returns:
        Summary dict containing inserted, skipped, duplicate, rejected counts and detailed row breakdown.
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"Workbook not found at {file_path}"}

    try:
        df = pd.read_excel(file_path, sheet_name="Service_History")
    except Exception as e:
        return {"success": False, "error": f"Failed reading Service_History sheet: {str(e)}"}

    total_rows = len(df)
    inserted = 0
    skipped = 0
    duplicates = 0
    rejected = 0
    row_reports = []
    affected_vehicle_ids = set()

    for idx, row in df.iterrows():
        record_id = str(row.get("Service_Record_ID", "")).strip()
        dataset_vid = str(row.get("Vehicle_ID", "")).strip()
        service_date_raw = row.get("Service_Date")
        odo_raw = row.get("Odometer_at_Service_km")
        service_type = str(row.get("Service_Type", "Periodic service")).strip()
        component = str(row.get("Component_or_System", "General")).strip()
        work_performed = str(row.get("Work_Performed", "")).strip()
        cost_raw = row.get("Service_Cost_INR", 0)
        parts_cost_raw = row.get("Parts_Cost_INR")
        labour_cost_raw = row.get("Labour_Cost_INR")
        next_odo_raw = row.get("Next_Service_Due_km")
        dtc_raw = row.get("Diagnostic_Trouble_Code")
        workshop = str(row.get("Workshop_or_Source", "Imported")).strip()
        evidence_status = str(row.get("Evidence_Status", "Imported record")).strip()

        # 1. Check vehicle mapping
        target_db_id = vehicle_mapping.get(dataset_vid)
        if not target_db_id:
            skipped += 1
            row_reports.append({
                "source_record_id": record_id,
                "dataset_vehicle_id": dataset_vid,
                "status": "SKIPPED",
                "reason": f"No target database vehicle mapped for dataset ID '{dataset_vid}'.",
            })
            continue

        target_vehicle = Vehicle.query.get(target_db_id)
        if not target_vehicle:
            rejected += 1
            row_reports.append({
                "source_record_id": record_id,
                "dataset_vehicle_id": dataset_vid,
                "status": "REJECTED",
                "reason": f"Target vehicle ID {target_db_id} does not exist in database.",
            })
            continue

        # 2. Check for duplicate imports (Idempotence)
        existing_record = MaintenanceRecord.query.filter_by(
            vehicle_id=target_vehicle.id,
            source_record_id=record_id,
        ).first()
        if existing_record:
            duplicates += 1
            row_reports.append({
                "source_record_id": record_id,
                "dataset_vehicle_id": dataset_vid,
                "target_vehicle": target_vehicle.registration_number,
                "status": "DUPLICATE_SKIPPED",
                "reason": f"Record {record_id} already imported for vehicle {target_vehicle.registration_number} (Record ID: {existing_record.id}).",
            })
            continue

        # 3. Validation
        service_date = parse_service_date(service_date_raw)
        if not service_date:
            rejected += 1
            row_reports.append({
                "source_record_id": record_id,
                "dataset_vehicle_id": dataset_vid,
                "status": "REJECTED",
                "reason": f"Invalid or unparseable service date: '{service_date_raw}'.",
            })
            continue

        try:
            cost = float(cost_raw) if pd.notnull(cost_raw) else 0.0
            if cost < 0:
                raise ValueError("Cost cannot be negative")
        except (ValueError, TypeError):
            rejected += 1
            row_reports.append({
                "source_record_id": record_id,
                "dataset_vehicle_id": dataset_vid,
                "status": "REJECTED",
                "reason": f"Invalid service cost: '{cost_raw}'.",
            })
            continue

        odometer = None
        if pd.notnull(odo_raw):
            try:
                odometer = float(odo_raw)
                if odometer < 0:
                    raise ValueError("Odometer cannot be negative")
            except (ValueError, TypeError):
                rejected += 1
                row_reports.append({
                    "source_record_id": record_id,
                    "dataset_vehicle_id": dataset_vid,
                    "status": "REJECTED",
                    "reason": f"Invalid odometer reading: '{odo_raw}'.",
                })
                continue

        next_odometer = None
        if pd.notnull(next_odo_raw):
            try:
                next_odometer = float(next_odo_raw)
            except (ValueError, TypeError):
                next_odometer = None

        parts_cost = float(parts_cost_raw) if pd.notnull(parts_cost_raw) else None
        labour_cost = float(labour_cost_raw) if pd.notnull(labour_cost_raw) else None
        dtc_code = str(dtc_raw).strip().upper() if pd.notnull(dtc_raw) and str(dtc_raw).strip() != "" and str(dtc_raw).strip().lower() != "nan" else None

        # Determine category mapping for CAR OS
        category_map = {
            "Engine / filters": "Engine",
            "Brakes": "Brakes",
            "Cooling system": "AC & Cooling",
            "Tyres": "Tyres & Wheels",
            "Suspension": "Inspection",
            "Battery / electrical": "Electrical",
            "Transmission": "Transmission",
            "EV inspection": "Inspection",
            "Hybrid system": "Inspection",
        }
        category = category_map.get(component, "Oil & Lubrication" if "periodic" in service_type.lower() else "Maintenance & Repair")

        description = work_performed
        if dtc_code:
            description += f" [Observed DTC: {dtc_code}]"

        # 4. If not dry_run, persist record
        if not dry_run:
            maint_record = MaintenanceRecord(
                vehicle_id=target_vehicle.id,
                service_date=service_date,
                service_category=category,
                component_name=f"{component} ({service_type})",
                odometer_at_service=odometer,
                description=description,
                cost=cost,
                next_service_odometer=next_odometer,
                status="Completed",
                source_record_id=record_id,
                evidence_status=evidence_status,
                workshop=workshop,
                parts_cost=parts_cost,
                labour_cost=labour_cost,
                diagnostic_trouble_code=dtc_code,
            )
            db.session.add(maint_record)
            db.session.flush()  # Obtain maint_record.id

            # Create non-duplicated linked expense if requested
            if create_expense_records and cost > 0:
                expense = ExpenseRecord(
                    vehicle_id=target_vehicle.id,
                    date=service_date,
                    category="Maintenance & Repair",
                    amount=cost,
                    description=f"Auto-logged for service: {maint_record.component_name} [{record_id}]",
                    linked_maintenance_id=maint_record.id,
                )
                db.session.add(expense)
                db.session.flush()
                maint_record.expense_id = expense.id

            affected_vehicle_ids.add(target_vehicle.id)

        inserted += 1
        row_reports.append({
            "source_record_id": record_id,
            "dataset_vehicle_id": dataset_vid,
            "target_vehicle": target_vehicle.registration_number,
            "component": component,
            "cost": cost,
            "status": "READY_TO_INSERT" if dry_run else "INSERTED",
            "service_date": service_date.isoformat(),
        })

    # If executed, commit and update affected vehicle health scores
    if not dry_run and inserted > 0:
        db.session.commit()
        for vid in affected_vehicle_ids:
            v = Vehicle.query.get(vid)
            if v:
                h = calculate_health_score(
                    v.manufacturing_year, v.odometer_km, v.service_history, v.reported_issues, obd_record=v.latest_obd
                )
                v.health_score = h["score"]
                v.health_status = h["status"]
                val = calculate_resale_value(v.make, v.model, v.manufacturing_year, v.odometer_km, h["score"])
                v.estimated_resale_value = float(val["estimated_value"])
        db.session.commit()

    return {
        "success": True,
        "dry_run": dry_run,
        "total_rows": total_rows,
        "inserted": inserted,
        "skipped": skipped,
        "duplicates": duplicates,
        "rejected": rejected,
        "rows": row_reports,
    }

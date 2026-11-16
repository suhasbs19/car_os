"""
Maintenance routes: CRUD for maintenance records and reminders.
"""
from datetime import date
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from models import db, Vehicle, MaintenanceRecord
from services.maintenance_service import classify_maintenance_status

maintenance_bp = Blueprint("maintenance", __name__)

CATEGORIES = [
    "Oil & Lubrication", "Brakes", "Tyres & Wheels", "Engine",
    "Transmission", "Electrical", "AC & Cooling", "Body & Exterior",
    "Inspection", "Insurance", "Other",
]
STATUSES = ["Completed", "Pending", "In Progress", "Cancelled"]


@maintenance_bp.route("/maintenance")
def list_maintenance():
    vehicle_id = request.args.get("vehicle_id", type=int)
    category_filter = request.args.get("category", "").strip()
    status_filter = request.args.get("status", "").strip()

    query = MaintenanceRecord.query
    if vehicle_id:
        query = query.filter_by(vehicle_id=vehicle_id)
    if category_filter:
        query = query.filter_by(service_category=category_filter)
    if status_filter:
        query = query.filter_by(status=status_filter)

    records = query.order_by(MaintenanceRecord.service_date.desc()).all()
    vehicles = Vehicle.query.order_by(Vehicle.make).all()

    from services.maintenance_budget_service import get_model_maintenance_benchmarks, estimate_scheduled_service_budget
    benchmarks = get_model_maintenance_benchmarks()

    # Attach reminder info
    enriched = []
    for r in records:
        vehicle = Vehicle.query.get(r.vehicle_id)
        reminder = classify_maintenance_status(
            r.service_date, r.next_service_date, r.next_service_odometer,
            vehicle.odometer_km if vehicle else 0,
        )
        enriched.append({"record": r, "reminder": reminder, "vehicle": vehicle})

    # Upcoming scheduled service budgets for vehicles
    fleet_scheduled_budgets = []
    vehicles_for_budget = [Vehicle.query.get(vehicle_id)] if vehicle_id else vehicles
    for v in vehicles_for_budget:
        if v:
            b = estimate_scheduled_service_budget(v.make, v.model, v.odometer_km, v.fuel_type or "Petrol")
            b["vehicle"] = v
            fleet_scheduled_budgets.append(b)

    total_recorded_cost = sum(r.cost for r in records)
    completed_count = sum(1 for r in records if r.status == "Completed")
    pending_count = sum(1 for r in records if r.status == "Pending")

    return render_template(
        "maintenance.html",
        enriched=enriched,
        vehicles=vehicles,
        categories=CATEGORIES,
        statuses=STATUSES,
        vehicle_id=vehicle_id,
        category_filter=category_filter,
        status_filter=status_filter,
        benchmarks=benchmarks,
        fleet_scheduled_budgets=fleet_scheduled_budgets,
        total_recorded_cost=total_recorded_cost,
        completed_count=completed_count,
        pending_count=pending_count,
    )


@maintenance_bp.route("/maintenance/add", methods=["GET", "POST"])
def add_maintenance():
    vehicles = Vehicle.query.order_by(Vehicle.make).all()
    if request.method == "POST":
        errors = []
        vehicle_id = request.form.get("vehicle_id", type=int)
        service_date_str = request.form.get("service_date", "")
        category = request.form.get("service_category", "").strip()
        component = request.form.get("component_name", "").strip()
        odo_str = request.form.get("odometer_at_service", "")
        description = request.form.get("description", "").strip()
        cost_str = request.form.get("cost", "0")
        next_date_str = request.form.get("next_service_date", "")
        next_odo_str = request.form.get("next_service_odometer", "")
        status = request.form.get("status", "Completed")

        if not vehicle_id or not Vehicle.query.get(vehicle_id):
            errors.append("Please select a valid vehicle.")
        if not component:
            errors.append("Component/service name is required.")
        if not category:
            errors.append("Category is required.")

        service_date = None
        try:
            service_date = date.fromisoformat(service_date_str)
        except ValueError:
            errors.append("Invalid service date.")

        cost = 0.0
        try:
            cost = float(cost_str)
            if cost < 0:
                errors.append("Cost cannot be negative.")
        except ValueError:
            errors.append("Cost must be a number.")

        odometer = None
        if odo_str:
            try:
                odometer = float(odo_str)
                if odometer < 0:
                    errors.append("Odometer cannot be negative.")
            except ValueError:
                errors.append("Odometer must be a number.")

        next_date = None
        if next_date_str:
            try:
                next_date = date.fromisoformat(next_date_str)
            except ValueError:
                errors.append("Invalid next service date.")

        next_odo = None
        if next_odo_str:
            try:
                next_odo = float(next_odo_str)
            except ValueError:
                errors.append("Next service odometer must be a number.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "add_maintenance.html", vehicles=vehicles, categories=CATEGORIES,
                statuses=STATUSES, form_data=request.form,
            )

        record = MaintenanceRecord(
            vehicle_id=vehicle_id, service_date=service_date,
            service_category=category, component_name=component,
            odometer_at_service=odometer, description=description,
            cost=cost, next_service_date=next_date,
            next_service_odometer=next_odo, status=status,
        )
        db.session.add(record)
        try:
            db.session.commit()
            flash("Maintenance record added.", "success")
            return redirect(url_for("maintenance.list_maintenance", vehicle_id=vehicle_id))
        except Exception as e:
            db.session.rollback()
            flash(f"Database error: {str(e)}", "error")

    preselect = request.args.get("vehicle_id", type=int)
    return render_template(
        "add_maintenance.html", vehicles=vehicles, categories=CATEGORIES,
        statuses=STATUSES, form_data={"vehicle_id": preselect or ""},
    )


@maintenance_bp.route("/maintenance/<int:record_id>/delete", methods=["POST"])
def delete_maintenance(record_id):
    record = MaintenanceRecord.query.get_or_404(record_id)
    vid = record.vehicle_id
    try:
        db.session.delete(record)
        db.session.commit()
        flash("Maintenance record deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {str(e)}", "error")
    return redirect(url_for("maintenance.list_maintenance", vehicle_id=vid))


@maintenance_bp.route("/api/maintenance")
def api_list_maintenance():
    vehicle_id = request.args.get("vehicle_id", type=int)
    query = MaintenanceRecord.query
    if vehicle_id:
        query = query.filter_by(vehicle_id=vehicle_id)
    records = query.order_by(MaintenanceRecord.service_date.desc()).all()
    return jsonify([r.to_dict() for r in records])


# ── Dataset Ingestion Routes ──────────────────────────────────────────────────

@maintenance_bp.route("/maintenance/import", methods=["GET", "POST"])
def import_dataset():
    import os
    from flask import current_app
    from services.dataset_service import (
        inspect_dataset_workbook,
        suggest_candidate_mappings,
        preview_or_import_service_history,
    )

    workbook_path = os.path.join(current_app.root_path, "CAR_OS_Dataset_Service_History_VISIBLE.xlsx")
    inspection = inspect_dataset_workbook(workbook_path)
    candidates = suggest_candidate_mappings(workbook_path)
    registered_vehicles = Vehicle.query.order_by(Vehicle.make, Vehicle.model).all()

    result = None
    if request.method == "POST":
        # Extract vehicle mapping from form
        vehicle_mapping = {}
        for key, val in request.form.items():
            if key.startswith("mapping_") and val.strip():
                dataset_vid = key.replace("mapping_", "").strip()
                try:
                    vehicle_mapping[dataset_vid] = int(val.strip())
                except ValueError:
                    pass

        dry_run = bool(request.form.get("dry_run"))
        create_expenses = bool(request.form.get("create_expense_records"))

        result = preview_or_import_service_history(
            file_path=workbook_path,
            vehicle_mapping=vehicle_mapping,
            dry_run=dry_run,
            create_expense_records=create_expenses,
        )

        if result.get("success"):
            if dry_run:
                flash(
                    f"Dry run complete: {result['inserted']} record(s) ready to insert, "
                    f"{result['duplicates']} duplicate(s), {result['skipped']} skipped.",
                    "info",
                )
            else:
                flash(
                    f"Successfully ingested {result['inserted']} service record(s) "
                    f"({result['duplicates']} duplicate(s) skipped, {result['skipped']} unmapped).",
                    "success",
                )
        else:
            flash(result.get("error", "Import failed."), "error")

    return render_template(
        "import_dataset.html",
        workbook_filename="CAR_OS_Dataset_Service_History_VISIBLE.xlsx",
        inspection=inspection,
        candidates=candidates,
        registered_vehicles=registered_vehicles,
        result=result,
    )


@maintenance_bp.route("/api/dataset/inspect")
def api_dataset_inspect():
    import os
    from flask import current_app
    from services.dataset_service import inspect_dataset_workbook, suggest_candidate_mappings

    workbook_path = os.path.join(current_app.root_path, "CAR_OS_Dataset_Service_History_VISIBLE.xlsx")
    inspection = inspect_dataset_workbook(workbook_path)
    candidates = suggest_candidate_mappings(workbook_path)
    return jsonify({
        "inspection": inspection,
        "candidates": candidates,
    })


@maintenance_bp.route("/api/dataset/import", methods=["POST"])
def api_dataset_import():
    import os
    from flask import current_app
    from services.dataset_service import preview_or_import_service_history

    data = request.get_json() or {}
    workbook_path = os.path.join(current_app.root_path, "CAR_OS_Dataset_Service_History_VISIBLE.xlsx")
    vehicle_mapping = data.get("vehicle_mapping", {})
    dry_run = data.get("dry_run", True)
    create_expenses = data.get("create_expense_records", False)

    result = preview_or_import_service_history(
        file_path=workbook_path,
        vehicle_mapping=vehicle_mapping,
        dry_run=dry_run,
        create_expense_records=create_expenses,
    )
    return jsonify(result)


"""
Analytics routes: dashboard, expenses, valuation, decisions, reports.
"""
import os
import re
from datetime import date, timedelta
from collections import defaultdict
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, send_file
from models import db, Vehicle, MaintenanceRecord, FuelRecord, ExpenseRecord, DiagnosticRecord, OBDRecord
from services.decision_service import generate_decision
from services.valuation_service import VALUATION_DISCLAIMER, format_inr
from services.maintenance_service import get_upcoming_maintenance
from services.obd_import_service import (
    preview_obd_csv,
    execute_obd_import,
    IMPORT_TEMP_DIR,
    SUPPORTED_PARAMETERS,
    MAX_FILE_SIZE_BYTES,
)

analytics_bp = Blueprint("analytics", __name__)

EXPENSE_CATEGORIES = [
    "Fuel",
    "Maintenance/Repair",
    "Insurance",
    "Registration/Tax",
    "Cleaning",
    "Parts",
    "Tyres",
    "Parking & Tolls",
    "Other",
]


# ── Dashboard ────────────────────────────────────────────────────────────────

@analytics_bp.route("/")
@analytics_bp.route("/dashboard")
def dashboard():
    vehicles = Vehicle.query.all()
    total_vehicles = len(vehicles)
    healthy = sum(1 for v in vehicles if v.health_status == "Healthy")
    attention = sum(1 for v in vehicles if v.health_status == "Attention")
    critical = sum(1 for v in vehicles if v.health_status == "Critical")
    avg_health = (
        round(sum(v.health_score for v in vehicles if v.health_score is not None) / total_vehicles, 1)
        if total_vehicles > 0 else 0
    )
    total_resale = sum(v.estimated_resale_value for v in vehicles if v.estimated_resale_value)
    all_expenses = ExpenseRecord.query.all()
    # Exclude maintenance-linked expenses AND fuel-category expenses from standalone expenses to avoid double-counting in fleet TCO
    non_maint_expenses = sum(
        e.amount for e in all_expenses
        if e.linked_maintenance_id is None and e.category not in ["Fuel", "Fuel & Energy", "Charging"]
    )
    total_expenses = sum(e.amount for e in all_expenses)

    all_maint = MaintenanceRecord.query.all()
    total_maint_cost = sum(r.cost for r in all_maint)
    all_fuel = FuelRecord.query.all()
    total_fuel_cost = sum(r.cost for r in all_fuel)
    fleet_tco = total_maint_cost + total_fuel_cost + non_maint_expenses

    # Upcoming/overdue maintenance across all vehicles
    all_upcoming = []
    for v in vehicles:
        maint_records = list(v.maintenance_records.all())
        upcoming = get_upcoming_maintenance(v.id, maint_records, v.odometer_km)
        for u in upcoming:
            u["vehicle"] = v
            all_upcoming.append(u)

    # Recent vehicles
    recent_vehicles = Vehicle.query.order_by(Vehicle.created_at.desc()).limit(5).all()

    # Monthly expense trend (last 6 months)
    monthly_expenses = _monthly_expense_trend(6)

    # Status distribution for chart
    status_distribution = {"Healthy": healthy, "Attention": attention, "Critical": critical}

    # Maintenance cost by category
    maint_cost_by_cat = _maintenance_cost_by_category()

    return render_template(
        "index.html",
        total_vehicles=total_vehicles,
        avg_health=avg_health,
        healthy=healthy,
        attention=attention,
        critical=critical,
        total_resale=total_resale,
        total_expenses=total_expenses,
        non_maint_expenses=non_maint_expenses,
        fleet_tco=fleet_tco,
        all_upcoming=all_upcoming[:5],
        recent_vehicles=recent_vehicles,
        monthly_expenses=monthly_expenses,
        status_distribution=status_distribution,
        maint_cost_by_cat=maint_cost_by_cat,
        format_inr=format_inr,
    )


def _monthly_expense_trend(months: int) -> list:
    today = date.today()
    result = []
    for i in range(months - 1, -1, -1):
        month_date = (today.replace(day=1) - timedelta(days=i * 28)).replace(day=1)
        label = month_date.strftime("%b %Y")
        total = db.session.query(db.func.sum(ExpenseRecord.amount)).filter(
            db.extract("year", ExpenseRecord.date) == month_date.year,
            db.extract("month", ExpenseRecord.date) == month_date.month,
        ).scalar() or 0
        result.append({"month": label, "total": float(total)})
    return result


def _maintenance_cost_by_category() -> dict:
    records = MaintenanceRecord.query.all()
    cats = defaultdict(float)
    for r in records:
        cats[r.service_category] += r.cost
    return dict(cats)


# ── Expenses ─────────────────────────────────────────────────────────────────

@analytics_bp.route("/expenses")
def list_expenses():
    vehicle_id = request.args.get("vehicle_id", type=int)
    category_filter = request.args.get("category", "").strip()
    date_from_str = request.args.get("date_from", "")
    date_to_str = request.args.get("date_to", "")

    query = ExpenseRecord.query
    if vehicle_id:
        query = query.filter_by(vehicle_id=vehicle_id)
    if category_filter:
        query = query.filter_by(category=category_filter)
    if date_from_str:
        try:
            query = query.filter(ExpenseRecord.date >= date.fromisoformat(date_from_str))
        except ValueError:
            pass
    if date_to_str:
        try:
            query = query.filter(ExpenseRecord.date <= date.fromisoformat(date_to_str))
        except ValueError:
            pass

    expenses = query.order_by(ExpenseRecord.date.desc()).all()
    vehicles = Vehicle.query.order_by(Vehicle.make).all()

    # Category totals
    category_totals = defaultdict(float)
    for e in expenses:
        category_totals[e.category] += e.amount
    total = sum(e.amount for e in expenses)

    # Union of configured categories and any existing categories in the DB
    all_categories = sorted(list(set(EXPENSE_CATEGORIES + list(category_totals.keys()))))
    recent_maintenance = MaintenanceRecord.query.order_by(MaintenanceRecord.service_date.desc()).limit(30).all()

    return render_template(
        "expenses.html",
        expenses=expenses,
        vehicles=vehicles,
        categories=all_categories,
        modal_categories=EXPENSE_CATEGORIES,
        category_totals=dict(category_totals),
        total=total,
        vehicle_id=vehicle_id,
        category_filter=category_filter,
        date_from=date_from_str,
        date_to=date_to_str,
        today_iso=date.today().isoformat(),
        recent_maintenance=recent_maintenance,
    )


@analytics_bp.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    vehicles = Vehicle.query.order_by(Vehicle.make).all()
    recent_maintenance = MaintenanceRecord.query.order_by(MaintenanceRecord.service_date.desc()).limit(30).all()
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json

    if request.method == "POST":
        errors = []
        vehicle_id = request.form.get("vehicle_id", type=int)
        date_str = request.form.get("date", "").strip()
        category = request.form.get("category", "").strip()
        amount_str = request.form.get("amount", "").strip()
        description = request.form.get("description", "").strip()
        linked_maint = request.form.get("linked_maintenance_id", type=int)

        vehicle = Vehicle.query.get(vehicle_id) if vehicle_id else None
        if not vehicle_id or not vehicle:
            errors.append("Please select a valid registered vehicle.")
        if not category:
            errors.append("Expense category is required.")

        record_date = None
        if not date_str:
            record_date = date.today()
        else:
            try:
                record_date = date.fromisoformat(date_str)
            except ValueError:
                errors.append("Invalid date format (must be YYYY-MM-DD).")

        amount = 0.0
        try:
            amount = float(amount_str)
            if amount <= 0:
                errors.append("Amount must be greater than zero.")
        except ValueError:
            errors.append("Amount must be a valid number.")

        if linked_maint:
            maint_rec = MaintenanceRecord.query.get(linked_maint)
            if not maint_rec:
                linked_maint = None

        if errors:
            if is_ajax:
                return jsonify({"success": False, "errors": errors}), 400

            for e in errors:
                flash(e, "error")

            from_page = request.form.get("from_page")
            if from_page == "expenses":
                return redirect(url_for("analytics.list_expenses"))

            return render_template(
                "add_expense.html",
                vehicles=vehicles,
                categories=EXPENSE_CATEGORIES,
                recent_maintenance=recent_maintenance,
                form_data=request.form,
                today_iso=date.today().isoformat(),
            )

        expense = ExpenseRecord(
            vehicle_id=vehicle_id,
            date=record_date,
            category=category,
            amount=amount,
            description=description,
            linked_maintenance_id=linked_maint,
        )
        db.session.add(expense)
        try:
            db.session.commit()
            if is_ajax:
                from services.valuation_service import format_inr
                return jsonify({
                    "success": True,
                    "message": "Expense recorded successfully.",
                    "expense": {
                        "id": expense.id,
                        "vehicle_id": expense.vehicle_id,
                        "registration_number": vehicle.registration_number,
                        "vehicle_name": f"{vehicle.make} {vehicle.model}",
                        "date": expense.date.isoformat(),
                        "category": expense.category,
                        "amount": expense.amount,
                        "amount_formatted": format_inr(expense.amount),
                        "description": expense.description or "—",
                        "linked_maintenance_id": expense.linked_maintenance_id,
                    }
                }), 201

            flash("Expense recorded successfully.", "success")
            return redirect(url_for("analytics.list_expenses", vehicle_id=vehicle_id))
        except Exception as e:
            db.session.rollback()
            if is_ajax:
                return jsonify({"success": False, "errors": [f"Database error: {str(e)}"]}), 500
            flash(f"Database error: {str(e)}", "error")

    preselect = request.args.get("vehicle_id", type=int)
    return render_template(
        "add_expense.html",
        vehicles=vehicles,
        categories=EXPENSE_CATEGORIES,
        recent_maintenance=recent_maintenance,
        form_data={"vehicle_id": preselect or ""},
        today_iso=date.today().isoformat(),
    )


@analytics_bp.route("/expenses/<int:expense_id>/delete", methods=["POST"])
def delete_expense(expense_id):
    expense = ExpenseRecord.query.get_or_404(expense_id)
    vid = expense.vehicle_id
    try:
        db.session.delete(expense)
        db.session.commit()
        flash("Expense deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {str(e)}", "error")
    return redirect(url_for("analytics.list_expenses", vehicle_id=vid))


# ── Valuation ────────────────────────────────────────────────────────────────

@analytics_bp.route("/valuation")
def valuation():
    vehicles = Vehicle.query.all()
    from services.valuation_service import calculate_resale_value
    valuations = []
    has_changes = False
    for v in vehicles:
        health = v.health_score if v.health_score is not None else 80.0
        user_sp = v.original_showroom_price if (v.showroom_price_source == "User-Entered" and v.original_showroom_price and v.original_showroom_price > 0) else None

        val = calculate_resale_value(
            v.make, v.model, v.manufacturing_year, v.odometer_km, health,
            fuel_type=v.fuel_type or "Petrol",
            transmission=v.transmission or "Manual",
            variant=v.variant,
            service_history=v.service_history,
            reported_issues=v.reported_issues,
            engine="auto",
            original_showroom_price=user_sp,
        )
        val["vehicle"] = v
        valuations.append(val)

        # Resolve verified showroom price vs unverified / missing
        if user_sp is not None:
            resolved_sp = user_sp
            sp_source = "User-Entered"
            sp_verified = False
            sp_notes = v.showroom_price_notes or "User-Entered Showroom Price"
        else:
            sh_detail = val.get("showroom_detail", {})
            if sh_detail.get("is_exact_match"):
                resolved_sp = val.get("original_showroom_price")
                sp_source = sh_detail.get("source", "Verified Catalog")
                sp_verified = True
                sp_notes = sh_detail.get("status_label")
            else:
                resolved_sp = None
                sp_source = None
                sp_verified = False
                sp_notes = None

        if (
            v.estimated_resale_value != val["estimated_value"]
            or v.original_showroom_price != resolved_sp
            or v.current_market_price != val.get("current_market_price")
            or v.showroom_price_verified != sp_verified
        ):
            v.estimated_resale_value = val["estimated_value"]
            v.original_showroom_price = resolved_sp
            v.showroom_price_source = sp_source
            v.showroom_price_verified = sp_verified
            v.showroom_price_notes = sp_notes
            v.current_market_price = val.get("current_market_price")
            has_changes = True

    if has_changes:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    total_fleet_value = sum(d["estimated_value"] for d in valuations)
    total_showroom_value = sum(d.get("original_showroom_price") or 0 for d in valuations)
    total_market_value = sum(d.get("current_market_price") or 0 for d in valuations)

    return render_template(
        "valuation.html",
        valuations=valuations,
        total_fleet_value=total_fleet_value,
        total_showroom_value=total_showroom_value,
        total_market_value=total_market_value,
        valuation_disclaimer=VALUATION_DISCLAIMER,
        format_inr=format_inr,
    )


@analytics_bp.route("/api/vehicles/<int:vehicle_id>/valuation")
def api_vehicle_valuation(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    from services.valuation_service import calculate_resale_value
    val = calculate_resale_value(
        vehicle.make,
        vehicle.model,
        vehicle.manufacturing_year,
        vehicle.odometer_km,
        vehicle.health_score if vehicle.health_score is not None else 80.0,
        fuel_type=vehicle.fuel_type or "Petrol",
        transmission=vehicle.transmission or "Manual",
        variant=vehicle.variant,
        service_history=vehicle.service_history,
        reported_issues=vehicle.reported_issues,
        engine="auto",
        original_showroom_price=vehicle.original_showroom_price,
    )
    return jsonify({
        "vehicle_id": vehicle.id,
        "registration_number": vehicle.registration_number,
        "make": vehicle.make,
        "model": vehicle.model,
        "variant": vehicle.variant,
        "transmission": vehicle.transmission,
        "manufacturing_year": vehicle.manufacturing_year,
        "odometer_km": vehicle.odometer_km,
        "original_showroom_price": val.get("original_showroom_price"),
        "original_showroom_price_formatted": format_inr(val.get("original_showroom_price")) if val.get("original_showroom_price") else "Price unavailable",
        "showroom_price_source": vehicle.showroom_price_source,
        "showroom_price_verified": bool(vehicle.showroom_price_verified) if vehicle.showroom_price_verified is not None else False,
        "showroom_price_notes": vehicle.showroom_price_notes,
        "reference_starting_price": val.get("showroom_detail", {}).get("reference_starting_price"),
        "current_market_price": val.get("current_market_price"),
        "current_market_price_formatted": format_inr(val.get("current_market_price")) if val.get("current_market_price") else "N/A",
        "market_asking_range": val.get("market_asking_range"),
        "comparable_listings_count": val.get("comparable_listings_count", 0),
        "estimated_resale_value": val["estimated_value"],
        "estimated_resale_value_formatted": format_inr(val["estimated_value"]),
        "depreciation_amount": val.get("depreciation_amount"),
        "depreciation_percentage": val.get("depreciation_percentage"),
        "valuation_method": val.get("valuation_method"),
        "confidence_status": val.get("confidence_status"),
        "valuation_source": val.get("valuation_source"),
        "status_label": val.get("status_label"),
        "factors": val.get("factors"),
    })


# ── Maintain–Repair–Sell ─────────────────────────────────────────────────────

@analytics_bp.route("/decisions")
def decisions():
    vehicles = Vehicle.query.all()
    results = []
    for v in vehicles:
        decision = generate_decision(
            v,
            v.maintenance_records,
            v.expense_records,
            v.fuel_records,
        )
        results.append({"vehicle": v, "decision": decision})

    return render_template("decisions.html", results=results)


@analytics_bp.route("/decisions/<int:vehicle_id>")
def vehicle_decision(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    decision = generate_decision(
        vehicle,
        vehicle.maintenance_records,
        vehicle.expense_records,
        vehicle.fuel_records,
    )
    return render_template("decision_detail.html", vehicle=vehicle, decision=decision)


# ── Diagnostics ──────────────────────────────────────────────────────────────

@analytics_bp.route("/diagnostics")
def diagnostics():
    vehicle_id = request.args.get("vehicle_id", type=int)
    diag_query = DiagnosticRecord.query
    obd_query = OBDRecord.query
    if vehicle_id:
        diag_query = diag_query.filter_by(vehicle_id=vehicle_id)
        obd_query = obd_query.filter_by(vehicle_id=vehicle_id)
    records = diag_query.order_by(DiagnosticRecord.date.desc()).all()
    obd_records = obd_query.order_by(OBDRecord.timestamp.desc()).all()
    vehicles = Vehicle.query.order_by(Vehicle.make, Vehicle.model).all()
    return render_template(
        "diagnostics.html",
        records=records,
        obd_records=obd_records,
        vehicles=vehicles,
        vehicle_id=vehicle_id,
    )


@analytics_bp.route("/diagnostics/add", methods=["GET", "POST"])
def add_diagnostic():
    vehicles = Vehicle.query.order_by(Vehicle.make).all()
    if request.method == "POST":
        errors = []
        vehicle_id = request.form.get("vehicle_id", type=int)
        date_str = request.form.get("date", "")
        data_source = request.form.get("data_source", "Manual").strip()
        dtc_code = request.form.get("dtc_code", "").strip() or None
        param_name = request.form.get("parameter_name", "").strip() or None
        param_value = request.form.get("parameter_value", "").strip() or None
        notes = request.form.get("notes", "").strip()

        if not vehicle_id or not Vehicle.query.get(vehicle_id):
            errors.append("Please select a valid vehicle.")

        record_date = None
        try:
            record_date = date.fromisoformat(date_str)
        except ValueError:
            errors.append("Invalid date.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("add_diagnostic.html", vehicles=vehicles, form_data=request.form)

        record = DiagnosticRecord(
            vehicle_id=vehicle_id, date=record_date,
            data_source=data_source, dtc_code=dtc_code,
            parameter_name=param_name, parameter_value=param_value,
            notes=notes,
        )
        db.session.add(record)
        try:
            db.session.commit()
            flash("Diagnostic record added.", "success")
            return redirect(url_for("analytics.diagnostics", vehicle_id=vehicle_id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {str(e)}", "error")

    preselect = request.args.get("vehicle_id", type=int)
    return render_template(
        "add_diagnostic.html", vehicles=vehicles,
        form_data={"vehicle_id": preselect or ""},
    )


@analytics_bp.route("/diagnostics/import", methods=["GET"])
def import_obd():
    """Step 1: Upload CSV file and select target vehicle."""
    vehicle_id = request.args.get("vehicle_id", type=int)
    vehicles = Vehicle.query.order_by(Vehicle.make, Vehicle.model).all()
    return render_template(
        "import_obd.html",
        vehicles=vehicles,
        vehicle_id=vehicle_id,
        step=1,
    )


@analytics_bp.route("/diagnostics/import/preview", methods=["POST"])
def import_obd_preview():
    """Step 2: Inspect uploaded CSV, validate size/structure, and preview mappings."""
    vehicles = Vehicle.query.order_by(Vehicle.make, Vehicle.model).all()
    vehicle_id_str = request.form.get("vehicle_id")
    if not vehicle_id_str:
        flash("Please select a target vehicle.", "error")
        return redirect(url_for("analytics.import_obd"))

    try:
        vehicle_id = int(vehicle_id_str)
    except ValueError:
        flash("Invalid vehicle selected.", "error")
        return redirect(url_for("analytics.import_obd"))

    if not Vehicle.query.get(vehicle_id):
        flash("Selected vehicle does not exist.", "error")
        return redirect(url_for("analytics.import_obd"))

    if "csv_file" not in request.files:
        flash("Please upload a CSV file.", "error")
        return redirect(url_for("analytics.import_obd", vehicle_id=vehicle_id))

    file = request.files["csv_file"]
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for("analytics.import_obd", vehicle_id=vehicle_id))

    if not file.filename.lower().endswith(".csv"):
        flash("Only .csv files are supported for OBD telemetry import.", "error")
        return redirect(url_for("analytics.import_obd", vehicle_id=vehicle_id))

    content = file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        flash(f"File size exceeds safe limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB.", "error")
        return redirect(url_for("analytics.import_obd", vehicle_id=vehicle_id))

    preview_res = preview_obd_csv(content, file.filename, vehicle_id)
    if not preview_res.get("success"):
        flash(preview_res.get("error", "Error parsing CSV file."), "error")
        return redirect(url_for("analytics.import_obd", vehicle_id=vehicle_id))

    return render_template(
        "import_obd.html",
        vehicles=vehicles,
        vehicle_id=vehicle_id,
        preview=preview_res,
        step=2,
    )


@analytics_bp.route("/diagnostics/import/execute", methods=["POST"])
def import_obd_execute():
    """Step 3: Validate and commit mapped OBD telemetry rows."""
    token = request.form.get("token", "").strip()
    vehicle_id_str = request.form.get("vehicle_id")
    custom_notes = request.form.get("custom_notes", "").strip()

    if not token or not vehicle_id_str:
        flash("Session expired or missing vehicle reference.", "error")
        return redirect(url_for("analytics.import_obd"))

    try:
        vehicle_id = int(vehicle_id_str)
    except ValueError:
        flash("Invalid vehicle ID.", "error")
        return redirect(url_for("analytics.import_obd"))

    column_mapping = {}
    for param_key in SUPPORTED_PARAMETERS:
        val = request.form.get(f"mapping_{param_key}", "").strip()
        if val:
            column_mapping[param_key] = val

    result = execute_obd_import(
        token=token,
        vehicle_id=vehicle_id,
        column_mapping=column_mapping,
        custom_notes=custom_notes,
    )

    if not result.get("success"):
        flash(result.get("error", "Error during ingestion."), "error")
        return redirect(url_for("analytics.import_obd", vehicle_id=vehicle_id))

    accepted = result.get("accepted_count", 0)
    duplicates = result.get("duplicate_count", 0)
    rejected = result.get("rejected_count", 0)

    flash_msg = f"OBD import finished: {accepted} row(s) accepted, {duplicates} duplicate(s) prevented, {rejected} rejected."
    flash_type = "success" if accepted > 0 else "attention"
    flash(flash_msg, flash_type)

    return render_template(
        "import_obd.html",
        result=result,
        vehicle_id=vehicle_id,
        step=3,
    )


@analytics_bp.route("/diagnostics/import/errors/<token>")
def download_import_errors(token):
    """Download rejection details report as CSV."""
    safe_token = re.sub(r"[^a-zA-Z0-9_\-]", "", token)
    error_csv_path = os.path.join(IMPORT_TEMP_DIR, f"err_{safe_token}.csv")
    if not os.path.exists(error_csv_path):
        flash("Error report has expired or does not exist.", "error")
        return redirect(url_for("analytics.diagnostics"))
    return send_file(
        error_csv_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name="obd_import_rejections.csv",
    )


# ── Reports ──────────────────────────────────────────────────────────────────

@analytics_bp.route("/reports")
def reports():
    vehicles = Vehicle.query.all()
    # Aggregate stats per vehicle
    vehicle_reports = []
    for v in vehicles:
        maint = list(v.maintenance_records.all())
        fuel = list(v.fuel_records.all())
        expenses = list(v.expense_records.all())
        total_maint_cost = sum(r.cost for r in maint)
        total_fuel_cost = sum(r.cost for r in fuel)
        # Deduplication audit:
        # non_maint_expenses contains only standalone operational expenses (Insurance, Tolls, Tax, Accessories),
        # strictly excluding expense records that were auto-created from maintenance records.
        non_maint_expenses = sum(e.amount for e in expenses if e.linked_maintenance_id is None)
        linked_maint_expenses = sum(e.amount for e in expenses if e.linked_maintenance_id is not None)
        gross_expenses = sum(e.amount for e in expenses)
        total_tco = total_maint_cost + total_fuel_cost + non_maint_expenses
        total_dist = sum(r.distance_km for r in fuel)
        vehicle_reports.append({
            "vehicle": v,
            "maint_count": len(maint),
            "total_maint_cost": total_maint_cost,
            "fuel_records": len(fuel),
            "total_fuel_cost": total_fuel_cost,
            "total_expense": non_maint_expenses,           # Deduplicated standalone expenses
            "gross_expenses": gross_expenses,              # Total raw expense records
            "linked_maint_expenses": linked_maint_expenses,
            "total_tco": total_tco,                        # True Total Cost of Ownership
            "total_distance_km": round(total_dist, 1),
            "cost_per_km": round((total_maint_cost + total_fuel_cost) / total_dist, 2)
            if total_dist > 0 else None,
            "tco_per_km": round(total_tco / total_dist, 2) if total_dist > 0 else None,
        })
    return render_template("reports.html", vehicle_reports=vehicle_reports, format_inr=format_inr)


# ── Dashboard API ────────────────────────────────────────────────────────────

@analytics_bp.route("/api/dashboard")
def api_dashboard():
    vehicles = Vehicle.query.all()
    total = len(vehicles)
    healthy = sum(1 for v in vehicles if v.health_status == "Healthy")
    attention = sum(1 for v in vehicles if v.health_status == "Attention")
    critical = sum(1 for v in vehicles if v.health_status == "Critical")
    avg_health = (
        sum(v.health_score for v in vehicles if v.health_score is not None) / total
        if total > 0 else 0
    )
    total_resale = sum(v.estimated_resale_value or 0 for v in vehicles)
    all_expenses = ExpenseRecord.query.all()
    total_expenses = sum(e.amount for e in all_expenses)
    non_maint_expenses = sum(e.amount for e in all_expenses if e.linked_maintenance_id is None)
    all_maint = MaintenanceRecord.query.all()
    total_maint_cost = sum(r.cost for r in all_maint)
    all_fuel = FuelRecord.query.all()
    total_fuel_cost = sum(r.cost for r in all_fuel)
    fleet_tco = total_maint_cost + total_fuel_cost + non_maint_expenses

    return jsonify({
        "total_vehicles": total,
        "avg_health": round(avg_health, 1),
        "healthy": healthy,
        "attention": attention,
        "critical": critical,
        "total_resale_value": total_resale,
        "total_expenses": float(total_expenses),
        "non_maint_expenses": float(non_maint_expenses),
        "total_maint_cost": float(total_maint_cost),
        "total_tco": float(fleet_tco),
        "monthly_expenses": _monthly_expense_trend(6),
        "status_distribution": {"Healthy": healthy, "Attention": attention, "Critical": critical},
        "maintenance_cost_by_category": _maintenance_cost_by_category(),
    })


@analytics_bp.route("/api/ml/status")
def api_ml_status():
    from ml.predict import get_ml_model_status
    return jsonify(get_ml_model_status())


@analytics_bp.route("/api/reports")
def api_reports():
    vehicles = Vehicle.query.all()
    reports_data = []
    for v in vehicles:
        maint = list(v.maintenance_records.all())
        fuel = list(v.fuel_records.all())
        expenses = list(v.expense_records.all())
        total_maint_cost = sum(r.cost for r in maint)
        total_fuel_cost = sum(r.cost for r in fuel)
        non_maint_expenses = sum(e.amount for e in expenses if e.linked_maintenance_id is None)
        linked_maint_expenses = sum(e.amount for e in expenses if e.linked_maintenance_id is not None)
        gross_expenses = sum(e.amount for e in expenses)
        total_tco = total_maint_cost + total_fuel_cost + non_maint_expenses
        total_dist = sum(r.distance_km for r in fuel)
        reports_data.append({
            "vehicle_id": v.id,
            "registration_number": v.registration_number,
            "make": v.make,
            "model": v.model,
            "maint_count": len(maint),
            "total_maint_cost": total_maint_cost,
            "fuel_records_count": len(fuel),
            "total_fuel_cost": total_fuel_cost,
            "total_expenses": non_maint_expenses,        # Deduplicated standalone operational expenses
            "gross_expenses": gross_expenses,           # Raw expense table sum
            "linked_maint_expenses": linked_maint_expenses,
            "total_tco": total_tco,                     # True Total Cost of Ownership
            "total_distance_km": round(total_dist, 1),
            "cost_per_km": round((total_maint_cost + total_fuel_cost) / total_dist, 2) if total_dist > 0 else None,
            "tco_per_km": round(total_tco / total_dist, 2) if total_dist > 0 else None,
        })
    return jsonify(reports_data)

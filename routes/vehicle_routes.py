"""
Vehicle routes: CRUD operations for vehicle management.
"""
from datetime import date, datetime, timezone
import json
import re
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from models import db, Vehicle, OBDRecord
from services.health_service import calculate_health_score
from services.valuation_service import calculate_resale_value
from services.obd_service import validate_obd_data, analyze_obd_record
from services.vehicle_catalogue_service import search_vehicle_catalogue, get_vehicle_catalogue

vehicle_bp = Blueprint("vehicles", __name__)

CURRENT_YEAR = date.today().year
FUEL_TYPES = ["Petrol", "Diesel", "CNG", "Hybrid", "Electric"]
SERVICE_HISTORY_OPTIONS = ["Full", "Partial", "None", "Unknown"]


def _validate_registration(reg: str) -> bool:
    """Basic registration number validation (non-empty, alphanumeric/dash)."""
    if not reg:
        return False
    return bool(re.match(r"^[A-Za-z0-9\-\s]{2,20}$", reg.strip()))


def _compute_vehicle_scores(vehicle: Vehicle) -> None:
    """Recalculate and persist health score and realistic multi-tier valuation."""
    health = calculate_health_score(
        vehicle.manufacturing_year,
        vehicle.odometer_km,
        vehicle.service_history,
        vehicle.reported_issues,
        obd_record=vehicle.latest_obd,
    )
    vehicle.health_score = health["score"]
    vehicle.health_status = health["status"]

    # Preserve user-entered showroom price if explicitly provided by user
    user_sp = vehicle.original_showroom_price if (
        vehicle.original_showroom_price and vehicle.original_showroom_price > 0 and not vehicle.showroom_price_verified
    ) else None

    valuation = calculate_resale_value(
        vehicle.make,
        vehicle.model,
        vehicle.manufacturing_year,
        vehicle.odometer_km,
        health["score"],
        fuel_type=vehicle.fuel_type or "Petrol",
        transmission=vehicle.transmission or "Manual",
        engine="auto",
        variant=vehicle.variant,
        service_history=vehicle.service_history,
        reported_issues=vehicle.reported_issues,
        original_showroom_price=user_sp,
    )

    if user_sp is not None:
        vehicle.original_showroom_price = user_sp
        vehicle.showroom_price_source = vehicle.showroom_price_source or "User-Entered"
        vehicle.showroom_price_verified = False
        vehicle.showroom_price_notes = vehicle.showroom_price_notes or "User-Entered Showroom Price"
    else:
        sh_detail = valuation.get("showroom_detail", {})
        if sh_detail.get("is_exact_match"):
            vehicle.original_showroom_price = valuation.get("original_showroom_price")
            vehicle.showroom_price_source = sh_detail.get("source", "Verified Catalog")
            vehicle.showroom_price_verified = True
            vehicle.showroom_price_notes = sh_detail.get("status_label")
        else:
            vehicle.original_showroom_price = None
            vehicle.showroom_price_source = None
            vehicle.showroom_price_verified = False
            vehicle.showroom_price_notes = None

    vehicle.current_market_price = valuation.get("current_market_price")
    vehicle.estimated_resale_value = valuation["estimated_value"]

    # Record in ValuationRecord history
    from models.vehicle_models import ValuationRecord
    rec = ValuationRecord(
        vehicle_id=vehicle.id,
        original_showroom_price=valuation.get("original_showroom_price"),
        market_asking_price_min=valuation.get("market_asking_range", (None, None))[0] if valuation.get("market_asking_range") else None,
        market_asking_price_max=valuation.get("market_asking_range", (None, None))[1] if valuation.get("market_asking_range") else None,
        representative_market_price=valuation.get("current_market_price"),
        comparable_listings_count=valuation.get("comparable_listings_count", 0),
        estimated_resale_value=valuation["estimated_value"],
        depreciation_amount=valuation.get("depreciation_amount"),
        depreciation_percentage=valuation.get("depreciation_percentage"),
        valuation_method=valuation.get("valuation_method", "model-based"),
        valuation_source=valuation.get("valuation_source"),
        confidence_status=valuation.get("confidence_status"),
        notes=valuation.get("fallback_reason") or valuation.get("status_label"),
        input_snapshot=json.dumps(valuation.get("valuation_inputs", {})),
    )
    db.session.add(rec)


# ── Page routes ─────────────────────────────────────────────────────────────

@vehicle_bp.route("/vehicles")
def list_vehicles():
    query = Vehicle.query
    search = request.args.get("search", "").strip()
    fuel_filter = request.args.get("fuel_type", "").strip()
    status_filter = request.args.get("status", "").strip()

    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                Vehicle.make.ilike(like),
                Vehicle.model.ilike(like),
                Vehicle.registration_number.ilike(like),
            )
        )
    if fuel_filter:
        query = query.filter(Vehicle.fuel_type == fuel_filter)
    if status_filter:
        query = query.filter(Vehicle.health_status == status_filter)

    vehicles = query.order_by(Vehicle.created_at.desc()).all()
    return render_template(
        "vehicles.html",
        vehicles=vehicles,
        search=search,
        fuel_filter=fuel_filter,
        status_filter=status_filter,
        fuel_types=FUEL_TYPES,
    )


@vehicle_bp.route("/vehicles/add", methods=["GET", "POST"])
def add_vehicle():
    if request.method == "POST":
        errors = []
        make = request.form.get("make", "").strip()
        model = request.form.get("model", "").strip()
        reg = request.form.get("registration_number", "").strip().upper()
        year_str = request.form.get("manufacturing_year", "")
        odo_str = request.form.get("odometer_km", "0")
        fuel_type = request.form.get("fuel_type", "Petrol")
        variant = request.form.get("variant", "").strip() or None
        transmission = request.form.get("transmission", "Manual").strip()
        if transmission not in ["Manual", "Automatic"]:
            transmission = "Manual"
        service_history = request.form.get("service_history", "Unknown")
        issues_str = request.form.get("reported_issues", "0")
        notes = request.form.get("notes", "").strip()
        user_sp_str = request.form.get("original_showroom_price", "").strip()
        user_sp_source = request.form.get("showroom_price_source", "").strip()
        user_sp_notes = request.form.get("showroom_price_notes", "").strip()
        user_sp = None
        if user_sp_str:
            try:
                val_sp = float(user_sp_str)
                if val_sp > 0:
                    user_sp = val_sp
                else:
                    errors.append("Original showroom price must be greater than zero.")
            except ValueError:
                errors.append("Original showroom price must be a valid number.")

        if not make:
            errors.append("Make is required.")
        if not model:
            errors.append("Model is required.")
        if not _validate_registration(reg):
            errors.append("Registration number must be 2–20 alphanumeric characters.")

        try:
            year = int(year_str)
            if year < 1900 or year > CURRENT_YEAR:
                errors.append(f"Manufacturing year must be between 1900 and {CURRENT_YEAR}.")
        except ValueError:
            errors.append("Manufacturing year must be a valid integer.")
            year = CURRENT_YEAR

        try:
            odometer = float(odo_str)
            if odometer < 0:
                errors.append("Odometer cannot be negative.")
        except ValueError:
            errors.append("Odometer must be a number.")
            odometer = 0.0

        try:
            issues = int(issues_str)
            if issues < 0:
                errors.append("Reported issues cannot be negative.")
        except ValueError:
            errors.append("Reported issues must be an integer.")
            issues = 0

        if fuel_type not in FUEL_TYPES:
            errors.append("Invalid fuel type.")
        if service_history not in SERVICE_HISTORY_OPTIONS:
            errors.append("Invalid service history value.")

        # Duplicate check
        if not errors and Vehicle.query.filter_by(registration_number=reg).first():
            errors.append(f"A vehicle with registration '{reg}' already exists.")

        # Validate optional OBD-II diagnostic data
        has_obd, cleaned_obd, obd_errors = validate_obd_data(request.form)
        if obd_errors:
            errors.extend(obd_errors)

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "add_vehicle.html",
                fuel_types=FUEL_TYPES,
                service_history_options=SERVICE_HISTORY_OPTIONS,
                current_year=CURRENT_YEAR,
                form_data=request.form,
            )

        vehicle = Vehicle(
            make=make, model=model, registration_number=reg,
            manufacturing_year=year, odometer_km=odometer,
            fuel_type=fuel_type, variant=variant, transmission=transmission,
            service_history=service_history,
            reported_issues=issues, notes=notes,
            original_showroom_price=user_sp,
            showroom_price_source=user_sp_source or ("User-Entered" if user_sp else None),
            showroom_price_notes=user_sp_notes,
            showroom_price_verified=False if user_sp else False,
        )
        db.session.add(vehicle)
        db.session.flush()

        if has_obd:
            obd_rec = OBDRecord(
                vehicle_id=vehicle.id,
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                data_source=cleaned_obd["data_source"],
                connection_status=cleaned_obd["connection_status"],
                engine_rpm=cleaned_obd["engine_rpm"],
                vehicle_speed_kmh=cleaned_obd["vehicle_speed_kmh"],
                coolant_temp_c=cleaned_obd["coolant_temp_c"],
                engine_load_pct=cleaned_obd["engine_load_pct"],
                throttle_pos_pct=cleaned_obd["throttle_pos_pct"],
                fuel_system_status=cleaned_obd["fuel_system_status"],
                battery_voltage=cleaned_obd["battery_voltage"],
                dtc_codes=json.dumps(cleaned_obd["dtc_codes"]) if cleaned_obd["dtc_codes"] else None,
                notes=cleaned_obd["notes"],
            )
            db.session.add(obd_rec)
            db.session.flush()

        _compute_vehicle_scores(vehicle)

        try:
            db.session.commit()
            flash(f"Vehicle {reg} added successfully!", "success")
            return redirect(url_for("vehicles.vehicle_detail", vehicle_id=vehicle.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Database error: {str(e)}", "error")

    return render_template(
        "add_vehicle.html",
        fuel_types=FUEL_TYPES,
        service_history_options=SERVICE_HISTORY_OPTIONS,
        current_year=CURRENT_YEAR,
        form_data={},
    )


@vehicle_bp.route("/vehicles/<int:vehicle_id>")
def vehicle_detail(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    from services.health_service import HEALTH_DISCLAIMER
    from services.valuation_service import VALUATION_DISCLAIMER, calculate_resale_value
    from services.maintenance_service import get_upcoming_maintenance, calculate_maintenance_stats

    latest_obd = vehicle.latest_obd
    obd_analysis = analyze_obd_record(latest_obd)

    maint_records = list(vehicle.maintenance_records.order_by("service_date").all())
    upcoming = get_upcoming_maintenance(vehicle_id, maint_records, vehicle.odometer_km, obd_record=latest_obd)
    maint_stats = calculate_maintenance_stats(maint_records)

    fuel_records = list(vehicle.fuel_records.order_by("date").all())
    from services.fuel_service import aggregate_fuel_records
    fuel_stats = aggregate_fuel_records(fuel_records, vehicle.fuel_type)

    from services.showroom_price_service import get_starting_price_reference
    reference_starting_price = get_starting_price_reference(vehicle.make, vehicle.model)

    passed_sp = vehicle.original_showroom_price if vehicle.original_showroom_price and vehicle.original_showroom_price > 0 else None

    valuation_detail = calculate_resale_value(
        vehicle.make, vehicle.model, vehicle.manufacturing_year,
        vehicle.odometer_km, vehicle.health_score if vehicle.health_score is not None else 80.0,
        fuel_type=vehicle.fuel_type,
        transmission=vehicle.transmission or "Manual",
        engine="auto",
        variant=vehicle.variant,
        service_history=vehicle.service_history,
        reported_issues=vehicle.reported_issues,
        original_showroom_price=passed_sp,
    )
    from models.vehicle_models import ValuationRecord
    valuation_history = vehicle.valuation_records.order_by(ValuationRecord.valuation_date.desc()).limit(10).all()

    from services.maintenance_budget_service import estimate_scheduled_service_budget
    scheduled_budget = estimate_scheduled_service_budget(
        vehicle.make, vehicle.model, vehicle.odometer_km, vehicle.fuel_type
    )

    expense_records = list(vehicle.expense_records.order_by("date").all())
    total_expenses = sum(e.amount for e in expense_records)

    return render_template(
        "vehicle_detail.html",
        vehicle=vehicle,
        maint_records=maint_records,
        upcoming=upcoming,
        maint_stats=maint_stats,
        fuel_stats=fuel_stats,
        valuation_detail=valuation_detail,
        valuation_history=valuation_history,
        scheduled_budget=scheduled_budget,
        expense_records=expense_records,
        total_expenses=total_expenses,
        latest_obd=latest_obd,
        obd_analysis=obd_analysis,
        health_disclaimer=HEALTH_DISCLAIMER,
        valuation_disclaimer=VALUATION_DISCLAIMER,
        reference_starting_price=reference_starting_price,
    )


@vehicle_bp.route("/vehicles/<int:vehicle_id>/update-showroom-price", methods=["POST"])
def update_showroom_price(vehicle_id):
    """Handle manual entry/update of original ex-showroom price with user provenance."""
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    price_str = request.form.get("showroom_price", "").strip()
    source_str = request.form.get("showroom_price_source", "").strip()
    notes_str = request.form.get("showroom_price_notes", "").strip()

    if not price_str:
        flash("Please enter a valid original showroom price in INR.", "error")
        return redirect(url_for("vehicles.vehicle_detail", vehicle_id=vehicle.id))

    try:
        price = float(price_str)
        if price < 10000 or price > 200000000:
            flash("Showroom price must be between ₹10,000 and ₹20 Crore.", "error")
            return redirect(url_for("vehicles.vehicle_detail", vehicle_id=vehicle.id))

        vehicle.original_showroom_price = price
        vehicle.showroom_price_source = source_str or "User-Entered"
        vehicle.showroom_price_notes = notes_str or "Manual entry (unverified)"
        vehicle.showroom_price_verified = False

        _compute_vehicle_scores(vehicle)
        db.session.commit()
        flash("Original showroom price successfully recorded as user-entered and unverified.", "success")
    except ValueError:
        flash("Invalid price value entered.", "error")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to save showroom price: {str(e)}", "error")

    return redirect(url_for("vehicles.vehicle_detail", vehicle_id=vehicle.id))


@vehicle_bp.route("/vehicles/<int:vehicle_id>/delete", methods=["POST"])
def delete_vehicle(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    reg = vehicle.registration_number
    try:
        db.session.delete(vehicle)
        db.session.commit()
        flash(f"Vehicle {reg} deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting vehicle: {str(e)}", "error")
    return redirect(url_for("vehicles.list_vehicles"))


@vehicle_bp.route("/vehicles/<int:vehicle_id>/recalculate", methods=["POST"])
def recalculate_vehicle(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    _compute_vehicle_scores(vehicle)
    try:
        db.session.commit()
        flash("Health score and resale value recalculated.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {str(e)}", "error")
    return redirect(url_for("vehicles.vehicle_detail", vehicle_id=vehicle_id))


# ── API routes ───────────────────────────────────────────────────────────────

@vehicle_bp.route("/api/vehicles")
def api_list_vehicles():
    vehicles = Vehicle.query.all()
    return jsonify([v.to_dict() for v in vehicles])


@vehicle_bp.route("/api/vehicles/<int:vehicle_id>")
def api_get_vehicle(vehicle_id):
    vehicle = Vehicle.query.get_or_404(vehicle_id)
    return jsonify(vehicle.to_dict())


@vehicle_bp.route("/api/vehicles/catalogue")
def api_vehicle_catalogue():
    """Autocomplete endpoint providing make/model suggestions from local dataset."""
    q = request.args.get("q", "").strip()
    limit = min(request.args.get("limit", 15, type=int), 50)
    suggestions = search_vehicle_catalogue(q, limit=limit)
    return jsonify({
        "query": q,
        "count": len(suggestions),
        "suggestions": suggestions,
    })


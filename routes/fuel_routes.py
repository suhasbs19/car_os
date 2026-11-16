"""
Fuel and energy routes.
"""
from datetime import date
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from models import db, Vehicle, FuelRecord
from services.fuel_service import (
    calculate_fuel_efficiency, calculate_cost_per_km,
    aggregate_fuel_records, monthly_fuel_trend
)

fuel_bp = Blueprint("fuel", __name__)

FUEL_TYPES = ["Petrol", "Diesel", "CNG", "Hybrid", "Electric"]


@fuel_bp.route("/fuel")
def list_fuel():
    vehicle_id = request.args.get("vehicle_id", type=int)
    date_from_str = request.args.get("date_from", "").strip()
    date_to_str = request.args.get("date_to", "").strip()

    query = FuelRecord.query
    if vehicle_id:
        query = query.filter_by(vehicle_id=vehicle_id)
    if date_from_str:
        try:
            d_from = date.fromisoformat(date_from_str)
            query = query.filter(FuelRecord.date >= d_from)
        except ValueError:
            pass
    if date_to_str:
        try:
            d_to = date.fromisoformat(date_to_str)
            query = query.filter(FuelRecord.date <= d_to)
        except ValueError:
            pass

    records = query.order_by(FuelRecord.date.desc()).all()
    vehicles = Vehicle.query.order_by(Vehicle.make).all()

    # Aggregate stats keeping ICE and EV units strictly separate
    selected_vehicle = Vehicle.query.get(vehicle_id) if vehicle_id else None
    fuel_type = selected_vehicle.fuel_type if selected_vehicle else None
    stats = aggregate_fuel_records(records, fuel_type)
    trend = monthly_fuel_trend(records)

    return render_template(
        "fuel.html",
        records=records,
        vehicles=vehicles,
        stats=stats,
        trend=trend,
        vehicle_id=vehicle_id,
        date_from=date_from_str,
        date_to=date_to_str,
        selected_vehicle=selected_vehicle,
    )


@fuel_bp.route("/fuel/add", methods=["GET", "POST"])
def add_fuel():
    vehicles = Vehicle.query.order_by(Vehicle.make).all()
    if request.method == "POST":
        errors = []
        vehicle_id = request.form.get("vehicle_id", type=int)
        date_str = request.form.get("date", "")
        dist_str = request.form.get("distance_km", "")
        qty_str = request.form.get("quantity", "")
        cost_str = request.form.get("cost", "").strip()
        unit_price_str = request.form.get("unit_price", "").strip()
        notes = request.form.get("notes", "").strip()

        if not vehicle_id or not Vehicle.query.get(vehicle_id):
            errors.append("Please select a valid vehicle.")

        vehicle = Vehicle.query.get(vehicle_id) if vehicle_id else None
        fuel_type = vehicle.fuel_type if vehicle else "Petrol"

        record_date = None
        try:
            record_date = date.fromisoformat(date_str)
        except ValueError:
            errors.append("Invalid date.")

        distance = 0.0
        try:
            distance = float(dist_str)
            if distance <= 0:
                errors.append("Distance must be positive.")
        except ValueError:
            errors.append("Distance must be a number.")

        quantity = 0.0
        try:
            quantity = float(qty_str)
            if quantity <= 0:
                errors.append("Quantity must be positive.")
        except ValueError:
            errors.append("Quantity must be a number.")

        unit_price = None
        if unit_price_str:
            try:
                up_val = float(unit_price_str)
                if up_val <= 0:
                    errors.append("Unit price must be positive.")
                else:
                    unit_price = up_val
            except ValueError:
                errors.append("Unit price must be a valid number.")

        cost = None
        if cost_str:
            try:
                c_val = float(cost_str)
                if c_val <= 0:
                    errors.append("Cost must be greater than zero.")
                else:
                    cost = c_val
            except ValueError:
                errors.append("Cost must be a valid number.")

        # Determine cost from validated cost or quantity * unit_price:
        # Crucial: Use validated recorded cost directly; do not multiply an already calculated cost by quantity!
        final_cost = None
        if cost is not None:
            final_cost = cost
        elif unit_price is not None and quantity > 0:
            final_cost = round(quantity * unit_price, 2)
        else:
            errors.append("Please enter the total cost (₹) or price per unit (₹/unit).")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "add_fuel.html", vehicles=vehicles, form_data=request.form,
            )

        record = FuelRecord(
            vehicle_id=vehicle_id, date=record_date,
            distance_km=distance, quantity=quantity,
            cost=final_cost, fuel_type=fuel_type, notes=notes,
        )
        db.session.add(record)
        try:
            db.session.commit()
            flash("Fuel/energy record added successfully.", "success")
            return redirect(url_for("fuel.list_fuel", vehicle_id=vehicle_id))
        except Exception as e:
            db.session.rollback()
            flash(f"Database error: {str(e)}", "error")

    preselect = request.args.get("vehicle_id", type=int)
    return render_template(
        "add_fuel.html", vehicles=vehicles,
        form_data={"vehicle_id": preselect or ""},
    )


@fuel_bp.route("/fuel/<int:record_id>/delete", methods=["POST"])
def delete_fuel(record_id):
    record = FuelRecord.query.get_or_404(record_id)
    vid = record.vehicle_id
    try:
        db.session.delete(record)
        db.session.commit()
        flash("Fuel record deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {str(e)}", "error")
    return redirect(url_for("fuel.list_fuel", vehicle_id=vid))


@fuel_bp.route("/api/fuel")
def api_list_fuel():
    vehicle_id = request.args.get("vehicle_id", type=int)
    query = FuelRecord.query
    if vehicle_id:
        query = query.filter_by(vehicle_id=vehicle_id)
    records = query.order_by(FuelRecord.date.desc()).all()
    return jsonify([r.to_dict() for r in records])

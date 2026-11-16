"""
CAR OS - Database Models
SQLAlchemy ORM models for the vehicle management platform.
"""
import json
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Vehicle(db.Model):
    __tablename__ = "vehicles"

    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    registration_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    manufacturing_year = db.Column(db.Integer, nullable=False)
    odometer_km = db.Column(db.Float, nullable=False, default=0.0)
    fuel_type = db.Column(
        db.String(20),
        nullable=False,
        default="Petrol",
    )  # Petrol | Diesel | CNG | Hybrid | Electric
    service_history = db.Column(
        db.String(20), nullable=False, default="Unknown"
    )  # Full | Partial | None | Unknown
    reported_issues = db.Column(db.Integer, nullable=False, default=0)
    variant = db.Column(db.String(100), nullable=True)
    transmission = db.Column(db.String(30), nullable=True, default="Manual")
    original_showroom_price = db.Column(db.Float, nullable=True)
    showroom_price_source = db.Column(db.String(150), nullable=True)
    showroom_price_notes = db.Column(db.Text, nullable=True)
    showroom_price_verified = db.Column(db.Boolean, default=False)
    current_market_price = db.Column(db.Float, nullable=True)
    health_score = db.Column(db.Float, nullable=True)
    health_status = db.Column(db.String(20), nullable=True)
    estimated_resale_value = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    # Relationships
    maintenance_records = db.relationship(
        "MaintenanceRecord", backref="vehicle", lazy="dynamic", cascade="all, delete-orphan"
    )
    fuel_records = db.relationship(
        "FuelRecord", backref="vehicle", lazy="dynamic", cascade="all, delete-orphan"
    )
    expense_records = db.relationship(
        "ExpenseRecord", backref="vehicle", lazy="dynamic", cascade="all, delete-orphan"
    )
    diagnostic_records = db.relationship(
        "DiagnosticRecord", backref="vehicle", lazy="dynamic", cascade="all, delete-orphan"
    )
    obd_records = db.relationship(
        "OBDRecord", backref="vehicle", lazy="dynamic", cascade="all, delete-orphan",
        order_by="desc(OBDRecord.timestamp)"
    )
    valuation_records = db.relationship(
        "ValuationRecord", backref="vehicle", lazy="dynamic", cascade="all, delete-orphan",
        order_by="desc(ValuationRecord.valuation_date)"
    )

    @property
    def latest_obd(self):
        return self.obd_records.first()

    @property
    def latest_valuation(self):
        return self.valuation_records.first()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<Vehicle {self.registration_number}: {self.make} {self.model}>"

    def to_dict(self):
        return {
            "id": self.id,
            "make": self.make,
            "model": self.model,
            "registration_number": self.registration_number,
            "manufacturing_year": self.manufacturing_year,
            "odometer_km": self.odometer_km,
            "fuel_type": self.fuel_type,
            "service_history": self.service_history,
            "reported_issues": self.reported_issues,
            "variant": self.variant,
            "transmission": self.transmission,
            "original_showroom_price": self.original_showroom_price,
            "showroom_price_source": self.showroom_price_source,
            "showroom_price_notes": self.showroom_price_notes,
            "showroom_price_verified": bool(self.showroom_price_verified) if self.showroom_price_verified is not None else False,
            "current_market_price": self.current_market_price,
            "health_score": self.health_score,
            "health_status": self.health_status,
            "estimated_resale_value": self.estimated_resale_value,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MaintenanceRecord(db.Model):
    __tablename__ = "maintenance_records"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    service_date = db.Column(db.Date, nullable=False)
    service_category = db.Column(db.String(100), nullable=False)
    component_name = db.Column(db.String(200), nullable=False)
    odometer_at_service = db.Column(db.Float, nullable=True)
    description = db.Column(db.Text, nullable=True)
    cost = db.Column(db.Float, nullable=False, default=0.0)
    next_service_date = db.Column(db.Date, nullable=True)
    next_service_odometer = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Completed")
    created_at = db.Column(db.DateTime, default=utcnow)

    # Optional link to expense record (avoid double-counting)
    expense_id = db.Column(db.Integer, db.ForeignKey("expense_records.id"), nullable=True)

    # Ingestion & dataset traceability attributes
    source_record_id = db.Column(db.String(50), nullable=True, index=True)
    evidence_status = db.Column(db.String(100), nullable=True)
    workshop = db.Column(db.String(150), nullable=True)
    parts_cost = db.Column(db.Float, nullable=True)
    labour_cost = db.Column(db.Float, nullable=True)
    diagnostic_trouble_code = db.Column(db.String(50), nullable=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            "id": self.id,
            "vehicle_id": self.vehicle_id,
            "service_date": self.service_date.isoformat() if self.service_date else None,
            "service_category": self.service_category,
            "component_name": self.component_name,
            "odometer_at_service": self.odometer_at_service,
            "description": self.description,
            "cost": self.cost,
            "parts_cost": self.parts_cost,
            "labour_cost": self.labour_cost,
            "next_service_date": self.next_service_date.isoformat() if self.next_service_date else None,
            "next_service_odometer": self.next_service_odometer,
            "status": self.status,
            "source_record_id": self.source_record_id,
            "evidence_status": self.evidence_status,
            "workshop": self.workshop,
            "diagnostic_trouble_code": self.diagnostic_trouble_code,
        }


class FuelRecord(db.Model):
    __tablename__ = "fuel_records"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    distance_km = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Float, nullable=False)  # litres for ICE/CNG, kWh for EV
    cost = db.Column(db.Float, nullable=False)
    fuel_type = db.Column(db.String(20), nullable=False)  # mirrors vehicle fuel type
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def unit_price(self):
        """Effective price per unit (₹/L, ₹/kg, or ₹/kWh)."""
        return round(self.cost / self.quantity, 2) if (self.quantity and self.quantity > 0) else 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "vehicle_id": self.vehicle_id,
            "date": self.date.isoformat() if self.date else None,
            "distance_km": self.distance_km,
            "quantity": self.quantity,
            "cost": self.cost,
            "unit_price": self.unit_price,
            "fuel_type": self.fuel_type,
            "notes": self.notes,
        }


class ExpenseRecord(db.Model):
    __tablename__ = "expense_records"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    linked_maintenance_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            "id": self.id,
            "vehicle_id": self.vehicle_id,
            "date": self.date.isoformat() if self.date else None,
            "category": self.category,
            "amount": self.amount,
            "description": self.description,
            "linked_maintenance_id": self.linked_maintenance_id,
        }


class DiagnosticRecord(db.Model):
    __tablename__ = "diagnostic_records"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    data_source = db.Column(db.String(100), nullable=False, default="Manual")
    dtc_code = db.Column(db.String(50), nullable=True)
    parameter_name = db.Column(db.String(200), nullable=True)
    parameter_value = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            "id": self.id,
            "vehicle_id": self.vehicle_id,
            "date": self.date.isoformat() if self.date else None,
            "data_source": self.data_source,
            "dtc_code": self.dtc_code,
            "parameter_name": self.parameter_name,
            "parameter_value": self.parameter_value,
            "notes": self.notes,
        }


class OBDRecord(db.Model):
    __tablename__ = "obd_records"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    data_source = db.Column(db.String(50), nullable=False, default="Manual")  # "Manual" | "Live OBD"
    connection_status = db.Column(db.String(50), nullable=False, default="Not connected")  # "Connected" | "Not connected"
    engine_rpm = db.Column(db.Float, nullable=True)
    vehicle_speed_kmh = db.Column(db.Float, nullable=True)
    coolant_temp_c = db.Column(db.Float, nullable=True)
    engine_load_pct = db.Column(db.Float, nullable=True)
    throttle_pos_pct = db.Column(db.Float, nullable=True)
    fuel_system_status = db.Column(db.String(100), nullable=True)
    battery_voltage = db.Column(db.Float, nullable=True)
    dtc_codes = db.Column(db.Text, nullable=True)  # JSON-encoded list of strings e.g. '["P0420", "P0300"]'
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def dtc_list(self) -> list:
        if not self.dtc_codes:
            return []
        try:
            val = json.loads(self.dtc_codes)
            if isinstance(val, list):
                return [str(c).strip().upper() for c in val if str(c).strip()]
        except (ValueError, TypeError):
            return [c.strip().upper() for c in self.dtc_codes.split(",") if c.strip()]
        return []

    def to_dict(self):
        return {
            "id": self.id,
            "vehicle_id": self.vehicle_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "data_source": self.data_source,
            "connection_status": self.connection_status,
            "engine_rpm": self.engine_rpm,
            "vehicle_speed_kmh": self.vehicle_speed_kmh,
            "coolant_temp_c": self.coolant_temp_c,
            "engine_load_pct": self.engine_load_pct,
            "throttle_pos_pct": self.throttle_pos_pct,
            "fuel_system_status": self.fuel_system_status,
            "battery_voltage": self.battery_voltage,
            "dtc_codes": self.dtc_list,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ValuationRecord(db.Model):
    __tablename__ = "valuation_records"

    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicles.id"), nullable=False, index=True)
    valuation_date = db.Column(db.DateTime, default=utcnow, index=True)
    original_showroom_price = db.Column(db.Float, nullable=True)
    market_asking_price_min = db.Column(db.Float, nullable=True)
    market_asking_price_max = db.Column(db.Float, nullable=True)
    representative_market_price = db.Column(db.Float, nullable=True)
    comparable_listings_count = db.Column(db.Integer, default=0)
    estimated_resale_value = db.Column(db.Float, nullable=False)
    depreciation_amount = db.Column(db.Float, nullable=True)
    depreciation_percentage = db.Column(db.Float, nullable=True)
    valuation_method = db.Column(db.String(100), nullable=False, default="model-based")
    valuation_source = db.Column(db.String(150), nullable=True)
    confidence_status = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    input_snapshot = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            "id": self.id,
            "vehicle_id": self.vehicle_id,
            "valuation_date": self.valuation_date.isoformat() if self.valuation_date else None,
            "original_showroom_price": self.original_showroom_price,
            "market_asking_price_min": self.market_asking_price_min,
            "market_asking_price_max": self.market_asking_price_max,
            "representative_market_price": self.representative_market_price,
            "comparable_listings_count": self.comparable_listings_count,
            "estimated_resale_value": self.estimated_resale_value,
            "depreciation_amount": self.depreciation_amount,
            "depreciation_percentage": self.depreciation_percentage,
            "valuation_method": self.valuation_method,
            "valuation_source": self.valuation_source,
            "confidence_status": self.confidence_status,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def apply_sqlite_migrations(engine):
    """
    Safely and non-destructively inspects and migrates existing SQLite tables.
    Adds variant, transmission, original_showroom_price, and current_market_price
    columns to the vehicles table if they are not already present.
    """
    import sqlalchemy
    from sqlalchemy import inspect

    try:
        inspector = inspect(engine)
        if "vehicles" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("vehicles")]
            with engine.connect() as conn:
                if "variant" not in columns:
                    conn.execute(sqlalchemy.text("ALTER TABLE vehicles ADD COLUMN variant VARCHAR(100);"))
                if "transmission" not in columns:
                    conn.execute(sqlalchemy.text("ALTER TABLE vehicles ADD COLUMN transmission VARCHAR(30) DEFAULT 'Manual';"))
                if "original_showroom_price" not in columns:
                    conn.execute(sqlalchemy.text("ALTER TABLE vehicles ADD COLUMN original_showroom_price FLOAT;"))
                if "showroom_price_source" not in columns:
                    conn.execute(sqlalchemy.text("ALTER TABLE vehicles ADD COLUMN showroom_price_source VARCHAR(150);"))
                if "showroom_price_notes" not in columns:
                    conn.execute(sqlalchemy.text("ALTER TABLE vehicles ADD COLUMN showroom_price_notes TEXT;"))
                if "showroom_price_verified" not in columns:
                    conn.execute(sqlalchemy.text("ALTER TABLE vehicles ADD COLUMN showroom_price_verified BOOLEAN DEFAULT 0;"))
                if "current_market_price" not in columns:
                    conn.execute(sqlalchemy.text("ALTER TABLE vehicles ADD COLUMN current_market_price FLOAT;"))
                conn.commit()
    except Exception as e:
        # If in-memory or already locked, pass gracefully
        pass


# Additional indexes
Index("idx_maintenance_vehicle_date", MaintenanceRecord.vehicle_id, MaintenanceRecord.service_date)
Index("idx_fuel_vehicle_date", FuelRecord.vehicle_id, FuelRecord.date)
Index("idx_expense_vehicle_date", ExpenseRecord.vehicle_id, ExpenseRecord.date)
Index("idx_obd_vehicle_timestamp", OBDRecord.vehicle_id, OBDRecord.timestamp)
Index("idx_valuation_vehicle_date", ValuationRecord.vehicle_id, ValuationRecord.valuation_date)

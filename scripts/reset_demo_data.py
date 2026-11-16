"""
CAR OS - Database Reset & Realistic Demo Data Seeding Script
===========================================================
Safe, deterministic operational cleanup and comprehensive demonstration data seeding.

DISCLOSURE & NOTICE:
--------------------
- This operation is DESTRUCTIVE for operational records.
- Old operational records (vehicles, maintenance, fuel, expenses, OBD, diagnostics)
  WILL BE PERMANENTLY REMOVED and are NOT recoverable through this procedure.
- The user has explicitly selected NO BACKUP. No backup file is created.
- Non-operational tables, user accounts (if any), schema tables, indexes, constraints,
  and external datasets/ML model artifacts are strictly preserved.
- Database tables and schema definitions are NOT dropped or recreated.

Usage:
------
Dry Run (Default, non-destructive):
    python scripts/reset_demo_data.py
    python scripts/reset_demo_data.py --dry-run

Destructive Execution (Requires explicit flag):
    python scripts/reset_demo_data.py --confirm-destructive-cleanup
"""

import sys
import os
import argparse
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone

# Ensure project root is on Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app
from models import (
    db,
    Vehicle,
    MaintenanceRecord,
    FuelRecord,
    ExpenseRecord,
    DiagnosticRecord,
    OBDRecord,
    ValuationRecord,
)
from services.health_service import calculate_health_score
from services.valuation_service import calculate_resale_value
from services.decision_service import generate_decision

# Operational tables targeted for cleanup in strict FK-safe order
OPERATIONAL_TABLES_CLEANUP_ORDER = [
    "valuation_records",
    "diagnostic_records",
    "obd_records",
    "fuel_records",
    "maintenance_records",
    "expense_records",
    "vehicles",
]

# Supported application enums / categories for strict validation
ALLOWED_FUEL_TYPES = ["Petrol", "Diesel", "CNG", "Hybrid", "Electric"]
ALLOWED_SERVICE_HISTORIES = ["Full", "Partial", "None", "Unknown"]
ALLOWED_MAINTENANCE_CATEGORIES = [
    "Oil & Lubrication", "Brakes", "Tyres & Wheels", "Engine",
    "Transmission", "Electrical", "AC & Cooling", "Body & Exterior",
    "Inspection", "Insurance", "Other",
]
ALLOWED_MAINTENANCE_STATUSES = ["Completed", "Pending", "In Progress", "Cancelled"]
ALLOWED_EXPENSE_CATEGORIES = [
    "Fuel & Charging", "Maintenance & Repair", "Insurance",
    "Tyres & Components", "Parking & Tolls", "Tax & Registration", "Other",
]


def get_actual_sqlite_path(app) -> str:
    """Extract physical SQLite file path from Flask app config."""
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if uri.startswith("sqlite:///"):
        raw_path = uri.replace("sqlite:///", "")
        return os.path.abspath(raw_path)
    return uri


def get_database_inventory(db_path: str):
    """Inspect all SQLite tables, row counts, and foreign key dependencies."""
    if not os.path.exists(db_path):
        return {}, [], []
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tables = [row[0] for row in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
    ).fetchall()]
    row_counts = {}
    for t in tables:
        count = cur.execute(f'SELECT COUNT(*) FROM "{t}";').fetchone()[0]
        row_counts[t] = count
    fk_issues = cur.execute("PRAGMA foreign_key_check;").fetchall()
    conn.close()
    return row_counts, tables, fk_issues


def build_seed_dataset():
    """
    Constructs a deterministic, realistic demonstration dataset of 8 vehicles
    with comprehensive operational records representing varied conditions,
    powertrains, and decision scenarios in the Indian market.
    """
    today = date.today()
    base_time = datetime.now(timezone.utc).replace(tzinfo=None)

    # 8 distinct vehicles covering varied powertrains, ages, conditions, and decisions
    vehicles_data = [
        {
            "key": "creta",
            "make": "Hyundai",
            "model": "Creta",
            "variant": "1.5 SX",
            "transmission": "Manual",
            "registration_number": "DEMO-MH-001",
            "manufacturing_year": today.year - 2,
            "odometer_km": 24500.0,
            "fuel_type": "Petrol",
            "service_history": "Full",
            "reported_issues": 0,
            "notes": "[DEMO SYNTHETIC] Primary family compact SUV. Verified dealer service history, clean inspection records, normal telemetry.",
        },
        {
            "key": "nexon_ev",
            "make": "Tata",
            "model": "Nexon EV",
            "variant": "Long Range Empowered",
            "transmission": "Automatic",
            "registration_number": "DEMO-KA-002",
            "manufacturing_year": today.year - 1,
            "odometer_km": 16800.0,
            "fuel_type": "Electric",
            "service_history": "Full",
            "reported_issues": 0,
            "notes": "[DEMO SYNTHETIC] Electric urban commuter SUV. Charged via home AC wallbox; 12V auxiliary system normal, healthy battery state.",
        },
        {
            "key": "city",
            "make": "Honda",
            "model": "City",
            "variant": "1.5 V",
            "transmission": "Manual",
            "registration_number": "DEMO-DL-003",
            "manufacturing_year": today.year - 4,
            "odometer_km": 48000.0,
            "fuel_type": "Petrol",
            "service_history": "Full",
            "reported_issues": 1,
            "notes": "[DEMO SYNTHETIC] Executive sedan. Periodic dealer maintenance up to date; AC refrigerant topped up; upcoming 50k km scheduled service.",
        },
        {
            "key": "swift",
            "make": "Maruti Suzuki",
            "model": "Swift",
            "variant": "VDi",
            "transmission": "Manual",
            "registration_number": "DEMO-KA-004",
            "manufacturing_year": today.year - 7,
            "odometer_km": 98200.0,
            "fuel_type": "Diesel",
            "service_history": "Partial",
            "reported_issues": 2,
            "notes": "[DEMO SYNTHETIC] Daily diesel hatchback. Catalyst efficiency warning (P0420) and overdue scheduled service reminder.",
        },
        {
            "key": "thar",
            "make": "Mahindra",
            "model": "Thar",
            "variant": "CRDe 4x4",
            "transmission": "Manual",
            "registration_number": "DEMO-MH-005",
            "manufacturing_year": today.year - 13,
            "odometer_km": 215000.0,
            "fuel_type": "Diesel",
            "service_history": "None",
            "reported_issues": 5,
            "notes": "[DEMO SYNTHETIC] High-mileage utility 4x4. Heavy smoke, cylinder misfires (P0300, P0101), elevated coolant temperature, sell candidate.",
        },
        {
            "key": "fortuner",
            "make": "Toyota",
            "model": "Fortuner",
            "variant": "2.8 4x4 AT",
            "transmission": "Automatic",
            "registration_number": "DEMO-HR-006",
            "manufacturing_year": today.year - 5,
            "odometer_km": 72000.0,
            "fuel_type": "Diesel",
            "service_history": "Full",
            "reported_issues": 0,
            "notes": "[DEMO SYNTHETIC] Premium robust SUV for long-distance highway travel. Full Toyota dealer records matching empirical maintenance benchmarks.",
        },
        {
            "key": "baleno",
            "make": "Maruti Suzuki",
            "model": "Baleno",
            "variant": "Delta CNG",
            "transmission": "Manual",
            "registration_number": "DEMO-GJ-007",
            "manufacturing_year": today.year - 3,
            "odometer_km": 42000.0,
            "fuel_type": "CNG",
            "service_history": "Full",
            "reported_issues": 0,
            "notes": "[DEMO SYNTHETIC] Bi-fuel factory CNG premium hatchback. Economical city fleet runner with certified CNG cylinder compliance.",
        },
        {
            "key": "polo",
            "make": "Volkswagen",
            "model": "Polo",
            "variant": "1.0 TSI Highline Plus",
            "transmission": "Manual",
            "registration_number": "DEMO-TN-008",
            "manufacturing_year": today.year - 8,
            "odometer_km": 84000.0,
            "fuel_type": "Petrol",
            "service_history": "Partial",
            "reported_issues": 2,
            "notes": "[DEMO SYNTHETIC] Turbocharged petrol hatchback. Left front wheel speed sensor circuit DTC (C0035) requiring harness inspection.",
        },
    ]

    # Pre-defined telemetry / OBD specifications
    obd_specs = [
        {
            "vehicle_key": "creta",
            "offset_days": 2,
            "data_source": "Manual (Demo)",
            "connection_status": "Connected",
            "engine_rpm": 780.0,
            "vehicle_speed_kmh": 0.0,
            "coolant_temp_c": 88.5,
            "engine_load_pct": 22.4,
            "throttle_pos_pct": 13.5,
            "fuel_system_status": "Closed loop (O2 feedback active)",
            "battery_voltage": 12.65,
            "dtc_codes": None,
            "notes": "[DEMO SYNTHETIC] Bluetooth OBD-II idle scan. All monitors ready, closed-loop fueling active, normal battery voltage.",
        },
        {
            "vehicle_key": "nexon_ev",
            "offset_days": 7,
            "data_source": "Manual (Demo)",
            "connection_status": "Connected",
            "engine_rpm": 0.0,
            "vehicle_speed_kmh": 0.0,
            "coolant_temp_c": 42.0,
            "engine_load_pct": 0.0,
            "throttle_pos_pct": 0.0,
            "fuel_system_status": "Closed loop",
            "battery_voltage": 13.80,
            "dtc_codes": None,
            "notes": "[DEMO SYNTHETIC] EV auxiliary BMS diagnostic scan. 12V auxiliary system normal, thermal loop optimal.",
        },
        {
            "vehicle_key": "swift",
            "offset_days": 5,
            "data_source": "Manual (Demo)",
            "connection_status": "Connected",
            "engine_rpm": 820.0,
            "vehicle_speed_kmh": 0.0,
            "coolant_temp_c": 91.0,
            "engine_load_pct": 29.0,
            "throttle_pos_pct": 15.0,
            "fuel_system_status": "Closed loop",
            "battery_voltage": 12.10,
            "dtc_codes": json.dumps(["P0420"]),
            "notes": "[DEMO SYNTHETIC] Diagnostic scan tool retrieved P0420 (Catalyst efficiency below threshold). Downstream sensor slow.",
        },
        {
            "vehicle_key": "thar",
            "offset_days": 1,
            "data_source": "Manual (Demo)",
            "connection_status": "Connected",
            "engine_rpm": 960.0,
            "vehicle_speed_kmh": 0.0,
            "coolant_temp_c": 108.5,
            "engine_load_pct": 54.0,
            "throttle_pos_pct": 18.5,
            "fuel_system_status": "Open loop (due to system fault)",
            "battery_voltage": 11.60,
            "dtc_codes": json.dumps(["P0300", "P0101"]),
            "notes": "[DEMO SYNTHETIC] Critical scan. Cylinder misfire detected, MAF air signal deviation, elevated coolant temp (108.5C), low 12V battery.",
        },
        {
            "vehicle_key": "fortuner",
            "offset_days": 4,
            "data_source": "Manual (Demo)",
            "connection_status": "Connected",
            "engine_rpm": 720.0,
            "vehicle_speed_kmh": 0.0,
            "coolant_temp_c": 87.0,
            "engine_load_pct": 21.0,
            "throttle_pos_pct": 12.0,
            "fuel_system_status": "Closed loop",
            "battery_voltage": 12.70,
            "dtc_codes": None,
            "notes": "[DEMO SYNTHETIC] Periodic health check. Common rail fuel pressure within OEM parameters; no pending trouble codes.",
        },
        {
            "vehicle_key": "baleno",
            "offset_days": 3,
            "data_source": "Manual (Demo)",
            "connection_status": "Connected",
            "engine_rpm": 760.0,
            "vehicle_speed_kmh": 0.0,
            "coolant_temp_c": 86.0,
            "engine_load_pct": 24.0,
            "throttle_pos_pct": 14.0,
            "fuel_system_status": "Closed loop",
            "battery_voltage": 12.55,
            "dtc_codes": None,
            "notes": "[DEMO SYNTHETIC] Bi-fuel ECU scan. Dual map switching verified, stoichiometric lambda maintained on CNG.",
        },
        {
            "vehicle_key": "polo",
            "offset_days": 6,
            "data_source": "Manual (Demo)",
            "connection_status": "Connected",
            "engine_rpm": 790.0,
            "vehicle_speed_kmh": 0.0,
            "coolant_temp_c": 90.0,
            "engine_load_pct": 26.0,
            "throttle_pos_pct": 14.5,
            "fuel_system_status": "Closed loop",
            "battery_voltage": 12.20,
            "dtc_codes": json.dumps(["C0035"]),
            "notes": "[DEMO SYNTHETIC] ABS/Chassis scan retrieved DTC C0035 (Left Front Wheel Speed Circuit Malfunction).",
        },
        # City deliberately omitted from OBD records to test clean empty-state UX
    ]

    # Manual diagnostic inspection entries
    diagnostic_specs = [
        {
            "vehicle_key": "creta",
            "offset_days": 75,
            "data_source": "OBD-II Scanner (Demo)",
            "dtc_code": None,
            "parameter_name": "ECU Readiness & 12V Battery",
            "parameter_value": "Battery: 12.6V, MIL: OFF, Readiness: Complete",
            "notes": "[DEMO SYNTHETIC] Annual dealer scan. All onboard emissions readiness monitors set, no pending codes.",
        },
        {
            "vehicle_key": "nexon_ev",
            "offset_days": 90,
            "data_source": "BMS Telemetry (Demo)",
            "dtc_code": None,
            "parameter_name": "HV Traction Battery State-of-Health (SoH)",
            "parameter_value": "SoH: 98.4%, Max Cell Delta: 12mV",
            "notes": "[DEMO SYNTHETIC] EV service center scan. High-voltage battery pack shows healthy cell balance.",
        },
        {
            "vehicle_key": "city",
            "offset_days": 120,
            "data_source": "Manual Gauge (Demo)",
            "dtc_code": None,
            "parameter_name": "AC Low-side Refrigerant Pressure",
            "parameter_value": "28 PSI (Low before recharge; 35 PSI after recharge)",
            "notes": "[DEMO SYNTHETIC] AC refrigerant pressure low. Recharged and nitrogen leak test passed.",
        },
        {
            "vehicle_key": "swift",
            "offset_days": 20,
            "data_source": "OBD-II Scanner (Demo)",
            "dtc_code": "P0420",
            "parameter_name": "Catalyst System Efficiency Below Threshold (Bank 1)",
            "parameter_value": "Sensor 2 Downstream O2 Voltage Erratic",
            "notes": "[DEMO SYNTHETIC] Check engine light illuminated. Tailpipe emissions inspection required.",
        },
        {
            "vehicle_key": "thar",
            "offset_days": 15,
            "data_source": "OBD-II Scanner (Demo)",
            "dtc_code": "P0300",
            "parameter_name": "Random / Multiple Cylinder Misfire Detected",
            "parameter_value": "Idle RPM oscillation, Fuel Rail Pressure irregular",
            "notes": "[DEMO SYNTHETIC] Severe engine vibration. Injector spray compromise or low cylinder compression.",
        },
        {
            "vehicle_key": "thar",
            "offset_days": 15,
            "data_source": "OBD-II Scanner (Demo)",
            "dtc_code": "P0101",
            "parameter_name": "Mass Air Flow (MAF) Sensor Performance",
            "parameter_value": "Airflow signal deviates > 25% from calculated air mass",
            "notes": "[DEMO SYNTHETIC] Airbox inspection recommended; oil mist fouling detected on hot-wire element.",
        },
        {
            "vehicle_key": "polo",
            "offset_days": 10,
            "data_source": "OBD-II Scanner (Demo)",
            "dtc_code": "C0035",
            "parameter_name": "Left Front Wheel Speed Circuit Malfunction",
            "parameter_value": "Signal Dropout at 20 km/h",
            "notes": "[DEMO SYNTHETIC] ABS warning light intermittent. Sensor harness pin corroded.",
        },
    ]

    # Maintenance specifications and explicit linkage flags for expenses
    # link_expense_category: when set, creates a corresponding ExpenseRecord linked to avoid TCO double-counting
    maintenance_specs = [
        # Creta
        {
            "vehicle_key": "creta",
            "offset_days": 240,
            "service_category": "Oil & Lubrication",
            "component_name": "10,000 km Periodic Inspection",
            "odometer_at_service": 10200.0,
            "description": "[DEMO] Synthetic engine oil change, oil filter replacement, multipoint inspection.",
            "cost": 4500.0,
            "parts_cost": 3200.0,
            "labour_cost": 1300.0,
            "next_offset_days": -120,  # in past relative to service date -> today - 120
            "next_service_odometer": 20000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Hyundai Authorized - Bangalore Central",
            "link_expense": False,
        },
        {
            "vehicle_key": "creta",
            "offset_days": 75,
            "service_category": "Oil & Lubrication",
            "component_name": "20,000 km Major Service",
            "odometer_at_service": 20150.0,
            "description": "[DEMO] Engine oil, air cleaner filter, cabin AC filter, brake cleaning, wheel balancing.",
            "cost": 7800.0,
            "parts_cost": 5400.0,
            "labour_cost": 2400.0,
            "next_offset_days": 105,  # today + 105 days
            "next_service_odometer": 30000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Hyundai Authorized - Bangalore Central",
            "link_expense": True,  # Linked to expense
        },
        # Nexon EV
        {
            "vehicle_key": "nexon_ev",
            "offset_days": 90,
            "service_category": "Inspection",
            "component_name": "EV System Annual Check",
            "odometer_at_service": 10500.0,
            "description": "[DEMO] High-voltage battery diagnostics, cooling circuit check, software update v2.4.",
            "cost": 2200.0,
            "parts_cost": 600.0,
            "labour_cost": 1600.0,
            "next_offset_days": 180,
            "next_service_odometer": 25000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Tata Motors EV Service - Whitefield",
            "link_expense": False,
        },
        # Honda City
        {
            "vehicle_key": "city",
            "offset_days": 180,
            "service_category": "Oil & Lubrication",
            "component_name": "40,000 km Scheduled Service",
            "odometer_at_service": 40200.0,
            "description": "[DEMO] Engine oil replacement, oil filter, brake fluid flush, spark plug inspection.",
            "cost": 6200.0,
            "parts_cost": 4400.0,
            "labour_cost": 1800.0,
            "next_offset_days": 30,  # Service due in 30 days!
            "next_service_odometer": 50000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Honda Cars Service - Delhi North",
            "link_expense": False,
        },
        {
            "vehicle_key": "city",
            "offset_days": 120,
            "service_category": "AC & Cooling",
            "component_name": "AC Condenser Service & Refrigerant Top-up",
            "odometer_at_service": 44500.0,
            "description": "[DEMO] R134a refrigerant recharge, condenser coil cleaning, active carbon cabin filter.",
            "cost": 5100.0,
            "parts_cost": 3300.0,
            "labour_cost": 1800.0,
            "next_offset_days": 60,
            "next_service_odometer": 55000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Climate Care Workshop - Delhi",
            "link_expense": False,
        },
        # Swift (has an overdue reminder)
        {
            "vehicle_key": "swift",
            "offset_days": 380,
            "service_category": "Brakes",
            "component_name": "Front Brake Pads & Rotors Resurfacing",
            "odometer_at_service": 82000.0,
            "description": "[DEMO] Replaced front brake pads and resurfaced worn rotors.",
            "cost": 6400.0,
            "parts_cost": 4800.0,
            "labour_cost": 1600.0,
            "next_offset_days": -30,  # Overdue by 30 days!
            "next_service_odometer": 95000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Maruti Service Zone - Bangalore",
            "link_expense": False,
        },
        {
            "vehicle_key": "swift",
            "offset_days": 160,
            "service_category": "Transmission",
            "component_name": "Clutch Plate & Release Bearing Overhaul",
            "odometer_at_service": 91500.0,
            "description": "[DEMO] Repaired clutch slip. Installed OEM clutch disc, pressure plate, fresh gear oil.",
            "cost": 14200.0,
            "parts_cost": 9800.0,
            "labour_cost": 4400.0,
            "next_offset_days": 90,
            "next_service_odometer": 105000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Maruti Service Zone - Bangalore",
            "link_expense": True,  # Linked to expense
        },
        # Thar (high repairs, critical candidate)
        {
            "vehicle_key": "thar",
            "offset_days": 280,
            "service_category": "Engine",
            "component_name": "Turbocharger & Intercooler Reconditioning",
            "odometer_at_service": 198000.0,
            "description": "[DEMO] Reconditioned turbo shaft and intercooler assembly due to excessive oil consumption.",
            "cost": 28500.0,
            "parts_cost": 21000.0,
            "labour_cost": 7500.0,
            "next_offset_days": -60,
            "next_service_odometer": 210000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Mahindra Authorized Workshop - Thane",
            "link_expense": True,  # Linked to expense
        },
        {
            "vehicle_key": "thar",
            "offset_days": 110,
            "service_category": "Electrical",
            "component_name": "Alternator & Starter Motor Replacement",
            "odometer_at_service": 208000.0,
            "description": "[DEMO] Failed charging circuit replaced with remanufactured alternator unit.",
            "cost": 16800.0,
            "parts_cost": 13200.0,
            "labour_cost": 3600.0,
            "next_offset_days": -10,
            "next_service_odometer": 215000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Mahindra Authorized Workshop - Thane",
            "link_expense": False,
        },
        # Fortuner (Toyota empirical benchmarks)
        {
            "vehicle_key": "fortuner",
            "offset_days": 210,
            "service_category": "Oil & Lubrication",
            "component_name": "50,000 km Scheduled Maintenance",
            "odometer_at_service": 51200.0,
            "description": "[DEMO] Synthetic diesel engine oil, oil filter, air filter, fuel filter, differential oil check.",
            "cost": 9500.0,
            "parts_cost": 7100.0,
            "labour_cost": 2400.0,
            "next_offset_days": -20,
            "next_service_odometer": 60000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Toyota Nippon Service - Gurgaon",
            "link_expense": False,
        },
        {
            "vehicle_key": "fortuner",
            "offset_days": 60,
            "service_category": "Brakes",
            "component_name": "Front & Rear Heavy-Duty Brake Service",
            "odometer_at_service": 69800.0,
            "description": "[DEMO] Replaced front brake pads, caliper pin lubrication, brake hydraulic fluid flush.",
            "cost": 11400.0,
            "parts_cost": 8900.0,
            "labour_cost": 2500.0,
            "next_offset_days": 120,
            "next_service_odometer": 80000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Toyota Nippon Service - Gurgaon",
            "link_expense": False,
        },
        # Baleno (CNG periodic & compliance)
        {
            "vehicle_key": "baleno",
            "offset_days": 190,
            "service_category": "Oil & Lubrication",
            "component_name": "20,000 km Periodic Inspection",
            "odometer_at_service": 20400.0,
            "description": "[DEMO] Engine oil, oil filter, tyre rotation, throttle body cleaning.",
            "cost": 4100.0,
            "parts_cost": 2900.0,
            "labour_cost": 1200.0,
            "next_offset_days": -30,
            "next_service_odometer": 30000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Maruti Arena Service - Ahmedabad",
            "link_expense": False,
        },
        {
            "vehicle_key": "baleno",
            "offset_days": 50,
            "service_category": "Inspection",
            "component_name": "40,000 km CNG Safety & Filter Service",
            "odometer_at_service": 40100.0,
            "description": "[DEMO] Low & high-pressure CNG filter replacement, gas leak leak-detector test, valve inspection.",
            "cost": 3600.0,
            "parts_cost": 2400.0,
            "labour_cost": 1200.0,
            "next_offset_days": 130,
            "next_service_odometer": 50000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Maruti Arena Service - Ahmedabad",
            "link_expense": False,
        },
        # Polo (Attention / repairs)
        {
            "vehicle_key": "polo",
            "offset_days": 250,
            "service_category": "Oil & Lubrication",
            "component_name": "60,000 km Major Service",
            "odometer_at_service": 61500.0,
            "description": "[DEMO] Castrol Edge synthetic oil, oil filter, spark plugs, pollen filter, brake bleeding.",
            "cost": 9800.0,
            "parts_cost": 6900.0,
            "labour_cost": 2900.0,
            "next_offset_days": -80,
            "next_service_odometer": 75000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo Volkswagen Downtown - Chennai",
            "link_expense": False,
        },
        {
            "vehicle_key": "polo",
            "offset_days": 80,
            "service_category": "Tyres & Wheels",
            "component_name": "Front Suspension Strut Mounts & Bushings",
            "odometer_at_service": 79200.0,
            "description": "[DEMO] Replaced worn front shocker mountings and lower arm rubber bushings.",
            "cost": 8400.0,
            "parts_cost": 5900.0,
            "labour_cost": 2500.0,
            "next_offset_days": 100,
            "next_service_odometer": 90000.0,
            "status": "Completed",
            "evidence_status": "Demo Benchmark",
            "workshop": "Demo European Auto Garage - Chennai",
            "link_expense": False,
        },
    ]

    # Standalone expenses (Insurance, Fastag / Parking & Tolls, Tax, Tyres, Other)
    standalone_expense_specs = [
        # Creta
        {"vehicle_key": "creta", "offset_days": 180, "category": "Insurance", "amount": 18500.0, "desc": "[DEMO] Comprehensive Insurance Policy Renewal"},
        {"vehicle_key": "creta", "offset_days": 60, "category": "Parking & Tolls", "amount": 2000.0, "desc": "[DEMO] FASTag Highway Wallet Recharge"},
        {"vehicle_key": "creta", "offset_days": 30, "category": "Other", "amount": 2200.0, "desc": "[DEMO] Full Interior Foam Cleaning & Sanitization"},
        # Nexon EV
        {"vehicle_key": "nexon_ev", "offset_days": 200, "category": "Insurance", "amount": 21000.0, "desc": "[DEMO] Zero-Dep EV Electric Motor and Battery Cover"},
        {"vehicle_key": "nexon_ev", "offset_days": 90, "category": "Tyres & Components", "amount": 3500.0, "desc": "[DEMO] All-Weather Fitted 7D Cabin Floor Liners"},
        {"vehicle_key": "nexon_ev", "offset_days": 45, "category": "Parking & Tolls", "amount": 1500.0, "desc": "[DEMO] Metro Station Monthly EV Parking Pass"},
        # City
        {"vehicle_key": "city", "offset_days": 220, "category": "Insurance", "amount": 14200.0, "desc": "[DEMO] Annual Comprehensive Insurance Renewal"},
        {"vehicle_key": "city", "offset_days": 80, "category": "Tax & Registration", "amount": 1800.0, "desc": "[DEMO] Annual State Green Tax & PUC Certification"},
        {"vehicle_key": "city", "offset_days": 40, "category": "Parking & Tolls", "amount": 1200.0, "desc": "[DEMO] Delhi Airport Terminal 3 Parking"},
        # Swift
        {"vehicle_key": "swift", "offset_days": 150, "category": "Insurance", "amount": 9800.0, "desc": "[DEMO] Third-Party + Own Damage Policy Renewal"},
        {"vehicle_key": "swift", "offset_days": 40, "category": "Parking & Tolls", "amount": 1200.0, "desc": "[DEMO] Commercial Office Parking Monthly Pass"},
        # Thar
        {"vehicle_key": "thar", "offset_days": 300, "category": "Insurance", "amount": 7200.0, "desc": "[DEMO] Basic Third-Party Mandatory Liability Cover"},
        {"vehicle_key": "thar", "offset_days": 90, "category": "Other", "amount": 8500.0, "desc": "[DEMO] Emergency Towing & Flatbed Recovery Charges"},
        # Fortuner
        {"vehicle_key": "fortuner", "offset_days": 250, "category": "Insurance", "amount": 32000.0, "desc": "[DEMO] Full Bumper-to-Bumper Commercial/Personal Cover"},
        {"vehicle_key": "fortuner", "offset_days": 100, "category": "Tyres & Components", "amount": 12500.0, "desc": "[DEMO] Pair of Bridgestone Dueler All-Terrain Tyres"},
        {"vehicle_key": "fortuner", "offset_days": 30, "category": "Parking & Tolls", "amount": 3000.0, "desc": "[DEMO] NH48 National Highway Toll Passes"},
        # Baleno
        {"vehicle_key": "baleno", "offset_days": 210, "category": "Insurance", "amount": 13500.0, "desc": "[DEMO] Comprehensive Policy with CNG Kit Endorsement"},
        {"vehicle_key": "baleno", "offset_days": 70, "category": "Tax & Registration", "amount": 1500.0, "desc": "[DEMO] 3-Year Mandatory CNG Cylinder Hydrostatic Test"},
        {"vehicle_key": "baleno", "offset_days": 25, "category": "Parking & Tolls", "amount": 1800.0, "desc": "[DEMO] Expressway FASTag Monthly Recharge"},
        # Polo
        {"vehicle_key": "polo", "offset_days": 190, "category": "Insurance", "amount": 11000.0, "desc": "[DEMO] Comprehensive Policy with Roadside Assistance"},
        {"vehicle_key": "polo", "offset_days": 85, "category": "Tyres & Components", "amount": 4800.0, "desc": "[DEMO] 2 Goodyear Assurance Front Tyres Replacement"},
        {"vehicle_key": "polo", "offset_days": 20, "category": "Parking & Tolls", "amount": 1000.0, "desc": "[DEMO] City Center Mall Monthly Parking Voucher"},
    ]

    # Fuel / Energy fill-up and charging sessions
    fuel_specs = [
        # Creta (Petrol ~14 km/L, ~₹103.5/L)
        {"vehicle_key": "creta", "offset_days": 60, "dist": 480.0, "qty": 33.5, "cost": 3467.0, "fuel_type": "Petrol", "notes": "[DEMO] Highway run Bangalore to Mysore"},
        {"vehicle_key": "creta", "offset_days": 42, "dist": 420.0, "qty": 30.0, "cost": 3105.0, "fuel_type": "Petrol", "notes": "[DEMO] City office commuting"},
        {"vehicle_key": "creta", "offset_days": 28, "dist": 460.0, "qty": 32.0, "cost": 3312.0, "fuel_type": "Petrol", "notes": "[DEMO] Mixed suburban driving"},
        {"vehicle_key": "creta", "offset_days": 12, "dist": 500.0, "qty": 34.0, "cost": 3519.0, "fuel_type": "Petrol", "notes": "[DEMO] Full tank Shell V-Power"},
        # Nexon EV (Electric ~7.5 km/kWh, ~₹9-18/kWh)
        {"vehicle_key": "nexon_ev", "offset_days": 45, "dist": 210.0, "qty": 28.0, "cost": 252.0, "fuel_type": "Electric", "notes": "[DEMO] Home AC wallbox overnight charge (₹9/kWh)"},
        {"vehicle_key": "nexon_ev", "offset_days": 35, "dist": 230.0, "qty": 29.5, "cost": 265.5, "fuel_type": "Electric", "notes": "[DEMO] Domestic off-peak tariff 100% top-up"},
        {"vehicle_key": "nexon_ev", "offset_days": 20, "dist": 180.0, "qty": 24.0, "cost": 432.0, "fuel_type": "Electric", "notes": "[DEMO] Commercial 50kW DC fast charging (₹18/kWh)"},
        {"vehicle_key": "nexon_ev", "offset_days": 5, "dist": 240.0, "qty": 30.0, "cost": 270.0, "fuel_type": "Electric", "notes": "[DEMO] Home wallbox regular commute charge"},
        # City (Petrol ~15 km/L)
        {"vehicle_key": "city", "offset_days": 50, "dist": 450.0, "qty": 30.5, "cost": 3156.0, "fuel_type": "Petrol", "notes": "[DEMO] Ring road commute"},
        {"vehicle_key": "city", "offset_days": 30, "dist": 480.0, "qty": 32.0, "cost": 3312.0, "fuel_type": "Petrol", "notes": "[DEMO] Delhi - Gurgaon expressway run"},
        {"vehicle_key": "city", "offset_days": 14, "dist": 440.0, "qty": 29.5, "cost": 3053.0, "fuel_type": "Petrol", "notes": "[DEMO] Full tank Indian Oil"},
        # Swift (Diesel ~19 km/L, ~₹90/L)
        {"vehicle_key": "swift", "offset_days": 50, "dist": 620.0, "qty": 32.0, "cost": 2880.0, "fuel_type": "Diesel", "notes": "[DEMO] Highway trip to Hassan"},
        {"vehicle_key": "swift", "offset_days": 30, "dist": 580.0, "qty": 31.5, "cost": 2835.0, "fuel_type": "Diesel", "notes": "[DEMO] Regular city diesel fill"},
        {"vehicle_key": "swift", "offset_days": 14, "dist": 540.0, "qty": 30.0, "cost": 2700.0, "fuel_type": "Diesel", "notes": "[DEMO] BPCL high-speed diesel"},
        # Thar (Diesel ~9.8 km/L, high consumption)
        {"vehicle_key": "thar", "offset_days": 45, "dist": 380.0, "qty": 38.5, "cost": 3465.0, "fuel_type": "Diesel", "notes": "[DEMO] Heavy consumption, exhaust smoke observed"},
        {"vehicle_key": "thar", "offset_days": 22, "dist": 360.0, "qty": 37.0, "cost": 3330.0, "fuel_type": "Diesel", "notes": "[DEMO] Low fuel efficiency due to misfire condition"},
        # Fortuner (Diesel ~11.5 km/L)
        {"vehicle_key": "fortuner", "offset_days": 55, "dist": 580.0, "qty": 50.0, "cost": 4500.0, "fuel_type": "Diesel", "notes": "[DEMO] Delhi - Chandigarh return run"},
        {"vehicle_key": "fortuner", "offset_days": 32, "dist": 610.0, "qty": 52.5, "cost": 4725.0, "fuel_type": "Diesel", "notes": "[DEMO] Highway expedition full tank"},
        {"vehicle_key": "fortuner", "offset_days": 10, "dist": 560.0, "qty": 49.0, "cost": 4410.0, "fuel_type": "Diesel", "notes": "[DEMO] Premium diesel fill HPCL"},
        # Baleno (CNG in kg! ~25.5 km/kg, ~₹86/kg)
        {"vehicle_key": "baleno", "offset_days": 40, "dist": 230.0, "qty": 9.0, "cost": 774.0, "fuel_type": "CNG", "notes": "[DEMO] Adani Gas Ahmedabad CNG station (₹86/kg)"},
        {"vehicle_key": "baleno", "offset_days": 28, "dist": 250.0, "qty": 9.8, "cost": 842.8, "fuel_type": "CNG", "notes": "[DEMO] Full cylinder top-up (200 bar)"},
        {"vehicle_key": "baleno", "offset_days": 18, "dist": 220.0, "qty": 8.6, "cost": 739.6, "fuel_type": "CNG", "notes": "[DEMO] City courier run CNG fill"},
        {"vehicle_key": "baleno", "offset_days": 6, "dist": 260.0, "qty": 10.1, "cost": 868.6, "fuel_type": "CNG", "notes": "[DEMO] Highway commute to Vadodara"},
        # Polo (Petrol ~13.5 km/L)
        {"vehicle_key": "polo", "offset_days": 48, "dist": 440.0, "qty": 32.5, "cost": 3363.0, "fuel_type": "Petrol", "notes": "[DEMO] Chennai East Coast Road drive"},
        {"vehicle_key": "polo", "offset_days": 26, "dist": 420.0, "qty": 31.0, "cost": 3208.0, "fuel_type": "Petrol", "notes": "[DEMO] City stop-and-go commute"},
        {"vehicle_key": "polo", "offset_days": 9, "dist": 460.0, "qty": 34.0, "cost": 3519.0, "fuel_type": "Petrol", "notes": "[DEMO] Full tank Shell super petrol"},
    ]

    return {
        "vehicles": vehicles_data,
        "obd_specs": obd_specs,
        "diagnostic_specs": diagnostic_specs,
        "maintenance_specs": maintenance_specs,
        "standalone_expenses": standalone_expense_specs,
        "fuel_specs": fuel_specs,
    }


def validate_seed_data_against_schema(data):
    """
    Validates model constraints, foreign keys, non-null fields, and allowed values
    in memory before touching any persistent database records.
    """
    errors = []
    vehicle_keys = set()
    regs = set()

    # 1. Validate vehicles
    for v in data["vehicles"]:
        k = v["key"]
        if k in vehicle_keys:
            errors.append(f"Duplicate vehicle key: {k}")
        vehicle_keys.add(k)

        reg = v["registration_number"]
        if reg in regs:
            errors.append(f"Duplicate registration number: {reg}")
        regs.add(reg)

        if not (2 <= len(reg) <= 20):
            errors.append(f"Invalid registration length: {reg}")
        if v["fuel_type"] not in ALLOWED_FUEL_TYPES:
            errors.append(f"Invalid fuel type '{v['fuel_type']}' for {reg}")
        if v["service_history"] not in ALLOWED_SERVICE_HISTORIES:
            errors.append(f"Invalid service history '{v['service_history']}' for {reg}")
        if v["odometer_km"] < 0:
            errors.append(f"Negative odometer for {reg}")
        if v["reported_issues"] < 0:
            errors.append(f"Negative reported issues for {reg}")

    # 2. Validate OBD specs
    for o in data["obd_specs"]:
        vk = o["vehicle_key"]
        if vk not in vehicle_keys:
            errors.append(f"OBD spec references unknown vehicle key: {vk}")
        if o["coolant_temp_c"] is not None and not (0 <= o["coolant_temp_c"] <= 150):
            errors.append(f"Implausible coolant temp {o['coolant_temp_c']} for {vk}")
        if o["battery_voltage"] is not None and not (8.0 <= o["battery_voltage"] <= 16.0):
            errors.append(f"Implausible battery voltage {o['battery_voltage']} for {vk}")

    # 3. Validate Diagnostics
    for d in data["diagnostic_specs"]:
        vk = d["vehicle_key"]
        if vk not in vehicle_keys:
            errors.append(f"Diagnostic spec references unknown vehicle key: {vk}")

    # 4. Validate Maintenance
    for m in data["maintenance_specs"]:
        vk = m["vehicle_key"]
        if vk not in vehicle_keys:
            errors.append(f"Maintenance spec references unknown vehicle key: {vk}")
        if m["service_category"] not in ALLOWED_MAINTENANCE_CATEGORIES:
            errors.append(f"Invalid maintenance category '{m['service_category']}'")
        if m["status"] not in ALLOWED_MAINTENANCE_STATUSES:
            errors.append(f"Invalid maintenance status '{m['status']}'")
        if m["cost"] < 0:
            errors.append(f"Negative maintenance cost for {vk}")

    # 5. Validate Expenses
    for e in data["standalone_expenses"]:
        vk = e["vehicle_key"]
        if vk not in vehicle_keys:
            errors.append(f"Expense spec references unknown vehicle key: {vk}")
        if e["category"] not in ALLOWED_EXPENSE_CATEGORIES:
            errors.append(f"Invalid expense category '{e['category']}'")
        if e["amount"] <= 0:
            errors.append(f"Non-positive expense amount {e['amount']} for {vk}")

    # 6. Validate Fuel
    for f in data["fuel_specs"]:
        vk = f["vehicle_key"]
        if vk not in vehicle_keys:
            errors.append(f"Fuel spec references unknown vehicle key: {vk}")
        if f["dist"] <= 0 or f["qty"] <= 0 or f["cost"] <= 0:
            errors.append(f"Fuel quantities/costs must be positive for {vk}")
        if f["fuel_type"] not in ALLOWED_FUEL_TYPES:
            errors.append(f"Invalid fuel type '{f['fuel_type']}' in fuel records")

    return errors


def execute_reset_and_seeding(app, apply_changes: bool = False):
    """
    Orchestrates the dry-run or transactional reset and seed execution.
    """
    db_path = get_actual_sqlite_path(app)
    print("=" * 78)
    print(" CAR OS - DATABASE DEMO DATA RESET & SEEDING ENGINE")
    print("=" * 78)
    print(f"Target Database: {db_path}")
    print(f"Database Exists: {os.path.exists(db_path)}")
    if os.path.exists(db_path):
        print(f"Current Size:    {os.path.getsize(db_path):,} bytes")
    print("-" * 78)

    # 1. Before counts and table classification
    before_counts, all_tables, before_fk_issues = get_database_inventory(db_path)
    operational_tables = [t for t in OPERATIONAL_TABLES_CLEANUP_ORDER if t in all_tables]
    preserved_tables = [t for t in all_tables if t not in operational_tables]

    print("TABLES TARGETED FOR OPERATIONAL RESET (Strict deletion order):")
    for t in operational_tables:
        print(f"  * {t:<24} Current records: {before_counts.get(t, 0)}")

    print("\nTABLES PRESERVED (Non-operational / Schema / Metadata):")
    if preserved_tables:
        for t in preserved_tables:
            print(f"  * {t:<24} Current records: {before_counts.get(t, 0)}")
    else:
        print("  (None found in SQLite catalog -- schema tables and external assets remain intact)")

    if before_fk_issues:
        print(f"\n[WARNING] Found {len(before_fk_issues)} pre-existing foreign-key violations in target db:")
        for issue in before_fk_issues:
            print(f"   Table '{issue[0]}' rowid {issue[1]} references missing parent in '{issue[2]}'")
        print("   -> These orphaned records will be cleanly resolved during this operational reset.")

    # 2. Build seed data & validate against ORM schema
    print("\nBuilding and validating demonstration dataset...")
    seed_data = build_seed_dataset()
    val_errors = validate_seed_data_against_schema(seed_data)
    if val_errors:
        print("\n[CRITICAL ERROR] Seed data failed schema validation:")
        for err in val_errors:
            print(f"  - {err}")
        print("\nAborting without modifying database.")
        sys.exit(1)
    print("[OK] In-memory schema and validation rules passed successfully.")
    print(f"[OK] Planned vehicle count:        {len(seed_data['vehicles'])}")
    print(f"[OK] Planned maintenance entries: {len(seed_data['maintenance_specs'])}")
    print(f"[OK] Planned fuel/energy entries: {len(seed_data['fuel_specs'])}")
    print(f"[OK] Planned expense entries:     {len(seed_data['standalone_expenses']) + sum(1 for m in seed_data['maintenance_specs'] if m['link_expense'])}")
    print(f"[OK] Planned OBD telemetry rows:  {len(seed_data['obd_specs'])}")
    print(f"[OK] Planned manual diagnostics:  {len(seed_data['diagnostic_specs'])}")

    # 3. Dry-run Mode Check
    if not apply_changes:
        print("\n" + "#" * 78)
        print(" DRY RUN COMPLETE: NO DATABASE CHANGES APPLIED")
        print(" To execute the destructive cleanup and data replacement, run:")
        print(" python scripts/reset_demo_data.py --confirm-destructive-cleanup")
        print("#" * 78)
        return {
            "mode": "dry-run",
            "db_path": db_path,
            "before_counts": before_counts,
            "operational_tables": operational_tables,
            "preserved_tables": preserved_tables,
        }

    # 4. Destructive Application
    print("\n" + "!" * 78)
    print(" APPLYING DESTRUCTIVE OPERATIONAL CLEANUP & SEEDING TRANSACTION")
    print(" User explicitly selected NO BACKUP. Records are being replaced in-place.")
    print("!" * 78)

    today = date.today()
    base_time = datetime.now(timezone.utc).replace(tzinfo=None)

    with app.app_context():
        # Start transactional block
        session = db.session
        try:
            # Step A: Delete child records in safe dependency order
            print("\nPurging old operational records (FK-safe order)...")
            deleted_counts = {}
            for table_name in OPERATIONAL_TABLES_CLEANUP_ORDER:
                model_class = {
                    "valuation_records": ValuationRecord,
                    "diagnostic_records": DiagnosticRecord,
                    "obd_records": OBDRecord,
                    "fuel_records": FuelRecord,
                    "maintenance_records": MaintenanceRecord,
                    "expense_records": ExpenseRecord,
                    "vehicles": Vehicle,
                }[table_name]

                count = model_class.query.count()
                model_class.query.delete()
                deleted_counts[table_name] = count
                print(f"  - Cleared {table_name:<22} ({count} deleted)")

            session.flush()

            # Step B: Insert vehicles
            print("\nInserting 8 realistic demonstration vehicles...")
            vehicle_map = {}
            for v_spec in seed_data["vehicles"]:
                veh = Vehicle(
                    make=v_spec["make"],
                    model=v_spec["model"],
                    variant=v_spec.get("variant"),
                    transmission=v_spec.get("transmission", "Manual"),
                    registration_number=v_spec["registration_number"],
                    manufacturing_year=v_spec["manufacturing_year"],
                    odometer_km=v_spec["odometer_km"],
                    fuel_type=v_spec["fuel_type"],
                    service_history=v_spec["service_history"],
                    reported_issues=v_spec["reported_issues"],
                    notes=v_spec["notes"],
                )
                session.add(veh)
                session.flush()
                vehicle_map[v_spec["key"]] = veh

            # Step C: Insert OBD telemetry records
            print("Inserting synthetic OBD-II telemetry records...")
            for o_spec in seed_data["obd_specs"]:
                veh = vehicle_map[o_spec["vehicle_key"]]
                obd_time = base_time - timedelta(days=o_spec["offset_days"])
                obd_rec = OBDRecord(
                    vehicle_id=veh.id,
                    timestamp=obd_time,
                    data_source=o_spec["data_source"],
                    connection_status=o_spec["connection_status"],
                    engine_rpm=o_spec["engine_rpm"],
                    vehicle_speed_kmh=o_spec["vehicle_speed_kmh"],
                    coolant_temp_c=o_spec["coolant_temp_c"],
                    engine_load_pct=o_spec["engine_load_pct"],
                    throttle_pos_pct=o_spec["throttle_pos_pct"],
                    fuel_system_status=o_spec["fuel_system_status"],
                    battery_voltage=o_spec["battery_voltage"],
                    dtc_codes=o_spec["dtc_codes"],
                    notes=o_spec["notes"],
                )
                session.add(obd_rec)
            session.flush()

            # Step D: Recalculate health scores & resale valuations using authoritative services
            print("Calculating derived health scores and resale values via CAR OS services...")
            for key, veh in vehicle_map.items():
                # Re-query latest OBD if any
                latest_obd = veh.obd_records.order_by(OBDRecord.timestamp.desc()).first()
                health = calculate_health_score(
                    veh.manufacturing_year,
                    veh.odometer_km,
                    veh.service_history,
                    veh.reported_issues,
                    obd_record=latest_obd,
                )
                veh.health_score = health["score"]
                veh.health_status = health["status"]

                valuation = calculate_resale_value(
                    veh.make,
                    veh.model,
                    veh.manufacturing_year,
                    veh.odometer_km,
                    health["score"],
                    fuel_type=veh.fuel_type or "Petrol",
                    engine="auto",
                )
                veh.estimated_resale_value = float(valuation["estimated_value"])
            session.flush()

            # Step E: Insert manual diagnostic entries
            print("Inserting manual diagnostic inspection entries...")
            for d_spec in seed_data["diagnostic_specs"]:
                veh = vehicle_map[d_spec["vehicle_key"]]
                diag_date = today - timedelta(days=d_spec["offset_days"])
                diag_rec = DiagnosticRecord(
                    vehicle_id=veh.id,
                    date=diag_date,
                    data_source=d_spec["data_source"],
                    dtc_code=d_spec["dtc_code"],
                    parameter_name=d_spec["parameter_name"],
                    parameter_value=d_spec["parameter_value"],
                    notes=d_spec["notes"],
                )
                session.add(diag_rec)
            session.flush()

            # Step F: Insert maintenance and linked expenses
            print("Inserting maintenance records and establishing anti-double-counting expense links...")
            for m_spec in seed_data["maintenance_specs"]:
                veh = vehicle_map[m_spec["vehicle_key"]]
                s_date = today - timedelta(days=m_spec["offset_days"])
                next_date = today + timedelta(days=m_spec["next_offset_days"])

                m_rec = MaintenanceRecord(
                    vehicle_id=veh.id,
                    service_date=s_date,
                    service_category=m_spec["service_category"],
                    component_name=m_spec["component_name"],
                    odometer_at_service=m_spec["odometer_at_service"],
                    description=m_spec["description"],
                    cost=m_spec["cost"],
                    parts_cost=m_spec["parts_cost"],
                    labour_cost=m_spec["labour_cost"],
                    next_service_date=next_date,
                    next_service_odometer=m_spec["next_service_odometer"],
                    status=m_spec["status"],
                    evidence_status=m_spec["evidence_status"],
                    workshop=m_spec["workshop"],
                )
                session.add(m_rec)
                session.flush()

                if m_spec["link_expense"]:
                    # Create linked expense record so TCO excludes it from non_maint_expenses
                    exp_rec = ExpenseRecord(
                        vehicle_id=veh.id,
                        date=s_date,
                        category="Maintenance & Repair",
                        amount=m_spec["cost"],
                        description=f"[DEMO LINKED EXPENSE] Invoice for {m_spec['component_name']}",
                        linked_maintenance_id=m_rec.id,
                    )
                    session.add(exp_rec)
                    session.flush()
                    m_rec.expense_id = exp_rec.id

            # Step G: Insert standalone expenses
            print("Inserting standalone operational expenses (Insurance, Fastag, Tax)...")
            for e_spec in seed_data["standalone_expenses"]:
                veh = vehicle_map[e_spec["vehicle_key"]]
                exp_date = today - timedelta(days=e_spec["offset_days"])
                exp_rec = ExpenseRecord(
                    vehicle_id=veh.id,
                    date=exp_date,
                    category=e_spec["category"],
                    amount=e_spec["amount"],
                    description=e_spec["desc"],
                    linked_maintenance_id=None,
                )
                session.add(exp_rec)
            session.flush()

            # Step H: Insert fuel/energy fill-up logs
            print("Inserting fuel and energy consumption records...")
            for f_spec in seed_data["fuel_specs"]:
                veh = vehicle_map[f_spec["vehicle_key"]]
                f_date = today - timedelta(days=f_spec["offset_days"])
                fuel_rec = FuelRecord(
                    vehicle_id=veh.id,
                    date=f_date,
                    distance_km=f_spec["dist"],
                    quantity=f_spec["qty"],
                    cost=f_spec["cost"],
                    fuel_type=f_spec["fuel_type"],
                    notes=f_spec["notes"],
                )
                session.add(fuel_rec)
            session.flush()

            # Step I: Calculate health scores and tri-tier valuations
            print("Calculating health scores and tri-tier valuations...")
            from routes.vehicle_routes import _compute_vehicle_scores
            for veh in vehicle_map.values():
                _compute_vehicle_scores(veh)
            session.flush()

            # Commit the full transaction
            session.commit()
            print("\n[OK] Database transaction committed successfully!")

        except Exception as e:
            session.rollback()
            print(f"\n[CRITICAL ERROR] Transaction rolled back due to error: {e}")
            raise e

    # 5. Post-verification
    after_counts, _, after_fk_issues = get_database_inventory(db_path)
    print("\n" + "=" * 78)
    print(" VERIFICATION & ROW COUNT SUMMARY")
    print("=" * 78)
    print(f"{'Table Name':<25} {'Before':<10} {'Deleted':<10} {'Inserted':<10} {'After':<10}")
    print("-" * 65)
    for t in OPERATIONAL_TABLES_CLEANUP_ORDER:
        b = before_counts.get(t, 0)
        d = deleted_counts.get(t, 0)
        a = after_counts.get(t, 0)
        ins = a  # Since table was completely replaced
        print(f"{t:<25} {b:<10} {d:<10} {ins:<10} {a:<10}")

    print("-" * 65)
    print("PRESERVED TABLES:")
    if preserved_tables:
        for t in preserved_tables:
            print(f"{t:<25} Before: {before_counts.get(t, 0)}  After: {after_counts.get(t, 0)} (Unchanged)")
    else:
        print("  All schema structures and application assets preserved.")

    print(f"\nForeign Key Integrity Check: {len(after_fk_issues)} issues found.")
    if after_fk_issues:
        for iss in after_fk_issues:
            print(f"  [ERROR] FK failure: {iss}")
    else:
        print("[OK] Zero foreign-key violations (PRAGMA foreign_key_check is completely clean).")

    return {
        "mode": "applied",
        "db_path": db_path,
        "before_counts": before_counts,
        "after_counts": after_counts,
        "deleted_counts": deleted_counts,
        "fk_issues": after_fk_issues,
    }


def main():
    parser = argparse.ArgumentParser(
        description="CAR OS Database Demo Data Reset & Seeding Script"
    )
    parser.add_argument(
        "--confirm-destructive-cleanup",
        "--apply",
        action="store_true",
        dest="apply",
        help="Explicit confirmation to execute destructive operational cleanup and seeding.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run validation and plan presentation without modifying the database (default).",
    )
    args = parser.parse_args()

    # Determine execution mode: apply only if explicitly flagged
    apply_mode = args.apply and not args.dry_run

    app = create_app("development")
    execute_reset_and_seeding(app, apply_changes=apply_mode)


if __name__ == "__main__":
    main()

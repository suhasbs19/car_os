# CAR OS: Intelligent Vehicle System and Cost Management Platform

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0.3-black.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite%203-lightgrey.svg)](https://www.sqlite.org/)
[![Scikit-Learn](https://img.shields.io/badge/ML-Scikit--Learn%201.6+-orange.svg)](https://scikit-learn.org/)
[![License](https://img.shields.io/badge/License-Academic%20Demo-green.svg)]()

> **Academic College Mini-Project**: A full-stack, end-to-end intelligent automotive management platform designed to track vehicle lifecycle health, operating expenditures, fuel/charging energy efficiency, scheduled maintenance reminders, diagnostic trouble codes (DTCs), prototype valuation estimates, and explainable **Maintain–Repair–Sell** decision recommendations.

---

## 📌 Table of Contents
1. [Project Overview](#-project-overview)
2. [Key Capabilities & Modules](#-key-capabilities--modules)
3. [Architecture & Design Decisions](#-architecture--design-decisions)
4. [Folder Structure](#-folder-structure)
5. [Installation & Setup](#-installation--setup)
6. [Quickstart (Run Application)](#-quickstart-run-application)
7. [Seeding Demonstration Data](#-seeding-demonstration-data)
8. [Machine Learning Engine](#-machine-learning-engine)
9. [REST API Documentation](#-rest-api-documentation)


---

## 🚗 Project Overview

Vehicle owners, fleet managers, and second-hand automobile buyers often struggle to maintain an accurate understanding of actual vehicle health, true operational running cost per kilometre, and the tipping point where cumulative repair expenditures outpace vehicle equity.

**CAR OS** solves this problem by integrating:
- **Telemetry & Lifecycle Records**: Centralized tracking of odometer, manufacturing year, and service history.
- **Rule-Based Explainable Health Scoring**: Deterministic formulas evaluating age, mileage, service compliance, and active defects.
- **Multi-Fuel & EV Energy Accounting**: Unified calculation supporting Petrol/Diesel/CNG ($km/L$) and Electric Vehicles ($km/kWh$).
- **Total Cost of Ownership (TCO)**: Complete expense analytics combining fuel/charging, preventive servicing, repairs, insurance, taxes, and tolls.
- **Decision Support System**: Objective rule criteria categorizing vehicles into **Maintain**, **Repair**, or **Sell** recommendations with full transparency.
- **Companion Machine Learning Pipelines**: Demonstrating applied supervised learning models (classification and regression) on baseline demonstration data.

---

## ⚡ Key Capabilities & Modules

| Module | Features & Capabilities |
| :--- | :--- |
| **Dashboard** | Fleet status overview, total active vehicles, average fleet health score, monthly expenditure breakdown, quick health status badges, and upcoming maintenance alerts. |
| **Vehicle Registry** | Complete CRUD operations for vehicles, registration validation, multi-fuel classification, automated health and resale value recomputation on save/update. |
| **Maintenance Management** | Service log history, component replacement records, odometer-at-service tracking, scheduled interval calculation, and overdue notification badges. |
| **Fuel & Charging Logs** | Fuel fill-ups (litres) and EV battery charging (kWh), fuel efficiency trend calculations, cost per unit, and cost per kilometre metrics. |
| **Expense Tracker** | Categorized non-fuel expenditures (Insurance, Taxes, FASTag Tolls, Detailing, Ad-hoc repairs) with double-counting prevention. |
| **Diagnostics & OBD-II** | Manual OBD-II DTC (Diagnostic Trouble Code) logging (e.g. `P0420`, `P0300`), parameter checks, battery voltage monitoring, and sensor readiness logs. |
| **Valuation Estimator** | Prototype residual market estimation in Indian Rupees (₹ INR) based on age depreciation curves, mileage degradation factors, and overall health multipliers. |
| **Maintain–Repair–Sell** | Algorithmic multi-factor decision engine balancing vehicle salvage value against rolling 12-month repair costs and critical defects. |

---

## 🏗 Architecture & Design Decisions

CAR OS follows modern software engineering best practices:

- **Backend**: Python 3 with Flask application factory pattern (`create_app`) and modular Blueprints (`routes/`).
- **Database / ORM**: SQLAlchemy 2.0 with SQLite relational storage. Foreign keys, cascades, and compound index optimizations for analytical queries.
- **Frontend**: Clean, responsive Vanilla HTML5, modern CSS3 design system with CSS custom properties (variables), semantic HTML, responsive tables, and interactive cards.
- **Explainability Over Black Boxes**: In critical automotive decision-making, deterministic formulas guarantee auditability and eliminate hallucinated advice. ML models are provided as analytical extensions clearly distinguished from the core deterministic rules.

---

## 📂 Folder Structure

```
d:\caros\
├── app.py                     # Flask Application Factory and template filters
├── run.py                     # Application startup entry point
├── config.py                  # Environment configurations (Dev, Test, Prod)
├── requirements.txt           # Python dependency requirements
├── seed_data.py               # Database seeder with realistic demo fleet
│
├── models/
│   ├── __init__.py            # SQLAlchemy database instance export
│   └── vehicle_models.py      # Vehicle, Maintenance, Fuel, Expense, Diagnostic ORM models
│
├── routes/
│   ├── vehicle_routes.py      # Vehicle CRUD endpoints & details view
│   ├── maintenance_routes.py  # Service record routes & reminder handlers
│   ├── fuel_routes.py         # Refuelling and EV charging routes
│   └── analytics_routes.py    # Dashboard, reports, valuation & decision views
│
├── services/
│   ├── health_service.py      # Deterministic health scoring algorithm (0-100)
│   ├── valuation_service.py   # Depreciation & resale value estimator (₹ INR)
│   ├── fuel_service.py        # Fuel economy (km/L & km/kWh) and cost/km
│   ├── maintenance_service.py # Preventative maintenance reminder engine
│   └── decision_service.py    # Maintain vs Repair vs Sell decision logic
│
├── ml/
│   ├── train_models.py        # Supervised ML training pipelines (RF & Gradient Boosting)
│   ├── evaluation.py          # Model metrics (MAE, RMSE, R², classification report)
│   ├── predict.py             # Model inference & status transparency provider
│   └── saved_models/          # Serialized scikit-learn models (*.pkl)
│
├── templates/                 # Jinja2 HTML templates
│   ├── base.html              # Core navigation layout and design tokens
│   ├── index.html             # Main dashboard with KPI cards and fleet tables
│   ├── vehicles.html          # Vehicle directory
│   ├── add_vehicle.html       # Vehicle registration form
│   ├── vehicle_detail.html    # Single vehicle deep-dive & audit log
│   ├── maintenance.html       # Maintenance log & reminders
│   ├── add_maintenance.html   # Service entry form
│   ├── fuel.html              # Fuel and charging logs
│   ├── add_fuel.html          # Refuel / charge entry form
│   ├── expenses.html          # Expense registry
│   ├── add_expense.html       # Expense entry form
│   ├── diagnostics.html       # OBD-II diagnostics log
│   ├── add_diagnostic.html    # Diagnostic entry form
│   ├── valuation.html         # Fleet valuation summary
│   ├── decisions.html         # Maintain–Repair–Sell overview
│   ├── decision_detail.html   # Vehicle-specific decision breakdown
│   └── reports.html           # Fleet cost and usage summaries
│
├── static/
│   ├── css/
│   │   └── main.css           # Premium responsive styling and theme variables
│   └── js/
│       └── main.js            # Dynamic DOM interactions and dismissible alerts
│
├── tests/
│   ├── test_calculations.py   # Unit tests for scoring and valuation boundaries
│   ├── test_vehicles.py       # CRUD & validation tests with in-memory SQLite
│   └── test_api.py            # End-to-end blueprint & service integration tests
│
└── instance/
    └── caros.db               # SQLite database file (generated automatically)
```

---

## ⚙ Installation & Setup

### Prerequisites
- Python 3.10, 3.11, 3.12, or 3.14
- Virtual environment support (`venv`)

### 1. Activate Virtual Environment
On Windows PowerShell:
```powershell
cd d:\caros
.\venv\Scripts\Activate.ps1
```
*(Or create a new venv: `python -m venv venv`)*

### 2. Install Required Dependencies
```powershell
pip install -r requirements.txt
```

---

## 🚀 Quickstart (Run Application)

### 1. Seed Initial Demonstration Data
To populate the database with 5 diverse sample vehicles (Petrol SUV, EV, Diesel Hatchback, Executive Sedan, High-mileage Utility 4x4) and comprehensive service/fuel records:
```powershell
python seed_data.py
```

### 2. Ingest Service History Dataset (Optional / Demonstrative)
CAR OS includes an audited dataset ingestion engine for `CAR_OS_Dataset_Service_History_VISIBLE.xlsx`:
- **Web UI**: Navigate to `http://127.0.0.1:5000/maintenance/import` to inspect sheets, review algorithm-suggested vehicle mappings, and run simulation (dry run) or live database ingestion.
- **REST API**:
  ```powershell
  # Inspect workbook metadata
  Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/dataset/inspect" -Method Get
  ```

### 3. Launch the Web Application
```powershell
python run.py
```
Open your browser and navigate to:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 🤖 Machine Learning Engine & Literature Survey Alignment

Grounding: 15 automotive literature survey papers (`CAR_OS_Literature_Survey_Detailed_Summary.pdf`) across predictive maintenance, resale valuation, driving telemetry, fuel economy, and EV battery SOH/SOC estimation.

CAR OS provides three supervised ML pipelines in `ml/train_models.py`:

1. **Health Status Classifier**:
   - Algorithm: `RandomForestClassifier` (100 estimators, balanced class weights, StandardScaler).
   - Features: `age`, `odometer`, `reported_issues`, `service_history`, `fuel_type`.
   - Target: `health_status` (`Healthy`, `Attention`, `Critical`).
2. **Resale Value Regressor**:
   - Algorithm: `GradientBoostingRegressor` (100 estimators).
   - Features: `age`, `odometer`, `reported_issues`, `health_score`, `service_history`, `fuel_type`.
   - Target: `resale_value` (Continuous INR ₹).
3. **Fuel / Energy Efficiency Regressor**:
   - Algorithm: `Ridge` regression (alpha=1.0).
   - Features: `age`, `odometer`, `reported_issues`, `health_score`, `fuel_type`.
   - Target: `fuel_efficiency` ($km/L$ for ICE, $km/kWh$ for EV).

### Training the Models:
```powershell
python ml/train_models.py
```

### Running Formal Model Evaluation & Audit:
```powershell
python ml/evaluation.py
```

> **Academic Integrity Notice**: As documented in literature survey paper 12 (Mahale et al.) regarding severe class imbalance and paper 13 (Abderrachid et al.) regarding temporal failure degradation, the 32 service records in the demonstration Excel file contain no ground-truth component failure targets. CAR OS retains transparent rule-based heuristics as its primary, audited authority, while providing ML models as companion comparative estimators with full disclosure of synthetic demonstration data.

---

## 🌐 REST API Documentation

CAR OS exposes clean JSON endpoints for headless integration:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/dashboard` | Fleet KPI metrics, status distributions, upcoming service count |
| `GET` | `/api/vehicles` | List all vehicles with health scores and resale values |
| `GET` | `/api/vehicles/<id>` | Full JSON payload for a single vehicle |
| `DELETE` | `/api/vehicles/<id>` | Delete vehicle and cascade associated records |
| `GET` | `/api/maintenance` | List maintenance records across fleet |
| `GET` | `/api/dataset/inspect` | Inspect sheets, row counts, and mapping candidates in Excel dataset |
| `POST` | `/api/dataset/import` | Execute preview (dry-run) or live idempotent service history ingestion |
| `GET` | `/api/ml/status` | Model status, active algorithms, confusion matrix, and transparency notices |
| `GET` | `/api/reports` | Fleet cost summaries, total expenditures, and cost per km |

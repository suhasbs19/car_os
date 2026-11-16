# CAR OS — Indian Vehicle Maintenance Cost Analysis Report

**Date of Report:** October 28, 2026  
**Dataset Reference:** `dataset/Vehicle Maintenance- Service Records.csv`  
**Service Implementation:** `services/maintenance_budget_service.py`  
**Regression Test Suite:** `tests/test_indian_datasets_integration.py`  

---

## 1. Executive Summary

To support preventive maintenance budgeting and realistic scheduled service forecasting in CAR OS, the audited Indian vehicle maintenance dataset was integrated into a dedicated service layer (`services/maintenance_budget_service.py`).

Rather than treating these historical records as unpredictable mechanical breakdowns, the analysis recognizes them as **periodic scheduled service records** (10,000 km interval packages). The resulting engine provides vehicle owners with an empirical forecast of upcoming service intervals (10k, 20k, 30k, 40k, 50k, 60k, 70k, 80k, 90k, 100k km), recommended inspection checklists, and expected cost bands in Indian Rupees (INR ₹).

---

## 2. Dataset Ingestion & Data Hygiene

### 2.1 File & Schema Specifications
- **Source File:** `dataset/Vehicle Maintenance- Service Records.csv`
- **File Size:** 137,390 bytes
- **Record Count:** 1,139 service records
- **Total Columns:** 24 columns
- **Geography:** Service centers in Mumbai and Chennai.
- **Currency & Units:** Currency is in Indian Rupees (₹ INR); vehicle distance is in kilometres (km).

### 2.2 Misspelled Column Handling
The dataset contains a notable typo in column 21: `whell_alignment_and_balancing`.
- **Policy:** The original CSV file is preserved with 100% byte fidelity.
- **Normalization:** In `services/maintenance_budget_service.py`, the processing layer maps this column to the standardized attribute `wheel_alignment_and_balancing`.

### 2.3 Brand & Model Coverage
The dataset covers two manufacturers across four distinct models:
1. **Honda:** Jazz, Amaze, City (Hatchback and Sedans)
2. **Toyota:** Fortuner (Full-size SUV)

---

## 3. Cost Analysis & Component Replacement Patterns

### 3.1 Service Cost Distribution by Model
| Brand | Model | Sample Records | Median Cost (₹) | Mean Cost (₹) | Std Dev (₹) | Min (₹) | Max (₹) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Honda** | **Jazz** | 321 | ₹2,335.00 | ₹2,746.52 | ₹1,570.61 | ₹767.00 | ₹12,185.00 |
| **Honda** | **Amaze** | 305 | ₹2,450.00 | ₹2,889.34 | ₹1,612.44 | ₹812.00 | ₹11,940.00 |
| **Honda** | **City** | 298 | ₹2,510.00 | ₹3,014.18 | ₹1,685.20 | ₹845.00 | ₹12,850.00 |
| **Toyota** | **Fortuner** | 215 | ₹4,596.00 | ₹4,812.90 | ₹1,984.10 | ₹1,250.00 | ₹14,210.00 |

### 3.2 Key Findings: Fixed-Price Service Packages
- Across the 1,139 records, a substantial proportion of Toyota Fortuner routine service visits record an exact service package price of **₹4,596.00** (reflecting Toyota's standardized periodic maintenance package in authorized dealerships).
- For Honda models, routine minor services (lube, engine oil, oil filter) cluster between **₹2,335.00 and ₹2,510.00**.
- Major service milestones (40,000 km, 80,000 km, 100,000 km) introduce component replacements (spark plugs, transmission fluid, coolant, brake pads) that push service bills to between **₹5,500.00 and ₹12,500.00**.

### 3.3 Component Replacement Frequencies (14 Tracked Items)
The 14 component replacement flags were evaluated across all 1,139 service events:

| Component Flag | Overall Replacement Rate (%) | Primary Service Interval |
| :--- | :--- | :--- |
| **Engine Oil** | 98.4% | Every 10,000 km / 1 Year |
| **Oil Filter** | 96.8% | Every 10,000 km / 1 Year |
| **Air Filter** | 58.2% | Every 20,000 km |
| **Cabin/AC Filter** | 52.1% | Every 20,000 km |
| **Wheel Alignment & Balancing** | 64.7% | Every 10,000 km |
| **Brake Pads (Front/Rear)** | 24.3% | 30,000 – 40,000 km |
| **Brake Fluid** | 31.8% | Every 40,000 km / 2 Years |
| **Coolant Flush** | 22.4% | Every 40,000 – 50,000 km |
| **Spark Plugs (Petrol)** | 18.9% | 40,000 km (Nickel) / 100,000 km (Iridium) |
| **Transmission Fluid** | 14.2% | Every 40,000 – 60,000 km |
| **Battery Replacement** | 8.6% | 3 to 4 Years (~40,000 – 50,000 km) |
| **Tyre Replacement** | 6.1% | 40,000 – 60,000 km |
| **Wiper Blades** | 34.5% | Annual monsoon prep (~10,000 – 20,000 km) |
| **Fuel Filter** | 19.7% | Every 40,000 km |

---

## 4. Scheduling & Budget Estimator Implementation

### 4.1 Interval Milestone Calculation
Given a vehicle's current odometer reading `current_odometer_km`:
$$\text{next\_milestone} = \left(\lfloor \text{current\_odometer\_km} / 10000 \rfloor + 1\right) \times 10000$$
$$\text{km\_remaining} = \max(0, \text{next\_milestone} - \text{current\_odometer\_km})$$

### 4.2 Segment-Based Fallback for Unsupported Makes
Because the dataset is specific to Honda and Toyota records:
- Supported makes/models use the empirical model-specific cost distributions.
- Unsupported makes/models (e.g., Maruti Suzuki, Hyundai, Tata, Mahindra) are gracefully mapped to a matching vehicle segment benchmark (Hatchback, Sedan, SUV, EV) computed from the dataset without failing or throwing unhandled exceptions.

### 4.3 Strict TCO & Incurred Expense Independence
A critical architectural boundary is enforced:
1. **Never Insert Incurred Expenses:** The estimated budget is calculated in-memory on demand. It is **never** inserted into the `expense_record` or `maintenance_record` database tables.
2. **No Double Counting:** The Total Cost of Ownership (TCO) in reports and vehicle profiles continues to sum only *actual incurred expenses* (`total_maint_cost + total_fuel_cost + total_expenses`).
3. **UI Transparency:** The vehicle details template (`templates/vehicle_detail.html`) renders the scheduled budget inside a distinct card with an explicit disclaimer:
   > *"Advisory Budget Only — Not an Incurred Expense. This is an informational scheduled service forecast based on empirical Indian dealership maintenance records. It is NOT an actual invoice and is NOT added to your recorded expenses or TCO."*

---

## 5. Limitations & Future Scope

1. **Geographical Limitation:** The records originate exclusively from Mumbai and Chennai authorised centers. Tier-2/Tier-3 city labor rates and non-metro independent garage pricing are not represented.
2. **Make Limitations:** The dataset is limited to Honda and Toyota. Future versions can incorporate crowdsourced or fleet maintenance records for Maruti Suzuki, Tata Motors, and Hyundai to expand empirical brand coverage.
3. **Unscheduled Repairs:** Major collision repairs, transmission overhauls, and engine rebuilds are not scheduled services and fall outside the scope of this estimator.

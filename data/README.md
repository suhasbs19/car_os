# CAR OS - Reference Datasets & Catalogs

This directory contains standardized, maintainable vehicle pricing and OBD reference datasets utilized across CAR OS services.

## Datasets in `data/`

### 1. `indian_starting_prices_top5.csv` & `.json`
- **Source Document:** `dataset/Top5_Car_Brands_India_Prices_15plus.pdf`
- **Compiled Provenance:** Autocar India, 91Wheels, CarDekho, CarOnPhone, CarTrade, Rushlane (2026 price lists; compiled 28 Oct 2026)
- **Scope:** 74 popular passenger vehicle models across top 5 Indian brands:
  - Maruti Suzuki (16 models)
  - Tata Motors (15 models)
  - Mahindra (15 models)
  - Hyundai (15 models)
  - Toyota (13 models)
- **Key Semantics:** Starting ex-showroom prices ("From (Rs. lakh)") for base trims only. Never silently inferred for historical years or higher trims. Uncertainty notes preserved (e.g. e Vitara battery extra, Creta N Line source variations, Tucson facelift availability, Vellfire/Land Cruiser in Crore).

### 2. `indian_showroom_prices.csv`
- **Scope:** 102 verified variant-level historical ex-showroom prices across trims (2015–2025) for Hyundai, Tata, Maruti Suzuki, Honda, Mahindra, Toyota, Volkswagen, Kia, Skoda.
- **Key Semantics:** Strictly distinguishes ex-showroom from on-road costs. Used when exact variant + year match exists.

### 3. `obd_reference_parameters.json`
- **Scope:** Powertrain-differentiated OBD-II parameter ranges and PID applicability:
  - Petrol, CNG, Diesel, Hybrid, Electric (EV)
- **Key Safeguards:** 
  - Coolant Temp and Engine RPM marked non-applicable to EVs.
  - 12V Auxiliary Voltage explicitly separated from High-Voltage traction battery SOH/SOC.
  - Deviations treated as diagnostic indicators requiring technician inspection, not conclusive proof of mechanical component failure.
- **Note:** Document `OBD_Details_All_Cars.pdf` was not present on disk; reference parameters were grounded in SAE J1979/ISO 15031 standards and empirical `dataset/drive*.csv` telemetry.

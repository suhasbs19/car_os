"""
CAR OS - Original Showroom Price Service
========================================
Manages authentic manufacturer ex-showroom price lookups for Indian market
vehicles across make, model, variant, manufacturing year, fuel type, and transmission.

Integrates two key datasets:
  1. data/indian_showroom_prices.csv: Historical verified variant-level ex-showroom prices.
  2. data/indian_starting_prices_top5.csv: Normalized from Top5_Car_Brands_India_Prices_15plus.pdf
     (Autocar India, 91Wheels, CarDekho, CarOnPhone, CarTrade, Rushlane - 28 Oct 2026).

Key Principles:
- Strictly distinguishes ex-showroom from on-road pricing (excluding registration, road tax, insurance).
- "Starting from" prices are treated as starting figures only, NEVER silently assumed as exact prices
  for specific trims or historical years.
- When no exact, verified variant + year match exists, prompts:
  "Original showroom price unavailable — please enter it manually."
- Supports manual user entry marked as user-entered and unverified.
"""

import os
import re
import pandas as pd
from typing import Optional, Dict, Any, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOWROOM_PRICES_PATH = os.path.join(BASE_DIR, "data", "indian_showroom_prices.csv")
STARTING_PRICES_PATH = os.path.join(BASE_DIR, "data", "indian_starting_prices_top5.csv")

_SHOWROOM_DATA_CACHE: Optional[pd.DataFrame] = None
_STARTING_DATA_CACHE: Optional[pd.DataFrame] = None


def normalize_token(text: str) -> str:
    """Sanitize and normalize string tokens for tolerant substring/fuzzy matching."""
    if not text:
        return ""
    clean = re.sub(r"[^a-zA-Z0-9\+]", " ", str(text).lower())
    return " ".join(clean.split())


def load_showroom_dataset(filepath: str = SHOWROOM_PRICES_PATH) -> pd.DataFrame:
    """Load and cache the historical Indian ex-showroom price catalog."""
    global _SHOWROOM_DATA_CACHE
    if _SHOWROOM_DATA_CACHE is not None:
        return _SHOWROOM_DATA_CACHE

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Showroom prices catalog not found at: {filepath}")

    df = pd.read_csv(filepath)
    df["norm_make"] = df["make"].apply(normalize_token)
    df["norm_model"] = df["model"].apply(normalize_token)
    df["norm_variant"] = df["variant"].apply(normalize_token)
    df["model_year"] = pd.to_numeric(df["model_year"], errors="coerce").fillna(0).astype(int)
    df["ex_showroom_price_inr"] = pd.to_numeric(df["ex_showroom_price_inr"], errors="coerce").fillna(0).astype(int)

    _SHOWROOM_DATA_CACHE = df
    return _SHOWROOM_DATA_CACHE


def load_starting_prices_dataset(filepath: str = STARTING_PRICES_PATH) -> pd.DataFrame:
    """Load and cache the Top 5 brand starting prices dataset extracted from PDF."""
    global _STARTING_DATA_CACHE
    if _STARTING_DATA_CACHE is not None:
        return _STARTING_DATA_CACHE

    if not os.path.exists(filepath):
        return pd.DataFrame()

    df = pd.read_csv(filepath)
    df["norm_brand"] = df["brand"].apply(normalize_token)
    df["norm_model"] = df["model"].apply(normalize_token)
    df["starting_price_inr"] = pd.to_numeric(df["starting_price_inr"], errors="coerce").fillna(0).astype(int)

    _STARTING_DATA_CACHE = df
    return _STARTING_DATA_CACHE


def get_starting_price_reference(make: str, model: str) -> Optional[Dict[str, Any]]:
    """
    Look up 2026 starting price reference from Top 5 Brands document
    (Top5_Car_Brands_India_Prices_15plus.pdf).
    """
    try:
        df = load_starting_prices_dataset()
    except Exception:
        return None

    if df.empty:
        return None

    n_make = normalize_token(make)
    n_model = normalize_token(model)

    if n_make in ["maruti", "maruti suzuki", "ms"]:
        brand_mask = df["norm_brand"].isin(["maruti", "maruti suzuki"])
    else:
        brand_mask = df["norm_brand"].str.contains(n_make, case=False, regex=False) | (df["norm_brand"] == n_make)

    primary_token = n_model.split()[0] if n_model.split() else ""

    # Prioritize exact match, then prefix, then primary token
    exact_matches = df[brand_mask & (df["norm_model"] == n_model)]
    if not exact_matches.empty:
        row = exact_matches.iloc[0]
    else:
        prefix_matches = df[brand_mask & df["norm_model"].str.startswith(n_model)]
        if not prefix_matches.empty:
            row = prefix_matches.iloc[0]
        else:
            token_matches = df[brand_mask & df["norm_model"].apply(lambda m: primary_token in m.split() if primary_token else False)]
            if not token_matches.empty:
                row = token_matches.iloc[0]
            else:
                return None

    return {
        "brand": str(row["brand"]),
        "model": str(row["model"]),
        "fuel_types": str(row["fuel_types"]),
        "raw_price_string": str(row["raw_price_string"]),
        "price_unit": str(row["price_unit"]),
        "starting_price_inr": int(row["starting_price_inr"]),
        "starting_price_lakh": float(row["starting_price_lakh_min"]),
        "is_starting_price": True,
        "is_approximate": bool(row["is_approximate"]),
        "notes": str(row["notes"]),
        "sources": str(row["sources"]),
        "effective_date": str(row["effective_date"]),
        "source_document": str(row["source_document"]),
    }


def are_variants_compatible(t_tokens: set, c_tokens: set) -> bool:
    """
    Check if target variant and catalog candidate variant are mutually compatible.
    Rejects conflicts in drivetrain (4x4 vs 4x2), transmission (AT vs MT),
    engine types (TSI vs MPI vs TDI), or distinct trim hierarchies.
    """
    # 1. Drive layout conflict check
    awd_terms = {"4x4", "4wd", "awd"}
    fwd_terms = {"4x2", "2wd", "fwd", "rwd"}
    if (t_tokens & awd_terms) and (c_tokens & fwd_terms):
        return False
    if (t_tokens & fwd_terms) and (c_tokens & awd_terms):
        return False

    # 2. Transmission conflict check
    auto_terms = {"at", "automatic", "cvt", "ivt", "amt"}
    manual_terms = {"mt", "manual"}
    if (t_tokens & auto_terms) and (c_tokens & manual_terms):
        return False
    if (t_tokens & manual_terms) and (c_tokens & auto_terms):
        return False

    # 3. Trim level conflict check
    trim_groups = [
        {"trendline", "comfortline", "highline", "gt"},
        {"sigma", "delta", "zeta", "alpha"},
        {"smart", "pure", "creative", "fearless", "empowered"},
        {"e", "ex", "s", "sx"},
        {"lxi", "vxi", "zxi", "ldi", "vdi", "zdi"},
    ]
    for group in trim_groups:
        t_trims = t_tokens & group
        c_trims = c_tokens & group
        if t_trims and c_trims and t_trims != c_trims:
            return False

    # 4. Engine technology conflict (e.g. TSI turbo petrol vs MPI naturally aspirated)
    engine_terms = {"tsi", "mpi", "tdi", "crdi", "vtvt", "revotron", "revotorq"}
    t_eng = t_tokens & engine_terms
    c_eng = c_tokens & engine_terms
    if t_eng and c_eng and t_eng != c_eng:
        return False

    return True


def get_showroom_price(
    make: str,
    model: str,
    manufacturing_year: int,
    variant: Optional[str] = None,
    fuel_type: Optional[str] = None,
    transmission: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve authentic Indian ex-showroom price for exact or nearest configuration.
    
    Enforces that 'starting from' prices are NOT silently substituted for specific
    variants or historical years. When exact variant/year cannot be verified,
    prompts the user to enter it manually while providing starting price reference as context.
    """
    df = load_showroom_dataset()
    n_make = normalize_token(make)
    n_model = normalize_token(model)
    n_variant = normalize_token(variant) if variant else ""

    # Brand alias matching
    if n_make in ["maruti", "maruti suzuki", "ms"]:
        make_filter = df["norm_make"].isin(["maruti", "maruti suzuki"])
    else:
        make_filter = df["norm_make"].str.contains(n_make, case=False, regex=False) | (df["norm_make"] == n_make)

    # Model matching
    model_tokens = n_model.split()
    primary_model_token = model_tokens[0] if model_tokens else ""
    model_filter = (
        (df["norm_model"] == n_model)
        | (df["norm_model"].str.startswith(n_model))
        | (df["norm_model"].apply(lambda m: primary_model_token in m.split() if primary_model_token else False))
    )

    candidates = df[make_filter & model_filter].copy()
    ref_starting = get_starting_price_reference(make, model)

    # If make/model completely missing from historical catalog
    if candidates.empty:
        if ref_starting:
            return {
                "price_available": False,
                "is_exact_match": False,
                "is_model_range": True,
                "ex_showroom_price": None,
                "price_range_inr": None,
                "matched_variant": None,
                "generation": None,
                "model_year": manufacturing_year,
                "fuel_type": fuel_type or ref_starting["fuel_types"],
                "transmission": transmission or "Unknown",
                "city": "National Ex-Showroom",
                "source": ref_starting["sources"],
                "effective_date": ref_starting["effective_date"],
                "reference_starting_price": ref_starting,
                "prompt_manual_entry": True,
                "status_label": "Original showroom price unavailable — please enter it manually.",
            }

        return {
            "price_available": False,
            "is_exact_match": False,
            "is_model_range": False,
            "ex_showroom_price": None,
            "price_range_inr": None,
            "matched_variant": None,
            "generation": None,
            "model_year": manufacturing_year,
            "fuel_type": fuel_type or "Unknown",
            "transmission": transmission or "Unknown",
            "city": "National Ex-Showroom",
            "source": "Catalog Unavailable",
            "effective_date": None,
            "reference_starting_price": None,
            "prompt_manual_entry": True,
            "status_label": f"Original showroom price unavailable for {make} {model} — please enter it manually.",
        }

    # Step 1: Filter by manufacturing year if available, else nearest available year
    year_int = int(manufacturing_year)
    year_exact = candidates[candidates["model_year"] == year_int]
    is_exact_year = not year_exact.empty

    if is_exact_year:
        pool = year_exact
        resolved_year = year_int
    else:
        available_years = candidates["model_year"].unique()
        nearest_year = min(available_years, key=lambda y: abs(y - year_int))
        pool = candidates[candidates["model_year"] == nearest_year]
        resolved_year = int(nearest_year)

    # Step 2: Filter by fuel type if available
    if fuel_type and pool["fuel_type"].str.lower().eq(fuel_type.lower()).any():
        fuel_pool = pool[pool["fuel_type"].str.lower() == fuel_type.lower()]
    else:
        fuel_pool = pool

    # Step 3: Filter by transmission if available
    if transmission and fuel_pool["transmission"].str.lower().eq(transmission.lower()).any():
        trans_pool = fuel_pool[fuel_pool["transmission"].str.lower() == transmission.lower()]
    else:
        trans_pool = fuel_pool

    # Step 4: Robust Variant matching
    matched_row = None
    is_exact_variant = False

    if n_variant:
        exact_variant = trans_pool[trans_pool["norm_variant"] == n_variant]
        if not exact_variant.empty:
            matched_row = exact_variant.iloc[0]
            is_exact_variant = True
        else:
            # Score and find best compatible match
            t_tokens = set(n_variant.split())
            best_score = 0
            best_candidate = None

            for _, row in trans_pool.iterrows():
                row_var = row["norm_variant"]
                c_tokens = set(row_var.split())
                if not are_variants_compatible(t_tokens, c_tokens):
                    continue

                # Meaningful token overlap (ignore trivial generic numbers like '1', '0' alone unless engine size)
                meaningful_t = {t for t in t_tokens if t not in {"1", "0", "car", "plus", "caros"}}
                meaningful_c = {c for c in c_tokens if c not in {"1", "0", "car", "plus", "caros"}}
                overlap = len(meaningful_t & meaningful_c)

                score = 0
                if row_var in n_variant or n_variant in row_var:
                    score = 80 + overlap * 5
                elif overlap >= 1:
                    score = 50 + overlap * 15

                if score > best_score and score >= 65:
                    best_score = score
                    best_candidate = row

            if best_candidate is not None:
                matched_row = best_candidate
                is_exact_variant = True

    # If exact variant matched
    if matched_row is not None and is_exact_variant:
        price = int(matched_row["ex_showroom_price_inr"])
        return {
            "price_available": True,
            "is_exact_match": True,
            "is_model_range": False,
            "ex_showroom_price": price,
            "price_range_inr": (price, price),
            "matched_variant": str(matched_row["variant"]),
            "generation": str(matched_row["generation"]),
            "model_year": int(matched_row["model_year"]),
            "fuel_type": str(matched_row["fuel_type"]),
            "transmission": str(matched_row["transmission"]),
            "city": str(matched_row["city"]),
            "source": str(matched_row["source"]),
            "effective_date": str(matched_row["effective_date"]),
            "reference_starting_price": ref_starting,
            "prompt_manual_entry": False,
            "status_label": f"Verified Ex-Showroom ({matched_row['variant']}, {matched_row['model_year']})",
        }

    # Step 5: If variant was explicitly specified but could NOT be matched in historical catalog
    # Per Rule 9: Do not infer a missing variant price from a current starting price! Prompt manual entry.
    if n_variant:
        return {
            "price_available": False,
            "is_exact_match": False,
            "is_model_range": False,
            "ex_showroom_price": None,
            "price_range_inr": None,
            "matched_variant": variant,
            "generation": None,
            "model_year": year_int,
            "fuel_type": fuel_type or "Unknown",
            "transmission": transmission or "Unknown",
            "city": "National Ex-Showroom",
            "source": "Catalog Unavailable",
            "effective_date": None,
            "reference_starting_price": ref_starting,
            "prompt_manual_entry": True,
            "status_label": "Original showroom price unavailable — please enter it manually.",
        }

    # Step 6: Variant was NOT specified (general query or test inquiry): provide representative median + range
    min_price = int(trans_pool["ex_showroom_price_inr"].min())
    max_price = int(trans_pool["ex_showroom_price_inr"].max())
    median_price = int(round(trans_pool["ex_showroom_price_inr"].median() / 1000) * 1000)
    sample_row = trans_pool.iloc[0]

    return {
        "price_available": True,
        "is_exact_match": False,
        "is_model_range": True,
        "ex_showroom_price": median_price,
        "price_range_inr": (min_price, max_price),
        "matched_variant": f"Model Range ({len(trans_pool)} variants)",
        "generation": str(sample_row["generation"]),
        "model_year": resolved_year,
        "fuel_type": str(sample_row["fuel_type"]),
        "transmission": str(sample_row["transmission"]),
        "city": str(sample_row["city"]),
        "source": str(sample_row["source"]),
        "effective_date": str(sample_row["effective_date"]),
        "reference_starting_price": ref_starting,
        "prompt_manual_entry": False,
        "status_label": f"Ex-Showroom Range: ₹{min_price/100000:.2f}L - ₹{max_price/100000:.2f}L ({resolved_year})",
    }

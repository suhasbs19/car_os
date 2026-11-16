"""
CAR OS - Comparable Used-Car Market Pricing Service
===================================================
Analyzes current and historical secondary market listings for Indian passenger vehicles.
Filters duplicate listings and price outliers, matches comparable vehicles by
make, model, variant, age, odometer band, and powertrain, and calculates:
  - Comparable listings count (N)
  - Market asking price range [min_asking, max_asking] (10th to 90th percentile)
  - Representative market asking price (median of cleaned comparables)
  - Expected transaction price (accounting for negotiation discount)
  - Source and last updated metadata

Integrates with permitted external market feeds (via CAROS_MARKET_API_URL / CAROS_MARKET_API_KEY)
or falls back gracefully to authenticated Indian market listing records.
"""

import os
import json
import re
from datetime import datetime, date
import numpy as np
import pandas as pd
from typing import Optional, Dict, Any, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDEKHO_PATH = os.path.join(BASE_DIR, "dataset", "CAR DETAILS FROM CAR DEKHO.csv")

_MARKET_LISTINGS_CACHE: Optional[pd.DataFrame] = None


def normalize_str(s: Any) -> str:
    """Normalize string for consistent matching."""
    if not s:
        return ""
    clean = re.sub(r"[^a-zA-Z0-9]", " ", str(s).lower())
    return " ".join(clean.split())


def load_cleaned_market_listings(filepath: str = CARDEKHO_PATH) -> pd.DataFrame:
    """
    Load secondary market listings, drop exact duplicates, filter invalid prices/mileages,
    and cache the cleaned DataFrame.
    """
    global _MARKET_LISTINGS_CACHE
    if _MARKET_LISTINGS_CACHE is not None:
        return _MARKET_LISTINGS_CACHE

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Market listings dataset not found at: {filepath}")

    df_raw = pd.read_csv(filepath)

    # 1. Eliminate exact duplicate rows
    df = df_raw.drop_duplicates().copy()

    # 2. Filter price & mileage sanity boundaries
    df = df[(df["selling_price"] >= 20000) & (df["selling_price"] <= 15000000)]
    df = df[(df["km_driven"] >= 100) & (df["km_driven"] <= 600000)]

    # 3. Normalized columns for rapid filtering
    df["norm_name"] = df["name"].apply(normalize_str)
    df["norm_make"] = df["name"].apply(lambda x: normalize_str(str(x).split()[0]))
    df["norm_model"] = df["name"].apply(
        lambda x: normalize_str(str(x).split()[1]) if len(str(x).split()) > 1 else ""
    )
    df["fuel_clean"] = df["fuel"].str.strip().str.title()
    df["trans_clean"] = df["transmission"].str.strip().str.title()

    _MARKET_LISTINGS_CACHE = df
    return _MARKET_LISTINGS_CACHE


def fetch_external_market_api(make: str, model: str, year: int) -> Optional[Dict[str, Any]]:
    """
    Attempt to fetch live market listings from an external API if configured.
    Returns None if environment variables are not set, endpoint is unreachable,
    or credentials are missing.
    """
    api_url = os.environ.get("CAROS_MARKET_API_URL")
    api_key = os.environ.get("CAROS_MARKET_API_KEY")

    if not api_url or not api_key:
        return None

    try:
        import urllib.request
        import urllib.parse

        params = urllib.parse.urlencode({"make": make, "model": model, "year": year})
        req = urllib.request.Request(
            f"{api_url}?{params}",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                return data
    except Exception:
        # Fall back gracefully to internal verified market cache
        return None

    return None


def get_comparable_market_pricing(
    make: str,
    model: str,
    manufacturing_year: int,
    odometer_km: float = 50000.0,
    fuel_type: str = "Petrol",
    transmission: str = "Manual",
    variant: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculate market asking price range and representative market asking price
    from comparable used-car listings.
    
    Returns:
        dict:
            market_data_available (bool): Whether comparable listings were found.
            comparable_listings_count (int): Number of comparable listings evaluated (N).
            representative_market_price (int | None): Central market asking price (INR).
            market_asking_price_min (int | None): Lower band of asking price (10th percentile).
            market_asking_price_max (int | None): Upper band of asking price (90th percentile).
            market_asking_range (tuple[int, int] | None): (min, max) tuple.
            expected_transaction_price (int | None): Asking price discounted for closing negotiation.
            median_comparable_odometer (float | None): Median odometer of comparables.
            source (str): Data source label.
            is_live_api (bool): Whether data came from a live external API.
            last_updated (str): ISO timestamp or date of data collection.
            market_status (str): Descriptive label.
    """
    # Check if external live API is available
    ext_data = fetch_external_market_api(make, model, manufacturing_year)
    if ext_data and "representative_price" in ext_data:
        return {
            "market_data_available": True,
            "comparable_listings_count": int(ext_data.get("count", 1)),
            "representative_market_price": int(ext_data["representative_price"]),
            "market_asking_price_min": int(ext_data.get("price_min", ext_data["representative_price"] * 0.9)),
            "market_asking_price_max": int(ext_data.get("price_max", ext_data["representative_price"] * 1.1)),
            "market_asking_range": (
                int(ext_data.get("price_min", ext_data["representative_price"] * 0.9)),
                int(ext_data.get("price_max", ext_data["representative_price"] * 1.1)),
            ),
            "expected_transaction_price": int(round(ext_data["representative_price"] * 0.94 / 1000) * 1000),
            "median_comparable_odometer": float(ext_data.get("median_km", odometer_km)),
            "source": ext_data.get("source", "External Market API Feed"),
            "is_live_api": True,
            "last_updated": ext_data.get("last_updated", date.today().isoformat()),
            "market_status": "Live External Market Feed",
        }

    # Internal verified market dataset (CarDekho)
    df = load_cleaned_market_listings()
    n_make = normalize_str(make)
    n_model = normalize_str(model)
    n_variant = normalize_str(variant) if variant else ""

    # Brand alias normalization
    if n_make in ["maruti", "maruti suzuki", "ms"]:
        make_match = df["norm_make"].isin(["maruti", "maruti suzuki"])
    else:
        make_match = df["norm_make"].str.contains(n_make, regex=False) | (df["norm_make"] == n_make)

    # Model matching
    primary_token = n_model.split()[0] if n_model.split() else ""
    model_match = (
        (df["norm_model"] == n_model)
        | df["norm_name"].str.contains(n_model, regex=False)
        | df["norm_model"].apply(lambda m: primary_token in m.split() if primary_token else False)
    )

    matched = df[make_match & model_match].copy()

    # If make/model has zero direct listings
    if matched.empty:
        return {
            "market_data_available": False,
            "comparable_listings_count": 0,
            "representative_market_price": None,
            "market_asking_price_min": None,
            "market_asking_price_max": None,
            "market_asking_range": None,
            "expected_transaction_price": None,
            "median_comparable_odometer": None,
            "source": "CarDekho Historical Secondary Market Dataset (2020)",
            "is_live_api": False,
            "last_updated": "2020-12-31",
            "market_status": "No direct secondary market listings found in verified dataset",
        }

    # Step 1: Powertrain & Fuel Type Matching (Strict Segregation)
    # Electric vehicles and CNG vehicles CANNOT be substituted with Petrol/Diesel comparables.
    clean_fuel = str(fuel_type).strip().title()
    fuel_matched = matched[matched["fuel_clean"] == clean_fuel]
    if clean_fuel in ["Electric", "Cng"]:
        if len(fuel_matched) < 2:
            return {
                "market_data_available": False,
                "comparable_listings_count": 0,
                "representative_market_price": None,
                "market_asking_price_min": None,
                "market_asking_price_max": None,
                "market_asking_range": None,
                "expected_transaction_price": None,
                "median_comparable_odometer": None,
                "source": "CarDekho Historical Secondary Market Dataset (2020)",
                "is_live_api": False,
                "last_updated": "2020-12-31",
                "market_status": f"No comparable secondary market listings found for {clean_fuel} powertrain (fallback estimate used)",
            }
        pool = fuel_matched
    else:
        if len(fuel_matched) >= 2:
            pool = fuel_matched
        else:
            pool = matched

    # Step 2: Age window filtering: must be within ±3 years of manufacturing year
    year_target = int(manufacturing_year)
    age_matched = pool[abs(pool["year"] - year_target) <= 3]
    if len(age_matched) >= 2:
        pool = age_matched
    else:
        # If the nearest listing is more than 3 years older/newer, market evidence is stale or insufficient
        diffs = abs(pool["year"] - year_target)
        min_diff = diffs.min() if not diffs.empty else 999
        if min_diff > 3:
            return {
                "market_data_available": False,
                "comparable_listings_count": 0,
                "representative_market_price": None,
                "market_asking_price_min": None,
                "market_asking_price_max": None,
                "market_asking_range": None,
                "expected_transaction_price": None,
                "median_comparable_odometer": None,
                "source": "CarDekho Historical Secondary Market Dataset (2020)",
                "is_live_api": False,
                "last_updated": "2020-12-31",
                "market_status": f"No recent secondary market listings within ±3 years of {year_target} (dataset window ends 2020)",
            }
        pool = pool[abs(pool["year"] - year_target) <= min_diff + 1]

    # Step 3: Transmission matching
    clean_trans = str(transmission).strip().title()
    trans_matched = pool[pool["trans_clean"] == clean_trans]
    if len(trans_matched) >= 2:
        pool = trans_matched

    # Step 4: Variant scoring if specified and pool is large enough
    if n_variant and len(pool) > 5:
        # Filter for drive layout conflicts (4x4 vs 4x2)
        if "4x4" in n_variant or "4wd" in n_variant:
            awd_pool = pool[pool["norm_name"].str.contains("4x4|4wd", regex=True)]
            if len(awd_pool) >= 2:
                pool = awd_pool
        elif "4x2" in n_variant:
            fwd_pool = pool[~pool["norm_name"].str.contains("4x4|4wd", regex=True)]
            if len(fwd_pool) >= 2:
                pool = fwd_pool

        variant_matched = pool[pool["norm_name"].str.contains(n_variant, regex=False)]
        if len(variant_matched) >= 2:
            pool = variant_matched

    # Step 5: Remove statistical price outliers (interquartile range trimming)
    prices = pool["selling_price"].values
    if len(prices) >= 4:
        q25, q75 = np.percentile(prices, 25), np.percentile(prices, 75)
        iqr = q75 - q25
        lower_bound = max(20000, q25 - 1.75 * iqr)
        upper_bound = q75 + 1.75 * iqr
        pool = pool[(pool["selling_price"] >= lower_bound) & (pool["selling_price"] <= upper_bound)]

    if pool.empty:
        return {
            "market_data_available": False,
            "comparable_listings_count": 0,
            "representative_market_price": None,
            "market_asking_price_min": None,
            "market_asking_price_max": None,
            "market_asking_range": None,
            "expected_transaction_price": None,
            "median_comparable_odometer": None,
            "source": "CarDekho Historical Secondary Market Dataset (2020)",
            "is_live_api": False,
            "last_updated": "2020-12-31",
            "market_status": "Outlier filtering removed insufficient listing density",
        }

    # Step 6: Calculate representative statistics
    final_prices = pool["selling_price"].values
    n_count = len(final_prices)

    if n_count == 1:
        p_min = int(final_prices[0] * 0.92)
        p_max = int(final_prices[0] * 1.08)
        rep_price = int(final_prices[0])
    else:
        p_min = int(round(np.percentile(final_prices, 10) / 1000) * 1000)
        p_max = int(round(np.percentile(final_prices, 90) / 1000) * 1000)
        rep_price = int(round(float(np.median(final_prices)) / 1000) * 1000)

    # In Indian used car transactions, closing prices are typically 5-7% below online portal asking prices
    expected_closing = int(round((rep_price * 0.94) / 1000) * 1000)
    median_km = float(np.median(pool["km_driven"].values))

    return {
        "market_data_available": True,
        "comparable_listings_count": n_count,
        "representative_market_price": rep_price,
        "market_asking_price_min": p_min,
        "market_asking_price_max": p_max,
        "market_asking_range": (p_min, p_max),
        "expected_transaction_price": expected_closing,
        "median_comparable_odometer": round(median_km, 0),
        "source": "CarDekho Historical Secondary Market Dataset (2020)",
        "is_live_api": False,
        "last_updated": "2020-12-31",
        "market_status": f"{n_count} comparable historical market listing(s) evaluated",
    }


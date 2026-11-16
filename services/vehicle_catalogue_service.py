"""
CAR OS - Vehicle Catalogue & Make/Model Autocomplete Service
Loads unique makes and models from Indian automotive datasets (CarDekho)
with fallback to an empirical catalogue of Indian-market vehicles.
Provides debounced, case-insensitive, fuzzy/partial matching search.
"""
import os
import re
from typing import List, Dict, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDEKHO_PATH = os.path.join(BASE_DIR, "dataset", "CAR DETAILS FROM CAR DEKHO.csv")

# Baseline curated catalogue of popular Indian-market makes and models
# Ensures modern vehicles (e.g. EV models, post-2020 releases) and standard brands are always present
CURATED_INDIAN_CATALOGUE: List[Tuple[str, str]] = [
    # Maruti Suzuki
    ("Maruti Suzuki", "Swift"),
    ("Maruti Suzuki", "Dzire"),
    ("Maruti Suzuki", "Baleno"),
    ("Maruti Suzuki", "Brezza"),
    ("Maruti Suzuki", "Wagon R"),
    ("Maruti Suzuki", "Alto"),
    ("Maruti Suzuki", "Alto 800"),
    ("Maruti Suzuki", "Alto K10"),
    ("Maruti Suzuki", "Ertiga"),
    ("Maruti Suzuki", "Ciaz"),
    ("Maruti Suzuki", "Celerio"),
    ("Maruti Suzuki", "Ignis"),
    ("Maruti Suzuki", "S-Cross"),
    ("Maruti Suzuki", "Eeco"),
    ("Maruti Suzuki", "Omni"),
    ("Maruti Suzuki", "Grand Vitara"),
    ("Maruti Suzuki", "Fronx"),
    ("Maruti Suzuki", "Jimny"),
    ("Maruti Suzuki", "XL6"),
    ("Maruti Suzuki", "Invicto"),
    ("Maruti Suzuki", "S-Presso"),
    ("Maruti Suzuki", "800"),
    ("Maruti Suzuki", "Zen"),
    ("Maruti Suzuki", "Zen Estilo"),
    ("Maruti Suzuki", "Ritz"),
    ("Maruti Suzuki", "SX4"),
    ("Maruti Suzuki", "A-Star"),
    # Also support "Maruti" as make
    ("Maruti", "Swift"),
    ("Maruti", "Dzire"),
    ("Maruti", "Baleno"),
    ("Maruti", "Brezza"),
    ("Maruti", "Wagon R"),
    ("Maruti", "Alto"),
    ("Maruti", "Alto 800"),
    ("Maruti", "Alto K10"),
    ("Maruti", "Ertiga"),
    ("Maruti", "Ciaz"),
    ("Maruti", "Celerio"),
    ("Maruti", "Ignis"),
    ("Maruti", "S-Cross"),
    ("Maruti", "Eeco"),
    ("Maruti", "Omni"),
    ("Maruti", "Grand Vitara"),
    ("Maruti", "Fronx"),
    ("Maruti", "Jimny"),
    ("Maruti", "XL6"),
    ("Maruti", "S-Presso"),
    ("Maruti", "800"),
    ("Maruti", "Zen"),
    ("Maruti", "Zen Estilo"),
    ("Maruti", "Ritz"),
    ("Maruti", "SX4"),
    ("Maruti", "A-Star"),

    # Hyundai
    ("Hyundai", "Creta"),
    ("Hyundai", "Venue"),
    ("Hyundai", "i20"),
    ("Hyundai", "Grand i10"),
    ("Hyundai", "i10"),
    ("Hyundai", "Verna"),
    ("Hyundai", "Aura"),
    ("Hyundai", "Exter"),
    ("Hyundai", "Tucson"),
    ("Hyundai", "Alcazar"),
    ("Hyundai", "Santro"),
    ("Hyundai", "Santro Xing"),
    ("Hyundai", "Elantra"),
    ("Hyundai", "Xcent"),
    ("Hyundai", "Eon"),
    ("Hyundai", "Getz"),
    ("Hyundai", "Kona Electric"),
    ("Hyundai", "Ioniq 5"),

    # Tata
    ("Tata", "Nexon"),
    ("Tata", "Nexon EV"),
    ("Tata", "Punch"),
    ("Tata", "Punch EV"),
    ("Tata", "Harrier"),
    ("Tata", "Safari"),
    ("Tata", "Safari Storme"),
    ("Tata", "Tiago"),
    ("Tata", "Tiago EV"),
    ("Tata", "Tigor"),
    ("Tata", "Tigor EV"),
    ("Tata", "Altroz"),
    ("Tata", "Curvv"),
    ("Tata", "Indica"),
    ("Tata", "Indica Vista"),
    ("Tata", "Indica V2"),
    ("Tata", "Indigo"),
    ("Tata", "Indigo CS"),
    ("Tata", "Indigo Marina"),
    ("Tata", "Nano"),
    ("Tata", "Hexa"),
    ("Tata", "Aria"),
    ("Tata", "Sumo"),
    ("Tata", "Sumo Gold"),
    ("Tata", "Bolt"),
    ("Tata", "Zest"),

    # Mahindra
    ("Mahindra", "Scorpio"),
    ("Mahindra", "Scorpio-N"),
    ("Mahindra", "Scorpio Classic"),
    ("Mahindra", "Bolero"),
    ("Mahindra", "Bolero Neo"),
    ("Mahindra", "Thar"),
    ("Mahindra", "Thar Roxx"),
    ("Mahindra", "XUV700"),
    ("Mahindra", "XUV500"),
    ("Mahindra", "XUV300"),
    ("Mahindra", "XUV3XO"),
    ("Mahindra", "XUV400 EV"),
    ("Mahindra", "Xylo"),
    ("Mahindra", "Marazzo"),
    ("Mahindra", "KUV100"),
    ("Mahindra", "TUV300"),
    ("Mahindra", "Verito"),
    ("Mahindra", "Quanto"),

    # Honda
    ("Honda", "City"),
    ("Honda", "Amaze"),
    ("Honda", "Elevate"),
    ("Honda", "Civic"),
    ("Honda", "Jazz"),
    ("Honda", "WR-V"),
    ("Honda", "BR-V"),
    ("Honda", "CR-V"),
    ("Honda", "Brio"),
    ("Honda", "Mobilio"),
    ("Honda", "Accord"),

    # Toyota
    ("Toyota", "Innova"),
    ("Toyota", "Innova Crysta"),
    ("Toyota", "Innova Hycross"),
    ("Toyota", "Fortuner"),
    ("Toyota", "Fortuner Legender"),
    ("Toyota", "Glanza"),
    ("Toyota", "Urban Cruiser"),
    ("Toyota", "Urban Cruiser Hyryder"),
    ("Toyota", "Hilux"),
    ("Toyota", "Camry"),
    ("Toyota", "Corolla Altis"),
    ("Toyota", "Corolla"),
    ("Toyota", "Etios"),
    ("Toyota", "Etios Liva"),
    ("Toyota", "Etios Cross"),
    ("Toyota", "Yaris"),
    ("Toyota", "Qualis"),

    # Kia
    ("Kia", "Seltos"),
    ("Kia", "Sonet"),
    ("Kia", "Carens"),
    ("Kia", "Carnival"),
    ("Kia", "EV6"),

    # MG
    ("MG", "Hector"),
    ("MG", "Hector Plus"),
    ("MG", "ZS EV"),
    ("MG", "Astor"),
    ("MG", "Comet EV"),
    ("MG", "Gloster"),
    ("MG", "Windsor EV"),

    # Renault
    ("Renault", "Kwid"),
    ("Renault", "Triber"),
    ("Renault", "Kiger"),
    ("Renault", "Duster"),
    ("Renault", "Lodgy"),
    ("Renault", "Pulse"),
    ("Renault", "Scala"),
    ("Renault", "Captur"),

    # Volkswagen
    ("Volkswagen", "Polo"),
    ("Volkswagen", "Vento"),
    ("Volkswagen", "Taigun"),
    ("Volkswagen", "Virtus"),
    ("Volkswagen", "Tiguan"),
    ("Volkswagen", "Ameo"),
    ("Volkswagen", "Jetta"),
    ("Volkswagen", "Passat"),

    # Skoda
    ("Skoda", "Slavia"),
    ("Skoda", "Kushaq"),
    ("Skoda", "Octavia"),
    ("Skoda", "Superb"),
    ("Skoda", "Kodiaq"),
    ("Skoda", "Rapid"),
    ("Skoda", "Fabia"),
    ("Skoda", "Yeti"),
    ("Skoda", "Laura"),

    # Nissan
    ("Nissan", "Magnite"),
    ("Nissan", "Kicks"),
    ("Nissan", "Micra"),
    ("Nissan", "Sunny"),
    ("Nissan", "Terrano"),

    # Jeep
    ("Jeep", "Compass"),
    ("Jeep", "Meridian"),
    ("Jeep", "Wrangler"),

    # Ford
    ("Ford", "EcoSport"),
    ("Ford", "Endeavour"),
    ("Ford", "Figo"),
    ("Ford", "Aspire"),
    ("Ford", "Figo Aspire"),
    ("Ford", "Freestyle"),
    ("Ford", "Fiesta"),

    # Land Rover
    ("Land Rover", "Discovery Sport"),
    ("Land Rover", "Range Rover Evoque"),
    ("Land Rover", "Range Rover Velar"),
    ("Land Rover", "Defender"),

    # Mercedes-Benz
    ("Mercedes-Benz", "C-Class"),
    ("Mercedes-Benz", "E-Class"),
    ("Mercedes-Benz", "S-Class"),
    ("Mercedes-Benz", "GLA"),
    ("Mercedes-Benz", "GLC"),
    ("Mercedes-Benz", "GLE"),

    # BMW
    ("BMW", "3 Series"),
    ("BMW", "5 Series"),
    ("BMW", "X1"),
    ("BMW", "X3"),
    ("BMW", "X5"),

    # Audi
    ("Audi", "A4"),
    ("Audi", "A6"),
    ("Audi", "Q3"),
    ("Audi", "Q5"),
    ("Audi", "Q7"),
]

# Global cache
_CATALOGUE_CACHE: Optional[List[Dict[str, str]]] = None


def parse_cardekho_name(raw_name: str) -> Optional[Tuple[str, str]]:
    """
    Parse a CarDekho listing title into a clean (make, model) tuple.
    Extracts high-level model families rather than individual engine/trim variants.
    """
    if not raw_name or not isinstance(raw_name, str):
        return None
    name = raw_name.strip()
    if not name:
        return None

    # Handle known multi-word brand prefixes
    if name.startswith("Land Rover"):
        make = "Land Rover"
        rest = name[len("Land Rover"):].strip()
    elif name.startswith("Mercedes-Benz"):
        make = "Mercedes-Benz"
        rest = name[len("Mercedes-Benz"):].strip()
    elif name.startswith("Maruti Suzuki"):
        make = "Maruti Suzuki"
        rest = name[len("Maruti Suzuki"):].strip()
    else:
        parts = name.split()
        make = parts[0]
        rest = " ".join(parts[1:])

    # Clean rest
    if rest.startswith("New "):
        rest = rest[4:].strip()

    tokens = rest.split()
    if not tokens:
        return make, "Other"

    # Known multi-word model families in Indian context
    KNOWN_TWO_WORDS = {
        "wagon r", "vitara brezza", "swift dzire", "alto 800", "alto k10", "zen estilo",
        "grand i10", "elite i20", "i20 active", "santro xing",
        "corolla altis", "innova crysta", "etios liva", "etios cross", "urban cruiser",
        "safari storme", "indica vista", "indica v2", "indigo marina", "indigo ecs", "indigo cs", "sumo gold",
        "figo aspire", "range rover", "discovery sport", "verito vibe", "nexon ev", "punch ev",
        "c-class", "e-class", "s-class", "3 series", "5 series", "hector plus", "zs ev", "comet ev",
    }

    if len(tokens) >= 2:
        two_word_lower = f"{tokens[0]} {tokens[1]}".lower()
        if two_word_lower in KNOWN_TWO_WORDS:
            model = f"{tokens[0]} {tokens[1]}"
            return make, _normalize_model_name(model)

        # Check if second token is a well-known model suffix
        if tokens[1].lower() in {"800", "k10", "ev", "cross", "liva", "crysta", "altis", "brezza", "dzire", "xing"}:
            model = f"{tokens[0]} {tokens[1]}"
            return make, _normalize_model_name(model)

    # Single token model
    return make, _normalize_model_name(tokens[0])


def _normalize_model_name(name: str) -> str:
    """Format model name cleanly (e.g. 'Wagon R', 'i20', 'XUV700')."""
    words = name.strip().split()
    formatted = []
    for w in words:
        wl = w.lower()
        if wl in {"i10", "i20", "cr-v", "wr-v", "br-v"}:
            formatted.append(wl[0].lower() + wl[1:].upper())
        elif re.match(r"^[a-zA-Z]{1,3}\d{2,4}$", w):  # XUV700, KUV100, TUV300
            formatted.append(w.upper())
        elif wl in {"ev", "amg", "gti", "cng"}:
            formatted.append(wl.upper())
        else:
            formatted.append(w.capitalize())
    return " ".join(formatted)


def extract_catalogue_from_cardekho(csv_path: str = CARDEKHO_PATH) -> List[Tuple[str, str]]:
    """Extract unique make/model combinations from CarDekho CSV."""
    if not os.path.exists(csv_path):
        return []

    results = set()
    try:
        import csv
        with open(csv_path, mode="r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header or "name" not in header:
                return []
            name_idx = header.index("name")
            for row in reader:
                if len(row) > name_idx and row[name_idx].strip():
                    parsed = parse_cardekho_name(row[name_idx])
                    if parsed:
                        make, model = parsed
                        results.add((make, model))
                        if make == "Maruti":
                            results.add(("Maruti Suzuki", model))
    except Exception:
        return []

    return sorted(list(results))


def get_vehicle_catalogue(reload: bool = False) -> List[Dict[str, str]]:
    """
    Get the consolidated vehicle catalogue list.
    Each item is a dict: {'make': str, 'model': str, 'label': str}
    Cached in memory for high performance.
    """
    global _CATALOGUE_CACHE
    if _CATALOGUE_CACHE is not None and not reload:
        return _CATALOGUE_CACHE

    combined = set(CURATED_INDIAN_CATALOGUE)

    # Merge dataset if available
    if os.path.exists(CARDEKHO_PATH):
        try:
            from_csv = extract_catalogue_from_cardekho(CARDEKHO_PATH)
            for m, mod in from_csv:
                combined.add((m, mod))
        except Exception:
            pass

    # Build sorted dict list
    catalogue = []
    for make, model in sorted(list(combined), key=lambda x: (x[0].lower(), x[1].lower())):
        catalogue.append({
            "make": make,
            "model": model,
            "label": f"{make} {model}",
        })

    _CATALOGUE_CACHE = catalogue
    return _CATALOGUE_CACHE


def search_vehicle_catalogue(query: str, limit: int = 15) -> List[Dict[str, str]]:
    """
    Search the vehicle catalogue with debounced query.
    Supports:
    - Case-insensitive matching
    - Partial matching (substring and prefix)
    - Spaces in make and model names
    - Multi-token matching (e.g. 'maruti swift', 'nexon ev')
    - Proper ranking: prefix matches prioritized over loose substrings.
    """
    if not query or not query.strip():
        return []

    q = query.strip().lower()
    q_tokens = [t for t in re.split(r"[\s\-_]+", q) if t]
    catalogue = get_vehicle_catalogue()

    exact_matches = []
    prefix_full = []
    prefix_model = []
    prefix_make = []
    contains_all_tokens = []
    contains_query = []

    for item in catalogue:
        make = item["make"]
        model = item["model"]
        label = item["label"]

        make_l = make.lower()
        model_l = model.lower()
        label_l = label.lower()

        # 1. Exact match
        if label_l == q or model_l == q:
            exact_matches.append(item)
            continue

        # 2. Starts with query
        if label_l.startswith(q):
            prefix_full.append(item)
            continue

        # 3. Model starts with query
        if model_l.startswith(q):
            prefix_model.append(item)
            continue

        # 4. Make starts with query
        if make_l.startswith(q):
            prefix_make.append(item)
            continue

        # 5. Check if all query tokens match either make or model
        if q_tokens and all(token in label_l for token in q_tokens):
            contains_all_tokens.append(item)
            continue

        # 6. Query is substring
        if q in label_l:
            contains_query.append(item)

    # Combine with deterministic priority and deduplicate
    combined = []
    seen = set()
    for bucket in (exact_matches, prefix_full, prefix_model, prefix_make, contains_all_tokens, contains_query):
        for it in bucket:
            key = (it["make"], it["model"])
            if key not in seen:
                seen.add(key)
                combined.append(it)
                if len(combined) >= limit:
                    return combined

    return combined

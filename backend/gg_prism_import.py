import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

# --- LOCAL IMPORTS ---
from .path import prism_dump_dir

def _ensure_json(v: Any) -> Optional[Any]:
    """
    Helper to ensure data is a valid Python object (dict/list).
    Parses strings as JSON if necessary.
    """
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        s = v.strip()
        # Basic sanity check before trying to parse
        if s and s[0] in "[{":
            try:
                return json.loads(s)
            except Exception:
                return None
    return None

def _pretty_from_locale(locale_key: str) -> str:
    """
    Converts internal SteelSeries locale keys into human-readable names.
    Example: 'steelseriesOrange' -> 'SteelSeries Orange'
    """
    if not locale_key: return "Unknown"

    # Extract the tail (e.g., "features.lighting.presets.steelseriesOrange")
    tail = locale_key.split(".")[-1]

    special_cases = {
        "steelseriesOrange": "SteelSeries Orange",
        "reactiveLine": "Reactive - Line",
        "reactiveRipple": "Reactive - Ripple",
        "reactiveSingleKey": "Reactive - Single Key",
    }

    if tail in special_cases:
        return special_cases[tail]

    # Regex to split CamelCase into "Camel Case"
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tail)

    # Capitalize first letter
    if s:
        s = s[0].upper() + s[1:]

    return s.replace("Steelseries", "SteelSeries")

def load_gg_prism_presets(dump_dir: str) -> Dict[str, dict]:
    """
    Loads and normalizes Prism RGB presets from raw JSON dumps.

    This function is designed to handle different versions of the SteelSeries GG
    database schema by looking for multiple possible field names.

    Args:
        dump_dir: Directory containing the raw JSON files.

    Returns:
        Dict mapping readable Preset Names to their configuration dictionaries.
    """
    # Resolve directory path
    d = Path(dump_dir).expanduser() if dump_dir else prism_dump_dir()

    # Attempt to read both potential source files and merge their contents
    files_to_read = ["prism_presets_raw.json", "presets.json"]
    all_rows = []

    for fname in files_to_read:
        p = d / fname
        if p.exists():
            try:
                content = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(content, list):
                    all_rows.extend(content)
            except:
                pass

    if not all_rows:
        return {}

    presets: Dict[str, dict] = {}

    for r in all_rows:
        # --- FLEXIBLE DATA EXTRACTION ---
        # The schema often changes between 'name', 'name_locale_key', etc.

        # 1. Determine Name
        locale = r.get("name_locale_key") or r.get("name") or "Unknown"
        name = _pretty_from_locale(locale)

        # 2. Determine ID
        pid = r.get("id") or r.get("config_id")

        # 3. Determine Mode
        # If 'mode' is missing, it implies a standard 'base' layer in newer DBs.
        mode = r.get("mode", "base")

        # 4. Extract Configuration Data
        # 'configurations' table uses 'data', 'configs' table uses 'config_json' or 'json'
        raw_data = r.get("data") or r.get("config_json") or r.get("json")

        data_obj = _ensure_json(raw_data)

        # Validate Data Structure
        if not isinstance(data_obj, list):
            # Sometimes the JSON is wrapped in a container object {"data": [...]}
            if isinstance(data_obj, dict) and "data" in data_obj:
                 data_obj = data_obj["data"]
            else:
                continue # Skip invalid rows

        # Filter Modes: Only accept Base/Idle layers or standard defaults.
        # Note: We are permissive here because 'mode' is often missing in dumps.
        if mode not in ("baseOrIdle", "base", "idle", "default"):
            pass

        # Construct Normalized Config Object
        cfg = {
            "type": "gg_prism",
            "dump_dir": str(d),
            "gg": {
                "id": pid,
                "mode": mode,
                "requires_bitmap_coordinates": int(r.get("requires_bitmap_coordinates", 0) or 0),
                "name_locale_key": locale,
                "data": data_obj,
            }
        }

        # --- COLLISION HANDLING ---
        # If a preset with this name already exists (e.g. from multiple files),
        # keep the one with the larger data payload, assuming it is the "complete" version.
        if name in presets:
            current_len = len(str(presets[name]["gg"]["data"]))
            new_len = len(str(data_obj))

            if new_len > current_len:
                presets[name] = cfg
        else:
            presets[name] = cfg

    return presets

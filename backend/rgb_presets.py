import colorsys
import sys
import os

# --- IMPORTS ---
try:
    from backend.gg_prism_import import load_gg_prism_presets
    from backend.path import prism_dump_dir
except ImportError:
    # Allow running this file standalone for debugging/generation purposes
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from backend.gg_prism_import import load_gg_prism_presets
    from backend.path import prism_dump_dir

# --- CONSTANTS & CONFIGURATION ---

# The authoritative list of presets to be displayed in the UI.
# This ensures a consistent order and filters out broken/test presets found in raw DB dumps.
ORDERED_WANTED_NAMES = [
    "Off",
    "Apex Pro Actuation",
    "Aqua",
    "Chasing Ghosts",
    "Clown",
    "Color Fusion",
    "Comet",
    "Disco Mode",
    "Drain",
    "FaZe",
    "Freeway",
    "Haze",
    "Prism",
    "Radioactive Glow",
    "Rainbow",
    "Rainbow Split",
    "Self-Destruct",
    "Shaved Ice",
    "Solar",
    "Static Fade",
    "SteelSeries Orange",
    "SteelSeries Pride",
    "Twilight",
    "Vapor Dreams",
    "Wabash & Lake",
    "Warp Drive",
    "West Coast"
]

# Mapping table to normalize disparate naming conventions from different GG versions.
NAME_MAPPING = {
    "Chasing Ghosts": "Chasing Ghosts",
    "Faze": "FaZe",
    "Radioactive": "Radioactive Glow",
    "Self Destruct": "Self-Destruct",
    "Wabash And Lake": "Wabash & Lake",
    "Pride": "SteelSeries Pride",
    "Heatmap": "Apex Pro Actuation",
    "Disabled": "Off",
    "Base": "Prism",
    "Immutable Default": "Prism",
    "Rainbow": "Rainbow",
    "Color Shift": "Static Fade"
}

# Presets that are implemented manually in Python code, bypassing the Prism engine.
MANUAL_OVERRIDE_PRESETS = {
    "Apex Pro Actuation",
    "Disco Mode"
}

# Presets that structurally require the "Breathing" modifier flag to be forced on.
BREATH_PRESETS = {"FaZe", "Static Fade", "Solar"}

# --- HELPER FUNCTIONS ---

def _gen_rainbow(steps=30):
    """Generates a standard HSV rainbow palette."""
    palette = []
    for i in range(steps):
        hue = i / steps
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        palette.append((int(r * 255), int(g * 255), int(b * 255)))
    return palette

# --- MANUAL DEFINITIONS ---
RAINBOW_PALETTE = _gen_rainbow(40)
DEEP_BLUE = (7, 0, 112)

# Initialize dictionary with hardcoded implementations
PRESETS = {
    "Off": {"type": "static", "colors": [(0, 0, 0)]},
    "Apex Pro Actuation": {"type": "static", "colors": [DEEP_BLUE]},
    "Disco Mode": {"type": "disco", "colors": RAINBOW_PALETTE, "speed": 1.0, "density": 0.2},
}

# --- DYNAMIC IMPORT LOGIC ---
try:
    dump_path = str(prism_dump_dir())
    gg_data = load_gg_prism_presets(dump_path)
    # print(f"[Presets] Loaded {len(gg_data)} raw records.")

    for original_name, config in gg_data.items():
        # Clean up name (remove version numbers etc.)
        clean_name = original_name.split("(")[0].strip()
        target_name = NAME_MAPPING.get(clean_name, clean_name)

        if target_name in ORDERED_WANTED_NAMES:
            # Skip if we have a manual python implementation
            if target_name in MANUAL_OVERRIDE_PRESETS: continue

            # Apply specific modifiers
            if target_name in BREATH_PRESETS:
                config["is_breathe_preset"] = True

            # --- PATCH: Radioactive Glow ---
            # This specific preset needs a fixed origin at the Left Ctrl key to radiate correctly.
            # Coordinates reverse-engineered from zone_cache: Y=89 (Bottom row), X=147 (Left side).
            if target_name == "Radioactive Glow":
                try:
                    grp = config["gg"]["data"][0]["graphics"][0]
                    grp["foreground"]["origin"] = {"x": 147, "y": 89}
                    grp["foreground"]["isOriginFixed"] = True
                except (KeyError, IndexError, TypeError):
                    pass

            PRESETS[target_name] = config

except Exception as e:
    print(f"[Warning] GG Prism Import Failed: {e}")

# --- FINALIZATION ---
# Ensure every requested name exists to prevent UI crashes.
# If an effect failed to import, fallback to white static.
for name in ORDERED_WANTED_NAMES:
    if name not in PRESETS:
        PRESETS[name] = {"type": "static", "colors": [(255, 255, 255)]}

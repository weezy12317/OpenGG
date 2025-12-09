"""
This module handles the localization of key labels for the GUI.
It uses a 'diff-based' approach:
1. Define a standard US ANSI layout as the base.
2. Define language specific overrides (only keys that differ).
"""

# --- 1. DEFAULT LABELS (US ANSI Base) ---
DEFAULT_LABELS = {
    # Number Row & Symbols
    "grave": "`\n~",
    "1": "1\n!", "2": "2\n@", "3": "3\n#", "4": "4\n$", "5": "5\n%",
    "6": "6\n^", "7": "7\n&", "8": "8\n*", "9": "9\n(", "0": "0\n)",
    "minus": "-\n_", "equal": "=\n+",

    # Letters & Brackets
    "bracket_left": "[\n{", "bracket_right": "]\n}",
    "backslash": "\\\n|",
    "semicolon": ";\n:", "apostrophe": "\'\n\"",
    "comma": ",\n<", "dot": ".\n>", "slash": "/\n?",

    # Modifiers & Functional Keys
    "left_ctrl": "CTRL", "right_ctrl": "CTRL",
    "left_alt": "ALT", "right_alt": "ALT",
    "left_shift": "SHIFT", "right_shift": "SHIFT",
    "left_gui": "META", "right_gui": "META", # Windows/Command Key
    "enter": "ENTER", "backspace": "BACKSPACE",
    "caps_lock": "CAPS", "tab": "TAB",
    "esc": "ESC", "fn": "FN",
    "space": "",

    # Navigation Cluster
    "insert": "INS", "delete": "DEL", "home": "HOME", "end": "END",
    "page_up": "PU", "page_down": "PD",
    "print_screen": "PRT", "scroll_lock": "SCR", "pause": "PAU",
    "up": "↑", "down": "↓", "left": "←", "right": "→",

    # Numpad
    "num_lock": "NUM", "kp_slash": "/", "kp_asterisk": "*", "kp_minus": "-",
    "kp_7": "7", "kp_8": "8", "kp_9": "9", "kp_plus": "+",
    "kp_4": "4", "kp_5": "5", "kp_6": "6",
    "kp_1": "1", "kp_2": "2", "kp_3": "3", "kp_enter": "ENT",
    "kp_0": "0", "kp_dot": ".",

    # ISO Defaults (Generic Fallbacks if specific lang is missing)
    "iso_pipe": "< >\n|",
    "iso_hash": "#\n'",
}

# --- 2. LANGUAGE OVERRIDES ---
LANGUAGES = {
    "English (US)": {}, # Identity mapping

    "German (DE)": {
        # Letters (Y/Z Swap & Umlauts)
        "z": "Y", "y": "Z",
        "semicolon": "Ö", "apostrophe": "Ä", "bracket_left": "Ü",

        # Symbols
        "bracket_right": "+ \n *", "backslash": "# \n '", # ISO Hash (next to Enter)
        "minus": "ß \n ?", "equal": "´ \n `",
        "comma": ", \n ;", "dot": ". \n :", "slash": "- \n _",
        "grave": "^ \n °",
        "iso_pipe": "< \n >", # Key next to Left Shift

        # Number Row (Shift layer differs significantly)
        "2": "2 \n \"", "3": "3 \n §", "6": "6 \n &",
        "7": "7 \n /", "8": "8 \n (", "9": "9 \n )", "0": "0 \n =",

        # Modifiers
        "right_alt": "ALT\nGR",
        "left_ctrl": "STRG", "right_ctrl": "STRG",
        "delete": "ENTF", "insert": "EINF",
        "home": "POS1", "end": "ENDE",
        "page_up": "BILD\n↑", "page_down": "BILD\n↓",
        "print_screen": "DRUCK",
    },

    "English (UK)": {
        # UK is ISO but QWERTY
        "iso_hash": "# \n ~",
        "iso_pipe": "\\ \n |",
        "2": "2 \n \"", "3": "3 \n £",
        "apostrophe": "@ \n '",
        "grave": "` \n ¬",
        "backslash": "# \n ~"
    },
}

# --- 3. LOOKUP LOGIC ---

def get_key_label(lang_name, key_name):
    """
    Resolves the display label for a given key.

    Args:
        lang_name (str): Selected language (e.g. "German (DE)").
        key_name (str): Internal key identifier (e.g. "page_up").

    Returns:
        str: The localized label text (may contain newlines).
    """
    # 1. Check specific language pack
    if lang_name in LANGUAGES:
        lang_map = LANGUAGES[lang_name]
        if key_name in lang_map:
            return lang_map[key_name]

    # 2. Check defaults
    if key_name in DEFAULT_LABELS:
        return DEFAULT_LABELS[key_name]

    # 3. Fallback: Generate generic label (e.g. "f1" -> "F1")
    display = key_name.upper().replace("_", " ")

    # Shorten GUI/Meta to fit keycaps if missed in defaults
    if "GUI" in display: display = display.replace("GUI", "WIN")

    return display

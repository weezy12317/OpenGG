"""
This module defines the physical layout coordinates for the GUI renderer.
Coordinate Format: (x, y, width, height)
Units: Standard key width (1.0 = standard square key like 'A').

These coordinates are used by:
1. The GUI Visualizer (to draw the keyboard on screen).
2. The RGB Engine (to map spatial effects like 'Wave' to physical keys).
"""

# =============================================================================
# BASE LAYOUT BLOCKS
# =============================================================================

# Standard 60% ANSI Block (Alphanumeric Area)
BLOCK_60_ANSI = {
    # Row 1 (Numbers)
    'grave': (0, 1.5, 1, 1), '1': (1, 1.5, 1, 1), '2': (2, 1.5, 1, 1), '3': (3, 1.5, 1, 1),
    '4': (4, 1.5, 1, 1), '5': (5, 1.5, 1, 1), '6': (6, 1.5, 1, 1), '7': (7, 1.5, 1, 1),
    '8': (8, 1.5, 1, 1), '9': (9, 1.5, 1, 1), '0': (10, 1.5, 1, 1),
    'minus': (11, 1.5, 1, 1), 'equal': (12, 1.5, 1, 1), 'backspace': (13, 1.5, 2, 1),

    # Row 2 (Top Letters)
    'tab': (0, 2.5, 1.5, 1), 'q': (1.5, 2.5, 1, 1), 'w': (2.5, 2.5, 1, 1), 'e': (3.5, 2.5, 1, 1),
    'r': (4.5, 2.5, 1, 1), 't': (5.5, 2.5, 1, 1), 'y': (6.5, 2.5, 1, 1), 'u': (7.5, 2.5, 1, 1),
    'i': (8.5, 2.5, 1, 1), 'o': (9.5, 2.5, 1, 1), 'p': (10.5, 2.5, 1, 1),
    'bracket_left': (11.5, 2.5, 1, 1), 'bracket_right': (12.5, 2.5, 1, 1), 'backslash': (13.5, 2.5, 1.5, 1),

    # Row 3 (Home Row)
    'caps_lock': (0, 3.5, 1.75, 1), 'a': (1.75, 3.5, 1, 1), 's': (2.75, 3.5, 1, 1), 'd': (3.75, 3.5, 1, 1),
    'f': (4.75, 3.5, 1, 1), 'g': (5.75, 3.5, 1, 1), 'h': (6.75, 3.5, 1, 1), 'j': (7.75, 3.5, 1, 1),
    'k': (8.75, 3.5, 1, 1), 'l': (9.75, 3.5, 1, 1),
    'semicolon': (10.75, 3.5, 1, 1), 'apostrophe': (11.75, 3.5, 1, 1), 'enter': (12.75, 3.5, 2.25, 1),

    # Row 4 (Bottom Letters)
    'left_shift': (0, 4.5, 2.25, 1), 'z': (2.25, 4.5, 1, 1), 'x': (3.25, 4.5, 1, 1), 'c': (4.25, 4.5, 1, 1),
    'v': (5.25, 4.5, 1, 1), 'b': (6.25, 4.5, 1, 1), 'n': (7.25, 4.5, 1, 1), 'm': (8.25, 4.5, 1, 1),
    'comma': (9.25, 4.5, 1, 1), 'dot': (10.25, 4.5, 1, 1), 'slash': (11.25, 4.5, 1, 1), 'right_shift': (12.25, 4.5, 2.75, 1),

    # Row 5 (Modifiers & Spacebar)
    'left_ctrl': (0, 5.5, 1.25, 1), 'left_gui': (1.25, 5.5, 1.25, 1), 'left_alt': (2.5, 5.5, 1.25, 1),
    'space': (3.75, 5.5, 6.25, 1),
    'right_alt': (10.0, 5.5, 1.25, 1), 'right_gui': (11.25, 5.5, 1.25, 1), 'fn': (12.5, 5.5, 1.25, 1), 'right_ctrl': (13.75, 5.5, 1.25, 1),

    # Esc (Physical reference for TKL/Full, usually overwritten in Mini)
    'esc': (0, 0, 1, 1)
}

# Standard 60% ISO Block (Europe - Big Enter, Split Left Shift)
BLOCK_60_ISO = BLOCK_60_ANSI.copy()
BLOCK_60_ISO.update({
    'enter': (13.75, 3.5, 1.25, 2),      # Tall Enter
    'iso_hash': (12.75, 3.5, 1, 1),      # Key next to Enter (# or ')
    'left_shift': (0, 4.5, 1.25, 1),     # Short Left Shift
    'iso_pipe': (1.25, 4.5, 1, 1),       # Key next to Left Shift (< > |)
})
# Remove ANSI specific key that conflicts with ISO Enter
if 'backslash' in BLOCK_60_ISO:
    del BLOCK_60_ISO['backslash']

# Pure 60% variations (e.g., Apex Pro Mini)
# In these layouts, 'Esc' moves into the number row, replacing Tilde/Grave
BLOCK_60_ANSI_PURE = BLOCK_60_ANSI.copy()
BLOCK_60_ANSI_PURE['esc'] = (0, 1.5, 1, 1)
if 'grave' in BLOCK_60_ANSI_PURE: del BLOCK_60_ANSI_PURE['grave']

BLOCK_60_ISO_PURE = BLOCK_60_ISO.copy()
BLOCK_60_ISO_PURE['esc'] = (0, 1.5, 1, 1)
if 'grave' in BLOCK_60_ISO_PURE: del BLOCK_60_ISO_PURE['grave']

# Function Row (F1-F12 + Esc position for TKL/Full)
BLOCK_F_ROW = {
    'esc': (0, 0, 1, 1),
    'f1': (2, 0, 1, 1), 'f2': (3, 0, 1, 1), 'f3': (4, 0, 1, 1), 'f4': (5, 0, 1, 1),
    'f5': (6.5, 0, 1, 1), 'f6': (7.5, 0, 1, 1), 'f7': (8.5, 0, 1, 1), 'f8': (9.5, 0, 1, 1),
    'f9': (11, 0, 1, 1), 'f10': (12, 0, 1, 1), 'f11': (13, 0, 1, 1), 'f12': (14, 0, 1, 1),
}

# =============================================================================
# NAVIGATION BLOCKS
# =============================================================================

# A) Full Navigation Block (Standard TKL, no OLED)
BLOCK_NAV_FULL = {
    'print_screen': (15.5, 0, 1, 1), 'scroll_lock': (16.5, 0, 1, 1), 'pause': (17.5, 0, 1, 1),
    'insert': (15.5, 1.5, 1, 1), 'home': (16.5, 1.5, 1, 1), 'page_up': (17.5, 1.5, 1, 1),
    'delete': (15.5, 2.5, 1, 1), 'end': (16.5, 2.5, 1, 1), 'page_down': (17.5, 2.5, 1, 1),
    'up': (16.5, 4.5, 1, 1),
    'left': (15.5, 5.5, 1, 1), 'down': (16.5, 5.5, 1, 1), 'right': (17.5, 5.5, 1, 1),
}

# B) OLED Navigation Block (TKL with OLED)
# The top row (PrintScreen, ScrollLock, Pause) is removed to make space for the screen.
BLOCK_NAV_OLED = {
    'insert': (15.5, 1.5, 1, 1), 'home': (16.5, 1.5, 1, 1), 'page_up': (17.5, 1.5, 1, 1),
    'delete': (15.5, 2.5, 1, 1), 'end': (16.5, 2.5, 1, 1), 'page_down': (17.5, 2.5, 1, 1),
    'up': (16.5, 4.5, 1, 1),
    'left': (15.5, 5.5, 1, 1), 'down': (16.5, 5.5, 1, 1), 'right': (17.5, 5.5, 1, 1),
}

# C) Numpad Block (Full Size)
NX = 19.0  # X Offset for Numpad
BLOCK_NUMPAD = {
    'num_lock': (NX, 1.5, 1, 1), 'kp_slash': (NX+1, 1.5, 1, 1), 'kp_asterisk': (NX+2, 1.5, 1, 1), 'kp_minus': (NX+3, 1.5, 1, 1),
    'kp_7': (NX, 2.5, 1, 1), 'kp_8': (NX+1, 2.5, 1, 1), 'kp_9': (NX+2, 2.5, 1, 1), 'kp_plus': (NX+3, 2.5, 1, 2),
    'kp_4': (NX, 3.5, 1, 1), 'kp_5': (NX+1, 3.5, 1, 1), 'kp_6': (NX+2, 3.5, 1, 1),
    'kp_1': (NX, 4.5, 1, 1), 'kp_2': (NX+1, 4.5, 1, 1), 'kp_3': (NX+2, 4.5, 1, 1), 'kp_enter': (NX+3, 4.5, 1, 2),
    'kp_0': (NX, 5.5, 2, 1), 'kp_dot': (NX+2, 5.5, 1, 1),
}

# =============================================================================
# LAYOUT ASSEMBLY
# =============================================================================

LAYOUTS = {
    # 60% Layouts (e.g. Apex Pro Mini)
    "MINI_ANSI": BLOCK_60_ANSI_PURE.copy(),
    "MINI_ISO": BLOCK_60_ISO_PURE.copy(),

    # Standard TKL (Fallback)
    "TKL_ANSI": {**BLOCK_60_ANSI, **BLOCK_F_ROW, **BLOCK_NAV_FULL},
    "TKL_ISO": {**BLOCK_60_ISO, **BLOCK_F_ROW, **BLOCK_NAV_FULL},

    # Apex TKL (With OLED gap)
    "TKL_ANSI_OLED": {**BLOCK_60_ANSI, **BLOCK_F_ROW, **BLOCK_NAV_OLED},
    "TKL_ISO_OLED": {**BLOCK_60_ISO, **BLOCK_F_ROW, **BLOCK_NAV_OLED},

    # Full Size
    "FULL_ANSI": {**BLOCK_60_ANSI, **BLOCK_F_ROW, **BLOCK_NAV_FULL, **BLOCK_NUMPAD},
    "FULL_ISO": {**BLOCK_60_ISO, **BLOCK_F_ROW, **BLOCK_NAV_FULL, **BLOCK_NUMPAD},

    # Full Size with OLED
    "FULL_ANSI_OLED": {**BLOCK_60_ANSI, **BLOCK_F_ROW, **BLOCK_NAV_OLED, **BLOCK_NUMPAD},
    "FULL_ISO_OLED": {**BLOCK_60_ISO, **BLOCK_F_ROW, **BLOCK_NAV_OLED, **BLOCK_NUMPAD},
}

# --- PUBLIC HELPER ---

def get_layout(type_str, variant="ANSI", has_oled=False):
    """
    Selects the correct coordinate map based on hardware parameters.

    Args:
        type_str (str): "TKL", "FULL", or "MINI".
        variant (str): "ANSI" or "ISO".
        has_oled (bool): True if the device has an OLED screen (removes top Nav row).

    Returns:
        dict: A dictionary of {key_name: (x, y, w, h)}.
    """
    base_key = f"{type_str}_{variant}"

    # Try to find OLED specific version first
    if has_oled:
        oled_key = f"{base_key}_OLED"
        if oled_key in LAYOUTS:
            return LAYOUTS[oled_key]

    # Fallback to standard version (or default TKL ANSI)
    return LAYOUTS.get(base_key, LAYOUTS["TKL_ANSI"])

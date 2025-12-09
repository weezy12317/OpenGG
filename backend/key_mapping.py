# --- OMNIPOINT KEYS (HALL EFFECT) ---
# These keys are equipped with adjustable magnetic Hall Effect sensors.
# They support:
#   1. Adjustable Actuation Distance (0.1mm - 4.0mm)
#   2. Rapid Trigger Technology
#   3. Dual-Actuation / Protection Mode
#   4. Per-Key RGB
OMNIPOINT_KEYS = {
    # Row 1 (Numbers)
    '1': 0x1e, '2': 0x1f, '3': 0x20, '4': 0x21, '5': 0x22,
    '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27,
    'minus': 0x2d, 'equal': 0x2e, 'backspace': 0x2a,

    # Row 2 (Top Letters)
    'tab': 0x2b,
    'q': 0x14, 'w': 0x1a, 'e': 0x08, 'r': 0x15, 't': 0x17, 'y': 0x1c, 'u': 0x18,
    'i': 0x0c, 'o': 0x12, 'p': 0x13,
    'bracket_left': 0x2f, 'bracket_right': 0x30, 'backslash': 0x31,

    # Row 3 (Home Row)
    'caps_lock': 0x39,
    'a': 0x04, 's': 0x16, 'd': 0x07, 'f': 0x09, 'g': 0x0a, 'h': 0x0b,
    'j': 0x0d, 'k': 0x0e, 'l': 0x0f,
    'semicolon': 0x33, 'apostrophe': 0x34, 'enter': 0x28,

    # Row 4 (Bottom Letters)
    'left_shift': 0xe1,
    'z': 0x1d, 'x': 0x1b, 'c': 0x06, 'v': 0x19, 'b': 0x05, 'n': 0x11, 'm': 0x10,
    'comma': 0x36, 'dot': 0x37, 'slash': 0x38,
    'right_shift': 0xe5,

    # Row 5 (Modifiers & Space)
    'left_ctrl': 0xe0, 'left_gui': 0xe3, 'left_alt': 0xe2, 'space': 0x2c,
    'right_alt': 0xe6, 'right_gui': 0xe7, 'right_ctrl': 0xe4,

    # ISO Specific Keys (Often supported on newer hardware revisions)
    'iso_pipe': 0x64,  # Key next to Left Shift (< > |)
    'iso_hash': 0x32,  # Key next to Enter (# ')
    'grave': 0x35,     # Tilde/Grave key (Position varies by region)
}

# --- STANDARD KEYS (MECHANICAL / LOCKED) ---
# These keys use standard switches or are locked by the firmware.
# They DO NOT support adjustable actuation.
# They ONLY support RGB lighting updates.
STANDARD_KEYS = {
    # Function Row
    'esc': 0x29,
    'f1': 0x3a, 'f2': 0x3b, 'f3': 0x3c, 'f4': 0x3d, 'f5': 0x3e, 'f6': 0x3f,
    'f7': 0x40, 'f8': 0x41, 'f9': 0x42, 'f10': 0x43, 'f11': 0x44, 'f12': 0x45,

    # SteelSeries Special Key
    'fn': 0xf0, 'ss_key': 0xf0,

    # Navigation Cluster
    'print_screen': 0x46, 'scroll_lock': 0x47, 'pause': 0x48,
    'insert': 0x49, 'home': 0x4a, 'page_up': 0x4b,
    'delete': 0x4c, 'end': 0x4d, 'page_down': 0x4e,
    'right': 0x4f, 'left': 0x50, 'down': 0x51, 'up': 0x52,

    # Numpad (Full Size / TKL usually omit these)
    'num_lock': 0x53,
    'kp_slash': 0x54, 'kp_asterisk': 0x55, 'kp_minus': 0x56, 'kp_plus': 0x57,
    'kp_enter': 0x58,
    'kp_1': 0x59, 'kp_2': 0x5a, 'kp_3': 0x5b, 'kp_4': 0x5c, 'kp_5': 0x5d,
    'kp_6': 0x5e, 'kp_7': 0x5f, 'kp_8': 0x60, 'kp_9': 0x61, 'kp_0': 0x62,
    'kp_dot': 0x63,
}

# Master lookup table combining all keys
ALL_KEYS = {**OMNIPOINT_KEYS, **STANDARD_KEYS}

# --- HELPER FUNCTIONS ---

def get_key_code(name):
    """
    Retrieves the USB HID usage code for a given key name.

    Args:
        name (str): The logical name of the key (e.g., 'enter', 'f1').

    Returns:
        int or None: The HID code if found.
    """
    key = name.lower().strip()
    return ALL_KEYS.get(key, None)

# --- LED MATRIX MAPPING ---
# In most cases, the HID code corresponds directly to the LED address on the controller.
# However, distinct firmware versions or layouts may require overrides.
LED_MAPPING = {
    # Example Overrides:
    # 0xe5: 229,  # Right Shift
    # 0xf0: 240,  # Fn Key
}

def get_led_id(hid_code):
    """
    Maps a USB HID code to the physical LED address on the controller.

    Args:
        hid_code (int): The USB HID usage code.

    Returns:
        int: The address index for the RGB packet.
    """
    return LED_MAPPING.get(hid_code, hid_code)

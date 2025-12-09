# Vendor ID for SteelSeries (Constant across most of their peripherals)
STEELSERIES_VENDOR_ID = 0x1038

# --- FEATURE FLAGS (Bitmasks) ---
# Used to dynamically toggle UI elements and Driver logic based on hardware capabilities.
FEAT_ACTUATION  = 1   # Support for adjustable actuation points (OmniPoint switches)
FEAT_RAPID_TRIG = 2   # Support for Rapid Trigger technology
FEAT_OLED       = 4   # Presence of an OLED Smart Display
FEAT_RGB        = 8   # Support for Per-Key RGB Lighting
FEAT_WIRELESS   = 16  # Wireless connectivity support (may require different packet headers)

# --- DEVICE DATABASE ---
# Maps USB Product IDs (PID) to device metadata and capability flags.
# To find your PID: `lsusb` on Linux or Device Manager on Windows.
SUPPORTED_DEVICES = {
    # --- APEX PRO TKL (2023 Edition) ---
    0x1628: {
        "name": "Apex Pro TKL (2023)",
        "layout_type": "TKL",
        "features": FEAT_ACTUATION | FEAT_RAPID_TRIG | FEAT_OLED | FEAT_RGB,
        "packet_size_cmd": 64,
        "packet_size_data": 644
    },

    # --- APEX PRO TKL (Legacy Edition) ---
    0x1610: {
        "name": "Apex Pro TKL (Legacy)",
        "layout_type": "TKL",
        "features": FEAT_ACTUATION | FEAT_RAPID_TRIG | FEAT_OLED | FEAT_RGB,
        "packet_size_cmd": 64,
        "packet_size_data": 644
    },

    # --- APEX PRO MINI (Wired) ---
    0x1854: {
        "name": "Apex Pro Mini",
        "layout_type": "MINI",  # 60% Layout
        "features": FEAT_ACTUATION | FEAT_RAPID_TRIG | FEAT_RGB,  # Note: No OLED
        "packet_size_cmd": 64,
        "packet_size_data": 644
    },

    # --- APEX PRO FULL SIZE ---
    0x160c: {
        "name": "Apex Pro Full",
        "layout_type": "FULL",  # 100% Layout with Numpad
        "features": FEAT_ACTUATION | FEAT_RAPID_TRIG | FEAT_OLED | FEAT_RGB,
        "packet_size_cmd": 64,
        "packet_size_data": 644
    }
}

def get_device_info(product_id):
    """
    Retrieves the capability dictionary for a specific USB Product ID.

    Args:
        product_id (int): The USB Product ID (PID) of the connected device.

    Returns:
        dict: Device configuration or None if unsupported.
    """
    return SUPPORTED_DEVICES.get(product_id, None)

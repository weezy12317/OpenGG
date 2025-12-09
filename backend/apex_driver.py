import time
import threading
import usb.core
import usb.util

# --- LOCAL IMPORTS ---
from backend.device_db import STEELSERIES_VENDOR_ID, SUPPORTED_DEVICES
from backend.key_mapping import OMNIPOINT_KEYS, ALL_KEYS, get_led_id

# --- CONSTANTS ---
ID_VENDOR = STEELSERIES_VENDOR_ID
# Default Product ID used for fallback scanning (e.g., Apex Pro TKL)
ID_PRODUCT_DEFAULT = 0x1628
INTERFACE_NUM = 1

# Packet Size Definitions (Hardware Constraints)
SIZE_CMD = 64
SIZE_DATA = 644

class ApexPro:
    """
    Hardware driver for SteelSeries Apex Pro keyboards.
    Handles raw USB communication via PyUSB (libusb).
    """

    def __init__(self):
        self.interface = INTERFACE_NUM
        self.dev = None
        self.device_info = None
        self.pid = 0
        self.lock = threading.RLock()

        # Pre-calculate unique, sorted keys for RGB processing.
        # This prevents recalculating the list on every RGB frame (Performance optimization).
        self.sorted_led_keys = sorted(list(set(ALL_KEYS.values())))

        # 1. Device Discovery
        # Scan all connected USB devices to find a supported SteelSeries product.
        devs = usb.core.find(find_all=True, idVendor=ID_VENDOR)

        for d in devs:
            if d.idProduct in SUPPORTED_DEVICES:
                self.dev = d
                self.pid = d.idProduct
                self.device_info = SUPPORTED_DEVICES[self.pid]
                break

        # Fallback: If no specific supported PID was found, try the generic default.
        if self.dev is None:
            self.dev = usb.core.find(idVendor=ID_VENDOR, idProduct=ID_PRODUCT_DEFAULT)
            if self.dev is None:
                raise ValueError("No supported SteelSeries keyboard found.")

        # 2. USB Interface Setup
        self._ensure_claimed()

        # 3. Initialization Handshake
        # Sends a reset/wakeup command to the controller.
        self._send_cmd([0x90, 0x00])

    def _ensure_claimed(self):
        """
        Detaches the operating system's kernel driver (hid-generic)
        and claims the USB interface for raw communication.
        """
        if self.dev is None: return

        # Step 1: Detach Kernel Driver
        try:
            if self.dev.is_kernel_driver_active(self.interface):
                self.dev.detach_kernel_driver(self.interface)
        except Exception:
            # Ignore errors (e.g., if already detached or permissions issue)
            pass

        # Step 2: Claim Interface
        try:
            usb.util.claim_interface(self.dev, self.interface)
        except Exception:
            pass

    def _send_packet(self, data_list, target_size: int):
        """
        Constructs and sends a raw USB control transfer packet.

        Args:
            data_list: List of integers or a bytearray.
            target_size: The required packet size (64 or 644 bytes).
        """
        if not self.dev: return

        # Performance Optimization:
        # If input is already bytes/bytearray, assume it is valid and skip the slow loop.
        if isinstance(data_list, (bytes, bytearray)):
            safe_data = bytearray(data_list)
        else:
            # Clamp values to valid byte range (0-255) to prevent crashes
            safe_data = bytearray([max(0, min(255, int(x))) for x in data_list])

        # Pad with zeros if the packet is too short
        if len(safe_data) < target_size:
            safe_data += bytearray([0x00] * (target_size - len(safe_data)))
        # Truncate if the packet is too long
        elif len(safe_data) > target_size:
            safe_data = safe_data[:target_size]

        with self.lock:
            try:
                # bmRequestType: 0x21 (Host to Device, Class, Interface)
                # bRequest: 0x09 (Set Report)
                # wValue: 0x0200 (Report Type: Output)
                self.dev.ctrl_transfer(0x21, 0x09, 0x0200, self.interface, safe_data, timeout=1000)
            except usb.core.USBError as e:
                # Ignore timeout errors (errno 110) which often occur during high-frequency RGB updates
                if e.errno != 110:
                    pass

    def _send_cmd(self, data: list[int]):
        """Sends a small control command (64 bytes)."""
        self._send_packet(data, SIZE_CMD)

    def _send_data(self, data: list[int]):
        """Sends a large data payload (644 bytes), used for RGB and Config."""
        self._send_packet(data, SIZE_DATA)

    def _send_commit(self):
        """Sends the 'Save/Apply' command to commit changes to the device."""
        self._send_cmd([0x34, 0x00])

    # --- MATH HELPERS ---

    def _mm_to_raw(self, mm: float) -> int:
        """
        Converts actuation distance (mm) to the hardware's raw integer format (0-255).
        Based on reverse-engineered calibration points.
        """
        if mm <= 0.1: return 5
        if mm >= 4.0: return 224

        # Calibration map: {mm: raw_value}
        CAL = {0.1: 5, 2.1: 62, 4.0: 224}
        keys = sorted(CAL.keys())

        # Linear interpolation between calibration points
        for i in range(len(keys) - 1):
            low, high = keys[i], keys[i+1]
            if low <= mm <= high:
                ratio = (mm - low) / (high - low)
                val = CAL[low] + ratio * (CAL[high] - CAL[low])
                return int(round(val))
        return 5

    def _compute_reset_raw(self, raw_act: int) -> int:
        """
        Calculates the reset point based on the actuation point.
        Ensures a small hysteresis gap to prevent key chatter.
        """
        if raw_act <= 5: return 5
        return max(0, raw_act - 5)

    # --- PROFILE MANAGEMENT ---

    def load_onboard_profile(self, profile_index):
        """
        Forces the keyboard to switch to a specific onboard memory slot (1-5).

        The device often locks up if switched directly. This method uses a
        'Clean Switch' routine: Dispose -> Temp Connection -> Switch -> Dispose -> Reconnect.
        """
        if not (1 <= profile_index <= 5): return

        # 1. Dispose current connection resources
        try:
            usb.util.dispose_resources(self.dev)
        except: pass

        time.sleep(0.002)  # Allow USB bus to settle

        # 2. Create a temporary connection just for the switch command
        try:
            temp_dev = usb.core.find(idVendor=ID_VENDOR, idProduct=self.pid)
            if temp_dev:
                # Detach kernel driver again for the temp connection
                if temp_dev.is_kernel_driver_active(self.interface):
                    try: temp_dev.detach_kernel_driver(self.interface)
                    except: pass

                usb.util.claim_interface(temp_dev, self.interface)

                idx_byte = profile_index - 1

                # Command: Select Profile (0xB2)
                temp_dev.ctrl_transfer(0x21, 0x09, 0x0200, self.interface,
                                     bytearray([0xB2, idx_byte]) + bytearray([0x00] * 62))
                time.sleep(0.1)

                # Command: Commit (0x34)
                temp_dev.ctrl_transfer(0x21, 0x09, 0x0200, self.interface,
                                     bytearray([0x34, 0x00]) + bytearray([0x00] * 62))
                time.sleep(0.05)

                # Command: Handshake (0x90)
                temp_dev.ctrl_transfer(0x21, 0x09, 0x0200, self.interface,
                                     bytearray([0x90, 0x00]) + bytearray([0x00] * 62))

                usb.util.dispose_resources(temp_dev)

        except Exception:
            pass

        # 3. Restore main connection
        time.sleep(0.5)  # Wait for device flash memory to reload
        self.dev = usb.core.find(idVendor=ID_VENDOR, idProduct=self.pid)
        if self.dev:
            self._ensure_claimed()
            self._send_cmd([0x90, 0x00])  # New session handshake

    # --- CONFIGURATION (ACTUATION & RAPID TRIGGER) ---

    def apply_config(self, config_dict: dict[int, dict]):
        """
        Applies the full configuration to the device.
        Updates Actuation points, Rapid Trigger sensitivity, and Feature Modes.
        """
        if not self.dev: return

        # 1. Actuation Data (Header: 0x38 0x61)
        packet_act = [0x38, 0x61, 0x44, 0x00]
        for name, hid_code in OMNIPOINT_KEYS.items():
            settings = config_dict.get(hid_code, {})
            act = float(settings.get("actuation", 1.8))

            raw_act = self._mm_to_raw(act)
            raw_reset = self._compute_reset_raw(raw_act)
            packet_act.extend([hid_code, raw_act, raw_reset])

        self._send_data(packet_act)

        # 2. Rapid Trigger Sensitivity (Header: 0x38 0x65)
        packet_rt = [0x38, 0x65, 0x44, 0x04]
        for name, hid_code in OMNIPOINT_KEYS.items():
            settings = config_dict.get(hid_code, {})
            rt_sens = float(settings.get("rt_sens", 0.1))

            # Hardware expects value * 10 (e.g., 0.1mm -> 1)
            val = int(round(max(0.1, min(4.0, rt_sens)) * 10))
            packet_rt.extend([val, hid_code])

        self._send_data(packet_rt)

        # 3. Hardware Modes (Header: 0x38 0x62)
        packet_mod = [0x38, 0x62, 0x44, 0x04]
        for name, hid_code in ALL_KEYS.items():
            settings = config_dict.get(hid_code, {})
            mode = int(settings.get("mode", 0))
            packet_mod.extend([mode, hid_code])

        self._send_data(packet_mod)

        # Commit all changes
        time.sleep(0.05)
        self._send_commit()

    def apply_partial_config(self, partial_cfg: dict[int, dict]):
        """
        Updates settings only for specific keys provided in the dictionary.
        Used for real-time UI updates to avoid sending full config packets.
        """
        pkt_act = [0x38, 0x61, 0x44, 0x00]
        pkt_rt  = [0x38, 0x65, 0x44, 0x04]
        pkt_mod = [0x38, 0x62, 0x44, 0x04]

        for hid_code, settings in partial_cfg.items():
            act = float(settings.get("actuation", 1.8))
            rt_sens = float(settings.get("rt_sens", 0.1))
            mode = int(settings.get("mode", 0))

            raw_act = self._mm_to_raw(act)
            raw_reset = self._compute_reset_raw(raw_act)
            rt_val = int(round(max(0.1, min(4.0, rt_sens)) * 10))

            pkt_act.extend([hid_code, raw_act, raw_reset])
            pkt_rt.extend([rt_val, hid_code])
            pkt_mod.extend([mode, hid_code])

        # Send only if data was added (len > header size)
        if len(pkt_act) > 4: self._send_data(pkt_act)
        if len(pkt_rt) > 4:  self._send_data(pkt_rt)
        if len(pkt_mod) > 4: self._send_data(pkt_mod)
        self._send_commit()

    # --- LIGHTING & OLED ---

    def set_rgb(self, color_dict):
        """
        Sends RGB data to the keyboard.
        Updates keys in chunks of 40 to adhere to hardware buffer limits.
        """
        if not self.dev: return

        # Constants for chunking
        CHUNK_SIZE = 40

        # Use pre-sorted keys (cached in __init__)
        all_unique_keys = self.sorted_led_keys

        # Create chunks
        chunks = [all_unique_keys[i:i + CHUNK_SIZE] for i in range(0, len(all_unique_keys), CHUNK_SIZE)]

        for chunk in chunks:
            # Header: 0x40 0x54 = RGB Data
            packet = [0x40, 0x54]

            for hid_code in chunk:
                # Retrieve color tuple (R, G, B) or default to black
                raw_rgb = color_dict.get(hid_code, (0, 0, 0))

                # Simple integer casting
                r = int(raw_rgb[0])
                g = int(raw_rgb[1])
                b = int(raw_rgb[2])

                # Get physical LED address
                led_address = get_led_id(hid_code)
                packet.extend([led_address, r, g, b])

            self._send_data(packet)

            # Minimal sleep to allow the USB controller to digest the chunk
            # NOTE: If RGB feels laggy, this sleep might be the bottleneck.
            time.sleep(0.0005)

    def set_oled_image(self, image_data):
        """
        Sends a 640-byte 1-bit image buffer to the OLED display.
        Arg: image_data must be a list or bytes of length 640.
        """
        if len(image_data) != 640: return
        # Header: 0x38 0x83 = OLED Data
        packet = [0x38, 0x83, 0x00] + list(image_data)
        self._send_data(packet)

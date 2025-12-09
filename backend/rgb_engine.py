import threading
import time
import math
import random
from pathlib import Path

# --- LOCAL IMPORTS ---
from backend.key_mapping import ALL_KEYS
from backend.layouts import LAYOUTS, get_layout
from backend.path import prism_dump_dir
from backend.gg_prism_runtime import GGPrismRuntime

# Target Frame Time: 0.05s = 20 FPS (Good balance for USB bandwidth vs smoothness)
FRAME_TIME = 0.05

class RGBEngine(threading.Thread):
    """
    Background thread responsible for calculating and sending RGB frames
    to the keyboard hardware. Supports both legacy algorithmic effects
    and the new GG Prism Runtime.
    """
    def __init__(self, keyboard_driver):
        super().__init__()
        self.kb = keyboard_driver
        self.running = True
        self.daemon = True
        self._paused = False

        # Configuration State
        self.bg_type = "static"
        self.bg_colors = [(255, 0, 0)]
        self.bg_speed = 1.0

        # Disco Mode State
        self.disco_states = {}
        self.disco_density = 0.15

        # Per-Key Overrides (Static overlays on top of animations)
        self.overrides = {}

        # GG Prism Runtime State
        self._gg_runtime = None
        self._gg_compiled = None
        self._gg_time_scale = 1.0

        # Physical Layout Mapping (UI Coordinates -> Normalized 0-1 Space)
        try:
            dev_info = getattr(self.kb, 'device_info', {})
            layout_type = dev_info.get('layout_type', 'TKL')
            has_oled = bool(dev_info.get('features', 0) & 4) # 4 is FEAT_OLED bitmask
            layout_data = get_layout(layout_type, "ANSI", has_oled)
        except Exception:
            layout_data = LAYOUTS.get("TKL_ANSI", {})

        self.key_coords = self._build_coord_map(layout_data)

    def _build_coord_map(self, layout):
        """
        Converts pixel/key-unit coordinates from LAYOUTS into normalized spatial coordinates.
        X is normalized roughly to 0-23, Y to 0-7.
        """
        coords = {}
        for k_name, val in layout.items():
            hid = ALL_KEYS.get(k_name)
            if hid:
                # Calculate center point of the key
                cx = val[0] + val[2] / 2
                cy = val[1] + val[3] / 2
                # Normalize arbitrary scales
                coords[hid] = (cx / 23.0, cy / 7.0)
        return coords

    def pause(self):
        """Pauses the rendering loop. Used during bulk USB transfers (e.g. Profile Switching)."""
        self._paused = True

    def resume(self):
        """Resumes the rendering loop."""
        self._paused = False

    def stop(self):
        """Stops the thread gracefully."""
        self.running = False
        self.join(timeout=1.0)

    def update_speed(self, speed):
        """Updates animation speed on the fly."""
        self.bg_speed = max(0.1, float(speed))
        self._gg_time_scale = self.bg_speed

    def set_background(self, config, speed_override=None):
        """
        Configures the active background effect.

        Args:
            config (dict): Configuration dictionary (type, colors, etc).
            speed_override (float): Optional speed multiplier.
        """
        self.bg_type = config.get("type", "static")

        # CASE 1: SteelSeries GG Prism Effect
        if self.bg_type == "gg_prism":
            dump = config.get("dump_dir", str(prism_dump_dir()))
            if self._gg_runtime is None:
                self._gg_runtime = GGPrismRuntime(dump)

            force_breath = config.get("is_breathe_preset", False)
            self._gg_compiled = self._gg_runtime.compile(config.get("gg", {}), force_breathe=force_breath)

            val = float(speed_override) if speed_override else 1.0
            self._gg_time_scale = val
            return

        # CASE 2: Legacy / Manual Effects (Static, Wave, Disco)
        # Parse Colors
        self.bg_colors = [self._hex_to_rgb(c) for c in config.get("colors", [(0,0,0)])]

        # Parse Speed
        val = float(speed_override) if speed_override else config.get("speed", 1.0)
        self.bg_speed = val

        # Reset Disco State
        self.disco_density = float(config.get("density", 0.15))
        self.disco_states = {}

    def set_overrides(self, ov):
        """Sets per-key static color overrides."""
        self.overrides = {
            k: {"mode": v.get("mode"), "color": self._hex_to_rgb(v.get("color"))}
            for k, v in ov.items()
        }

    def _hex_to_rgb(self, c):
        """Helper: Converts Hex String or Tuple to RGB Tuple."""
        if isinstance(c, (list, tuple)): return tuple(c)
        try:
            return tuple(int(c.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        except:
            return (0, 0, 0)

    def run(self):
        """Main Render Loop."""
        t = 0.0
        while self.running:
            if self._paused:
                time.sleep(0.1)
                continue

            start = time.perf_counter()
            frame = {}
            t += self.bg_speed * 0.02

            try:
                # --- STEP 1: RENDER BACKGROUND ---

                if self.bg_type == "gg_prism":
                    if self._gg_runtime:
                        ms = int(time.time() * 1000 * self._gg_time_scale)
                        frame = self._gg_runtime.render(self._gg_compiled, self.key_coords, ms)

                elif self.bg_type == "static":
                    c = self.bg_colors[0]
                    for h in self.key_coords: frame[h] = c

                elif self.bg_type == "disco":
                    self._render_disco(frame)

                elif self.bg_type == "wave":
                    # Simple legacy wave implementation
                    for hid, (cx, cy) in self.key_coords.items():
                        frame[hid] = self._interpolate_palette(cx - t)

                # --- STEP 2: APPLY OVERRIDES ---
                for hid, ov in self.overrides.items():
                    frame[hid] = ov["color"]

                # --- STEP 3: SEND TO HARDWARE ---
                self.kb.set_rgb(frame)

            except Exception:
                # Prevent crashing the thread on transient math/USB errors
                pass

            # Maintain Target Framerate
            dt = time.perf_counter() - start
            time.sleep(max(0.001, FRAME_TIME - dt))

    def _render_disco(self, frame):
        """Logic for the 'Disco' effect (random flashing keys)."""
        pool = self.bg_colors

        for hid in self.key_coords:
            # Initialize state for new keys
            if hid not in self.disco_states:
                c = (0, 0, 0)
                targ = random.choice(pool) if pool else (255, 255, 255)
                # State: [cr, cg, cb, tr, tg, tb, progress, step]
                self.disco_states[hid] = [
                    c[0], c[1], c[2],
                    targ[0], targ[1], targ[2],
                    0.0,
                    random.uniform(0.1, 0.3) * self.bg_speed
                ]

            state = self.disco_states[hid]
            state[6] += state[7] # Advance progress

            # Target Reached? Pick new target
            if state[6] >= 1.0:
                # Set current color as old target
                state[0], state[1], state[2] = state[3], state[4], state[5]

                # 15% chance to go dark (creates "twinkle" effect)
                if random.random() < 0.15:
                    nt = (0, 0, 0)
                else:
                    nt = random.choice(pool)

                state[3], state[4], state[5] = nt[0], nt[1], nt[2]
                state[6] = 0.0
                state[7] = random.uniform(0.1, 0.3) * self.bg_speed

            # Interpolate
            p = state[6]
            r = int(state[0] + (state[3] - state[0]) * p)
            g = int(state[1] + (state[4] - state[1]) * p)
            b = int(state[2] + (state[5] - state[2]) * p)
            frame[hid] = (r, g, b)

    def _interpolate_palette(self, t):
        """
        Interpolates between a list of colors based on position t (0.0-1.0).
        Used for the legacy 'wave' effect.
        """
        if not self.bg_colors: return (0, 0, 0)
        n = len(self.bg_colors)
        t = t % 1.0
        idx = int(t * n)
        nxt = (idx + 1) % n
        blend = (t * n) - idx
        c1, c2 = self.bg_colors[idx], self.bg_colors[nxt]
        return (
            int(c1[0] + (c2[0] - c1[0]) * blend),
            int(c1[1] + (c2[1] - c1[1]) * blend),
            int(c1[2] + (c2[2] - c1[2]) * blend)
        )

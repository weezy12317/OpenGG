import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Any

# --- CONSTANTS ---
RGB = Tuple[int, int, int]

# Magic scalar derived from reverse engineering the official Engine.
# Adjusts the spatial wavelength to match the physical keyboard dimensions.
WAVELENGTH_SCALAR = 32.0

# Global speed factor to sync animation timing with the official engine.
GLOBAL_SPEED_MODIFIER = 0.6

# --- MATH HELPERS ---

def clamp01(v: float) -> float:
    """Clamps a value between 0.0 and 1.0."""
    return max(0.0, min(1.0, v))

def rgb_lerp(c1: RGB, c2: RGB, t: float) -> RGB:
    """
    Linear Interpolation between two RGB colors.
    t: 0.0 = c1, 1.0 = c2
    """
    t = clamp01(t)
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t)
    )

# --- DATA STRUCTURES ---

@dataclass(frozen=True)
class StopRGB:
    pos: float
    rgb: RGB

class GradientStops:
    """
    Manages a list of color stops for a gradient.
    Handles sampling at specific time/positions (t) with wrap-around support.
    """
    def __init__(self, raw_stops: List[dict]):
        temp_stops = []
        max_pos = 1.0

        # Parse raw dictionaries
        for s in raw_stops:
            p = float(s.get("position", 0))
            c = s.get("color", {})
            rgb = (int(c.get("red", 0)), int(c.get("green", 0)), int(c.get("blue", 0)))
            temp_stops.append((p, rgb))

        # Normalize positions if they exceed 1.0 (some presets use arbitrary scales)
        if temp_stops:
            mx = max(p for p, _ in temp_stops)
            if mx > 1.0: max_pos = mx

        self.stops = []
        for p, rgb in temp_stops:
            norm_p = p / max_pos if max_pos > 0 else 0
            self.stops.append(StopRGB(norm_p, rgb))

        self.stops.sort(key=lambda x: x.pos)

    def sample(self, t: float) -> RGB:
        """Samples the gradient at position t (0.0 to 1.0)."""
        if not self.stops: return (0, 0, 0)

        # Wrap t for cyclic animations (e.g., t=1.2 becomes 0.2)
        t = t - math.floor(t)

        # 1. Check before first stop (Wrap-around from last stop)
        if t <= self.stops[0].pos:
            last, first = self.stops[-1], self.stops[0]
            # Calculate total span across the boundary
            span = (1.0 - last.pos) + first.pos
            if span <= 0.0001: return first.rgb

            # Interpolate
            local_t = (t + (1.0 - last.pos)) / span
            return rgb_lerp(last.rgb, first.rgb, local_t)

        # 2. Check standard segments
        for i in range(len(self.stops) - 1):
            s1, s2 = self.stops[i], self.stops[i+1]
            if s1.pos <= t <= s2.pos:
                span = s2.pos - s1.pos
                if span <= 0.0001: return s1.rgb
                local_t = (t - s1.pos) / span
                return rgb_lerp(s1.rgb, s2.rgb, local_t)

        # 3. Check after last stop (Wrap-around to first stop)
        last, first = self.stops[-1], self.stops[0]
        span = (1.0 - last.pos) + first.pos
        if span <= 0.0001: return last.rgb
        local_t = (t - last.pos) / span
        return rgb_lerp(last.rgb, first.rgb, local_t)

@dataclass(frozen=True)
class StopMask:
    pos: float
    opacity: float

class MaskGradient:
    """
    Handles opacity/alpha gradients (Apertures).
    Used for effects like "Breathing" where transparency changes over time/space.
    """
    def __init__(self, data: dict):
        self.stops = []
        init = data.get("initialMask", {})
        cur_op = float(init.get("opacity", 255)) / 255.0
        self.stops.append(StopMask(0.0, cur_op))

        sections = data.get("sections", [])
        if not sections:
            self.stops.append(StopMask(1.0, cur_op))
            return

        # Calculate total length to normalize positions
        total_len = sum(int(s.get("length", 0)) for s in sections)
        if total_len == 0: total_len = 1

        current_pos = 0.0
        for sec in sections:
            length = int(sec.get("length", 0))
            fm = sec.get("finalMask", {})
            target_op = float(fm.get("opacity", 255)) / 255.0
            current_pos += length

            norm_pos = current_pos / total_len
            self.stops.append(StopMask(norm_pos, target_op))

    def sample(self, t: float) -> float:
        """Returns opacity value (0.0 to 1.0) at position t."""
        if not self.stops: return 1.0
        t = t - math.floor(t)

        # Wrap-around logic identical to GradientStops but for single float
        if t <= self.stops[0].pos:
             s1, s2 = self.stops[-1], self.stops[0]
             span = (1.0 - s1.pos) + s2.pos
             if span <= 0.0001: return s2.opacity
             local_t = (t + (1.0 - s1.pos)) / span
             return s1.opacity + (s2.opacity - s1.opacity) * local_t

        for i in range(len(self.stops) - 1):
            s1, s2 = self.stops[i], self.stops[i+1]
            if s1.pos <= t <= s2.pos:
                span = s2.pos - s1.pos
                if span <= 0.0001: return s1.opacity
                local_t = (t - s1.pos) / span
                return s1.opacity + (s2.opacity - s1.opacity) * local_t

        s1, s2 = self.stops[-1], self.stops[0]
        span = (1.0 - s1.pos) + s2.pos
        if span <= 0.0001: return s1.opacity
        local_t = (t - s1.pos) / span
        return s1.opacity + (s2.opacity - s1.opacity) * local_t

@dataclass
class Layer:
    duration_ms: int
    spatial_wavelength: float
    origin: Tuple[float, float]
    is_origin_fixed: bool
    gradient: Optional[GradientStops]
    mask: Optional[MaskGradient]
    shape: int # 0=Linear, 1=Radial
    is_static: bool

@dataclass
class Graphic:
    zIndex: int
    foreground: Optional[Layer]
    background: Optional[Layer]
    aperture: Optional[Layer]
    allowed_hids: Optional[Set[int]]

@dataclass
class CompiledEffect:
    default_color: RGB
    graphics: List[Graphic]
    is_breathe: bool

# --- RUNTIME ENGINE ---

class GGPrismRuntime:
    """
    The core rendering engine for SteelSeries Prism effects.

    It maps physical keyboard coordinates to abstract animation layers.
    Logic is reverse-engineered from the behavior of the official engine.
    """
    def __init__(self, dump_dir: str):
        self.dump_dir = Path(dump_dir).expanduser()

        # Load device-specific coordinate maps
        self.zone_cache = self._read_json(self.dump_dir / "zone_cache.json") or []
        self.plane_configs = self._read_json(self.dump_dir / "coordinate_plane_configs.json") or []

        # Calculate coordinate bounds for normalization
        self.p_x, self.p_y, self.p_w, self.p_h = self._calculate_bounds()
        self.key_map, self.bitmap_map = self._build_key_maps()

    def _read_json(self, path: Path):
        try: return json.loads(path.read_text(encoding="utf-8"))
        except: return None

    def _calculate_bounds(self):
        """Determines the bounding box of the keyboard for spatial calculations."""
        # Defaults based on typical Apex Pro measurements
        min_x, min_y, max_x, max_y = 31000, 30000, 33500, 31000

        if self.plane_configs:
            pc = self.plane_configs[0]
            min_x = float(pc.get("x_start", min_x))
            min_y = float(pc.get("y_start", min_y))
            max_x = float(pc.get("x_end", max_x))
            max_y = float(pc.get("y_end", max_y))

        return min_x, min_y, (max_x - min_x), (max_y - min_y)

    def _build_key_maps(self):
        """Maps HID codes to physical (x, y) coordinates."""
        km, bm = {}, {}
        for z in self.zone_cache:
            hid = int(z.get("hid_code", 0))
            if hid == 0: continue

            # Prefer adjusted coordinates, fallback to raw
            x = float(z.get("adjusted_x") or z.get("x") or 0)
            y = float(z.get("adjusted_y") or z.get("y") or 0)
            km[hid] = (x, y)

            # Map bitmap grid positions to HID for Per-Key effects
            bx, by = int(z.get("bitmap_x", -1)), int(z.get("bitmap_y", -1))
            if bx >= 0: bm[f"{bx},{by}"] = hid

        return km, bm

    def compile(self, gg_blob: dict, force_breathe: bool = False) -> CompiledEffect:
        """
        Parses a raw GG Prism JSON object into an optimized `CompiledEffect` structure.
        Flattens hierarchy and resolves color defaults.
        """
        graphics = []
        raw_data = gg_blob.get("data")
        if raw_data is None: raw_data = gg_blob

        def_col_rgb = (0, 0, 0)

        def extract_color(obj):
            dc = obj.get("defaultColor")
            if dc: return (int(dc.get("red",0)), int(dc.get("green",0)), int(dc.get("blue",0)))
            return None

        def scan(item):
            nonlocal def_col_rgb
            if not isinstance(item, dict): return

            c = extract_color(item)
            if c: def_col_rgb = c

            # Determine if this effect is limited to specific keys
            item_hids = None
            if "perKeySelectionLimitation" in item:
                item_hids = set()
                for lim in item["perKeySelectionLimitation"]:
                    k = f"{lim.get('x')},{lim.get('y')}"
                    if k in self.bitmap_map: item_hids.add(self.bitmap_map[k])

            # 1. Standard Graphics
            if "graphics" in item:
                graphics.extend(self._parse_graphics_list(item["graphics"], item_hids))

            # 2. Base Configuration (Legacy/Advanced format)
            if "base" in item:
                base = item["base"]
                gl = base.get("globalConfig", {})

                gc = extract_color(gl)
                if gc: def_col_rgb = gc

                # Global graphics
                graphics.extend(self._parse_graphics_list(gl.get("graphics", []), None))

                # Per-Key configurations
                pk = base.get("perKeyConfigs", [])
                if isinstance(pk, list):
                    for p in pk:
                        hids = set()
                        for area in p.get("bitmapAreas", []):
                            k = f"{area.get('x')},{area.get('y')}"
                            if k in self.bitmap_map: hids.add(self.bitmap_map[k])

                        cfg = p.get("config", {})
                        if hids:
                            graphics.extend(self._parse_graphics_list(cfg.get("graphics", []), hids))

        if isinstance(raw_data, list):
            for i in raw_data: scan(i)
        elif isinstance(raw_data, dict):
            scan(raw_data)

        graphics.sort(key=lambda x: x.zIndex)
        return CompiledEffect(default_color=def_col_rgb, graphics=graphics, is_breathe=force_breathe)

    def _parse_graphics_list(self, raw, hids):
        out = []
        if not isinstance(raw, list): return out
        for g in raw:
            if not isinstance(g, dict): continue
            out.append(Graphic(
                zIndex=int(g.get("zIndex", 0)),
                foreground=self._parse_layer(g.get("foreground"), False),
                background=self._parse_layer(g.get("background"), False),
                aperture=self._parse_layer(g.get("aperture"), True),
                allowed_hids=hids
            ))
        return out

    def _parse_layer(self, data: dict, is_mask: bool) -> Optional[Layer]:
        if not data: return None
        grad = None
        mask = None

        if is_mask:
            mask = MaskGradient(data.get("gradient", {}))
        else:
            colors = data.get("gradient", {}).get("colors", [])
            if not colors: return None
            grad = GradientStops(colors)

        raw_dur = int(data.get("duration", 0))
        is_static = (raw_dur == 0)
        dur = raw_dur if raw_dur > 0 else 1000

        wl = float(data.get("spatialWavelength", 0))

        orig = data.get("origin", {})
        ox, oy = float(orig.get("x", 0)), float(orig.get("y", 0))

        is_fixed = bool(data.get("isOriginFixed", False))
        shape = int(data.get("phaseMatrixShape", 0))

        return Layer(dur, wl, (ox, oy), is_fixed, grad, mask, shape, is_static)

    def _eval_phase(self, layer: Layer, kx: float, ky: float, t_ms: int, is_breathe: bool) -> float:
        """
        Optimized phase calculation.
        Uses local variables to minimize object attribute lookups (which are slow in Python).
        """
        # 1. Temporal Phase
        if layer.is_static:
            time_phase = 0.0
        else:
            # Local lookup for speed
            dur = layer.duration_ms
            raw_t = ((t_ms * GLOBAL_SPEED_MODIFIER) % dur) / dur

            if is_breathe:
                # Optimized Triangle Wave: 2*t if t<0.5 else 2*(1-t)
                time_phase = raw_t * 2 if raw_t < 0.5 else 2.0 - (raw_t * 2)
            else:
                time_phase = raw_t

        # 2. Spatial Phase (Optimized)
        spatial_phase = 0.0
        wl = layer.spatial_wavelength # Local var

        if abs(wl) > 0.01:
            # Resolve Origin (Local vars)
            ox, oy = layer.origin
            if ox <= 10000: ox += self.p_x
            if oy <= 10000: oy += self.p_y

            dx = kx - ox
            dy = ky - oy

            # Pre-calculate absolute wavelength scalar
            scaled_wl = abs(wl) * WAVELENGTH_SCALAR

            # Shape Logic
            shape = layer.shape
            if shape == 1: # Radial
                # hypot is slightly faster/cleaner than sqrt(x*x + y*y)
                dist = math.hypot(dx, dy)
                spatial_phase = dist / scaled_wl
            elif shape == 3: # Vertical
                spatial_phase = abs(dy) / scaled_wl
            else: # Horizontal
                spatial_phase = abs(dx) / scaled_wl

            # Apply Direction (Sign of wavelength)
            if wl < 0:
                spatial_phase *= -1

        return time_phase - spatial_phase

    def render(self, compiled_effect: CompiledEffect, key_coords_ui_norm: Dict[int, Tuple[float, float]], t_ms: int) -> Dict[int, RGB]:
        frame = {}
        is_breath = compiled_effect.is_breathe
        graphics = compiled_effect.graphics

        # Localize bounds for speed
        px, py, pw, ph = self.p_x, self.p_y, self.p_w, self.p_h
        key_map = self.key_map

        # Pre-calculate active keys list to avoid .keys() call overhead
        active_keys = key_coords_ui_norm.keys()

        for hid in active_keys:
            # Fast Coordinate Lookup
            if hid in key_map:
                kx, ky = key_map[hid]
            else:
                # Fallback calculation
                cx, cy = key_coords_ui_norm.get(hid, (0,0))
                kx = px + (cx * pw)
                ky = py + (cy * ph)

            # Start with default color
            # We treat RGB as simple integers here for speed
            fr, fg, fb = compiled_effect.default_color

            # Process Layers
            for g in graphics:
                # Fast set check
                if g.allowed_hids is not None and hid not in g.allowed_hids:
                    continue

                # --- BACKGROUND ---
                br, bg, bb = 0, 0, 0
                has_bg = False

                if g.background:
                    t = self._eval_phase(g.background, kx, ky, t_ms, is_breath)
                    # Inline sample logic if possible, but calling method is cleaner
                    br, bg, bb = g.background.gradient.sample(t)
                    has_bg = True

                # --- FOREGROUND ---
                fgr, fgg, fgb = 0, 0, 0
                has_fg = False

                if g.foreground:
                    t = self._eval_phase(g.foreground, kx, ky, t_ms, is_breath)
                    fgr, fgg, fgb = g.foreground.gradient.sample(t)
                    has_fg = True

                # --- COMPOSITING (Optimization: Skip math if layer is empty) ---
                if not has_bg and not has_fg:
                    continue

                # Aperture / Mask
                mask_val = 1.0
                if g.aperture:
                    t = self._eval_phase(g.aperture, kx, ky, t_ms, is_breath)
                    mask_val = g.aperture.mask.sample(t)

                # Blend BG and FG
                # Logic: If we have FG, use it. If we have BG, use it. If both, blend?
                # Usually Prism renders FG on top of BG.

                lr, lg, lb = 0, 0, 0

                if has_fg:
                    # If fully opaque, skip BG calculation
                    lr, lg, lb = fgr, fgg, fgb
                elif has_bg:
                    lr, lg, lb = br, bg, bb

                # Blend Layer onto Frame (Standard Alpha Blending)
                # mask_val is effectively the alpha of the new layer
                if mask_val > 0.0:
                    inv_mask = 1.0 - mask_val
                    fr = int(fr * inv_mask + lr * mask_val)
                    fg = int(fg * inv_mask + lg * mask_val)
                    fb = int(fb * inv_mask + lb * mask_val)

            frame[hid] = (fr, fg, fb)

        return frame

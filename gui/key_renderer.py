from PIL import Image, ImageDraw, ImageFont
import os

# --- DESIGN CONSTANTS ---
TEXT_COLOR = (240, 240, 240)  # Off-White text
ACCENT_BLUE = (65, 105, 225)  # RoyalBlue (Protection Mode)
ACCENT_YELLOW = (255, 215, 0) # Gold (Rapid Trigger)

# Feature Bitmasks (Must match definitions in main.py)
MASK_PROT = 1
MASK_RT   = 2

class KeyRenderer:
    """
    Generates dynamic keycap images for the UI.
    Handles text rendering (centering, multi-line) and feature status icons (RT/Protection).
    """
    def __init__(self):
        self.font_path = self._find_system_font()

        # Load fonts safely
        try:
            if self.font_path:
                self.font_large = ImageFont.truetype(self.font_path, 18)
                self.font_small = ImageFont.truetype(self.font_path, 13)
            else:
                # Fallback if no TTF found
                raise IOError("No system font found")
        except:
            # Fallback to internal PIL bitmap font (ugly but functional)
            self.font_large = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

    def _find_system_font(self):
        """
        Scans common Linux font directories for a suitable Sans-Serif Bold font.
        Returns the path to the first match or None.
        """
        candidates = [
            "/usr/share/fonts/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/gnu-free/FreeSansBold.ttf"
        ]
        for p in candidates:
            if os.path.exists(p): return p
        return None

    def draw_icon_bolt(self, draw, x, y, size=10):
        """Draws a lightning bolt icon indicating Rapid Trigger is active."""
        coords = [
            (x + size*0.6, y), (x, y + size*0.6),
            (x + size*0.4, y + size*0.6), (x + size*0.2, y + size),
            (x + size, y + size*0.3), (x + size*0.5, y + size*0.3)
        ]
        draw.polygon(coords, fill=ACCENT_YELLOW)

    def draw_icon_shield(self, draw, x, y, size=10):
        """Draws a shield icon indicating Protection Mode is active."""
        # Top arc
        draw.pieslice([x, y, x+size, y+size], 0, 180, fill=ACCENT_BLUE)
        # Middle rect
        draw.rectangle([x, y, x+size, y+size/2], fill=ACCENT_BLUE)
        # Bottom point
        draw.polygon([(x, y+size/2), (x+size, y+size/2), (x+size/2, y+size)], fill=ACCENT_BLUE)

    def create_key_image(self, label, width, height, mode=0):
        """
        Generates a transparent RGBA image for a single key.

        Args:
            label (str): Key text (e.g. "A" or "1\n!").
            width (int): Target width in pixels.
            height (int): Target height in pixels.
            mode (int): Bitmask for active features (RT/Prot).

        Returns:
            PIL.Image: The generated image.
        """
        width = int(width)
        height = int(height)

        # Transparent background (The UI button handles the background color)
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # --- TEXT RENDERING ---
        if "\n" in label:
            # Dual label (e.g., Number Row: '1' on top, '!' on bottom)
            parts = label.split("\n")
            top_txt, bot_txt = parts[0], parts[1]

            # Draw Top (Small)
            bbox_t = draw.textbbox((0, 0), top_txt, font=self.font_small)
            w_t = bbox_t[2] - bbox_t[0]
            # y=15% from top
            draw.text((width/2 - w_t/2, height*0.15), top_txt, font=self.font_small, fill=TEXT_COLOR)

            # Draw Bottom (Large)
            bbox_b = draw.textbbox((0, 0), bot_txt, font=self.font_large)
            w_b = bbox_b[2] - bbox_b[0]
            # y=45% from top
            draw.text((width/2 - w_b/2, height*0.45), bot_txt, font=self.font_large, fill=TEXT_COLOR)
        else:
            # Single label (e.g. 'A' or 'ENTER')
            # Use small font for long words like 'PRINT SCREEN'
            font_use = self.font_small if len(label) > 2 else self.font_large

            bbox = draw.textbbox((0, 0), label, font=font_use)
            tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]

            # Center vertically, slightly biased upwards to leave room for icons
            draw.text((width/2 - tw/2, height*0.35 - th/2), label, font=font_use, fill=TEXT_COLOR)

        # --- ICON RENDERING ---
        icon_size = 12
        base_y = height - icon_size - 6  # Padding from bottom

        has_prot = (mode & MASK_PROT) > 0
        has_rt   = (mode & MASK_RT) > 0

        if has_prot and has_rt:
            # Draw both icons centered with a gap
            gap = 6
            center = width / 2
            x_shield = center - gap/2 - icon_size
            x_bolt = center + gap/2

            self.draw_icon_shield(draw, x_shield, base_y, icon_size)
            self.draw_icon_bolt(draw, x_bolt, base_y, icon_size)

        elif has_prot:
            # Draw shield centered
            self.draw_icon_shield(draw, (width - icon_size)/2, base_y, icon_size)

        elif has_rt:
            # Draw bolt centered
            self.draw_icon_bolt(draw, (width - icon_size)/2, base_y, icon_size)

        return img

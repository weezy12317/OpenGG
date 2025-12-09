import customtkinter as ctk
import tkinter as tk
from PIL import Image, ImageTk
import colorsys

class CustomColorPicker(ctk.CTkToplevel):
    """
    A custom, modal color picker dialog using HSV color space.

    Features:
    - HSV Color Model for intuitive selection.
    - Low-res rendering + Bilinear Upscaling for high-performance updates.
    - Hex code input/output.
    """
    def __init__(self, parent, initial_color="#FFFFFF", on_pick_callback=None):
        super().__init__(parent)
        self.on_pick_callback = on_pick_callback
        self.result_color = None

        self.title("Select Color")
        self.geometry("400x480")
        self.resizable(False, False)

        # Make window modal (block interactions with main window)
        self.transient(parent)

        # Internal State (HSV Model is easier for pickers)
        self.h = 0.0
        self.s = 0.0
        self.v = 1.0
        self._parse_initial_color(initial_color)

        self.setup_ui()
        self.update_visuals()

        # Bring to front and grab focus safely
        self.lift()
        self.after(100, self._safe_grab)

    def _safe_grab(self):
        """Attempts to grab input focus without crashing if window is already destroyed."""
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _parse_initial_color(self, hex_col):
        """Converts HEX string to internal HSV state."""
        if not hex_col or not isinstance(hex_col, str) or not hex_col.startswith("#"):
            hex_col = "#FFFFFF"

        try:
            r = int(hex_col[1:3], 16) / 255.0
            g = int(hex_col[3:5], 16) / 255.0
            b = int(hex_col[5:7], 16) / 255.0
            self.h, self.s, self.v = colorsys.rgb_to_hsv(r, g, b)
        except ValueError:
            self.h, self.s, self.v = 0, 0, 1

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)

        # 1. Saturation / Value Canvas (Large Box)
        self.sv_size = 250
        self.canvas_sv = tk.Canvas(
            self, width=self.sv_size, height=self.sv_size,
            bd=0, highlightthickness=0, cursor="crosshair", bg="#222"
        )
        self.canvas_sv.pack(pady=(20, 10))

        # Bind interactions
        self.canvas_sv.bind("<B1-Motion>", self.on_sv_drag)
        self.canvas_sv.bind("<Button-1>", self.on_sv_drag)

        # Selection Circle cursor
        self.sv_marker = self.canvas_sv.create_oval(0, 0, 10, 10, outline="white", width=2)

        # 2. Hue Bar (Slider)
        self.hue_width = 300
        self.hue_height = 30
        self.canvas_hue = tk.Canvas(
            self, width=self.hue_width, height=self.hue_height,
            bd=0, highlightthickness=0, cursor="sb_h_double_arrow", bg="#222"
        )
        self.canvas_hue.pack(pady=10)
        self.canvas_hue.bind("<B1-Motion>", self.on_hue_drag)
        self.canvas_hue.bind("<Button-1>", self.on_hue_drag)

        self._draw_hue_gradient()

        # Hue Indicator Line
        self.hue_marker = self.canvas_hue.create_line(0, 0, 0, 30, fill="black", width=3)

        # 3. Info & Preview Area
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(pady=20)

        # Color Preview Box
        self.lbl_preview = ctk.CTkLabel(info_frame, text="", width=60, height=40, fg_color="#FFFFFF", corner_radius=5)
        self.lbl_preview.pack(side="left", padx=20)

        ctk.CTkLabel(info_frame, text="HEX:").pack(side="left", padx=(10, 5))
        self.entry_hex = ctk.CTkEntry(info_frame, width=80, font=("Monospace", 12))
        self.entry_hex.pack(side="left")
        self.entry_hex.bind("<Return>", self.on_hex_submit)
        self.entry_hex.bind("<FocusOut>", self.on_hex_submit)

        # 4. Action Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", pady=20, padx=20)

        ctk.CTkButton(btn_frame, text="Cancel", fg_color="#333", hover_color="#444",
                      command=self.cancel).pack(side="left", expand=True, padx=5)

        ctk.CTkButton(btn_frame, text="Select Color", fg_color="#1f538d",
                      command=self.confirm).pack(side="right", expand=True, padx=5)

    def _draw_hue_gradient(self):
        """Generates the static rainbow hue bar."""
        img = Image.new("RGB", (self.hue_width, 1))
        pixels = img.load()

        for x in range(self.hue_width):
            hue = x / self.hue_width
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            pixels[x, 0] = (int(r * 255), int(g * 255), int(b * 255))

        img = img.resize((self.hue_width, self.hue_height))
        self.tk_hue = ImageTk.PhotoImage(img)
        self.canvas_hue.create_image(0, 0, image=self.tk_hue, anchor="nw")

    def _draw_sv_gradient(self):
        """
        Generates the Saturation/Value gradient for the current Hue.

        PERFORMANCE TRICK:
        Rendering 250x250 pixels pixel-by-pixel in Python is very slow.
        Instead, we render a tiny 50x50 image and let PIL upscale it using
        Bilinear interpolation. This is visually identical but ~25x faster.
        """
        # Get base color from current Hue
        base_r, base_g, base_b = colorsys.hsv_to_rgb(self.h, 1.0, 1.0)

        res = 50 # Low resolution buffer
        img = Image.new("RGB", (res, res))
        pixels = img.load()

        # Pre-calculate base constants to avoid doing it inside the loop
        base_r_255 = base_r * 255
        base_g_255 = base_g * 255
        base_b_255 = base_b * 255

        for y in range(res):
            val = 1.0 - (y / res)
            for x in range(res):
                sat = x / res

                # Mixing logic: White (sat=0) -> Color (sat=1) -> Black (val=0)
                r = (255 + (base_r_255 - 255) * sat) * val
                g = (255 + (base_g_255 - 255) * sat) * val
                b = (255 + (base_b_255 - 255) * sat) * val

                pixels[x, y] = (int(r), int(g), int(b))

        # Upscale with interpolation for smooth look
        img = img.resize((self.sv_size, self.sv_size), Image.Resampling.BILINEAR)
        self.tk_sv = ImageTk.PhotoImage(img)

        # Update Canvas
        if hasattr(self, 'sv_img_id'):
            self.canvas_sv.itemconfigure(self.sv_img_id, image=self.tk_sv)
        else:
            self.sv_img_id = self.canvas_sv.create_image(0, 0, image=self.tk_sv, anchor="nw")
            self.canvas_sv.tag_lower(self.sv_img_id)

    def update_visuals(self):
        """Redraws the gradients and updates UI elements based on internal state."""
        self._draw_sv_gradient()

        r, g, b = colorsys.hsv_to_rgb(self.h, self.s, self.v)
        hex_code = f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"

        # Update Text Entry
        self.entry_hex.delete(0, "end")
        self.entry_hex.insert(0, hex_code)

        # Update Preview Box Color
        self.lbl_preview.configure(fg_color=hex_code)

        # Update Hue Marker Position
        hx = self.h * self.hue_width
        self.canvas_hue.coords(self.hue_marker, hx, 0, hx, self.hue_height)

        # Update SV Marker Position
        sv_x = self.s * self.sv_size
        sv_y = (1.0 - self.v) * self.sv_size
        r_rad = 5
        self.canvas_sv.coords(self.sv_marker, sv_x - r_rad, sv_y - r_rad, sv_x + r_rad, sv_y + r_rad)

        # Contrast handling: marker should be black on bright backgrounds, white on dark
        marker_col = "black" if self.v > 0.5 else "white"
        self.canvas_sv.itemconfigure(self.sv_marker, outline=marker_col)

    # --- INPUT HANDLERS ---

    def on_hue_drag(self, event):
        x = min(max(event.x, 0), self.hue_width)
        self.h = x / self.hue_width
        self.update_visuals()

    def on_sv_drag(self, event):
        x = min(max(event.x, 0), self.sv_size)
        y = min(max(event.y, 0), self.sv_size)

        self.s = x / self.sv_size
        self.v = 1.0 - (y / self.sv_size)
        self.update_visuals()

    def on_hex_submit(self, event=None):
        hex_code = self.entry_hex.get()
        if len(hex_code) == 7 and hex_code.startswith("#"):
            try:
                self._parse_initial_color(hex_code)
                self.update_visuals()
            except: pass

    def confirm(self):
        r, g, b = colorsys.hsv_to_rgb(self.h, self.s, self.v)
        rgb = (int(r * 255), int(g * 255), int(b * 255))
        hex_code = f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"

        if self.on_pick_callback:
            self.on_pick_callback(rgb, hex_code)

        self.result_color = (rgb, hex_code)
        self.destroy()

    def cancel(self):
        self.result_color = None
        self.destroy()

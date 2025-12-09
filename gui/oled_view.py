import sys
import os
import customtkinter as ctk
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk, ImageFont

# --- IMPORTS ---
# Conditional imports to support running this file standalone for testing
try:
    from gui.custom_image_picker import CustomImagePicker
except ImportError:
    sys.path.append(os.path.dirname(__file__))
    from custom_image_picker import CustomImagePicker

try:
    from backend.oled_processing import OLED_WIDTH, OLED_HEIGHT
except ImportError:
    # Fallback constants if backend is not reachable
    OLED_WIDTH = 128
    OLED_HEIGHT = 40

# --- EDITOR CONFIG ---
# Scale factor for the UI editor (4x zoom makes it easier to draw pixels)
EDITOR_SCALE = 4
CANVAS_W = OLED_WIDTH * EDITOR_SCALE
CANVAS_H = OLED_HEIGHT * EDITOR_SCALE

class OLEDFrame(ctk.CTkFrame):
    """
    A 1-bit Pixel Art Editor for the OLED Display.
    Maintains two states:
    1. self.image (PIL): The actual 1-bit data sent to hardware.
    2. self.canvas (Tkinter): The scaled-up visual representation for the user.
    """
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance

        # Data Model: 1-Bit Image (Black/White)
        self.image = Image.new("1", (OLED_WIDTH, OLED_HEIGHT), 0)
        self.draw = ImageDraw.Draw(self.image)
        self.history = []

        # Tool State
        self.is_drawing = False
        self.last_x = 0
        self.last_y = 0
        self.brush_color = 1  # 1 = White (Pixel On), 0 = Black (Pixel Off)

        self.photo_image = None # Keep reference to prevent GC

        # Load Font (Try to find a good system font, else fallback)
        self.font = self._load_system_font()

        # Build UI
        self.setup_ui()

    def _load_system_font(self):
        candidates = [
            "/usr/share/fonts/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/arial.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
        ]
        for path in candidates:
            if os.path.exists(path):
                try: return ImageFont.truetype(path, 24)
                except: pass
        return ImageFont.load_default()

    def setup_ui(self):
        # --- TOOLBAR ---
        toolbar = ctk.CTkFrame(self)
        toolbar.pack(fill="x", pady=(0, 10))
        btn_padding = 5

        # Import Button
        btn_import = ctk.CTkButton(toolbar, text="Import Image", width=100, command=self.import_image)
        btn_import.pack(side="left", padx=5, pady=btn_padding)

        # Clear Button
        btn_clear = ctk.CTkButton(toolbar, text="Clear All", width=80,
                                  fg_color="#c0392b", hover_color="#e74c3c",
                                  command=self.clear_canvas)
        btn_clear.pack(side="left", padx=5, pady=btn_padding)

        # Undo Button
        btn_undo = ctk.CTkButton(toolbar, text="Undo", width=80,
                                 fg_color="#555555", hover_color="#666666",
                                 command=self.undo)
        btn_undo.pack(side="left", padx=5, pady=btn_padding)

        # Draw/Erase Switcher
        self.mode_var = ctk.StringVar(value="Draw")
        seg_btn = ctk.CTkSegmentedButton(toolbar, values=["Draw", "Erase"], command=self.set_brush_mode)
        seg_btn.set("Draw")
        seg_btn.pack(side="right", padx=10, pady=btn_padding)

        # --- EDITOR CANVAS ---
        editor_container = ctk.CTkFrame(self, fg_color="#111")
        editor_container.pack(pady=10, padx=20)

        self.canvas = tk.Canvas(editor_container, width=CANVAS_W, height=CANVAS_H, bg="black", highlightthickness=0)
        self.canvas.pack(padx=10, pady=10)

        # Bind Mouse Events
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        # --- TEXT TOOL ---
        text_frame = ctk.CTkFrame(self, fg_color="transparent")
        text_frame.pack(pady=(0, 20))

        self.entry_text = ctk.CTkEntry(text_frame, placeholder_text="Enter text here...", width=200)
        self.entry_text.pack(side="left", padx=5)
        self.entry_text.bind("<Return>", lambda e: self.add_text())

        btn_text = ctk.CTkButton(text_frame, text="Add Text", width=100, command=self.add_text)
        btn_text.pack(side="left", padx=5)

        # --- SEND BUTTON ---
        self.btn_apply = ctk.CTkButton(self, text="Send to OLED", height=40,
                                       font=ctk.CTkFont(size=16, weight="bold"),
                                       command=self.send_to_hardware)
        self.btn_apply.pack(pady=10)

    def set_brush_mode(self, value):
        self.brush_color = 1 if value == "Draw" else 0

    # --- STATE MANAGEMENT ---

    def save_state(self):
        """Snapshots the current image to the undo history."""
        if len(self.history) > 20:
            self.history.pop(0)
        self.history.append(self.image.copy())

    def undo(self):
        """Restores the last snapshot."""
        if not self.history: return
        last_state = self.history.pop()
        self.image = last_state.copy()
        self.draw = ImageDraw.Draw(self.image)
        self.redraw_canvas_from_image()

    def clear_canvas(self):
        """Wipes the canvas black."""
        self.save_state()

        # 1. Reset Data
        self.image = Image.new("1", (OLED_WIDTH, OLED_HEIGHT), 0)
        self.draw = ImageDraw.Draw(self.image)

        # 2. Reset Visuals
        self.canvas.delete("all")
        self.redraw_canvas_from_image()

    def redraw_canvas_from_image(self):
        """
        Synchronizes the visible Tkinter canvas with the internal PIL image data.
        Scales the 128x40 image up to the editor size using Nearest Neighbor (pixelated look).
        """
        self.canvas.delete("all")

        # Resize for display
        preview = self.image.resize((CANVAS_W, CANVAS_H), Image.Resampling.NEAREST)

        # Convert to RGB because Tkinter has issues with 1-bit bitmaps sometimes
        preview = preview.convert("RGB")

        self.photo_image = ImageTk.PhotoImage(preview)
        self.canvas.create_image(0, 0, image=self.photo_image, anchor="nw")

    def load_image_data(self, raw_data_list):
        """Called by main app to populate editor from a saved profile."""
        self.history = [] # Clear undo stack on new load

        if not raw_data_list or len(raw_data_list) != 640:
            self.image = Image.new("1", (OLED_WIDTH, OLED_HEIGHT), 0)
        else:
            try:
                byte_data = bytes(raw_data_list)
                self.image = Image.frombytes("1", (OLED_WIDTH, OLED_HEIGHT), byte_data)
            except Exception as e:
                print(f"[OLED] Load Error: {e}")
                self.image = Image.new("1", (OLED_WIDTH, OLED_HEIGHT), 0)

        self.draw = ImageDraw.Draw(self.image)
        self.redraw_canvas_from_image()

    # --- TOOLS ---

    def add_text(self):
        text = self.entry_text.get()
        if not text: return

        self.save_state()

        # Center the text
        bbox = self.draw.textbbox((0, 0), text, font=self.font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (OLED_WIDTH - w) / 2
        y = (OLED_HEIGHT - h) / 2 - 4  # -4 optical adjustment

        self.draw.text((x, y), text, font=self.font, fill=1)
        self.redraw_canvas_from_image()

    def import_image(self):
        def on_image_picked(path):
            if path:
                self.save_state()
                try:
                    loaded_img = Image.open(path)

                    # Force fit
                    loaded_img = loaded_img.resize((OLED_WIDTH, OLED_HEIGHT), Image.Resampling.LANCZOS)
                    # Dither to 1-bit
                    loaded_img = loaded_img.convert("1")

                    self.image = loaded_img
                    self.draw = ImageDraw.Draw(self.image)
                    self.redraw_canvas_from_image()
                except Exception as e:
                    print(f"Import Error: {e}")

        CustomImagePicker(self, on_pick_callback=on_image_picked)

    # --- INPUT HANDLERS (DRAWING) ---

    def on_mouse_down(self, event):
        self.save_state()
        self.is_drawing = True
        self.last_x = event.x
        self.last_y = event.y
        self._paint_line(event.x, event.y, event.x, event.y)

    def on_mouse_drag(self, event):
        if self.is_drawing:
            self._paint_line(self.last_x, self.last_y, event.x, event.y)
            self.last_x = event.x
            self.last_y = event.y

    def on_mouse_up(self, event):
        self.is_drawing = False

    def _paint_line(self, x1, y1, x2, y2):
        """
        Draws a line on both the UI canvas and the internal data image.
        Mapping logic: Screen Coord / Scale = Data Coord.
        """
        # 1. Update UI (Visual Feedback)
        color_str = "white" if self.brush_color else "black"
        self.canvas.create_line(x1, y1, x2, y2, fill=color_str, width=EDITOR_SCALE, capstyle=tk.ROUND)

        # 2. Update Data (Hardware Model)
        sx = int(x1 / EDITOR_SCALE)
        sy = int(y1 / EDITOR_SCALE)
        ex = int(x2 / EDITOR_SCALE)
        ey = int(y2 / EDITOR_SCALE)

        self.draw.line([(sx, sy), (ex, ey)], fill=self.brush_color, width=1)

    # --- HARDWARE COMM ---

    def send_to_hardware(self):
        """Exports the current image to bytes and sends it via the driver."""
        if self.app.kb:
            data = list(self.image.tobytes())

            # Ensure 640 bytes exact
            if len(data) < 640: data += [0] * (640 - len(data))
            data = data[:640]

            self.app.kb.set_oled_image(data)

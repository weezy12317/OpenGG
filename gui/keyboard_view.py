import customtkinter as ctk
import tkinter as tk

# --- LOCAL IMPORTS ---
from gui.key_renderer import KeyRenderer
from backend.layouts import LAYOUTS
from backend.key_mapping import OMNIPOINT_KEYS
from backend.languages import get_key_label

# --- THEME CONSTANTS ---
COLOR_APP_BG = "#242424"
COLOR_CHASSIS = "#161616"
COLOR_CHASSIS_BORDER = "#050505"
COLOR_KEY_BASE = "#2B2B2B"
COLOR_KEY_HOVER = "#3E3E3E"
COLOR_KEY_DISABLED = "#111111"
COLOR_SELECTION_BORDER = "#FFFFFF"
COLOR_RUBBERBAND = "#4169E1"  # Royal Blue for selection box

class KeyboardFrame(ctk.CTkFrame):
    """
    The main visualizer component.
    Renders the keyboard layout, handles selection (Click/Drag), and updates key visuals.
    """
    def __init__(self, master, on_selection_change_callback):
        super().__init__(master, fg_color=COLOR_APP_BG, corner_radius=0)

        self.callback = on_selection_change_callback
        self.renderer = KeyRenderer()

        # Visual Caches (to prevent re-rendering unchanged keys)
        self.key_data_cache = {}
        self.key_states_cache = {}

        self.current_layout = LAYOUTS.get("TKL_ANSI", {})
        self.current_language = "English (US)"

        # Selection State
        self.selected_keys = set()
        self.selection_snapshot = set()
        self.drag_mode = "replace"  # replace, add, remove
        self.selection_mode = "all" # all, omnipoint

        # Dragging State
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.is_dragging = False

        # Rendering Metrics
        self.key_objects = {}
        self.unit_size = 60  # 1 Key Unit = 60px
        self.gap_w = 11
        self.gap_h = 9
        self.chassis_padding = 20

        # Main Drawing Surface
        self.canvas = tk.Canvas(
            self, bg=COLOR_APP_BG, highlightthickness=0, bd=0
        )
        self.canvas.pack(fill="both", expand=True)

        # Rubberband Selection Box (4 thin frames forming a rect)
        self.rubberband_frames = []
        for _ in range(4):
            f = ctk.CTkFrame(self, fg_color=COLOR_RUBBERBAND, corner_radius=0, border_width=0)
            self.rubberband_frames.append(f)

        # Bind Global Mouse Events (for clicking empty space)
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        self.render_layout()

    # --- EVENT BINDING HELPERS ---

    def force_bind_events(self, widget, key_name):
        """
        Recursively binds mouse events to a widget and ALL its children.

        Why? CTkButton is a composite widget (Frame + Canvas + Label).
        Clicking the text label physically blocks the event from reaching the button
        unless we manually bind the event to the label too.
        """
        def handler_down(event): self.on_mouse_down(event, override_key=key_name)
        def handler_drag(event): self.on_mouse_drag(event)
        def handler_up(event):   self.on_mouse_up(event)

        # 1. Bind to Main Widget
        widget.bind("<ButtonPress-1>", handler_down, add="+")
        widget.bind("<B1-Motion>", handler_drag, add="+")
        widget.bind("<ButtonRelease-1>", handler_up, add="+")

        # 2. Identify Internal Parts of CustomTkinter Widgets
        parts = []
        if hasattr(widget, "_canvas"): parts.append(widget._canvas)
        if hasattr(widget, "_text_label"): parts.append(widget._text_label)
        if hasattr(widget, "_image_label"): parts.append(widget._image_label)

        # 3. Catch-all for future versions
        for child in widget.winfo_children():
            parts.append(child)

        for part in parts:
            if part and part != widget:
                # Use add="+" to ensure we don't overwrite internal CTk logic
                part.bind("<ButtonPress-1>", handler_down, add="+")
                part.bind("<B1-Motion>", handler_drag, add="+")
                part.bind("<ButtonRelease-1>", handler_up, add="+")

    # --- PUBLIC API ---

    def update_key_data(self, key_data_dict):
        """Receives new config data (actuation points, etc.) and refreshes visuals."""
        self.key_data_cache.update(key_data_dict)
        self.key_states_cache = {}  # Invalidate visual cache
        self.refresh_visuals()

    def set_mode(self, mode):
        """Switches selection filter (e.g. only allow Omnipoint keys)."""
        self.selection_mode = mode
        if mode == "omnipoint":
            # Deselect keys that are no longer valid
            to_remove = [k for k in self.selected_keys if k not in OMNIPOINT_KEYS]
            if to_remove:
                for k in to_remove: self.selected_keys.remove(k)
                self.callback(list(self.selected_keys))

        self.key_states_cache = {}
        self.refresh_visuals()

    def set_language(self, lang_name):
        self.current_language = lang_name
        self.render_layout()

    def select_all(self):
        if self.selection_mode == "omnipoint":
            self.selected_keys = {k for k in self.key_objects.keys() if k in OMNIPOINT_KEYS}
        else:
            self.selected_keys = set(self.key_objects.keys())

        self.key_states_cache = {}
        self.refresh_visuals()
        self.callback(list(self.selected_keys))

    # --- RENDERING ---

    def create_rounded_rect(self, x1, y1, x2, y2, radius=25, **kwargs):
        """Helper to draw a rounded rectangle on the standard Tkinter Canvas."""
        points = [
            x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1, x2, y1, x2, y1+radius,
            x2, y1+radius, x2, y2-radius, x2, y2-radius, x2, y2, x2-radius, y2, x2-radius, y2,
            x1+radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y2-radius, x1, y1+radius,
            x1, y1+radius, x1, y1
        ]
        return self.canvas.create_polygon(points, **kwargs, smooth=True)

    def render_layout(self):
        """Builds the entire keyboard visual from scratch based on the current layout."""
        self.canvas.delete("all")
        self.key_objects = {}
        self.key_states_cache = {}

        if not self.current_layout: return

        # Calculate Bounding Box
        max_u_x = 0
        max_u_y = 0
        for k, (ux, uy, uw, uh) in self.current_layout.items():
            if (ux + uw) > max_u_x: max_u_x = ux + uw
            if (uy + uh) > max_u_y: max_u_y = uy + uh

        keys_width = max_u_x * self.unit_size
        keys_height = max_u_y * self.unit_size
        chassis_w = keys_width + (self.chassis_padding * 2)
        chassis_h = keys_height + (self.chassis_padding * 2)

        canvas_w = int(chassis_w + 40)
        canvas_h = int(chassis_h + 40)

        self.configure(width=canvas_w, height=canvas_h)
        self.canvas.configure(width=canvas_w, height=canvas_h)

        offset_x = 20
        offset_y = 20

        # Draw Chassis
        self.create_rounded_rect(
            offset_x, offset_y,
            offset_x + chassis_w, offset_y + chassis_h,
            radius=15, fill=COLOR_CHASSIS, outline=COLOR_CHASSIS_BORDER
        )

        # Draw OLED Placeholder (if applicable)
        if max_u_x > 16:
            oled_px_x = offset_x + self.chassis_padding + (15.5 * self.unit_size)
            oled_px_y = offset_y + self.chassis_padding
            oled_px_w = (3 * self.unit_size) - self.gap_w
            oled_px_h = (1 * self.unit_size) - self.gap_h
            self.canvas.create_rectangle(oled_px_x, oled_px_y, oled_px_x + oled_px_w, oled_px_y + oled_px_h,
                                         outline="#333", fill="#000", width=2)

        # Draw Keys
        for key_name, (u_x, u_y, u_w, u_h) in self.current_layout.items():
            x1 = offset_x + self.chassis_padding + (u_x * self.unit_size)
            y1 = offset_y + self.chassis_padding + (u_y * self.unit_size)
            w_px = (u_w * self.unit_size) - self.gap_w
            h_px = (u_h * self.unit_size) - self.gap_h

            label = get_key_label(self.current_language, key_name)

            # Using CTkButton to represent keys
            btn = ctk.CTkButton(
                self.canvas, text=label, width=w_px, height=h_px, corner_radius=4,
                font=("Arial", 10, "bold"), border_width=0,
                fg_color=COLOR_KEY_BASE, bg_color=COLOR_CHASSIS, hover_color=COLOR_KEY_HOVER
            )

            # Place on Canvas using create_window
            self.canvas.create_window(x1, y1, window=btn, anchor="nw")

            # Store metadata
            btn.original_text = label
            self.key_objects[key_name] = {
                'x1': x1, 'y1': y1, 'x2': x1 + w_px, 'y2': y1 + h_px,
                'width': w_px, 'height': h_px, 'widget': btn
            }

        self.refresh_visuals()

        # Apply Recursive Bindings to fix click issues
        for key_name, data in self.key_objects.items():
            self.force_bind_events(data['widget'], key_name)

    def is_selectable(self, key_name):
        if self.selection_mode == "omnipoint":
            return key_name in OMNIPOINT_KEYS
        return True

    # --- RUBBERBAND LOGIC ---

    def update_rubberband(self, x1, y1, x2, y2):
        """Draws the blue selection rectangle."""
        left, top = min(x1, x2), min(y1, y2)
        width, height = int(abs(x2 - x1)), int(abs(y2 - y1))

        # Ensure minimal visibility
        if width < 1: width = 1
        if height < 1: height = 1

        # Move the 4 lines (frames) to form a box
        # Top
        self.rubberband_frames[0].place(x=left, y=top)
        self.rubberband_frames[0].configure(width=width, height=2)
        # Bottom
        self.rubberband_frames[1].place(x=left, y=top+height)
        self.rubberband_frames[1].configure(width=width, height=2)
        # Left
        self.rubberband_frames[2].place(x=left, y=top)
        self.rubberband_frames[2].configure(width=2, height=height)
        # Right
        self.rubberband_frames[3].place(x=left+width, y=top)
        self.rubberband_frames[3].configure(width=2, height=height+2)

        for f in self.rubberband_frames: f.lift()

    def hide_rubberband(self):
        for f in self.rubberband_frames: f.place_forget()

    # --- INTERACTION LOGIC ---

    def _get_current_mouse_canvas_pos(self):
        """
        Calculates mouse position relative to the Canvas.
        Uses scaling correction to fix coordinate drift on HiDPI displays.
        """
        pointer_x = self.canvas.winfo_pointerx()
        pointer_y = self.canvas.winfo_pointery()
        root_x = self.canvas.winfo_rootx()
        root_y = self.canvas.winfo_rooty()

        try:
            scaling = ctk.get_widget_scaling()
            if scaling == 0: scaling = 1.0
        except:
            scaling = 1.0

        return (pointer_x - root_x) / scaling, (pointer_y - root_y) / scaling

    def on_mouse_down(self, event, override_key=None):
        # Use global coordinates to be independent of the clicked child widget
        mx, my = self._get_current_mouse_canvas_pos()

        self.is_dragging = True
        self.drag_start_x, self.drag_start_y = mx, my

        hit_key = override_key
        if not hit_key:
            # Fallback Hit Test (if user clicked slightly between keys)
            for key, data in self.key_objects.items():
                if not self.is_selectable(key): continue
                if data['x1'] <= mx <= data['x2'] and data['y1'] <= my <= data['y2']:
                    hit_key = key
                    break

        # Check for CTRL Key (Bitmask 4 or 0x40000 on Linux)
        ctrl_pressed = (event.state & 4) != 0 or (event.state & 0x40000) != 0

        self.selection_snapshot = self.selected_keys.copy()

        if hit_key:
            if ctrl_pressed:
                # Toggle logic
                self.drag_mode = "remove" if hit_key in self.selected_keys else "add"
            else:
                # Replace logic
                self.drag_mode = "replace"
        else:
            # Click on empty space
            self.drag_mode = "replace" if not ctrl_pressed else "add"

        current_target = {hit_key} if hit_key else set()
        self._apply_selection_logic(current_target)

        if not hit_key: self.hide_rubberband()

    def on_mouse_drag(self, event):
        if not self.is_dragging: return

        mx, my = self._get_current_mouse_canvas_pos()

        # Only draw rubberband if drag distance > 5px
        if abs(mx - self.drag_start_x) > 5 or abs(my - self.drag_start_y) > 5:
            self.update_rubberband(self.drag_start_x, self.drag_start_y, mx, my)

        # Calculate Selection Rectangle
        rx1, rx2 = sorted([self.drag_start_x, mx])
        ry1, ry2 = sorted([self.drag_start_y, my])

        keys_in_rect = set()
        for k, data in self.key_objects.items():
            if not self.is_selectable(k): continue

            # Simple AABB Collision Detection
            if (rx1 < data['x2'] and rx2 > data['x1'] and
                ry1 < data['y2'] and ry2 > data['y1']):
                keys_in_rect.add(k)

        self._apply_selection_logic(keys_in_rect)

    def _apply_selection_logic(self, active_keys):
        """Combines the current drag selection with the previous snapshot."""
        new_selection = set()

        if self.drag_mode == "replace":
            new_selection = active_keys
        elif self.drag_mode == "add":
            new_selection = self.selection_snapshot.union(active_keys)
        elif self.drag_mode == "remove":
            new_selection = self.selection_snapshot.difference(active_keys)

        if new_selection != self.selected_keys:
            self.selected_keys = new_selection
            self.refresh_visuals()

    def on_mouse_up(self, event):
        self.is_dragging = False
        self.hide_rubberband()
        self.callback(list(self.selected_keys))

    def refresh_visuals(self):
        """Re-generates key images where state has changed."""
        for key, data in self.key_objects.items():
            btn = data['widget']
            enabled = self.is_selectable(key)
            is_selected = key in self.selected_keys

            key_conf = self.key_data_cache.get(key, {})
            mode = key_conf.get("mode", 0)
            if not enabled: mode = 0

            # Cache Check: Skip rendering if nothing changed
            current_state = (is_selected, enabled, mode, data['width'], data['height'])
            if self.key_states_cache.get(key) == current_state:
                continue

            # Determine Colors
            bg_color = COLOR_KEY_DISABLED if not enabled else ("#3A3A3A" if is_selected else COLOR_KEY_BASE)
            border_color = COLOR_SELECTION_BORDER if is_selected else "#111"
            state = "disabled" if not enabled else "normal"

            # Render Image via KeyRenderer
            pil_img = self.renderer.create_key_image(btn.original_text, int(data['width']*2), int(data['height']*2), mode)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(data['width'], data['height']))

            btn.configure(image=ctk_img, text="", fg_color=bg_color, border_color=border_color, border_width=2, state=state)
            self.key_states_cache[key] = current_state

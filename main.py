import sys
import os
import time
import threading
import tkinter as tk

# --- THIRD PARTY IMPORTS ---
import customtkinter as ctk

# --- SYSTEM PATH SETUP ---
# Ensure the backend directory is visible to the Python interpreter
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# --- LOCAL BACKEND IMPORTS ---
from backend.config_manager import ConfigManager
from backend.autostart import AutostartManager
from backend.apex_driver import ApexPro
from backend.rgb_engine import RGBEngine
from backend.process_monitor import ProcessMonitor
from backend.key_mapping import ALL_KEYS, OMNIPOINT_KEYS
from backend.rgb_presets import PRESETS
from backend.languages import LANGUAGES, get_key_label
# Note: Device DB imports are handled lazily inside methods to prevent circular dependency issues if they arise.

# --- RUNTIME ARGUMENTS ---
# Check if the script is running in silent mode (background service/autostart)
IS_SILENT = "--silent" in sys.argv

# --- GUI SETUP ---
if not IS_SILENT:
    from gui.keyboard_view import KeyboardFrame
    from gui.oled_view import OLEDFrame
    from gui.custom_color_picker import CustomColorPicker

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

# --- CONSTANTS ---
# Column widths for the key configuration table
COL_WIDTH_KEY = 100
COL_WIDTH_ACT = 100
COL_WIDTH_RT = 120
COL_WIDTH_PROT = 100

# Bitmasks for feature flags
MASK_PROT = 1  # Protection Mode
MASK_RT = 2    # Rapid Trigger

# --- HELPER FUNCTIONS ---

def map_app_mode_to_hw(app_mode):
    """
    Converts the internal application mode bitmask to the hardware-specific integer value.
    Returns:
        4: Rapid Trigger
        3: Protection Mode
        0: Standard/Default
    """
    if app_mode & MASK_RT: return 4
    if app_mode & MASK_PROT: return 3
    return 0

# --- HEADLESS SERVICE ---

def run_headless():
    """
    Entry point for the background daemon.
    This function runs when the app is started via Autostart (no GUI).
    It monitors active processes to switch profiles automatically and maintains lighting.
    """
    try:
        cfg = ConfigManager()

        # Attempt to connect to the keyboard
        try:
            kb = ApexPro()
        except Exception:
            # If device is not found in headless mode, abort silently.
            return

        # Initialize RGB Engine
        rgb_engine = RGBEngine(kb)
        rgb_engine.start()

        def headless_load_profile(name):
            """
            Callback function to load a profile completely without UI interaction.
            Handles: Onboard memory switching, Actuation points, RGB, and OLED.
            """
            # Pause RGB to prevent USB saturation during bulk data transfer
            rgb_engine.pause()
            time.sleep(0.2)

            cfg.save_last_active_profile(name)

            # 1. Switch Onboard Profile (Hardware)
            hw_slot = cfg.get_profile_hw_slot(name)
            kb.load_onboard_profile(hw_slot)

            # 2. Apply Actuation & Rapid Trigger Settings
            all_keys = list(ALL_KEYS.keys())
            full_data = cfg.get_visual_data_for_all_keys(name, all_keys)
            config_dict = {}

            for k, v in full_data.items():
                hid = ALL_KEYS.get(k)
                if hid:
                    hw_mode = map_app_mode_to_hw(v.get("mode", 0))
                    settings = v.copy()
                    settings["mode"] = hw_mode
                    config_dict[hid] = settings

            kb.apply_config(config_dict)

            # 3. Apply RGB Settings
            linked_light = cfg.get_linked_lighting(name)
            light_data = cfg.get_lighting_data(linked_light)

            mode_name = light_data.get("mode", "static")
            speed = light_data.get("speed", 1.0)
            brightness = light_data.get("brightness", 1.0)

            # Determine Engine Configuration
            if mode_name in PRESETS:
                engine_config = PRESETS[mode_name].copy()
            else:
                # Custom Effect
                prim = light_data.get("primary_color", "#FF0000")
                engine_config = {
                    "type": mode_name.lower(),
                    "colors": [prim],
                    "speed": speed
                }

            # Apply Brightness logic for Static mode in Headless
            if engine_config["type"] == "static":
                c = engine_config["colors"][0]
                if isinstance(c, str):
                    h = c.lstrip("#")
                    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                else:
                    r, g, b = c
                engine_config["colors"] = [(int(r * brightness), int(g * brightness), int(b * brightness))]

            rgb_engine.set_background(engine_config, speed)

            # Apply Per-Key RGB Overrides
            overrides = light_data.get("static_colors", {})
            parsed_ov = {}

            for hid_str, val in overrides.items():
                try:
                    hid = int(hid_str)
                    if isinstance(val, dict):
                        m = val.get("mode", "static")
                        c = val.get("color", "#FFFFFF")
                    else:
                        m = "static"
                        c = str(val)

                    h = c.lstrip("#")
                    cr, cg, cb = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

                    if m == "static":
                        cr, cg, cb = int(cr * brightness), int(cg * brightness), int(cb * brightness)

                    parsed_ov[hid] = {"mode": m, "color": (cr, cg, cb)}
                except:
                    pass

            rgb_engine.set_overrides(parsed_ov)

            # 4. Apply OLED Settings
            linked_oled = cfg.get_linked_oled(name)
            oled_data = cfg.get_oled_data(linked_oled)
            raw_bytes = oled_data.get("image_data", [])

            is_empty = not raw_bytes or all(b == 0 for b in raw_bytes)
            if not is_empty:
                # Pad buffer to 640 bytes if necessary
                to_send = raw_bytes if len(raw_bytes) == 640 else raw_bytes + [0] * (640 - len(raw_bytes))
                kb.set_oled_image(to_send)

            rgb_engine.resume()

        # Start Process Monitor for automatic profile switching
        monitor = ProcessMonitor(cfg, headless_load_profile)
        monitor.start()

        # Load the last known active profile on startup
        last_prof = cfg.get_last_active_profile()
        headless_load_profile(last_prof)

        # Keep the main thread alive to allow the daemon threads to run
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        if 'rgb_engine' in locals(): rgb_engine.stop()
        if 'monitor' in locals(): monitor.stop()
    except Exception:
        # Retry loop to survive transient system errors
        while True:
            time.sleep(10)

import inspect
import time

def log_time(func):
    """Decorator that prints how long a function takes to run."""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start

        # Only print if it takes longer than 0.01s (10ms) to reduce spam
        if duration > 0.1:
            print(f"[{func.__name__}] took {duration:.3f}s")

        return result
    return wrapper

def profile_class(cls):
    """
    Applies the log_time decorator ONLY to methods defined in this specific class,
    ignoring inherited methods from libraries (like CustomTkinter).
    """
    for name, method in list(cls.__dict__.items()):
        # Check if it's a function and NOT a "dunder" method (like __str__)
        # We allow __init__ because that's often where slow startup code lives
        if inspect.isfunction(method) and (not name.startswith("__") or name == "__init__"):
            setattr(cls, name, log_time(method))
    return cls

# --- GUI APPLICATION CLASS ---
@profile_class
class OpenGGApp(ctk.CTk):
    """
    Main Application Window.
    Manages UI rendering, user input, and communication with the backend drivers.
    """
    def __init__(self):
        super().__init__()
        self.title("OpenGG - SteelSeries Controller")
        self.geometry("1400x950")

        self.autostart = AutostartManager()
        self.kb = None
        self.rgb_engine = None

        # --- HARDWARE INITIALIZATION ---
        try:
            self.kb = ApexPro()
            self.dev_info = self.kb.device_info

            # Initialize Lighting Engine
            self.rgb_engine = RGBEngine(self.kb)
            self.rgb_engine.start()

        except Exception:
            # Fallback for Demo Mode (No Hardware Detected)
            self.dev_info = {"features": 255, "layout_type": "TKL", "name": "Offline Mode"}
            self.rgb_engine = None

        # Import Icon
        try:
            icon_path = os.path.join(os.path.dirname(__file__), 'gui', 'assets', 'openGG_icon.png')

            if os.path.exists(icon_path):
                # Tkinter PhotoImage für Linux/Windows
                icon_img = tk.PhotoImage(file=icon_path)
                self.wm_iconphoto(True, icon_img)
            else:
                print(f"[UI] Icon nicht gefunden: {icon_path}")
        except Exception as e:
            print(f"[UI] Fehler beim Laden des Icons: {e}")

        # --- STATE MANAGEMENT ---
        self.cfg = ConfigManager()
        self.current_profile = self.cfg.get_last_active_profile()
        self.current_light_profile = self.cfg.get_linked_lighting(self.current_profile)
        self.current_oled_profile = self.cfg.get_linked_oled(self.current_profile)

        # UI State variables
        self.current_selection = []
        self.ignore_updates = False
        self.sidebar_expanded = True

        # Drag & Drop Logic Variables
        self.drag_start_y = 0
        self.dragging_item = None
        self.is_actually_dragging = False
        self.reorder_callback = None

        # Lighting State Defaults
        self.current_custom_effect = "static"
        self.effect_speed = 1.0
        self.effect_color = "#FF0000"

        # --- UI LAYOUT ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. Sidebar (Left)
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # 2. Stage (Center - Keyboard View)
        self.stage = ctk.CTkFrame(self, fg_color="transparent")
        self.stage.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)

        # 3. Inspector (Right - Settings)
        self.inspector = ctk.CTkFrame(self, width=340, corner_radius=0)
        self.inspector.grid(row=0, column=2, sticky="nsew")

        # --- BUILD COMPONENTS ---
        self.setup_sidebar()
        self.setup_stage_and_table()
        self.setup_inspector()

        # Start Process Monitor (UI Mode)
        self.monitor = ProcessMonitor(self.cfg, self.on_auto_switch_profile)
        self.monitor.start()

        # Set initial physical layout (ANSI/ISO)
        self.change_region(self.opt_layout.get())

        # Defer final state initialization to ensure UI renders first
        self.after(100, self.init_app_state)
        self.after(100,self._init_hardware)

    def _init_hardware(self):
            try:
                self.kb = ApexPro()
                self.dev_info = self.kb.device_info
                self.rgb_engine = RGBEngine(self.kb)
                self.rgb_engine.start()
            except Exception:
                self.dev_info = {"features": 255, "layout_type": "TKL", "name": "Offline Mode"}
                self.rgb_engine = None

    def init_app_state(self):
        """Loads the initial profile and updates UI state after startup."""

        self.on_tab_change()

        # Load the profile data
        self.load_profile(self.current_profile)
        self.update_autostart_btn()

        # UI update
        if hasattr(self, 'kb_view'):
             self.after(500, lambda: self.kb_view.select_all())

    # =========================================================================
    # UI CONSTRUCTION: SIDEBAR
    # =========================================================================
    def setup_sidebar(self):
        """Constructs the left navigation sidebar."""
        self.btn_toggle_sidebar = ctk.CTkButton(self.sidebar, text="☰", width=40, command=self.toggle_sidebar, fg_color="transparent", border_width=1)
        self.btn_toggle_sidebar.pack(pady=10, padx=10, anchor="w")

        self.lbl_app_name = ctk.CTkLabel(self.sidebar, text="OPENGG", font=ctk.CTkFont(size=22, weight="bold"))
        self.lbl_app_name.pack(pady=10)

        self.sb_scroll = ctk.CTkScrollableFrame(self.sidebar, label_text="CONFIGURATIONS")
        self.sb_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        self.refresh_profile_list()

        action_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        action_frame.pack(fill="x", padx=10, pady=(0, 20))

        self.btn_add = ctk.CTkButton(action_frame, text="+", width=35, height=35, font=ctk.CTkFont(size=20, weight="bold"),
                                     fg_color="#2ecc71", hover_color="#27ae60", command=self.add_profile_dialog)
        self.btn_add.pack(side="left")

        self.btn_link = ctk.CTkButton(action_frame, text="Link Game", height=35, fg_color="#2c3e50", hover_color="#34495e",
                                      command=self.open_performance_settings)
        self.btn_link.pack(side="left", padx=(5, 0), fill="x", expand=True)

        # Region Selector (ANSI/ISO)
        self.lbl_layout = ctk.CTkLabel(self.sidebar, text="Physical Region:")
        self.lbl_layout.pack(pady=(10,0))
        self.opt_layout = ctk.CTkOptionMenu(self.sidebar, values=["ANSI (US)", "ISO (EU/DE)"], command=self.change_region)
        self.opt_layout.set("ANSI (US)")
        self.opt_layout.pack(pady=(5, 10))

        # Language Selector
        lang_list = list(LANGUAGES.keys())
        self.opt_lang = ctk.CTkOptionMenu(self.sidebar, values=lang_list, command=self.change_language)
        self.opt_lang.set("English (US)")
        self.opt_lang.pack(pady=(5, 20))

    def build_sidebar_list(self, parent_frame, items, current_item, select_command,
                           delete_command=None, rename_command=None, reorder_command=None):
        """
        Generic helper to build a sortable list of items in the sidebar.
        Supports Drag & Drop reordering and context menus.
        """
        for widget in parent_frame.winfo_children():
            widget.destroy()

        display_list = list(items)
        if "Default" in display_list:
            display_list.remove("Default")
            display_list.insert(0, "Default")

        parent_frame.list_items = display_list

        # --- Drag & Drop Handlers ---
        def on_mouse_down(event, name):
            if name == "Default": return
            self.drag_start_y = event.y_root
            self.dragging_item = name
            self.is_actually_dragging = False

        def on_mouse_move(event, widget_row):
            if not self.dragging_item: return

            if not self.is_actually_dragging:
                # Deadzone check: prevent accidental drags on clicks
                if abs(event.y_root - self.drag_start_y) < 5: return
                self.is_actually_dragging = True
                self.configure(cursor="fleur")
                self.reorder_callback = reorder_command

            # Calculate new position
            row_height = 37
            mouse_y = parent_frame._parent_canvas.canvasy(event.y_root - parent_frame.winfo_rooty())
            target_index = int(mouse_y // row_height)
            current_list = parent_frame.list_items

            if target_index < 1: target_index = 1
            if target_index >= len(current_list): target_index = len(current_list) - 1

            try:
                current_index = current_list.index(self.dragging_item)
            except ValueError:
                return

            # Visual swap
            if current_index != target_index:
                item = current_list.pop(current_index)
                current_list.insert(target_index, item)
                parent_frame.list_items = current_list
                # Recursively rebuild list
                self.build_sidebar_list(parent_frame, current_list, current_item,
                                        select_command, delete_command, rename_command, reorder_command)

        def on_mouse_up(event, name):
            if self.dragging_item and self.is_actually_dragging:
                self.configure(cursor="")
                if self.reorder_callback:
                    self.reorder_callback(parent_frame.list_items)
            elif name:
                # Simple Click
                select_command(name)

            self.dragging_item = None
            self.is_actually_dragging = False
            self.reorder_callback = None

        # --- Render List Items ---
        for name in display_list:
            color = "#1f538d" if name == current_item else "transparent"
            row = ctk.CTkFrame(parent_frame, fg_color="transparent", height=35)
            row.pack(fill="x", pady=1)

            btn = ctk.CTkButton(row, text=name, fg_color=color, anchor="w", height=30, border_width=0)
            btn.pack(side="left", fill="x", expand=True, padx=(0, 2))

            if name != "Default":
                btn.bind("<Button-1>", lambda e, n=name: on_mouse_down(e, n))
                btn.bind("<B1-Motion>", lambda e, w=row: on_mouse_move(e, w))
                btn.bind("<ButtonRelease-1>", lambda e, n=name: on_mouse_up(e, n))
            else:
                btn.bind("<ButtonRelease-1>", lambda e, n=name: select_command(n))

            # Context Menu Button
            if name != "Default":
                cmd_btn = ctk.CTkButton(row, text="•••", width=25, height=25,
                                        fg_color="transparent", text_color="#aaa",
                                        hover_color="#333", font=("Arial", 14, "bold"))

                def show_context_menu(event, target_name):
                    m = tk.Menu(self, tearoff=0, bg="#2b2b2b", fg="white", activebackground="#1f538d", activeforeground="white", bd=0)
                    if rename_command:
                        m.add_command(label="Rename", command=lambda t=target_name: rename_command(t))
                    if delete_command:
                        m.add_command(label="Delete", command=lambda t=target_name: delete_command(t), foreground="#e74c3c")
                    try:
                        m.tk_popup(event.widget.winfo_rootx(), event.widget.winfo_rooty() + event.widget.winfo_height())
                    finally:
                        m.grab_release()

                cmd_btn.bind("<Button-1>", lambda e, n=name: show_context_menu(e, n))
                cmd_btn.pack(side="right")

    # =========================================================================
    # UI CONSTRUCTION: STAGE (CENTER)
    # =========================================================================
    def setup_stage_and_table(self):
        """Sets up the central keyboard visualization and the data table beneath it."""
        # 1. Keyboard Container
        self.kb_container = ctk.CTkScrollableFrame(self.stage, label_text="Keyboard View", orientation="horizontal", height=500)
        self.kb_container.pack(fill="x", expand=False, pady=0)
        self._bind_scroll(self.kb_container)

        self.kb_view = KeyboardFrame(self.kb_container, self.select_key)
        self.kb_view.pack(anchor="center", pady=0, padx=20)
        self.kb_view.set_mode("omnipoint")
        self._recursive_enable_scroll(self.kb_view, self.kb_container, "horizontal")

        # 2. Info Header
        self.info_container = ctk.CTkFrame(self.stage, fg_color="transparent")
        self.info_container.pack(fill="both", expand=True)

        self.lbl_selected_count = ctk.CTkLabel(self.info_container, text="Select keys to edit", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_selected_count.pack(anchor="w")

        # 3. Data Table
        self.table_container = ctk.CTkFrame(self.info_container, fg_color="transparent")
        self.table_container.pack(fill="both", expand=True)

        # Table Header Row
        self.table_header = ctk.CTkFrame(self.table_container, height=30, fg_color="#222", corner_radius=5)
        self.table_header.pack(fill="x")
        ctk.CTkLabel(self.table_header, text="Key", width=COL_WIDTH_KEY, anchor="w").pack(side="left", padx=10)
        ctk.CTkLabel(self.table_header, text="Actuation (mm)", width=COL_WIDTH_ACT, anchor="center").pack(side="left", padx=5)

        # Rapid Trigger Header
        frame_head_rt = ctk.CTkFrame(self.table_header, width=COL_WIDTH_RT, fg_color="transparent")
        frame_head_rt.pack(side="left", padx=5)
        ctk.CTkLabel(frame_head_rt, text="Rapid Trigger", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 5))
        self.chk_header_rt = ctk.CTkCheckBox(frame_head_rt, text="", width=20, command=self.on_header_rt_toggle)
        self.chk_header_rt.pack(side="left")

        # Protection Mode Header
        frame_head_prot = ctk.CTkFrame(self.table_header, width=COL_WIDTH_PROT, fg_color="transparent")
        frame_head_prot.pack(side="left", padx=5)
        ctk.CTkLabel(frame_head_prot, text="Protection", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 5))
        self.chk_header_prot = ctk.CTkCheckBox(frame_head_prot, text="", width=20, command=self.on_header_prot_toggle)
        self.chk_header_prot.pack(side="left")

        # Scrollable Content Area
        self.table_scroll = ctk.CTkScrollableFrame(self.table_container, fg_color="transparent")
        self.table_scroll.pack(fill="both", expand=True, pady=(5, 0))
        self._recursive_enable_scroll(self.table_scroll, self.table_scroll, "vertical")

    # =========================================================================
    # UI CONSTRUCTION: INSPECTOR (RIGHT)
    # =========================================================================
    def setup_inspector(self):
        """Sets up the tab view for Performance, Lighting, and OLED settings."""
        self.tabs = ctk.CTkTabview(self.inspector, width=300, command=self.on_tab_change)
        self.tabs.pack(pady=10, padx=10, fill="both", expand=True)

        self.tabs.add("Performance")
        self.tabs.add("Lighting")

        # Only add OLED tab if supported
        from backend.device_db import FEAT_OLED
        if self.dev_info["features"] & FEAT_OLED:
            self.tabs.add("OLED")
            self.setup_oled_tab()

    def setup_perf_tab(self):
        # 1. Define the parent tab
        tab = self.tabs.tab("Performance")

        # 2. Setup Column Weights (Optional but good for resizing)
        tab.grid_columnconfigure(0, weight=1)

        # Actuation Control
        ctk.CTkLabel(tab, text="Actuation", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 5))
        frame_act = ctk.CTkFrame(tab, fg_color="transparent")
        frame_act.pack(pady=5)
        self.entry_act = ctk.CTkEntry(frame_act, width=60, justify="center")
        self.entry_act.pack(side="left", padx=5)
        self.entry_act.bind("<Return>", self.on_entry_act_submit)
        self.entry_act.bind("<FocusOut>", self.on_entry_act_submit)
        ctk.CTkLabel(frame_act, text="mm").pack(side="left")

        self.slider_act = ctk.CTkSlider(tab, from_=0.1, to=4.0, number_of_steps=39, command=self.on_slider_act)
        self.slider_act.set(1.8)
        self.slider_act.pack(pady=5, fill="x", padx=20)

        # Rapid Trigger Control
        ctk.CTkLabel(tab, text="Rapid Trigger", font=ctk.CTkFont(weight="bold")).pack(pady=(30, 0))
        ctk.CTkLabel(tab, text="Sensitivity", font=ctk.CTkFont(size=12)).pack(pady=(0, 5))
        frame_rt = ctk.CTkFrame(tab, fg_color="transparent")
        frame_rt.pack(pady=5)
        self.entry_rt = ctk.CTkEntry(frame_rt, width=60, justify="center")
        self.entry_rt.pack(side="left", padx=5)
        self.entry_rt.bind("<Return>", self.on_entry_rt_submit)
        self.entry_rt.bind("<FocusOut>", self.on_entry_rt_submit)
        ctk.CTkLabel(frame_rt, text="mm").pack(side="left")

        self.slider_rt = ctk.CTkSlider(tab, from_=0.1, to=4.0, number_of_steps=39, command=self.on_slider_rt)
        self.slider_rt.set(0.1)
        self.slider_rt.pack(pady=5, fill="x", padx=20)

        # Action Buttons
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=10, pady=20)

        self.btn_reset = ctk.CTkButton(btn_frame, text="Reset All Keys", command=self.reset_all_keys,
                                       height=30, fg_color="#c0392b", hover_color="#e74c3c")
        self.btn_reset.pack(fill="x", pady=(0, 10))

        self.btn_apply = ctk.CTkButton(btn_frame, text="Apply Now", command=self.apply_to_keyboard,
                                       height=40, fg_color="#1f538d", font=ctk.CTkFont(weight="bold"))
        self.btn_apply.pack(fill="x", pady=(0, 10))

        self.btn_save_flash = ctk.CTkButton(btn_frame, text="Enable Autostart", command=self.toggle_autostart,
                                            height=30, fg_color="#333", text_color="#ddd", font=ctk.CTkFont(size=11))
        self.btn_save_flash.pack(fill="x")

    def setup_light_tab(self):
        tab = self.tabs.tab("Lighting")
        tab.grid_columnconfigure(0, weight=0, minsize=200)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # Left: Profile List
        frame_prof_list = ctk.CTkFrame(tab, width=200, corner_radius=0, fg_color="#1a1a1a")
        frame_prof_list.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=5)
        ctk.CTkLabel(frame_prof_list, text="RGB PROFILES", font=("Arial", 12, "bold")).pack(pady=5)
        self.light_prof_scroll = ctk.CTkScrollableFrame(frame_prof_list, fg_color="transparent")
        self.light_prof_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkButton(frame_prof_list, text="+ New Profile", fg_color="#2ecc71", command=self.add_light_prof).pack(fill="x", padx=5, pady=10)

        # Right: Content Area
        right_side_frame = ctk.CTkFrame(tab, fg_color="transparent")
        right_side_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        # Header
        header_frame = ctk.CTkFrame(right_side_frame, fg_color="transparent", height=40)
        header_frame.pack(side="top", fill="x", pady=(0, 10))
        ctk.CTkLabel(header_frame, text="Current Settings", font=("Arial", 14, "bold")).pack(side="left", padx=10)
        ctk.CTkButton(header_frame, text="Link to Profile", width=120, fg_color="#e67e22",
                      command=lambda: self.open_assign_dialog("lighting")).pack(side="right", padx=10)

        # Sub-Navigation (Presets vs Effects)
        seg_frame = ctk.CTkFrame(right_side_frame, fg_color="transparent")
        seg_frame.pack(side="top", fill="x", pady=(0, 10))

        btn_presets = ctk.CTkButton(seg_frame, text="Presets", width=100, command=lambda: self.show_light_subtab("Presets"), fg_color="#1f538d")
        btn_presets.pack(side="left", padx=5)

        btn_effects = ctk.CTkButton(seg_frame, text="Effects", width=100, command=lambda: self.show_light_subtab("Effects"), fg_color="transparent", border_width=1, text_color="gray")
        btn_effects.pack(side="left", padx=5)

        self.btn_light_tabs = {"Presets": btn_presets, "Effects": btn_effects}
        self.light_content = ctk.CTkFrame(right_side_frame, fg_color="transparent")
        self.light_content.pack(side="top", fill="both", expand=True)

        self.refresh_light_profile_list()
        self.show_light_subtab("Presets")

    def show_light_subtab(self, name):
        """Switches between the Presets list and the Custom Effect controls."""
        for widget in self.light_content.winfo_children():
            widget.destroy()

        # Update button visual state
        for k, btn in self.btn_light_tabs.items():
            if k == name:
                btn.configure(fg_color="#1f538d", text_color="white", border_width=0)
            else:
                btn.configure(fg_color="transparent", text_color="gray", border_width=1)

        if name == "Presets":
            self.build_presets_view()
        else:
            self.build_effects_view()

    def build_presets_view(self):
        """Renders the list of available RGB presets."""
        scroll = ctk.CTkScrollableFrame(self.light_content, label_text="Select Preset")
        scroll.pack(fill="both", expand=True)
        self._bind_scroll(scroll, "vertical")

        data = self.cfg.get_lighting_data(self.current_light_profile)
        current_mode = data.get("mode", "static")

        def add_preset_btn(name):
            is_active = (name == current_mode)
            fg = "#1f538d" if is_active else "transparent"
            txt = "white" if is_active else "gray"

            btn = ctk.CTkButton(scroll, text=name, anchor="w",
                                fg_color=fg, text_color=txt, border_width=1,
                                command=lambda n=name: self.apply_preset(n))
            btn.pack(fill="x", pady=2)
            self._bind_scroll(btn, "vertical")

        add_preset_btn("Off")
        for name in sorted(PRESETS.keys()):
            if name == "Off": continue
            add_preset_btn(name)

    def build_effects_view(self):
        """Renders controls for custom RGB effects (Static, Breath, etc.)."""
        list_frame = ctk.CTkScrollableFrame(self.light_content, label_text="Select Effect", height=200)
        list_frame.pack(fill="x", pady=5)
        self._bind_scroll(list_frame, "vertical")

        effects = ["Static", "Breath", "ColorShift", "Reflect"]
        for ef in effects:
            ctk.CTkButton(list_frame, text=ef, anchor="w", fg_color="transparent", border_width=1,
                          command=lambda e=ef: [setattr(self, "last_selected_effect_type", e.lower()), self.on_effect_change(e)]).pack(fill="x", pady=2)

        controls_frame = ctk.CTkFrame(self.light_content, fg_color="transparent")
        controls_frame.pack(fill="both", expand=True, pady=10)

        # Speed Control
        self.lbl_speed = ctk.CTkLabel(controls_frame, text="Speed")
        self.lbl_speed.pack(pady=(10, 5))
        self.slider_speed = ctk.CTkSlider(controls_frame, from_=0.1, to=5.0, command=self.on_light_speed)
        self.slider_speed.set(self.effect_speed)
        self.slider_speed.pack(pady=5, fill="x", padx=20)

        # Brightness Control
        self.lbl_dim = ctk.CTkLabel(controls_frame, text="Brightness")
        self.slider_dim = ctk.CTkSlider(controls_frame, from_=0.0, to=1.0, command=self.on_dimmer_change)
        self.slider_dim.set(1.0)

        # Color Control
        self.lbl_color = ctk.CTkLabel(controls_frame, text="Primary Color")
        self.lbl_color.pack(pady=(10, 5))
        self.btn_color_1 = ctk.CTkButton(controls_frame, text="Pick Color", fg_color=self.effect_color,
                                         command=lambda: self.pick_effect_color(1))
        self.btn_color_1.pack(pady=5)

    def setup_oled_tab(self):
        """Builds the OLED editor tab."""
        tab = self.tabs.tab("OLED")
        tab.grid_columnconfigure(0, weight=0, minsize=200)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # Left Column (List)
        frame_prof_list = ctk.CTkFrame(tab, width=200, corner_radius=0, fg_color="#1a1a1a")
        frame_prof_list.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=5)
        ctk.CTkLabel(frame_prof_list, text="OLED PROFILES", font=("Arial", 12, "bold")).pack(pady=5)
        self.oled_prof_scroll = ctk.CTkScrollableFrame(frame_prof_list, fg_color="transparent")
        self.oled_prof_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkButton(frame_prof_list, text="+ New OLED", fg_color="#2ecc71", command=self.add_oled_prof).pack(fill="x", padx=5, pady=10)

        # Right Column (Editor)
        frame_right = ctk.CTkFrame(tab, fg_color="transparent")
        frame_right.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        header_frame = ctk.CTkFrame(frame_right, fg_color="transparent", height=40)
        header_frame.pack(side="top", fill="x", pady=(0, 10))
        ctk.CTkLabel(header_frame, text="OLED Editor", font=("Arial", 14, "bold")).pack(side="left", padx=10)
        ctk.CTkButton(header_frame, text="Link to Profile...", width=120, fg_color="#e67e22",
                      command=lambda: self.open_assign_dialog("oled")).pack(side="right", padx=10)

        self.oled_editor = OLEDFrame(frame_right, self)
        self.oled_editor.pack(fill="both", expand=True)

        # Override save button functionality in the imported editor view
        if hasattr(self.oled_editor, 'btn_apply'):
            self.oled_editor.btn_apply.configure(command=self.oled_send_and_save)

        self.refresh_oled_profile_list()

    # =========================================================================
    # CORE LOGIC: REGION & LANGUAGE
    # =========================================================================
    def change_region(self, selection):
        """Updates the physical layout visualizer (ANSI/ISO)."""
        variant = "ISO" if "ISO" in selection else "ANSI"
        hw_type = self.dev_info.get("layout_type", "TKL")

        from backend.device_db import FEAT_OLED
        from backend.layouts import get_layout

        has_oled = bool(self.dev_info["features"] & FEAT_OLED)
        new_layout = get_layout(hw_type, variant, has_oled)

        if hasattr(self, 'kb_view'):
            self.kb_view.current_layout = new_layout
            self.kb_view.render_layout()
            self.kb_view.select_all()

    def change_language(self, lang_name):
        """Updates the key labels based on the selected language."""
        if hasattr(self, 'kb_view'):
            self.kb_view.set_language(lang_name)

    def toggle_sidebar(self):
        """Expands or collapses the left sidebar."""
        if self.sidebar_expanded:
            self.sidebar.configure(width=50)
            self.lbl_app_name.pack_forget()
            self.sb_scroll.pack_forget()
            self.btn_add.pack_forget()
            self.lbl_layout.pack_forget()
            self.opt_layout.pack_forget()
            self.sidebar_expanded = False
        else:
            self.sidebar.configure(width=220)
            self.lbl_app_name.pack(pady=10)
            self.sb_scroll.pack(fill="both", expand=True, padx=10, pady=10)
            self.refresh_profile_list()
            self.btn_add.pack(pady=10, padx=10)
            self.lbl_layout.pack(pady=(10, 5))
            self.opt_layout.pack(pady=(0, 20))
            self.sidebar_expanded = True

    # =========================================================================
    # CORE LOGIC: KEY SELECTION & DATA
    # =========================================================================
    def select_key(self, key_list):
        """
        Callback triggered when keys are selected in the visualizer.
        Populates the Inspector and the Data Table with the selected keys' data.
        """
        self.current_selection = list(key_list)
        self.ignore_updates = True

        count = len(key_list)
        self.lbl_selected_count.configure(text=f"Editing: {count} Keys" if count > 0 else "Select keys to edit")

        if count == 0:
            self._set_controls_state("disabled")
            self.chk_header_rt.deselect()
            self.chk_header_prot.deselect()
            self.rebuild_key_table([])
            self.ignore_updates = False
            return

        self._set_controls_state("normal")

        # Gather data for selected keys to determine slider positions
        actuations, rt_senss, modes = [], [], []
        for k in key_list:
            data = self.cfg.get_key_data(self.current_profile, k)
            if k in OMNIPOINT_KEYS:
                actuations.append(data.get("actuation", 1.8))
                rt_senss.append(data.get("rt_sens", 0.1))
            modes.append(data.get("mode", 0))

        # Update Actuation Sliders
        if hasattr(self, 'slider_act') and self.slider_act.winfo_exists():
            if not actuations:
                self.slider_act.configure(state="disabled"); self.entry_act.configure(state="disabled"); self.entry_act.delete(0, "end")
            else:
                if all(x == actuations[0] for x in actuations):
                    self.slider_act.set(actuations[0])
                    self.entry_act.delete(0, "end")
                    self.entry_act.insert(0, f"{actuations[0]:.1f}")
                else:
                    self.slider_act.set(min(actuations))
                    self.entry_act.delete(0, "end")
                    self.entry_act.configure(placeholder_text="Mix")

            # Update Rapid Trigger Sliders
        if hasattr(self, 'slider_act') and self.slider_act.winfo_exists():
            if not rt_senss:
                self.slider_rt.configure(state="disabled"); self.entry_rt.configure(state="disabled")
            else:
                if all(x == rt_senss[0] for x in rt_senss):
                    self.slider_rt.set(rt_senss[0])
                    self.entry_rt.delete(0, "end")
                    self.entry_rt.insert(0, f"{rt_senss[0]:.1f}")
                else:
                    self.slider_rt.set(min(rt_senss))
                    self.entry_rt.delete(0, "end")
                    self.entry_rt.configure(placeholder_text="Mix")

        # Update Header Checkboxes (if mix, use partial state logic if needed, here we just check if any)
        if modes:
            if any((m & MASK_RT) for m in modes): self.chk_header_rt.select()
            else: self.chk_header_rt.deselect()

            if any((m & MASK_PROT) for m in modes): self.chk_header_prot.select()
            else: self.chk_header_prot.deselect()

        self.rebuild_key_table(self.current_selection)
        self.ignore_updates = False

    def rebuild_key_table(self, key_list):
        """Rebuilds the table rows for the selected keys."""
        for widget in self.table_scroll.winfo_children():
            widget.destroy()

        if not key_list: return

        sorted_keys = sorted(key_list, key=self.get_sort_priority)

        for key_name in sorted_keys:
            if key_name not in OMNIPOINT_KEYS: continue
            row_data = self.cfg.get_key_data(self.current_profile, key_name)
            mode = row_data.get("mode", 0)

            row = ctk.CTkFrame(self.table_scroll, height=35, fg_color="transparent")
            row.pack(fill="x", pady=2)
            self._bind_row_scroll(row)

            # Format Display Name
            display_name = key_name.upper().replace("_", " ")
            if key_name.startswith(("left_", "right_")):
                parts = key_name.upper().split("_")
                side = "L" if parts[0] == "LEFT" else "R"
                rest = "META" if parts[1] == "GUI" else parts[1]
                display_name = f"{side}_{rest}"
            else:
                cur_lang = "English (US)"
                if hasattr(self, 'opt_lang'):
                    cur_lang = self.opt_lang.get()
                raw_label = get_key_label(cur_lang, key_name)
                display_name = raw_label.replace("\n", " ")

            # Column 1: Key Name
            key_box = ctk.CTkFrame(row, width=60, height=28, fg_color="#222", border_width=1, border_color="#888", corner_radius=4)
            key_box.pack(side="left", padx=10)
            key_box.pack_propagate(False)
            self._bind_row_scroll(key_box)
            lbl_name = ctk.CTkLabel(key_box, text=display_name, font=("Arial", 12, "bold"))
            lbl_name.place(relx=0.5, rely=0.5, anchor="center")
            self._bind_row_scroll(lbl_name)

            # Column 2: Actuation Value
            act_box = ctk.CTkFrame(row, width=60, height=28, fg_color="#222", border_width=1, border_color="#888", corner_radius=4)
            act_box.pack(side="left", padx=50)
            act_box.pack_propagate(False)
            self._bind_row_scroll(act_box)
            act_val = row_data.get("actuation", 1.8)
            lbl_act = ctk.CTkLabel(act_box, text=f"{act_val:.1f}", font=("Arial", 12, "bold"))
            lbl_act.place(relx=0.5, rely=0.5, anchor="center")
            self._bind_row_scroll(lbl_act)

            # Column 3: RT Checkbox
            is_rt = (mode & MASK_RT) > 0
            chk_rt = ctk.CTkCheckBox(row, text="", width=24, onvalue=1, offvalue=0, command=lambda k=key_name, m=mode: self.toggle_row_rt(k, m))
            if is_rt: chk_rt.select()
            chk_rt.pack(side="left", padx=(61, 5))
            self._bind_row_scroll(chk_rt)

            # Column 4: Protection Checkbox
            is_prot = (mode & MASK_PROT) > 0
            chk_prot = ctk.CTkCheckBox(row, text="", width=24, onvalue=1, offvalue=0, command=lambda k=key_name, m=mode: self.toggle_row_prot(k, m))
            if is_prot: chk_prot.select()
            chk_prot.pack(side="left", padx=(61, 5))
            self._bind_row_scroll(chk_prot)

    # --- INPUT HANDLERS (ACTUATION/RT) ---
    def _set_controls_state(self, state):
        # Check if the widgets exist before trying to configure them
        if not hasattr(self, 'slider_act') or not self.slider_act.winfo_exists():
            return

        self.slider_act.configure(state=state)
        self.slider_rt.configure(state=state)
        self.entry_act.configure(state=state)
        self.entry_rt.configure(state=state)

        if state == "disabled":
            self.chk_header_rt.configure(state="disabled")
            self.chk_header_prot.configure(state="disabled")
        else:
            self.chk_header_rt.configure(state="normal")
            self.chk_header_prot.configure(state="normal")

    def on_slider_act(self, value):
        if self.ignore_updates: return
        self.entry_act.delete(0, "end"); self.entry_act.insert(0, f"{value:.1f}")
        self._update_selected_keys(actuation=value)

    def on_entry_act_submit(self, event=None):
        try:
            val = max(0.1, min(4.0, float(self.entry_act.get())))
            self.slider_act.set(val)
            self._update_selected_keys(actuation=val)
        except ValueError: pass

    def on_slider_rt(self, value):
        if self.ignore_updates: return
        self.entry_rt.delete(0, "end"); self.entry_rt.insert(0, f"{value:.1f}")
        self._update_selected_keys(rt_sens=value)

    def on_entry_rt_submit(self, event=None):
        try:
            val = max(0.1, min(4.0, float(self.entry_rt.get())))
            self.slider_rt.set(val)
            self._update_selected_keys(rt_sens=val)
        except ValueError: pass

    def _update_selected_keys(self, **kwargs):
        """Updates config and hardware for the currently selected keys."""
        if not self.current_selection: return
        self.cfg.update_keys(self.current_profile, self.current_selection, **kwargs)

        if "mode" in kwargs:
            self.kb_view.update_key_data({k: {"mode": kwargs["mode"]} for k in self.current_selection})

        if self.kb:
            partial = {}
            for key_name in self.current_selection:
                if key_name not in OMNIPOINT_KEYS: continue
                data = self.cfg.get_key_data(self.current_profile, key_name)
                hid = OMNIPOINT_KEYS[key_name]
                hw_m = map_app_mode_to_hw(data["mode"])
                partial[hid] = {"actuation": data["actuation"], "rt_sens": data["rt_sens"], "mode": hw_m}
            if partial: self.kb.apply_partial_config(partial)

        self.rebuild_key_table(self.current_selection)

    def single_key_update(self, key_name, new_mode):
        self.cfg.update_keys(self.current_profile, [key_name], mode=new_mode)
        if self.kb:
            hid = OMNIPOINT_KEYS[key_name]
            data = self.cfg.get_key_data(self.current_profile, key_name)
            hw_m = map_app_mode_to_hw(new_mode)
            partial = {hid: {"actuation": data["actuation"], "rt_sens": data["rt_sens"], "mode": hw_m}}
            self.kb.apply_partial_config(partial)

        self.kb_view.update_key_data({key_name: {"mode": new_mode}})
        self.select_key(self.kb_view.selected_keys)

    def toggle_row_rt(self, key_name, current_mode):
        self.single_key_update(key_name, current_mode ^ MASK_RT)

    def toggle_row_prot(self, key_name, current_mode):
        self.single_key_update(key_name, current_mode ^ MASK_PROT)

    def on_header_rt_toggle(self):
        if self.ignore_updates: return
        self._update_mode_smart(rt_state=self.chk_header_rt.get())

    def on_header_prot_toggle(self):
        if self.ignore_updates: return
        self._update_mode_smart(prot_state=self.chk_header_prot.get())

    def _update_mode_smart(self, rt_state=None, prot_state=None):
        if not self.current_selection: return
        updates = {}
        partial = {}

        for key in self.current_selection:
            data = self.cfg.get_key_data(self.current_profile, key)
            new_mode = data.get("mode", 0)

            if rt_state is not None:
                new_mode = (new_mode | MASK_RT) if rt_state else (new_mode & ~MASK_RT)
            if prot_state is not None:
                new_mode = (new_mode | MASK_PROT) if prot_state else (new_mode & ~MASK_PROT)

            self.cfg.update_keys(self.current_profile, [key], mode=new_mode)
            updates[key] = {"mode": new_mode}

            if self.kb and key in OMNIPOINT_KEYS:
                hw_m = map_app_mode_to_hw(new_mode)
                partial[OMNIPOINT_KEYS[key]] = {"actuation": data["actuation"], "rt_sens": data["rt_sens"], "mode": hw_m}

        self.kb_view.update_key_data(updates)
        if self.kb and partial:
            self.kb.apply_partial_config(partial)
        self.rebuild_key_table(self.current_selection)

    def reset_all_keys(self):
        """Sets Actuation: 1.8, RT: Off, Prot: Off for ALL Omnipoint keys."""
        if not self.kb: return

        updates = {}
        config_payload = {}

        for key in OMNIPOINT_KEYS:
             updates[key] = {"actuation": 1.8, "mode": 0, "rt_sens": 0.1}

             # Prepare data for immediate HW application to avoid loop lag
             hid = OMNIPOINT_KEYS[key]
             config_payload[hid] = updates[key]

        # Update Config
        self.cfg.update_keys(self.current_profile, list(updates.keys()), actuation=1.8, mode=0, rt_sens=0.1)

        # Update GUI
        if hasattr(self, 'kb_view'):
            self.kb_view.update_key_data(updates)
            self.select_key(self.kb_view.selected_keys) # Refresh sliders if needed

        # Apply to HW
        self.kb.apply_config(config_payload)

    # =========================================================================
    # CORE LOGIC: LIGHTING
    # =========================================================================

    def apply_preset(self, preset_name):
        """Applies a pre-defined RGB preset (Rainbow, Wave, etc.)."""
        self.cfg.update_lighting_data(self.current_light_profile, mode=preset_name, static_colors={})
        self.effect_speed = 1.0

        if hasattr(self, 'slider_speed') and self.slider_speed.winfo_exists():
            self.slider_speed.set(1.0)

        self._update_rgb_engine()
        # Force redraw to show active selection state
        self.show_light_subtab("Presets")

    def on_effect_change(self, effect_name):
        """Switches to a custom effect type (Static, Breath, etc.)."""
        mode = effect_name.lower()

        if self.current_selection:
            # Applying effect only to selected keys (Per-Key override)
            light_data = self.cfg.get_lighting_data(self.current_light_profile)
            overrides = light_data.get("static_colors", {})
            raw_color = self.effect_color if self.effect_color else "#FF0000"

            for k_name in self.current_selection:
                hid = ALL_KEYS.get(k_name)
                if hid: overrides[str(hid)] = {"mode": mode, "color": raw_color}

            self.cfg.update_lighting_data(self.current_light_profile, static_colors=overrides)
        else:
            # Applying effect to Global Background
            self.current_custom_effect = mode
            self.cfg.update_lighting_data(self.current_light_profile, mode=effect_name)

        self.update_slider_visibility()
        self._update_rgb_engine()

    def update_slider_visibility(self):
        """Dynamically shows/hides speed and brightness sliders based on active effect."""
        light_data = self.cfg.get_lighting_data(self.current_light_profile)
        overrides = light_data.get("static_colors", {})
        global_mode = light_data.get("mode", "static").lower()

        is_bg_dynamic = global_mode in ["wave", "breath", "colorshift", "reflect", "disco"] or (global_mode in PRESETS and global_mode != "Off")
        is_bg_static = global_mode == "static"

        has_breathing_key = any(isinstance(v, dict) and v.get("mode") == "breath" for v in overrides.values())
        has_static_key = any(isinstance(v, dict) and v.get("mode") == "static" for v in overrides.values())

        show_speed = is_bg_dynamic or has_breathing_key
        show_dimmer = is_bg_static or has_static_key

        # Hide all first
        if hasattr(self, 'lbl_speed'): self.lbl_speed.pack_forget()
        if hasattr(self, 'slider_speed'): self.slider_speed.pack_forget()
        if hasattr(self, 'lbl_dim'): self.lbl_dim.pack_forget()
        if hasattr(self, 'slider_dim'): self.slider_dim.pack_forget()

        anchor = self.lbl_color if hasattr(self, 'lbl_color') else None
        if not anchor: return

        if show_dimmer:
            self.slider_dim.pack(pady=5, fill="x", padx=20, before=anchor)
            self.lbl_dim.pack(pady=(10, 5), before=self.slider_dim)
            anchor = self.lbl_dim

        if show_speed:
            self.slider_speed.pack(pady=5, fill="x", padx=20, before=anchor)
            self.lbl_speed.pack(pady=(10, 5), before=self.slider_speed)

    def pick_effect_color(self, idx):
        """Opens the custom color picker dialog."""
        current_hex = self.effect_color

        def on_pick(rgb, hex_code):
            self.effect_color = hex_code
            if hasattr(self, 'btn_color_1'): self.btn_color_1.configure(fg_color=hex_code)

            if self.current_selection:
                # Update specific keys
                light_data = self.cfg.get_lighting_data(self.current_light_profile)
                overrides = light_data.get("static_colors", {})
                for k_name in self.current_selection:
                    hid = ALL_KEYS.get(k_name)
                    if not hid: continue
                    current_entry = overrides.get(str(hid), {"mode": "static"})
                    if not isinstance(current_entry, dict): current_entry = {"mode": "static"}
                    current_entry["color"] = hex_code
                    overrides[str(hid)] = current_entry
                self.cfg.update_lighting_data(self.current_light_profile, static_colors=overrides)
            else:
                # Update background
                self.cfg.update_lighting_data(self.current_light_profile, primary_color=hex_code)

            self._update_rgb_engine()

        CustomColorPicker(self, initial_color=current_hex, on_pick_callback=on_pick)

    def _update_rgb_engine(self):
        """Sends current lighting configuration to the backend engine."""
        if not self.rgb_engine: return

        data = self.cfg.get_lighting_data(self.current_light_profile)
        dim_factor = data.get("brightness", 1.0)
        saved_mode_name = data.get("mode", "static")
        saved_speed = data.get("speed", 1.0)

        # Sync UI Sliders if they deviate
        if hasattr(self, 'slider_dim') and self.slider_dim.winfo_exists():
            if abs(self.slider_dim.get() - dim_factor) > 0.02: self.slider_dim.set(dim_factor)

        if hasattr(self, 'slider_speed') and self.slider_speed.winfo_exists():
            if abs(self.slider_speed.get() - saved_speed) > 0.02: self.slider_speed.set(saved_speed)

        # Build Background Config
        if saved_mode_name in PRESETS:
            engine_config = PRESETS[saved_mode_name].copy()
        else:
            raw_color = "#FF0000"
            if hasattr(self, 'btn_color_1') and self.btn_color_1.winfo_exists():
                raw_color = self.btn_color_1.cget("fg_color")
            if "primary_color" in data:
                raw_color = data["primary_color"]

            engine_config = {
                "type": saved_mode_name.lower(),
                "colors": [raw_color],
                "speed": saved_speed
            }

        # Apply brightness to static background color
        if engine_config["type"] == "static":
            base_col = engine_config["colors"][0]
            if isinstance(base_col, str):
                h = base_col.lstrip("#")
                r, g, b = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            else:
                r, g, b = base_col
            engine_config["colors"] = [(int(r * dim_factor), int(g * dim_factor), int(b * dim_factor))]

        self.rgb_engine.set_background(engine_config, speed_override=saved_speed)

        # Build Overrides Config
        overrides = data.get("static_colors", {})
        parsed_overrides = {}
        for hid_str, val in overrides.items():
            try:
                hid = int(hid_str)
                if isinstance(val, dict):
                    m = val.get("mode", "static")
                    c = val.get("color", "#FFFFFF")
                else:
                    m = "static"
                    c = str(val)

                h = c.lstrip("#")
                cr, cg, cb = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

                if m == "static":
                    cr, cg, cb = int(cr * dim_factor), int(cg * dim_factor), int(cb * dim_factor)

                parsed_overrides[hid] = {"mode": m, "color": (cr, cg, cb)}
            except:
                pass

        self.rgb_engine.set_overrides(parsed_overrides)

    def on_light_speed(self, val):
        self.effect_speed = val
        self.cfg.update_lighting_data(self.current_light_profile, speed=val)
        if self.rgb_engine: self.rgb_engine.update_speed(val)

    def on_dimmer_change(self, value):
        self.cfg.update_lighting_data(self.current_light_profile, brightness=value)
        self._update_rgb_engine()

    def refresh_light_profile_list(self):
        if not hasattr(self, 'light_prof_scroll') or not self.light_prof_scroll.winfo_exists():
            return

        self.build_sidebar_list(self.light_prof_scroll, self.cfg.get_all_lighting_profiles(),
                                self.current_light_profile, self.on_light_profile_select,
                                self.del_light_prof_action, self.rename_light_prof_action,
                                lambda l: [self.cfg.reorder_lighting_profiles(l), self.refresh_light_profile_list()])

    def del_light_prof_action(self, name):
        if self.current_light_profile == name: self.on_light_profile_select("Default")
        if self.cfg.delete_lighting_profile(name): self.refresh_light_profile_list()

    def on_light_profile_select(self, choice):
        self.current_light_profile = choice
        self.cfg.set_linked_lighting(self.current_profile, choice)
        self.refresh_light_profile_list()
        self.load_lighting_settings()

    def add_light_prof(self):
        dialog = QuickRenameDialog(self, "New Lighting", "Name for Lighting Profile:")
        name = dialog.get_input()
        if name and self.cfg.create_lighting_profile(name):
            self.refresh_light_profile_list()
            self.on_light_profile_select(name)

    def rename_light_prof_action(self, old_name):
        dialog = QuickRenameDialog(self, "Rename Lighting", f"Rename '{old_name}' to:", old_name)
        new_name = dialog.get_input()
        if new_name and self.cfg.rename_lighting_profile(old_name, new_name):
            if self.current_light_profile == old_name: self.current_light_profile = new_name
            self.refresh_light_profile_list()

    def load_lighting_settings(self):
        data = self.cfg.get_lighting_data(self.current_light_profile)
        self.current_custom_effect = data.get("mode", "static")
        self.effect_color = data.get("primary_color", "#FF0000")

        if hasattr(self, 'btn_color_1') and self.btn_color_1.winfo_exists():
            self.btn_color_1.configure(fg_color=self.effect_color)

        self.update_slider_visibility()
        self._update_rgb_engine()

    # =========================================================================
    # CORE LOGIC: OLED
    # =========================================================================

    def refresh_oled_profile_list(self):
        if not hasattr(self, 'oled_prof_scroll') or not self.oled_prof_scroll.winfo_exists():
            return

        self.build_sidebar_list(self.oled_prof_scroll, self.cfg.get_all_oled_profiles(),
                                self.current_oled_profile, self.on_oled_profile_select,
                                self.del_oled_prof_action, self.rename_oled_prof_action,
                                lambda l: [self.cfg.reorder_oled_profiles(l), self.refresh_oled_profile_list()])

    def del_oled_prof_action(self, name):
        if self.current_oled_profile == name: self.on_oled_profile_select("Default")
        if self.cfg.delete_oled_profile(name): self.refresh_oled_profile_list()

    def on_oled_profile_select(self, choice):
        self.current_oled_profile = choice
        self.cfg.set_linked_oled(self.current_profile, choice)
        self.refresh_oled_profile_list()
        self.load_oled_settings()

    def add_oled_prof(self):
        dialog = QuickRenameDialog(self, "New OLED", "Name for OLED Profile:")
        name = dialog.get_input()
        if name and self.cfg.create_oled_profile(name):
            self.refresh_oled_profile_list()
            self.on_oled_profile_select(name)

    def rename_oled_prof_action(self, old_name):
        dialog = QuickRenameDialog(self, "Rename OLED", f"Rename '{old_name}' to:", old_name)
        new_name = dialog.get_input()
        if new_name and self.cfg.rename_oled_profile(old_name, new_name):
            if self.current_oled_profile == old_name: self.current_oled_profile = new_name
            self.refresh_oled_profile_list()

    def load_oled_settings(self):
        data_dict = self.cfg.get_oled_data(self.current_oled_profile)
        raw_bytes = data_dict.get("image_data", [])

        if hasattr(self, 'oled_editor'): self.oled_editor.load_image_data(raw_bytes)

        if self.kb:
            is_empty = not raw_bytes or all(b == 0 for b in raw_bytes)
            if not is_empty:
                to_send = raw_bytes if len(raw_bytes) == 640 else raw_bytes + [0]*(640-len(raw_bytes))
                self.kb.set_oled_image(to_send)

    def oled_send_and_save(self):
        if self.kb:
            data = list(self.oled_editor.image.tobytes())
            if len(data) < 640: data += [0] * (640 - len(data))
            data = data[:640]
            self.kb.set_oled_image(data)
            self.cfg.update_oled_data(self.current_oled_profile, data)

    # =========================================================================
    # CORE LOGIC: PROFILE MANAGEMENT (CRUD)
    # =========================================================================

    def apply_to_keyboard(self):
        if not self.kb: return
        all_keys = list(ALL_KEYS.keys())
        full_data = self.cfg.get_visual_data_for_all_keys(self.current_profile, all_keys)
        config_dict = {}
        for key_name, settings in full_data.items():
            hid = ALL_KEYS.get(key_name)
            if hid:
                hw_m = map_app_mode_to_hw(settings.get("mode", 0))
                s_copy = settings.copy()
                s_copy["mode"] = hw_m
                config_dict[hid] = s_copy
        self.kb.apply_config(config_dict)

    def on_tab_change(self):
        current_tab = self.tabs.get()

        # --- LAZY LOADING LOGIC ---
        # Build the tab content the first time it is clicked
        if current_tab == "Performance" and not hasattr(self, "_perf_tab_built"):
            self.setup_perf_tab()
            self._perf_tab_built = True
        elif current_tab == "Lighting" and not hasattr(self, "_light_tab_built"):
            self.setup_light_tab()
            self._light_tab_built = True
        elif current_tab == "OLED" and not hasattr(self, "_oled_tab_built"):
            self.setup_oled_tab()
            self._oled_tab_built = True

        # --- EXISTING LOGIC ---
        if current_tab == "Performance":
            self.kb_view.set_mode("omnipoint")
            self.lbl_selected_count.configure(text="Mode: Performance")
            self.info_container.pack(fill="both", expand=True)
        else:
            self.kb_view.set_mode("all")
            self.lbl_selected_count.configure(text="Mode: Lighting/OLED")
            self.info_container.pack_forget()

        self.kb_view.select_all()

    def refresh_profile_list(self):
        self.build_sidebar_list(self.sb_scroll, self.cfg.get_all_profiles(), self.current_profile,
                                self.load_profile,
                                lambda n: self.on_profile_action("Delete", n),
                                lambda n: self.on_profile_action("Rename", n),
                                lambda l: [self.cfg.reorder_profiles(l), self.refresh_profile_list()])

    def on_profile_action(self, choice, profile_name):
        if choice == "Rename":
            dialog = QuickRenameDialog(self, "Rename Profile", f"Rename '{profile_name}' to:", profile_name)
            new_name = dialog.get_input()
            if new_name and self.cfg.rename_profile(profile_name, new_name):
                if self.current_profile == profile_name: self.current_profile = new_name
                self.refresh_profile_list()
        elif choice == "Delete":
            if self.current_profile == profile_name: self.load_profile("Default")
            if self.cfg.delete_profile(profile_name): self.refresh_profile_list()

    def load_profile(self, name):
        if not name: return

        # Update Internal State immediately so UI feels responsive
        self.current_profile = name
        self.cfg.save_last_active_profile(name)

        # Refresh the sidebar list immediately
        self.refresh_profile_list()

        # 3. Software Update (Actuation/RT settings)
        all_keys = list(ALL_KEYS.keys())
        full_data = self.cfg.get_visual_data_for_all_keys(name, all_keys)
        self.kb_view.update_key_data(full_data)
        self.apply_to_keyboard()

        # Update Lighting & OLED references
        self.current_light_profile = self.cfg.get_linked_lighting(name)
        self.current_oled_profile = self.cfg.get_linked_oled(name)

        if hasattr(self, 'refresh_light_profile_list'): self.refresh_light_profile_list()
        if hasattr(self, 'refresh_oled_profile_list'): self.refresh_oled_profile_list()

        # Load Visuals
        self.load_lighting_settings()
        self.load_oled_settings()

        # Update Selection (Refreshes the table if keys were selected)
        if hasattr(self, 'kb_view'):
            # Refresh only current selection instead of selecting all
            self.select_key(list(self.kb_view.selected_keys))

        # --- BACKGROUND TASK: HARDWARE SWITCH ---
        def _threaded_hw_switch():
            if self.kb and self.rgb_engine:
                # 1. Pause RGB to free up USB bandwidth
                self.rgb_engine.pause()
                time.sleep(0.001)

                # 2. Hardware Switch
                hw_slot = self.cfg.get_profile_hw_slot(name)
                self.kb.load_onboard_profile(hw_slot)

                # 3. Resume RGB
                self.rgb_engine.resume()

        threading.Thread(target=_threaded_hw_switch, daemon=True).start()

    def add_profile_dialog(self):
        dialog = QuickRenameDialog(self, "New Profile", "Profile Name:")
        name = dialog.get_input()
        if name and self.cfg.create_profile(name): self.refresh_profile_list()

    def open_performance_settings(self):
        """Opens a modal dialog to link Game/App Triggers and Onboard Slots."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Performance Settings: {self.current_profile}")
        dialog.geometry("400x450")
        dialog.resizable(False, False)
        dialog.transient(self)

        ctk.CTkLabel(dialog, text=f"Settings for '{self.current_profile}'", font=("Arial", 18, "bold")).pack(pady=(20, 10))

        # Hardware Slot Selector
        frame_slot = ctk.CTkFrame(dialog)
        frame_slot.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(frame_slot, text="Hardware Display Slot (C1-C5)", font=("Arial", 12, "bold")).pack(anchor="w", padx=10, pady=5)

        def on_slot_change(value):
            try:
                slot_num = int(value.replace("C", ""))
                self.cfg.set_profile_hw_slot(self.current_profile, slot_num)
            except: pass

        current_slot = self.cfg.get_profile_hw_slot(self.current_profile)
        seg_slot = ctk.CTkSegmentedButton(frame_slot, values=["C1", "C2", "C3", "C4", "C5"], command=on_slot_change)
        seg_slot.set(f"C{current_slot}")
        seg_slot.pack(fill="x", padx=10, pady=10)

        # Trigger Management
        frame_trig = ctk.CTkFrame(dialog)
        frame_trig.pack(fill="both", expand=True, padx=20, pady=10)
        ctk.CTkLabel(frame_trig, text="Auto-Switch Trigger", font=("Arial", 12, "bold")).pack(anchor="w", padx=10, pady=5)

        input_frame = ctk.CTkFrame(frame_trig, fg_color="transparent")
        input_frame.pack(fill="x", padx=5)
        entry = ctk.CTkEntry(input_frame, placeholder_text="e.g. cs2", width=180)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        scroll_trigs = ctk.CTkScrollableFrame(frame_trig, height=100, label_text="Active Triggers")
        scroll_trigs.pack(fill="both", expand=True, padx=5, pady=5)

        def refresh_trigger_list():
            for w in scroll_trigs.winfo_children(): w.destroy()
            current = self.cfg.get_profile_triggers(self.current_profile)
            if not current:
                ctk.CTkLabel(scroll_trigs, text="No triggers set").pack()
                return
            for t in current:
                row = ctk.CTkFrame(scroll_trigs, fg_color="transparent", height=25)
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(row, text=t, anchor="w").pack(side="left", padx=5)
                ctk.CTkButton(row, text="✕", width=25, height=25, fg_color="#c0392b",
                              command=lambda val=t: [self.cfg.remove_process_trigger(self.current_profile, val), refresh_trigger_list()]).pack(side="right", padx=5)

        def add_proc(event=None):
            proc = entry.get()
            if proc:
                self.cfg.add_process_trigger(self.current_profile, proc.lower())
                refresh_trigger_list()
                entry.delete(0, "end")

        ctk.CTkButton(input_frame, text="Add", width=60, command=add_proc, fg_color="#2ecc71").pack(side="right")
        entry.bind("<Return>", add_proc)
        refresh_trigger_list()

    def open_assign_dialog(self, type_mode="lighting"):
        """Opens a modal to link Lighting/OLED profiles to the current Performance Profile."""
        target_name = self.current_light_profile if type_mode == "lighting" else self.current_oled_profile
        title_type = "Lighting" if type_mode == "lighting" else "OLED"

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Assign {title_type}")
        dialog.geometry("400x500")
        dialog.transient(self)

        ctk.CTkLabel(dialog, text=f"Manage Links for '{target_name}'", font=("Arial", 16, "bold")).pack(pady=(20, 5))

        container = ctk.CTkFrame(dialog, fg_color="#1a1a1a")
        container.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        scroll = ctk.CTkScrollableFrame(container, label_text="Performance Profiles")
        scroll.pack(fill="both", expand=True, padx=5, pady=5)

        sorted_profs = sorted(self.cfg.get_all_profiles())
        if "Default" in sorted_profs:
            sorted_profs.remove("Default")
            sorted_profs.insert(0, "Default")

        def on_toggle(p_name, var):
            is_checked = var.get()
            if target_name == "Default" and not is_checked:
                var.set(True)
                return
            new_link = target_name if is_checked else "Default"
            if type_mode == "lighting": self.cfg.set_linked_lighting(p_name, new_link)
            else: self.cfg.set_linked_oled(p_name, new_link)

        for p in sorted_profs:
            row = ctk.CTkFrame(scroll, fg_color="transparent", height=30)
            row.pack(fill="x", pady=2)

            current_link = self.cfg.get_linked_lighting(p) if type_mode == "lighting" else self.cfg.get_linked_oled(p)
            is_linked_here = (current_link == target_name)
            check_var = ctk.BooleanVar(value=is_linked_here)

            display_text = p
            text_col = "white"
            if not is_linked_here and current_link != "Default":
                display_text = f"{p} (uses: {current_link})"
                text_col = "gray"

            ctk.CTkLabel(row, text=display_text, text_color=text_col, anchor="w").pack(side="left", padx=10, fill="x", expand=True)
            state = "disabled" if target_name == "Default" else "normal"
            ctk.CTkCheckBox(row, text="", width=24, variable=check_var, state=state,
                            command=lambda n=p, v=check_var: on_toggle(n, v)).pack(side="right", padx=10)

        ctk.CTkButton(dialog, text="Done", width=100, command=dialog.destroy).pack(pady=10)
        self.after(100, lambda: dialog.grab_set())

    def on_auto_switch_profile(self, profile_name):
        """Callback from Process Monitor when a game trigger is detected."""
        self.after(0, lambda: self.load_profile(profile_name))

    def update_autostart_btn(self):
        """Checks if the app is set to run on startup and updates the UI button."""
        self.btn_save_flash.configure(text="Checking...", state="disabled", fg_color="#555")

        def run_check():
            is_active = self.autostart.is_enabled()
            self.after(0, lambda: self._apply_autostart_visuals(is_active))

        threading.Thread(target=run_check, daemon=True).start()

    def _apply_autostart_visuals(self, is_active):
        if is_active:
            self.btn_save_flash.configure(
                text="Autostart: ACTIVE (Disable)",
                fg_color="#27ae60",
                hover_color="#2ecc71",
                state="normal"
            )
        else:
            self.btn_save_flash.configure(
                text="Enable Autostart (Restore on Boot)",
                fg_color="#333333",
                hover_color="#444",
                state="normal"
            )

    def toggle_autostart(self):
        """Enables or disables the Windows Registry / Linux Service autostart."""
        self.btn_save_flash.configure(text="Working...", state="disabled")

        def run_toggle():
            if self.autostart.is_enabled():
                self.autostart.disable_autostart()
            else:
                self.autostart.enable_autostart()
            self.after(0, self.update_autostart_btn)

        threading.Thread(target=run_toggle, daemon=True).start()

    def on_closing(self):
        """Cleanup before closing the application."""
        if hasattr(self, 'rgb_engine') and self.rgb_engine: self.rgb_engine.stop()
        if hasattr(self, 'monitor') and self.monitor: self.monitor.stop()
        self.destroy()
        sys.exit(0)

    # --- HELPERS: SCROLLING & SORTING ---

    def _bind_scroll(self, widget, orientation="horizontal"):
        """Binds mouse wheel events to a scrollable widget (Cross-platform support)."""
        def _scroll_handler(direction):
            parent = widget
            while parent:
                if isinstance(parent, ctk.CTkScrollableFrame):
                    if orientation == "horizontal":
                        parent._parent_canvas.xview_scroll(direction, "units")
                    else:
                        parent._parent_canvas.yview_scroll(direction, "units")
                    break
                parent = parent.master

        # Linux (X11)
        widget.bind("<Button-4>", lambda e: _scroll_handler(-1))
        widget.bind("<Button-5>", lambda e: _scroll_handler(1))
        # Windows/MacOS
        widget.bind("<MouseWheel>", lambda e: _scroll_handler(-1 * (e.delta // 120)))

    def _bind_row_scroll(self, widget):
        """Binds scrolling for elements inside the key table."""
        widget.bind("<Button-4>", lambda e: self.table_scroll._parent_canvas.yview_scroll(-1, "units"), add="+")
        widget.bind("<Button-5>", lambda e: self.table_scroll._parent_canvas.yview_scroll(1, "units"), add="+")

    def _recursive_enable_scroll(self, widget, target_scrollable, orientation="vertical"):
        """Recursively binds scroll events for complex nested widgets."""
        def scroll(direction):
            if hasattr(target_scrollable, "_parent_canvas"):
                if orientation == "vertical": target_scrollable._parent_canvas.yview_scroll(direction, "units")
                else: target_scrollable._parent_canvas.xview_scroll(direction, "units")

        widget.bind("<Button-4>", lambda e: scroll(-1), add="+")
        widget.bind("<Button-5>", lambda e: scroll(1), add="+")
        for child in widget.winfo_children():
            self._recursive_enable_scroll(child, target_scrollable, orientation)

    def get_sort_priority(self, key_name):
        """Helper to sort keys logically (Alpha -> Numbers -> Space -> Mods -> Other)."""
        k = key_name.lower()
        if len(k) == 1 and k.isalpha(): return (0, k)
        if k.isdigit(): return (1, k)
        if k == "space": return (2, k)
        left_mods = ["tab", "caps_lock", "left_shift", "left_ctrl", "left_gui", "left_alt"]
        if k in left_mods:
            try: return (3, left_mods.index(k))
            except: return (3, 99)
        right_mods = ["backspace", "enter", "right_shift", "right_alt", "right_gui", "right_ctrl", "fn"]
        if k in right_mods:
            try: return (4, right_mods.index(k))
            except: return (4, 99)
        return (5, k)

# --- UTILITIES ---

class QuickRenameDialog(ctk.CTkToplevel):
    """Simple Modal Dialog for renaming profiles or items."""
    def __init__(self, parent, title, prompt, initial_value=""):
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.geometry("300x150")
        self.resizable(False, False)
        self.transient(parent)

        try:
            x = parent.winfo_x() + (parent.winfo_width() // 2) - 150
            y = parent.winfo_y() + (parent.winfo_height() // 2) - 75
            self.geometry(f"+{x}+{y}")
        except: pass

        ctk.CTkLabel(self, text=prompt, font=("Arial", 14)).pack(pady=(20, 10))
        self.entry = ctk.CTkEntry(self, width=200)
        self.entry.pack(pady=5)
        self.entry.insert(0, initial_value)
        self.entry.bind("<Return>", self.confirm)
        self.entry.bind("<Escape>", self.cancel)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Ok", width=80, command=self.confirm).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Cancel", width=80, fg_color="#555", command=self.cancel).pack(side="left", padx=5)

        self.entry.focus_force()
        self.wait_visibility()
        try: self.grab_set()
        except: pass
        self.wait_window()

    def confirm(self, event=None):
        self.result = self.entry.get()
        self.destroy()

    def cancel(self, event=None):
        self.result = None
        self.destroy()

    def get_input(self):
        return self.result

# --- ENTRY POINT ---

if __name__ == "__main__":
    if IS_SILENT:
        run_headless()
    else:
        app = OpenGGApp()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()

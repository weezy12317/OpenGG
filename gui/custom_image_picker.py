import os
import customtkinter as ctk
from PIL import Image, ImageTk

class CustomImagePicker(ctk.CTkToplevel):
    """
    A custom, modal file explorer for selecting images.

    Features:
    - Directory navigation (Up/Down).
    - Filters for valid image extensions.
    - Real-time preview with aspect-ratio preservation.
    """
    def __init__(self, parent, start_dir=None, on_pick_callback=None):
        super().__init__(parent)
        self.on_pick_callback = on_pick_callback

        self.title("Import Image")
        self.geometry("700x500")
        self.resizable(False, False)

        # Modal behavior: block main window interaction
        self.transient(parent)

        # 1. Determine Startup Directory
        if start_dir and os.path.exists(start_dir):
            self.current_dir = start_dir
        else:
            # Fallback to User's Pictures folder or Home
            self.current_dir = os.path.expanduser("~/Pictures")
            if not os.path.exists(self.current_dir):
                self.current_dir = os.path.expanduser("~")

        self.selected_file = None

        self.setup_ui()
        self.load_dir(self.current_dir)

        # Safe focus grab pattern to prevent race conditions on window creation
        self.lift()
        self.after(100, self._safe_grab)

    def _safe_grab(self):
        """Attempts to grab input focus without crashing if window is destroyed."""
        try:
            self.grab_set()
            self.focus_force()
        except: pass

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1) # File List
        self.grid_columnconfigure(1, weight=2) # Preview
        self.grid_rowconfigure(1, weight=1)

        # --- HEADER (Navigation & Path) ---
        header = ctk.CTkFrame(self, fg_color="transparent", height=40)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=10)

        btn_up = ctk.CTkButton(header, text="⬆ Up", width=60, command=self.go_up)
        btn_up.pack(side="left", padx=(0, 5))

        self.lbl_path = ctk.CTkLabel(header, text=self.current_dir, anchor="w", fg_color="#222", corner_radius=5)
        self.lbl_path.pack(side="left", fill="x", expand=True, padx=5)

        # --- LEFT: FILE LIST ---
        self.scroll_files = ctk.CTkScrollableFrame(self, label_text="Files", width=250)
        self.scroll_files.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=10)

        # --- RIGHT: PREVIEW AREA ---
        preview_frame = ctk.CTkFrame(self, width=400)
        preview_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=10)
        preview_frame.pack_propagate(False)

        ctk.CTkLabel(preview_frame, text="Preview", font=("Arial", 12, "bold")).pack(pady=10)

        self.canvas_preview = ctk.CTkCanvas(preview_frame, bg="#1a1a1a", highlightthickness=0)
        self.canvas_preview.pack(fill="both", expand=True, padx=10, pady=10)

        # --- FOOTER (Actions) ---
        footer = ctk.CTkFrame(self, fg_color="transparent", height=50)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=10)

        btn_cancel = ctk.CTkButton(footer, text="Cancel", fg_color="#333", hover_color="#444", command=self.destroy)
        btn_cancel.pack(side="right", padx=5)

        self.btn_open = ctk.CTkButton(footer, text="Import Selected", state="disabled", command=self.confirm)
        self.btn_open.pack(side="right", padx=5)

    def load_dir(self, path):
        """
        Populates the scrollable list with directories and images from the given path.
        Handles permission errors gracefully.
        """
        try:
            items = sorted(os.listdir(path))
        except PermissionError:
            self.lbl_path.configure(text=f"{path} (Access Denied)")
            return

        self.current_dir = path
        self.lbl_path.configure(text=path)

        # Reset Selection State
        self.selected_file = None
        self.btn_open.configure(state="disabled")
        self.canvas_preview.delete("all")

        # Clear UI list
        for w in self.scroll_files.winfo_children(): w.destroy()

        # 1. Render Directories (Folders)
        for f in items:
            full = os.path.join(path, f)
            if os.path.isdir(full) and not f.startswith("."):
                btn = ctk.CTkButton(self.scroll_files, text=f"📁 {f}", anchor="w", fg_color="transparent",
                                    text_color="#aaa", hover_color="#333",
                                    command=lambda p=full: self.load_dir(p))
                btn.pack(fill="x", pady=1)

        # 2. Render Image Files
        valid_ext = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
        for f in items:
            if f.lower().endswith(valid_ext) and not f.startswith("."):
                btn = ctk.CTkButton(self.scroll_files, text=f"🖼 {f}", anchor="w", fg_color="transparent",
                                    border_width=1, border_color="#333",
                                    command=lambda n=f: self.select_file(n))
                btn.pack(fill="x", pady=1)

    def go_up(self):
        """Navigate to parent directory."""
        parent = os.path.dirname(self.current_dir)
        if parent and os.path.exists(parent) and parent != self.current_dir:
            self.load_dir(parent)

    def select_file(self, filename):
        """Handles file selection logic."""
        self.selected_file = os.path.join(self.current_dir, filename)
        self.btn_open.configure(state="normal")
        self.show_preview()

    def show_preview(self):
        """Renders the selected image onto the canvas, fitting it within bounds."""
        if not self.selected_file: return

        try:
            # Force update to get accurate dimensions
            self.canvas_preview.update_idletasks()
            cw = self.canvas_preview.winfo_width()
            ch = self.canvas_preview.winfo_height()

            # Fallback size if window hasn't rendered yet
            if cw < 10: cw, ch = 300, 200

            img = Image.open(self.selected_file)

            # High-quality resize maintaining aspect ratio
            img.thumbnail((cw, ch), Image.Resampling.LANCZOS)

            # Store reference to prevent garbage collection
            self.tk_img = ImageTk.PhotoImage(img)

            # Center image on canvas
            x = (cw - img.width) // 2
            y = (ch - img.height) // 2

            self.canvas_preview.delete("all")
            self.canvas_preview.create_image(x, y, image=self.tk_img, anchor="nw")

        except Exception as e:
            print(f"Preview Error: {e}")

    def confirm(self):
        """Passes the selected file path back to the parent via callback."""
        if self.selected_file and self.on_pick_callback:
            self.on_pick_callback(self.selected_file)
        self.destroy()

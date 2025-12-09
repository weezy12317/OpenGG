import json
import os
import pwd
import copy

# --- PATH CONFIGURATION ---
# Logic to determine the real user's home directory.
# This is crucial because if the app runs with 'sudo' (needed for USB access),
# os.path.expanduser("~") would point to /root/, but we want the config in /home/user/.
if 'SUDO_USER' in os.environ:
    real_user = os.environ['SUDO_USER']
    try:
        home_dir = pwd.getpwnam(real_user).pw_dir
    except KeyError:
        home_dir = f"/home/{real_user}"
    CONFIG_DIR = os.path.join(home_dir, ".config", "openGG")
else:
    CONFIG_DIR = os.path.expanduser("~/.config/openGG")

CONFIG_FILE = os.path.join(CONFIG_DIR, "profiles.json")

# --- DEFAULT CONSTANTS ---
DEFAULT_KEY_PERF = {"actuation": 1.8, "mode": 0, "rt_sens": 0.1}

DEFAULT_STRUCTURE = {
    "last_active": "Default",

    # 1. MAIN PROFILES (Performance + Links)
    # Stores Actuation, Rapid Trigger, and links to Lighting/OLED profiles.
    "profiles": {
        "Default": {
            "triggers": [],                # Process names (e.g., "cs2.exe")
            "linked_lighting": "Default",  # Pointer to lighting_profiles key
            "linked_oled": "Default",      # Pointer to oled_profiles key
            "keys": {},                    # Per-key overrides
            "hw_slot": 1                   # Onboard memory slot (1-5)
        }
    },

    # 2. LIGHTING PROFILES (RGB Only)
    # Stores RGB modes, colors, and per-key lighting overrides.
    "lighting_profiles": {
        "Default": {
            "mode": "static",
            "speed": 1.0,
            "brightness": 1.0,
            "primary_color": "#FF0000",
            "static_colors": {}            # Per-key color overrides
        }
    },

    # 3. OLED PROFILES (Image Data Only)
    # Stores raw byte arrays for the display.
    "oled_profiles": {
        "Default": {
            "image_data": []               # 640 bytes (128x40 px, 1-bit)
        }
    }
}

class ConfigManager:
    """
    Handles loading, saving, and managing the application state (profiles).
    Ensures data persistence across sessions using a JSON file.
    """
    def __init__(self):
        # Use deepcopy to ensure we don't modify the constant structure by reference
        self.data = copy.deepcopy(DEFAULT_STRUCTURE)
        self.load()

    def load(self):
        """
        Loads configuration from the JSON file.
        Creates the directory and file with defaults if they don't exist.
        """
        if not os.path.exists(CONFIG_DIR):
            try:
                os.makedirs(CONFIG_DIR, exist_ok=True)
            except OSError: pass

        if not os.path.exists(CONFIG_FILE):
            self.save()
        else:
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded_data = json.load(f)

                self.data = loaded_data

                # Structure Validation:
                # If the file is from an older version, we might need to reset or migrate.
                # Currently, if main sections are missing, we reset to default for safety.
                if "lighting_profiles" not in self.data or "oled_profiles" not in self.data:
                    self.data = copy.deepcopy(DEFAULT_STRUCTURE)
                    self.save()

            except (json.JSONDecodeError, OSError):
                # If file is corrupt, restore defaults
                self.data = copy.deepcopy(DEFAULT_STRUCTURE)
                self.save()

    def save(self):
        """Writes the current configuration state to disk."""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.data, f, indent=4)
        except OSError:
            pass

    def save_last_active_profile(self, name):
        """Updates the 'last_active' field to remember the user's choice on restart."""
        self.data["last_active"] = name
        self.save()

    def get_last_active_profile(self):
        """Retrieves the last used profile, falling back to 'Default' if missing."""
        last = self.data.get("last_active", "Default")
        if last not in self.data["profiles"]:
            return "Default"
        return last

    # --- GENERIC HELPERS ---

    def _reorder_dictionary(self, dict_key, new_order_list):
        """
        Reorders a dictionary in the config based on a list of keys.
        Used for rearranging profiles in the UI sidebar.
        """
        if dict_key not in self.data: return

        current_dict = self.data[dict_key]
        new_dict = {}

        # Insert items in the new order
        for name in new_order_list:
            if name in current_dict:
                new_dict[name] = current_dict[name]

        # Safety: Append any items that might have been missing from the order list
        for k, v in current_dict.items():
            if k not in new_dict:
                new_dict[k] = v

        self.data[dict_key] = new_dict
        self.save()

    # =========================================================================
    # MAIN PROFILE MANAGEMENT (Performance)
    # =========================================================================

    def get_all_profiles(self):
        return list(self.data.get("profiles", {}).keys())

    def create_profile(self, name):
        if name in self.data["profiles"]: return False
        self.data["profiles"][name] = {
            "triggers": [],
            "linked_lighting": "Default",
            "linked_oled": "Default",
            "keys": {},
            "hw_slot": 1
        }
        self.save()
        return True

    def delete_profile(self, name):
        if name == "Default": return False
        if len(self.data["profiles"]) <= 1: return False

        if name in self.data["profiles"]:
            del self.data["profiles"][name]
            # Reset active profile if we deleted the current one
            if self.data.get("last_active") == name:
                self.data["last_active"] = "Default"
            self.save()
            return True
        return False

    def rename_profile(self, old_name, new_name):
        if old_name == "Default": return False
        if old_name not in self.data["profiles"] or new_name in self.data["profiles"]:
            return False

        # Create new dict to preserve order (Python 3.7+ preserves insertion order)
        new_profiles = {}
        for key, val in self.data["profiles"].items():
            if key == old_name:
                new_profiles[new_name] = val
            else:
                new_profiles[key] = val

        self.data["profiles"] = new_profiles

        if self.data.get("last_active") == old_name:
            self.data["last_active"] = new_name

        self.save()
        return True

    def reorder_profiles(self, new_order_list):
        self._reorder_dictionary("profiles", new_order_list)

    # --- KEY DATA (Performance) ---

    def get_key_data(self, profile_name, key_name):
        """Returns specific key settings or defaults if not set."""
        prof = self.data["profiles"].get(profile_name)
        if not prof: return DEFAULT_KEY_PERF.copy()
        return prof["keys"].get(key_name, DEFAULT_KEY_PERF.copy())

    def get_visual_data_for_all_keys(self, profile_name, all_key_names):
        """
        Retrieves configuration for the entire keyboard efficiently.
        Merges stored overrides with default values.
        """
        prof = self.data["profiles"].get(profile_name)
        if not prof: return {}

        overrides = prof["keys"]
        result = {}

        for k in all_key_names:
            if k in overrides:
                result[k] = overrides[k]
            else:
                # Performance: Use copy() to prevent mutating the constant
                result[k] = DEFAULT_KEY_PERF.copy()
        return result

    def update_keys(self, profile_name, key_names, **kwargs):
        """Updates settings for a list of keys."""
        if profile_name not in self.data["profiles"]: return
        prof = self.data["profiles"][profile_name]

        for k in key_names:
            if k not in prof["keys"]:
                prof["keys"][k] = DEFAULT_KEY_PERF.copy()

            for setting, value in kwargs.items():
                # Safety check: prevent storing RGB data in performance profiles
                if setting != "rgb":
                    prof["keys"][k][setting] = value
        self.save()

    # =========================================================================
    # LIGHTING PROFILES
    # =========================================================================

    def get_all_lighting_profiles(self):
        return list(self.data.get("lighting_profiles", {}).keys())

    def create_lighting_profile(self, name):
        if name in self.data["lighting_profiles"]: return False
        self.data["lighting_profiles"][name] = {
            "mode": "static",
            "speed": 1.0,
            "brightness": 1.0,
            "primary_color": "#FF0000",
            "static_colors": {}
        }
        self.save()
        return True

    def get_lighting_data(self, light_prof_name):
        return self.data["lighting_profiles"].get(light_prof_name, self.data["lighting_profiles"]["Default"])

    def update_lighting_data(self, light_prof_name, **kwargs):
        if light_prof_name not in self.data["lighting_profiles"]: return
        prof = self.data["lighting_profiles"][light_prof_name]
        for k, v in kwargs.items():
            prof[k] = v
        self.save()

    def delete_lighting_profile(self, name):
        if name == "Default": return False
        if name in self.data["lighting_profiles"]:
            del self.data["lighting_profiles"][name]
            self.save()
            return True
        return False

    def rename_lighting_profile(self, old_name, new_name):
        if old_name == "Default": return False
        if old_name not in self.data["lighting_profiles"] or new_name in self.data["lighting_profiles"]:
            return False

        # 1. Rename the entry
        self.data["lighting_profiles"][new_name] = self.data["lighting_profiles"].pop(old_name)

        # 2. Update pointers in Main Profiles (Cascading rename)
        for perf_prof in self.data["profiles"].values():
            if perf_prof.get("linked_lighting") == old_name:
                perf_prof["linked_lighting"] = new_name

        self.save()
        return True

    def reorder_lighting_profiles(self, new_order_list):
        self._reorder_dictionary("lighting_profiles", new_order_list)

    # =========================================================================
    # OLED PROFILES
    # =========================================================================

    def get_all_oled_profiles(self):
        return list(self.data.get("oled_profiles", {}).keys())

    def create_oled_profile(self, name):
        if name in self.data["oled_profiles"]: return False
        self.data["oled_profiles"][name] = { "image_data": [] }
        self.save()
        return True

    def get_oled_data(self, oled_prof_name):
        return self.data["oled_profiles"].get(oled_prof_name, self.data["oled_profiles"]["Default"])

    def update_oled_data(self, oled_prof_name, image_data):
        if oled_prof_name not in self.data["oled_profiles"]: return
        self.data["oled_profiles"][oled_prof_name]["image_data"] = image_data
        self.save()

    def delete_oled_profile(self, name):
        if name == "Default": return False
        if name in self.data["oled_profiles"]:
            del self.data["oled_profiles"][name]
            self.save()
            return True
        return False

    def rename_oled_profile(self, old_name, new_name):
        if old_name == "Default": return False
        if old_name not in self.data["oled_profiles"] or new_name in self.data["oled_profiles"]:
            return False

        # 1. Rename the entry
        self.data["oled_profiles"][new_name] = self.data["oled_profiles"].pop(old_name)

        # 2. Update pointers in Main Profiles (Cascading rename)
        for perf_prof in self.data["profiles"].values():
            if perf_prof.get("linked_oled") == old_name:
                perf_prof["linked_oled"] = new_name

        self.save()
        return True

    def reorder_oled_profiles(self, new_order_list):
        self._reorder_dictionary("oled_profiles", new_order_list)

    # =========================================================================
    # LINKING LOGIC
    # =========================================================================

    def set_linked_lighting(self, main_profile, light_profile):
        """Associates a lighting profile with a performance profile."""
        if main_profile in self.data["profiles"] and light_profile in self.data["lighting_profiles"]:
            self.data["profiles"][main_profile]["linked_lighting"] = light_profile
            self.save()

    def get_linked_lighting(self, main_profile):
        """Returns the name of the associated lighting profile."""
        prof = self.data["profiles"].get(main_profile)
        if prof: return prof.get("linked_lighting", "Default")
        return "Default"

    def set_linked_oled(self, main_profile, oled_profile):
        """Associates an OLED profile with a performance profile."""
        if main_profile in self.data["profiles"] and oled_profile in self.data["oled_profiles"]:
            self.data["profiles"][main_profile]["linked_oled"] = oled_profile
            self.save()

    def get_linked_oled(self, main_profile):
        """Returns the name of the associated OLED profile."""
        prof = self.data["profiles"].get(main_profile)
        if prof: return prof.get("linked_oled", "Default")
        return "Default"

    # =========================================================================
    # HARDWARE & AUTOMATION
    # =========================================================================

    def set_profile_hw_slot(self, profile_name, slot_index):
        """Sets which onboard memory slot (1-5) to trigger when this profile loads."""
        if profile_name not in self.data["profiles"]: return
        valid_slot = max(1, min(5, int(slot_index)))
        self.data["profiles"][profile_name]["hw_slot"] = valid_slot
        self.save()

    def get_profile_hw_slot(self, profile_name):
        prof = self.data["profiles"].get(profile_name)
        if prof: return prof.get("hw_slot", 1)
        return 1

    def add_process_trigger(self, profile_name, process_name):
        """Adds an auto-switch trigger (e.g., 'cs2.exe') to a profile."""
        if profile_name not in self.data["profiles"]: return False
        prof = self.data["profiles"][profile_name]

        if "triggers" not in prof: prof["triggers"] = []

        if process_name not in prof["triggers"]:
            prof["triggers"].append(process_name)
            self.save()
        return True

    def remove_process_trigger(self, profile_name, process_name):
        if profile_name not in self.data["profiles"]: return False
        prof = self.data["profiles"][profile_name]

        if "triggers" in prof and process_name in prof["triggers"]:
            prof["triggers"].remove(process_name)
            self.save()
            return True
        return False

    def get_profile_triggers(self, profile_name):
        prof = self.data["profiles"].get(profile_name)
        if prof: return prof.get("triggers", [])
        return []

    def get_all_trigger_mappings(self):
        """
        Returns a flat dictionary for O(1) lookup during process monitoring.
        Format: {'process_name.exe': 'ProfileName'}
        """
        mapping = {}
        for p_name, data in self.data["profiles"].items():
            triggers = data.get("triggers", [])
            for t in triggers:
                mapping[t.lower()] = p_name
        return mapping

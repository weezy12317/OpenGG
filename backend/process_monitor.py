import threading
import time
import psutil

class ProcessMonitor(threading.Thread):
    """
    Background thread that monitors running system processes.
    Automatically switches the active profile when a configured application
    or game is detected.
    """
    def __init__(self, config_manager, callback_switch_profile):
        super().__init__()
        self.cfg = config_manager
        self.callback = callback_switch_profile
        self.running = True
        self.daemon = True  # Ensures thread dies when main app closes
        self.last_active_profile = None

    def run(self):
        """
        Main loop. Scans the process list every few seconds and compares
        it against the triggers defined in the configuration.
        """
        # Initial delay to allow system startup / app initialization
        time.sleep(2.0)

        while self.running:
            # 1. Fetch current triggers from config
            # Format: {'process_name_lowercase': 'Profile Name'}
            trigger_map = self.cfg.get_all_trigger_mappings()

            # Optimization: If no triggers are set, sleep longer to save CPU cycles
            if not trigger_map:
                time.sleep(5.0)
                continue

            # Default to "Default" profile unless a match is found
            target_profile = "Default"

            try:
                # 2. Iterate through all running processes
                # requesting 'name' is fast; 'cmdline' is slower but necessary for
                # identifying Wine/Proton games (which run under wine-preloader).
                for proc in psutil.process_iter(['name', 'cmdline']):
                    try:
                        p_info = proc.info

                        # Normalize data for case-insensitive matching
                        p_name = (p_info['name'] or "").lower()

                        # Join command line arguments into a single string
                        # e.g. ['/usr/bin/python', 'main.py'] -> "/usr/bin/python main.py"
                        p_cmd_list = p_info['cmdline'] or []
                        p_cmd_str = " ".join(p_cmd_list).lower()

                        # 3. Check against triggers
                        for trigger, profile_name in trigger_map.items():

                            # A) Exact match on process name (e.g. "cs2")
                            if trigger == p_name:
                                target_profile = profile_name
                                break

                            # B) Partial match in name (e.g. "discord" in "discord-bin")
                            if trigger in p_name:
                                target_profile = profile_name
                                break

                            # C) Partial match in command line (e.g. "cyberpunk" in "Z:\Games\Cyberpunk 2077\...")
                            # Essential for games running via Steam Proton or Lutris
                            if trigger in p_cmd_str:
                                target_profile = profile_name
                                break

                        # Optimization: Stop scanning immediately if a specific profile is found.
                        # This prevents wasting CPU scanning the rest of the 300+ processes.
                        if target_profile != "Default":
                            break

                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        # Process might have terminated during iteration; skip it.
                        continue

            except Exception:
                # Catch-all to prevent the monitoring thread from crashing due to system errors
                pass

            # 4. Apply Profile Switch (only if the target has changed)
            if target_profile != self.last_active_profile:
                self.last_active_profile = target_profile

                # Execute callback (triggers profile load in main thread)
                self.callback(target_profile)

            # 5. Wait before next scan
            time.sleep(5.0)

    def stop(self):
        """Signals the thread to stop gracefully."""
        self.running = False

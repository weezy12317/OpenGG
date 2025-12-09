import os
import sys
import subprocess

# --- CONSTANTS ---
# Path to the systemd user configuration directory
SYSTEMD_DIR = os.path.expanduser("~/.config/systemd/user")
SERVICE_NAME = "openGG-startup.service"
SERVICE_FILE = os.path.join(SYSTEMD_DIR, SERVICE_NAME)

class AutostartManager:
    """
    Manages the application's auto-start functionality on Linux.
    Uses 'systemd --user' services to launch the application in the background
    upon user login, without requiring root privileges.
    """

    def is_enabled(self):
        """
        Checks if the systemd service is currently installed and enabled.

        Returns:
            bool: True if the service file exists and systemctl reports it as enabled.
        """
        if not os.path.exists(SERVICE_FILE):
            return False

        try:
            # Query systemd for the service status
            res = subprocess.run(
                ["systemctl", "--user", "is-enabled", SERVICE_NAME],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            return res.returncode == 0
        except FileNotFoundError:
            # 'systemctl' command not found (e.g., non-systemd distro or minimal container)
            return False

    def enable_autostart(self):
        """
        Configures the application to start automatically on login.
        1. Creates the ~/.config/systemd/user directory.
        2. Writes a .service file pointing to the current python executable and main script.
        3. Reloads systemd and enables the service.

        Returns:
            bool: True if successful, False if permission errors or systemd failure occurred.
        """
        # 1. Ensure the systemd user directory exists
        if not os.path.exists(SYSTEMD_DIR):
            try:
                os.makedirs(SYSTEMD_DIR, exist_ok=True)
            except OSError:
                return False

        # 2. Resolve paths dynamically
        # We need the full path to the current Python interpreter (e.g., venv/bin/python)
        python_exe = sys.executable

        # Resolve the path to 'main.py' assuming this file is in 'backend/'
        # structure: root/main.py <--- root/backend/autostart.py
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(current_dir)
        script_path = os.path.join(root_dir, "main.py")

        if not os.path.exists(script_path):
            # Fallback for different directory structures
            script_path = os.path.abspath("main.py")

        # 3. Define the systemd service unit content
        # --silent argument ensures the app starts in headless/daemon mode
        content = f"""[Unit]
Description=OpenApex Profile Loader
After=graphical-session.target

[Service]
Type=simple
ExecStart={python_exe} "{script_path}" --silent
StandardOutput=journal
Restart=on-failure
RestartSec=5s
Environment=DISPLAY=:0

[Install]
WantedBy=default.target
"""

        try:
            # Write the service file
            with open(SERVICE_FILE, "w") as f:
                f.write(content)

            # Apply changes to systemd
            # daemon-reload: tells systemd to read the new file
            # enable: sets it to start on login
            # start: starts it immediately so the user doesn't have to reboot
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", SERVICE_NAME], check=True)
            subprocess.run(["systemctl", "--user", "start", SERVICE_NAME], check=True)

            return True
        except Exception:
            return False

    def disable_autostart(self):
        """
        Removes the auto-start configuration.
        Stops the service immediately and deletes the .service file.

        Returns:
            bool: True if successful.
        """
        try:
            # Stop the running instance and disable start-on-login
            subprocess.run(["systemctl", "--user", "stop", SERVICE_NAME], check=False)
            subprocess.run(["systemctl", "--user", "disable", SERVICE_NAME], check=False)

            # Remove the service file
            if os.path.exists(SERVICE_FILE):
                os.remove(SERVICE_FILE)

            # Refresh systemd to recognize the file is gone
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)

            return True
        except Exception:
            return False

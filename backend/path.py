import os
from pathlib import Path

def app_config_dir() -> Path:
    """
    Returns the root directory for the application's configuration files.

    Can be overridden by the 'OPENGG_CONFIG_DIR' environment variable.
    Defaults to '~/.config/openGG' (Standard Linux convention).
    """
    base = os.environ.get("OPENGG_CONFIG_DIR")
    if base:
        return Path(base).expanduser()
    return Path("~/.config/openGG").expanduser()

def prism_dump_dir() -> Path:
    """
    Returns the specific directory where SteelSeries Prism database dumps are stored.
    These dumps are used to import official lighting effects.
    """
    return app_config_dir() / "prism_db_dump"

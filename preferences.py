"""Small user settings file outside the application and source directories."""

import json
import os
import tempfile
from pathlib import Path


def settings_path():
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "Kadr" / "settings.json"


def load_theme(path=None):
    try:
        value = json.loads((path or settings_path()).read_text(encoding="utf-8")).get("theme")
        return value if value in ("light", "dark") else "light"
    except (OSError, ValueError, AttributeError):
        return "light"


def save_theme(theme, path=None):
    if theme not in ("light", "dark"):
        raise ValueError("Unknown theme")
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            json.dump({"theme": theme}, file)
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)

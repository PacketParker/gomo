"""Small JSON files for app state."""

import json
import os


def load_json(path, defaults):
    """The saved values for the keys in ``defaults``, or the defaults."""
    try:
        with open(path) as file:
            saved = json.load(file)
    except (OSError, ValueError):
        return dict(defaults)
    return {key: saved.get(key, value) for key, value in defaults.items()}


def save_json(path, data):
    temporary = f"{path}.tmp"
    with open(temporary, "w") as file:
        json.dump(data, file, indent=2)
    os.replace(temporary, path)  # atomic: never a half-written file

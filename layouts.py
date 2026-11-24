import json
import os
import re

PRESETS_FILE = "layouts.json"


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "layout"

def load_presets():
    if not os.path.exists(PRESETS_FILE):
        return []
    try:
        with open(PRESETS_FILE, "r") as presets_file:
            raw_presets = json.load(presets_file)["layouts"]       # the file is saved as {"layouts": [...]}
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("layout_presents.json could not be read:", error)
        return []

    presets = []
    for preset in raw_presets:
        if isinstance(preset, dict) and isinstance(preset.get("name"), str) and isinstance(preset.get("widgets"), list):
            preset.setdefault("id", _slug(preset["name"]))
            presets.append(preset)
    return presets

def _write_presets(presets):
    temp_file_name = PRESETS_FILE + ".tmp"
    with open(temp_file_name, "w") as temp_file:
        json.dump({"layouts": presets}, temp_file, indent=2)
    os.replace(temp_file_name, PRESETS_FILE)

def find_preset(presets, ref):
    """Look up a preset by id, then by name."""
    ref = str(ref).strip()
    for preset in presets:
        if preset["id"] == ref:
            return preset
    for preset in presets:
        if preset["name"].casefold() == ref.casefold():
            return preset
    return None

def save_preset(name, widgets):
    """Save widgets under name, replacing a preset with same name."""
    presets = load_presets()
    existing = next((p for p in presets if p["name"].casefold() == name.casefold()), None)
    if existing is not None:
        existing["widgets"] = widgets
    else:
        taken = {p["id"] for p in presets}
        base_id = _slug(name)
        preset_id, number = base_id, 2
        while preset_id in taken:
            preset_id = f"{base_id}-{number}"
            number += 1
        presets.append({"id": preset_id, "name": name, "widgets": widgets})
    _write_presets(presets)
    return existing is not None

def delete_preset(preset_id):
    _write_presets([p for p in load_presets() if p["id"] != preset_id])
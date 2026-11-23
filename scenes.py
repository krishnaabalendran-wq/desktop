import json
import os
import re

SCENES_FILE = "scenes.json"
DEFAULT_SCENE_COLOR = "#2b2f3a"


def starter_scenes():
    """Scenes everyone gets the first time."""
    return [
        {
            "id": "start-of-day", "name": "Start of day", "color": "#17492b",
            "steps": [
                {"type": "open_link", "url": "https://calendar.google.com"},
                {"type": "go_to_page", "page": 1},
                {"type": "message", "text": "Ready for the day"},
            ],
        },
        {
            "id": "presentation", "name": "Presentation", "color": "#1b3a6b",
            "steps": [
                {"type": "set_volume", "percent": 10},
                {"type": "go_to_page", "page": 2},
                {"type": "wait", "seconds": 3},
                {"type": "message", "text": "Good luck!"},
            ],
        },
        {
            "id": "deep-work", "name": "Deep work", "color": "#5a4410",
            "steps": [
                {"type": "set_volume", "percent": 20},
                {"type": "go_to_page", "page": 3},
                {"type": "message", "text": "Focus time"},
            ],
        },
        {
            "id": "leaving", "name": "Leaving", "color": "#4a2a5a",
            "steps": [
                {"type": "go_to_page", "page": 1},
                {"type": "copy_text", "text": "I'm out of the office and will reply tomorrow."},
                {"type": "message", "text": "See you tomorrow"},
            ],
        },
    ]

def load_scenes():
    """All scenees (list of dictionaries). Writes set if scenes.json doesn't exist."""
    if not os.path.exists(SCENES_FILE):
        scenes = starter_scenes()
        save_scenes(scenes)
        return scenes
    try:
        with open(SCENES_FILE, "r") as scenes_file:
            data = json.load(scenes_file)
        raw_scenes = data["scenes"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("scenes.json could not be read:", error)
        return starter_scenes()

    scenes = []
    for scene in raw_scenes:
        if isinstance(scene, dict) and isinstance(scene.get("name"), str) and isinstance(scene.get("steps"), list):
            scene.setdefault("id", scene["name"].lower().replace(" ", "-"))
            scenes.append(scene)
    return scenes

def save_scenes(scenes):
    """Write all scenes to disk."""
    temp_file_name = SCENES_FILE + ".tmp"
    with open(temp_file_name, "w") as temp_file:
        json.dump({"scenes": scenes}, temp_file, indent=2)
    os.replace(temp_file_name, SCENES_FILE)

def get_scene_color(scene):
    """The scene's button colour."""
    color = scene.get("color")
    if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return color
    return DEFAULT_SCENE_COLOR
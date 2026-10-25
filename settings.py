import copy
import json
import re
import sys
from pathlib import Path


APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
SETTINGS_PATH = APP_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "syntax_colors": {
        "string": "#a8d69a",
        "comment": "#6b6b6b",
        "keyword": "#8b5a2b",
        "class": "#d48c4a",
        "variable": "#ecd9b8",
        "number": "#e0b87a",
        "annotation": "#c58cd4",
        "operator": "#bbbbbb",
    },
    "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "shortcuts": {
        "run": "Ctrl+F5",
        "debug": "Ctrl+Shift+F5",
    },
}


def validate_settings(data):
    if not isinstance(data, dict):
        raise ValueError("Настройки должны быть JSON-объектом.")

    settings = copy.deepcopy(DEFAULT_SETTINGS)
    colors = data.get("syntax_colors", settings["syntax_colors"])
    if not isinstance(colors, dict):
        raise ValueError("Цвета подсветки должны быть объектом.")
    for name in settings["syntax_colors"]:
        color = colors.get(name, settings["syntax_colors"][name])
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError(f"Некорректный цвет подсветки: {name}.")
        settings["syntax_colors"][name] = color.lower()

    model = data.get("model", settings["model"])
    if not isinstance(model, str) or not model.strip() or len(model.strip()) > 200:
        raise ValueError("Название модели должно содержать от 1 до 200 символов.")
    settings["model"] = model.strip()

    shortcuts = data.get("shortcuts", settings["shortcuts"])
    if not isinstance(shortcuts, dict):
        raise ValueError("Горячие клавиши должны быть объектом.")
    for action in settings["shortcuts"]:
        shortcut = shortcuts.get(action, settings["shortcuts"][action])
        if not isinstance(shortcut, str) or not shortcut.strip() or len(shortcut.strip()) > 40:
            raise ValueError(f"Некорректное сочетание клавиш: {action}.")
        settings["shortcuts"][action] = shortcut.strip()
    if settings["shortcuts"]["run"].casefold() == settings["shortcuts"]["debug"].casefold():
        raise ValueError("Для запуска и отладки нужны разные сочетания клавиш.")

    return settings


def load_settings():
    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS)
    with SETTINGS_PATH.open("r", encoding="utf-8") as settings_file:
        return validate_settings(json.load(settings_file))


def save_settings(data):
    settings = validate_settings(data)
    temporary_path = SETTINGS_PATH.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as settings_file:
        json.dump(settings, settings_file, ensure_ascii=False, indent=2)
        settings_file.write("\n")
    temporary_path.replace(SETTINGS_PATH)
    return settings

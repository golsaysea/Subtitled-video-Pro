import json
import os


CONFIG_FILE = os.path.join(os.getcwd(), "settings.json")
DEFAULT_OUTPUT_RESOLUTION = "竖屏 1080x1920"
OUTPUT_RESOLUTION_OPTIONS = [
    "竖屏 1080x1920",
    "横屏 1920x1080",
    "正方 1080x1080",
    "自动检测 (跟随素材)",
]


def load_app_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_app_config(config):
    data = dict(config or {})
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_output_resolution():
    value = str(load_app_config().get("output_resolution") or DEFAULT_OUTPUT_RESOLUTION).strip()
    return value if value in OUTPUT_RESOLUTION_OPTIONS else DEFAULT_OUTPUT_RESOLUTION


def set_output_resolution(value):
    value = value if value in OUTPUT_RESOLUTION_OPTIONS else DEFAULT_OUTPUT_RESOLUTION
    config = load_app_config()
    config["output_resolution"] = value
    save_app_config(config)
    return value


def resolution_to_size(resolution_text, media_path="", get_media_size=None):
    text = str(resolution_text or DEFAULT_OUTPUT_RESOLUTION)
    if "1920x1080" in text:
        return 1920, 1080
    if "1080x1080" in text:
        return 1080, 1080
    if ("自动" in text or "跟随" in text) and media_path and callable(get_media_size):
        try:
            w, h = get_media_size(media_path)
            if w and h:
                return int(w), int(h)
        except Exception:
            pass
    return 1080, 1920

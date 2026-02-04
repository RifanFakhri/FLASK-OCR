import os
import yaml

# sekarang config_loader.py SEFOLDER dengan config.yaml
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
BBOX_CONFIG_PATH = os.path.join(BASE_DIR, "bbox_templates_config.yaml")

def load_yaml(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CONFIG = load_yaml(CONFIG_PATH)
BBOX_CONFIG = load_yaml(BBOX_CONFIG_PATH)
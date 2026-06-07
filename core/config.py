"""
config.py — Configuration loader for Jarvis Hub
"""
import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional

_DEFAULT_CONFIG_PATH = Path.home() / "jarvis-hub" / "config.yaml"

_config_cache: Optional[Dict[str, Any]] = None


def _resolve_paths_dict(obj: Any) -> Any:
    """Recursively resolve ~ in all string values."""
    if isinstance(obj, dict):
        return {k: _resolve_paths_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_paths_dict(item) for item in obj]
    elif isinstance(obj, str) and obj.startswith("~"):
        return str(Path(obj).expanduser().resolve())
    return obj


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from YAML file. Resolves ~ in paths."""
    global _config_cache

    if config_path is None:
        config_path = os.environ.get("JARVIS_CONFIG", str(_DEFAULT_CONFIG_PATH))

    path = Path(config_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Resolve all ~ paths
    cfg = _resolve_paths_dict(raw)

    # Set defaults where missing
    if cfg.get("telegram"):
        cfg["telegram"]["openclaw_path"] = cfg["telegram"].get("openclaw_path", "/opt/homebrew/bin/openclaw")

    if cfg.get("ollama"):
        cfg["ollama"]["url"] = cfg["ollama"].get("url", "http://localhost:11434")

    _config_cache = cfg
    return cfg


def get(key: str, default: Any = None) -> Any:
    """Get a config value using dot notation: 'telegram.target_chat_id'."""
    if _config_cache is None:
        load_config()

    parts = key.split(".")
    val = _config_cache
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            return default
        if val is None:
            return default
    return val


def reload_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Force reload config."""
    global _config_cache
    _config_cache = None
    return load_config(path)

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
        cfg["ollama"]["api_key"] = cfg["ollama"].get("api_key", "")

    # --- LLM multi-provider config (new) ----------------------------------------
    if cfg.get("llm"):
        llm_cfg = cfg["llm"]
        # Default provider: ollama (backward compat), but env var LLM_PROVIDER overrides
        active = os.environ.get("LLM_PROVIDER", "").strip().lower() or llm_cfg.get("provider", "ollama")
        llm_cfg["active_provider"] = active

        # Ensure ollama section has defaults
        if llm_cfg.get("ollama"):
            llm_cfg["ollama"]["url"] = llm_cfg["ollama"].get("url", "http://localhost:11434")
            llm_cfg["ollama"]["model"] = llm_cfg["ollama"].get("model", "qwen3.6:35b-a3b-mxfp8")
            llm_cfg["ollama"]["api_key"] = llm_cfg["ollama"].get("api_key", "")
            llm_cfg["ollama"]["timeout"] = llm_cfg["ollama"].get("timeout", 60)

        # Ensure omlx section has defaults
        if llm_cfg.get("omlx"):
            llm_cfg["omlx"]["base_url"] = llm_cfg["omlx"].get("base_url", "http://localhost:8000/v1")
            llm_cfg["omlx"]["model"] = llm_cfg["omlx"].get("model", "Qwen3.6-35B-A3B-MLX-8bit")
            llm_cfg["omlx"]["api_key"] = llm_cfg["omlx"].get("api_key", "")
            llm_cfg["omlx"]["timeout"] = llm_cfg["omlx"].get("timeout", 120)

        cfg["llm"] = llm_cfg

    # --- Database config (JH3.0) ---
    if cfg.get("db"):
        db_cfg = cfg["db"]
        db_cfg.setdefault("journal_mode", "WAL")
        db_cfg.setdefault("timeout", 30)
        # Set top-level db_path for backward compat with app.py
        cfg["db_path"] = db_cfg["path"]
        cfg["db"] = db_cfg

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

"""
config.py — Configuration loader for Jarvis Hub

Environment-aware profiles (prod/staging/dev) via JARVIS_ENV env var.
Supports: dot-notation access, YAML-based config, env var overrides,
hot-reload, and per-environment profile merging.
"""
import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional

_DEFAULT_CONFIG_PATH = Path.home() / "jarvis-hub" / "config.yaml"

# Default environment profiles (overridden by config.yaml env_section)
_DEFAULT_PROFILES: Dict[str, Dict[str, Any]] = {
    "prod": {
        "debug": False,
        "log_level": "WARNING",
        "testing": False,
        "cors_origins": "*",
        "rate_limit": "100/hour",
    },
    "staging": {
        "debug": True,
        "log_level": "INFO",
        "testing": False,
        "cors_origins": "*",
        "rate_limit": "1000/hour",
    },
    "dev": {
        "debug": True,
        "log_level": "DEBUG",
        "testing": True,
        "cors_origins": "*",
        "rate_limit": None,
    },
}

_config_cache: Optional[Dict[str, Any]] = None
_current_env: str = "dev"  # default, overridden by JARVIS_ENV


def _resolve_paths_dict(obj: Any) -> Any:
    """Recursively resolve ~ in all string values."""
    if isinstance(obj, dict):
        return {k: _resolve_paths_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_paths_dict(item) for item in obj]
    elif isinstance(obj, str) and obj.startswith("~"):
        return str(Path(obj).expanduser().resolve())
    return obj


def _load_profile(env: str) -> Dict[str, Any]:
    """Load default profile for environment."""
    return dict(_DEFAULT_PROFILES.get(env, _DEFAULT_PROFILES["dev"]))


def _apply_env_overrides(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment variable overrides to config."""
    # Database path override
    db_path = os.environ.get("JARVIS_DB_PATH")
    if db_path:
        if cfg.get("db"):
            cfg["db"]["path"] = db_path
            cfg["db_path"] = db_path
        else:
            cfg["db"] = {"path": db_path}
            cfg["db_path"] = db_path

    # Secret key
    flask_secret = os.environ.get("FLASK_SECRET_KEY")
    if flask_secret:
        cfg.setdefault("flask", {})["secret_key"] = flask_secret

    # Telegram override
    tg_chat = os.environ.get("JARVIS_TELEGRAM_CHAT_ID")
    if tg_chat:
        cfg.setdefault("telegram", {})["target_chat_id"] = tg_chat

    # LLM provider
    llm_provider = os.environ.get("LLM_PROVIDER")
    if llm_provider and cfg.get("llm"):
        cfg["llm"]["active_provider"] = llm_provider.lower()

    # CORS
    cors = os.environ.get("JARVIS_CORS_ORIGINS")
    if cors:
        cfg.setdefault("flask", {})["cors_origins"] = cors

    # Debug mode
    debug = os.environ.get("JARVIS_DEBUG", "").lower() in ("1", "true", "yes")
    if debug:
        cfg.setdefault("flask", {})["debug"] = True

    return cfg


def _merge_profiles(base: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge profile overrides into base config."""
    result = dict(base)
    for key, val in profile.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = {**result[key], **val}
        else:
            result[key] = val
    return result


def load_config(config_path: Optional[str] = None, env: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from YAML file. Resolves ~ in paths.

    Args:
        config_path: Optional path to YAML config file.
        env: Environment profile (prod/staging/dev). Defaults to JARVIS_ENV.

    Returns:
        Merged configuration dict.
    """
    global _config_cache, _current_env

    # Determine environment
    if env is None:
        env = os.environ.get("JARVIS_ENV", "dev").strip().lower()
    _current_env = env

    if config_path is None:
        config_path = os.environ.get("JARVIS_CONFIG", str(_DEFAULT_CONFIG_PATH))

    path = Path(config_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # Resolve all ~ paths
    cfg = _resolve_paths_dict(raw)

    # Load environment profile
    env_profile = _load_profile(env)

    # Apply YAML env_section overrides if present
    yaml_env = cfg.get("env_section", {}).get(env)
    if yaml_env and isinstance(yaml_env, dict):
        env_profile = {**env_profile, **yaml_env}

    # Merge profile overrides into base config
    cfg = _merge_profiles(cfg, env_profile)

    # Set defaults where missing
    if cfg.get("telegram"):
        cfg["telegram"]["openclaw_path"] = cfg["telegram"].get("openclaw_path", "/opt/homebrew/bin/openclaw")

    if cfg.get("ollama"):
        cfg["ollama"]["url"] = cfg["ollama"].get("url", "http://localhost:11434")
        cfg["ollama"]["api_key"] = cfg["ollama"].get("api_key", "")

    # --- LLM multi-provider config ---
    if cfg.get("llm"):
        llm_cfg = cfg["llm"]
        active = os.environ.get("LLM_PROVIDER", "").strip().lower() or llm_cfg.get("active_provider") or llm_cfg.get("provider", "ollama")
        llm_cfg["active_provider"] = active

        if llm_cfg.get("ollama"):
            llm_cfg["ollama"]["url"] = llm_cfg["ollama"].get("url", "http://localhost:11434")
            llm_cfg["ollama"]["model"] = llm_cfg["ollama"].get("model", "qwen3.6:35b-a3b-mxfp8")
            llm_cfg["ollama"]["api_key"] = llm_cfg["ollama"].get("api_key", "")
            llm_cfg["ollama"]["timeout"] = llm_cfg["ollama"].get("timeout", 60)

        if llm_cfg.get("omlx"):
            llm_cfg["omlx"]["base_url"] = llm_cfg["omlx"].get("base_url", "http://localhost:8000/v1")
            llm_cfg["omlx"]["model"] = llm_cfg["omlx"].get("model", "Qwen3.6-35B-A3B-MLX-8bit")
            llm_cfg["omlx"]["api_key"] = llm_cfg["omlx"].get("api_key", "")
            llm_cfg["omlx"]["timeout"] = llm_cfg["omlx"].get("timeout", 120)

        cfg["llm"] = llm_cfg

    # --- Database config ---
    if cfg.get("db"):
        db_cfg = cfg["db"]
        db_cfg.setdefault("journal_mode", "WAL")
        db_cfg.setdefault("timeout", 30)
        cfg["db_path"] = db_cfg["path"]
        cfg["db"] = db_cfg

    # --- Flask config defaults ---
    cfg.setdefault("flask", {})["secret_key"] = os.environ.get("FLASK_SECRET_KEY", os.urandom(32).hex())
    cfg.setdefault("flask", {})["debug"] = cfg.get("debug", False)
    cfg.setdefault("flask", {})["testing"] = cfg.get("testing", False)
    cfg["flask"] = cfg["flask"]  # preserve top-level

    # Apply env var overrides (highest priority)
    cfg = _apply_env_overrides(cfg)

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


def get_env() -> str:
    """Return current active environment (prod/staging/dev)."""
    if _config_cache is None:
        load_config()
    return _current_env


def reload_config(path: Optional[str] = None, env: Optional[str] = None) -> Dict[str, Any]:
    """Force reload config."""
    global _config_cache
    _config_cache = None
    return load_config(path, env)


def get_as_flask_config() -> Dict[str, Any]:
    """Return config dict formatted for Flask app.config."""
    cfg = load_config()

    flask_cfg = {}
    # Flatten common top-level keys
    flask_cfg["SECRET_KEY"] = cfg["flask"]["secret_key"]
    flask_cfg["DEBUG"] = cfg["flask"]["debug"]
    flask_cfg["TESTING"] = cfg["flask"]["testing"]
    flask_cfg["CORS_ORIGINS"] = cfg.get("flask", {}).get("cors_origins", "*")
    flask_cfg["RATE_LIMIT"] = cfg.get("flask", {}).get("rate_limit")
    flask_cfg["LOG_LEVEL"] = cfg.get("log_level", "INFO")
    flask_cfg["ENVIRONMENT"] = _current_env

    # DB config
    if cfg.get("db"):
        flask_cfg["DATABASE_PATH"] = cfg["db"]["path"]
        flask_cfg["DB_TIMEOUT"] = cfg["db"].get("timeout", 30)

    # Telegram
    if cfg.get("telegram"):
        flask_cfg["TG_CHAT_ID"] = cfg["telegram"].get("target_chat_id", "")
        flask_cfg["TG_OPENCLAW"] = cfg["telegram"].get("openclaw_path", "")

    # LLM
    if cfg.get("llm"):
        flask_cfg["LLM_PROVIDER"] = cfg["llm"]["active_provider"]
        active = cfg["llm"]["active_provider"]
        if active in cfg["llm"] and isinstance(cfg["llm"][active], dict):
            for k, v in cfg["llm"][active].items():
                flask_cfg[f"LLM_{active.upper()}_{k.upper()}"] = v

    return flask_cfg

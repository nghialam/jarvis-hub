"""
llm_client.py — Unified LLM Client for Jarvis Hub

Abstracts away the LLM backend so you can switch between Ollama and oMLX
(plus any OpenAI-compatible endpoint) by changing ONE config value.

Usage:
    from core.llm_client import llm_call, llm_parse_json, check_llm_health

    # Call LLM (auto-uses active provider from config)
    result = llm_call("Phân tích thị trường hôm nay...")

    # Parse JSON response
    data = llm_parse_json("Cho kết quả theo format JSON...")

    # Check if active provider is reachable
    healthy = check_llm_health()

Provider selection:
    - Set `llm.provider` in config.yaml: "ollama" or "omlx"
    - Falls back to "ollama" if section missing (backward compat)
    - Also respects LLM_PROVIDER env var for runtime override:
        export LLM_PROVIDER=omlx
        python app.py

Config structure (config.yaml):
    llm:
      provider: omlx          # ollama | omlx
      ollama:
        url: http://localhost:11434
        model: qwen3.6:35b-a3b-mxfp8
        api_key: ""
        timeout: 60
      omlx:
        base_url: http://localhost:8000/v1
        model: Qwen3.6-35B-A3B-MLX-8bit
        api_key: ""
        timeout: 120
"""
import json
import os
import re
import requests
from typing import Any, Dict, Optional

# --- Lazy config load --------------------------------------------------------

_config_cache: Optional[Dict[str, Any]] = None


def _get_config() -> Dict[str, Any]:
    """Load config once, cache it."""
    global _config_cache
    if _config_cache is None:
        try:
            import core.config as cfg_module
            _config_cache = cfg_module.load_config()
        except Exception:
            _config_cache = {}
    return _config_cache


def _get_provider_config() -> Dict[str, Any]:
    """Get the config for the ACTIVE provider."""
    cfg = _get_config()
    llm_section = cfg.get("llm", {})
    provider_name = os.environ.get("LLM_PROVIDER", "").strip().lower() or \
                    llm_section.get("provider", "").strip().lower() or \
                    "ollama"  # fallback for backward compat

    # Map provider name to config section
    provider_map = {
        "ollama": "ollama",
        "omlx": "omlx",
        "mlx": "omlx",
    }
    section_key = provider_map.get(provider_name, "ollama")

    providers = llm_section.get(section_key, {})

    return {
        "name": provider_name,
        "section": providers,
        "raw": llm_section,
    }


# --- Unified API call --------------------------------------------------------

def llm_call(
    prompt: str,
    system_prompt: Optional[str] = None,
    timeout: Optional[int] = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    stream: bool = False,
) -> Optional[str]:
    """Call the active LLM provider with a unified interface.

    Args:
        prompt: User prompt text.
        system_prompt: System message (optional, defaults to VN market analyst).
        timeout: Request timeout in seconds. Auto-detected from provider config if None.
        max_tokens: Max output tokens.
        temperature: Sampling temperature.
        stream: If True, returns generator of text chunks instead of full string.

    Returns:
        Generated text (or generator if stream=True), or None on failure.
    """
    pcfg = _get_provider_config()
    provider_name = pcfg["name"]
    pconfig = pcfg["section"]

    # Defaults from config
    if timeout is None:
        timeout = pconfig.get("timeout", 60)

    if system_prompt is None:
        system_prompt = "Ban la tro gi phan tich thi truong tai chinh Viet Nam."

    if provider_name == "ollama":
        return _call_ollama(
            prompt, system_prompt, timeout, max_tokens, temperature
        )
    elif provider_name in ("omlx", "mlx"):
        return _call_omlx(
            prompt, system_prompt, timeout, max_tokens, temperature
        )
    else:
        print(f"[LLM] Unknown provider '{provider_name}', falling back to ollama")
        return _call_ollama(
            prompt, system_prompt, timeout, max_tokens, temperature
        )


def _call_ollama(
    prompt: str,
    system_prompt: str,
    timeout: int,
    max_tokens: int,
    temperature: float,
) -> Optional[str]:
    """Call Ollama via /v1/chat/completions (OpenAI-compatible)."""
    pconfig = _get_provider_config()["section"]
    url = pconfig.get("url", "http://localhost:11434")
    model = pconfig.get("model", "qwen3.6:35b-a3b-mxfp8")
    api_key = pconfig.get("api_key", "")

    try:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        resp = requests.post(
            f"{url}/v1/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "stream": False,
                "temperature": temperature,
            },
            timeout=timeout,
        )

        if resp.status_code != 200:
            print(f"[LLM] {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return content if content else None

    except requests.exceptions.Timeout:
        print(f"[LLM] Ollama timeout after {timeout}s")
        return None
    except Exception as e:
        print(f"[LLM] Ollama error: {e}")
        return None


def _call_omlx(
    prompt: str,
    system_prompt: str,
    timeout: int,
    max_tokens: int,
    temperature: float,
) -> Optional[str]:
    """Call oMLX via /v1/chat/completions (OpenAI-compatible)."""
    pconfig = _get_provider_config()["section"]
    base_url = pconfig.get("base_url", "http://localhost:8000/v1")
    model = pconfig.get("model", "Qwen3.6-35B-A3B-MLX-8bit")
    api_key = pconfig.get("api_key", "")

    try:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "stream": False,
                "temperature": temperature,
            },
            timeout=timeout,
        )

        if resp.status_code != 200:
            print(f"[LLM] oMLX {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return content if content else None

    except requests.exceptions.Timeout:
        print(f"[LLM] oMLX timeout after {timeout}s")
        return None
    except Exception as e:
        print(f"[LLM] oMLX error: {e}")
        return None


# --- JSON parsing helper -----------------------------------------------------

def llm_parse_json(
    prompt: str,
    system_prompt: Optional[str] = None,
    timeout: Optional[int] = None,
    max_tokens: int = 4096,
) -> Optional[dict]:
    """Call LLM and parse response as JSON.

    Extracts JSON from markdown code blocks (```json ... ``` or ``` ... ```).
    """
    result = llm_call(prompt, system_prompt=system_prompt, timeout=timeout, max_tokens=max_tokens)
    if not result:
        return None

    # Try to extract JSON from markdown code blocks
    json_match = re.search(r"```(?:json)?\s*(.+?)\s*```", result, re.DOTALL)
    if json_match:
        result = json_match.group(1)

    try:
        return json.loads(result)
    except json.JSONDecodeError:
        print(f"[LLM] Failed to parse JSON: {result[:200]}")
        return None


# --- Health check ------------------------------------------------------------

def check_llm_health() -> Dict[str, Any]:
    """Check if the active LLM provider is reachable.

    Returns:
        {"healthy": bool, "provider": str, "details": str}
    """
    pcfg = _get_provider_config()
    provider_name = pcfg["name"]

    if provider_name == "ollama":
        pconfig = pcfg["section"]
        url = pconfig.get("url", "http://localhost:11434")
        try:
            resp = requests.get(f"{url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = [m.get("name", "?") for m in resp.json().get("models", [])]
                return {
                    "healthy": True,
                    "provider": "ollama",
                    "url": url,
                    "models": models,
                }
            return {"healthy": False, "provider": "ollama", "url": url, "details": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"healthy": False, "provider": "ollama", "url": url, "details": str(e)}

    elif provider_name in ("omlx", "mlx"):
        pconfig = pcfg["section"]
        base_url = pconfig.get("base_url", "http://localhost:8000/v1")
        try:
            resp = requests.get(f"{base_url}/models", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id", m.get("name", "?")) for m in data.get("data", [])]
                return {
                    "healthy": True,
                    "provider": "omlx",
                    "url": base_url,
                    "models": models,
                }
            return {"healthy": False, "provider": "omlx", "url": base_url, "details": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"healthy": False, "provider": "omlx", "url": base_url, "details": str(e)}

    return {"healthy": False, "provider": provider_name, "details": "Unknown provider"}


# --- Convenience: get current provider name ----------------------------------

def get_active_provider() -> str:
    """Return the name of the currently active LLM provider."""
    return _get_provider_config()["name"]


# --- Backward compatibility wrappers -----------------------------------------

def ollama_call(prompt: str, timeout: int = 60) -> Optional[str]:
    """Legacy wrapper — delegates to llm_call for backward compat.

    WARNING: This always uses the OLLAMA provider regardless of active config.
    Prefer llm_call() for new code.
    """
    # Temporarily force ollama provider
    orig_env = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "ollama"
    try:
        result = llm_call(prompt, timeout=timeout)
    finally:
        if orig_env is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = orig_env
    return result


def ollama_parse_json(prompt: str, timeout: int = 180) -> Optional[dict]:
    """Legacy wrapper — delegates to llm_parse_json for backward compat."""
    orig_env = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "ollama"
    try:
        result = llm_parse_json(prompt, timeout=timeout)
    finally:
        if orig_env is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = orig_env
    return result

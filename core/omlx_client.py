"""
omlx_client.py — OMLX (mlx-lm) API client for Jarvis Hub.

Replaces Ollama as the LLM inference backend.
Uses the OpenAI-compatible /v1/chat/completions endpoint.

Usage:
    from core.omlx_client import omlx_call
    result = omlx_call("Your prompt here")
"""
import json
import re
import requests
from typing import Optional


def _get_omlx_config():
    """Load OMLX config from Jarvis Hub config.yaml."""
    import core.config as cfg_module
    return cfg_module.load_config()


def omlx_call(prompt: str, timeout: int = 60) -> Optional[str]:
    """Call OMLX /v1/chat/completions to generate a response.

    Args:
        prompt: The user/system prompt text.
        timeout: Request timeout in seconds.

    Returns:
        The generated text, or None on failure.
    """
    config = _get_omlx_config()
    omlx_config = config.get("omlx", {})
    url = omlx_config.get("url", "http://localhost:11434")
    model = omlx_config.get("model", "Qwen3.6-35B-A3B-MLX-8bit")
    api_key = omlx_config.get("api_key", "")

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
                    {"role": "system", "content": "Ban la tro gi phan tich thi truong tai chinh Viet Nam."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 4096,
                "stream": False,
            },
            timeout=timeout,
        )

        if resp.status_code != 200:
            print(f"[OMLX] Returned {resp.status_code} for prompt: {prompt[:80]}")
            return None

        data = resp.json()
        # OMLX returns: choices[0].message.content
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return content if content else None

    except requests.exceptions.Timeout:
        print(f"[OMLX] Timeout for prompt: {prompt[:80]}")
        return None
    except Exception as e:
        print(f"[OMLX] Error: {e}")
        return None


def omlx_parse_json(prompt: str, timeout: int = 30) -> Optional[dict]:
    """Call OMLX and parse the response as JSON.

    Useful for structured outputs (sentiment analysis, etc.).

    Args:
        prompt: The prompt text.
        timeout: Request timeout in seconds.

    Returns:
        Parsed dict, or None on failure.
    """
    result = omlx_call(prompt, timeout=timeout)
    if not result:
        return None

    # Extract JSON from markdown code blocks if present
    json_match = re.search(r"```(?:json)?\s*(.+?)\s*```", result, re.DOTALL)
    if json_match:
        result = json_match.group(1)

    try:
        return json.loads(result)
    except json.JSONDecodeError:
        print(f"[OMLX] Failed to parse JSON response: {result[:200]}")
        return None

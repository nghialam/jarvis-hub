"""
ollama_client.py — Ollama API client for Jarvis Hub.

Uses the OpenAI-compatible /v1/chat/completions endpoint that Ollama provides.

Usage:
    from core.ollama_client import ollama_call
    result = ollama_call("Your prompt here")
"""
import json
import re
import requests
from typing import Optional


def _get_ollama_config():
    """Load Ollama config from Jarvis Hub config.yaml."""
    import core.config as cfg_module
    return cfg_module.load_config()


def ollama_call(prompt: str, timeout: int = 60) -> Optional[str]:
    """Call Ollama /v1/chat/completions to generate a response.

    Args:
        prompt: The user/system prompt text.
        timeout: Request timeout in seconds.

    Returns:
        The generated text, or None on failure.
    """
    config = _get_ollama_config()
    ollama_config = config.get("ollama", {})
    url = ollama_config.get("url", "http://localhost:11434")
    model = ollama_config.get("model", "qwen3.6:35b-a3b-mxfp8")
    api_key = ollama_config.get("api_key", "")

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
            print(f"[OLLAMA] Returned {resp.status_code} for prompt: {prompt[:80]}")
            return None

        data = resp.json()
        # Ollama returns: choices[0].message.content
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return content if content else None

    except requests.exceptions.Timeout:
        print(f"[OLLAMA] Timeout for prompt: {prompt[:80]}")
        return None
    except Exception as e:
        print(f"[OLLAMA] Error: {e}")
        return None


def ollama_parse_json(prompt: str, timeout: int = 180) -> Optional[dict]:
    """Call Ollama and parse the response as JSON.

    Useful for structured outputs (sentiment analysis, etc.).

    Args:
        prompt: The prompt text.
        timeout: Request timeout in seconds.

    Returns:
        Parsed dict, or None on failure.
    """
    result = ollama_call(prompt, timeout=timeout)
    if not result:
        return None

    # Extract JSON from markdown code blocks if present
    json_match = re.search(r"```(?:json)?\s*(.+?)\s*```", result, re.DOTALL)
    if json_match:
        result = json_match.group(1)

    try:
        return json.loads(result)
    except json.JSONDecodeError:
        print(f"[OLLAMA] Failed to parse JSON response: {result[:200]}")
        return None

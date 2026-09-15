"""
ollama_client.py — Ollama API client for Jarvis Hub (backward compat layer).

This module now delegates to llm_client.py for the unified provider-switching
logic. The old `ollama_call()` and `ollama_parse_json()` functions remain
available for backward compatibility — they always force the Ollama provider
regardless of the active LLM_PROVIDER setting.

For new code, prefer:
    from core.llm_client import llm_call, llm_parse_json, check_llm_health, get_active_provider

Usage (legacy):
    from core.ollama_client import ollama_call
    result = ollama_call("Your prompt here")
"""
from typing import Optional

# Delegate to unified llm_client
from core.llm_client import ollama_call, ollama_parse_json

__all__ = ["ollama_call", "ollama_parse_json"]

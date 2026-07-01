#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gotham — Package root for Gotham Brief orchestration.

Shared config constants extracted from gotham_brief.py monolith.
All other modules import configuration from here rather than duplicating.
"""

import os

# ─── Telegram ─────────────────────────────
TELEGRAM_CHAT_ID = os.environ.get(
    "JARVIS_TELEGRAM_CHAT_ID", "-1003801745265"
)

# ─── Ollama ──────────────────────────────
OMLX_URL = os.environ.get(
    "OMLX_HOST", "http://localhost:11434"
)
LLM_MODEL = os.environ.get(
    "LLM_MODEL", "Qwen3.6-35B-A3B-MLX-8bit"
)

# ─── Pipeline Defaults ──────────────────────
LLM_POOL_SIZE = 2              # Threads for parallel LLM dispatch
LLM_TOTAL_TIMEOUT_BUDGET = 500  # Total seconds for ALL calls combined  
LLM_RETRIES = 3                # Retries per individual prompt call

# ─── Kanban DB Path (extracted from run_pipeline inline) ────────
_KANBAN_DIR = str(
    os.path.join(os.path.dirname(__file__), "kanban")
)

KANBAN_DB_PATH = os.path.join(_KANBAN_DIR, "gotham_kanban.db")

"""Local-first memory system for Hermes agent.

Standalone, self-hosted alternative to Honcho Cloud:
- PostgreSQL + pgvector for persistence  
- Ollama bge-m3 for embeddings (no OpenRouter)
- Query → embed → semantic search
- Sessions, messages, conclusions (peer facts)
- Full Honcho-compatible tool API surface

## Components
- config.MemoryConfig — runtime configuration
- vector_store.VectorStore — PostgreSQL/pgvector backend  
- embedding_client.EmbeddingClient — Ollama embedding wrapper
- memory_manager.MemoryManager — orchestrator (search, sessions, conclude, context)
- plugin_adapter.LocalMemoryPlugin — Hermes tool registration

## Usage
```python
from local_memory_plugin import init, create_plugin_from_env

# One-shot start  
status = init()  # → {database: healthy, pgvector: True, ollama_ready: True}

# Or inline:
from config import MemoryConfig
from memory_manager import MemoryManager

config = MemoryConfig()
memory = MemoryManager(config)
health = memory.initialize()

# Search 
result = memory.search("what are Rex's preferences?")

# Save a persistent fact  
conclusion = memory.create_conclusion("user", "Rex prefers concise responses. No tables, bullets only.")

# Get full session context  
context = memory.get_context(peer_id="user")
```
"""

from .config import MemoryConfig  
from .vector_store import VectorStore
from .embedding_client import EmbeddingClient
from .memory_manager import MemoryManager
from .plugin_adapter import (
    LocalMemoryPlugin, 
    TOOL_SCHEMAS, 
    register_tools,
    create_plugin_from_env,
    init
)

__all__ = [
    "MemoryConfig",
    "VectorStore", 
    "EmbeddingClient",
    "MemoryManager",
    "LocalMemoryPlugin",
    "TOOL_SCHEMAS", 
    "register_tools",
    "create_plugin_from_env",
    "init"
]

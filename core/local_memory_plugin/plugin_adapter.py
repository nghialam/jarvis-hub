"""Hermes plugin adapter — bridges LocalMemory ↔ Hermes plugin interface.

Exposes tools matching honcho's API surface:
- honcho_profile: Read/update peer cards  
- honcho_search: Semantic search over memory
- honcho_context: Full session context snapshot  
- honcho_reasoning: Synthesized LLM answers from memory
- honcho_conclude: Save persistent facts
"""
import json
from typing import Dict, List, Optional, Callable
import sys

# Import local memory backend
sys.path.insert(0, '/Users/nghialam/.hermes/tools/local-memory-plugin')
try:
    from core.local_memory_plugin.config import MemoryConfig
    from core.local_memory_plugin.vector_store import VectorStore
    from core.local_memory_plugin.embedding_client import EmbeddingClient
    from core.local_memory_plugin.memory_manager import MemoryManager
except ImportError:
    import sys, os
    _plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if _plugin_dir not in sys.path:
        sys.path.insert(0, _plugin_dir)
    from core.local_memory_plugin.config import MemoryConfig
    from core.local_memory_plugin.vector_store import VectorStore
    from core.local_memory_plugin.embedding_client import EmbeddingClient
    from core.local_memory_plugin.memory_manager import MemoryManager


# Tool schemas matching Honcho's format
TOOL_SCHEMAS = [
    {
        "name": "honcho_profile",
        "description": (
            "Read or update a peer's CARD — a short, curated list of standing facts "
            "about that peer (name, role, preferences, communication style, recurring "
            "patterns). This is the cheapest, fastest Honcho call: no query, no LLM, "
            "just the current card. Pass `card` to overwrite it; omit `card` to read. "
            "An empty read returns a `hint` explaining why (observation disabled, fresh "
            "peer, representation still warming up) — that is NOT an error; the card "
            "accumulates over time from observed conversation. "
            "Related tools: honcho_context for the fuller standing snapshot (card + "
            "representation + summary + recent messages); honcho_search to find "
            "specific things that were actually said; honcho_reasoning for a "
            "synthesized answer to a question."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "peer": {
                    "type": "string",
                    "description": "Peer to query. Built-in aliases: 'user' (default), 'ai'. Or pass any peer ID from this workspace.",
                },
                "card": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New peer card as a list of fact strings. Omit to read the current card.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "honcho_search",
        "description": (
            "Hybrid (semantic + keyword) search over a peer's actual message "
            "history across ALL past sessions they took part in — not just the "
            "current one. Returns RRF-ranked raw message excerpts (what was "
            "literally said, including the assistant's own messages about the "
            "peer), no LLM synthesis. Cheaper and faster than honcho_reasoning. "
            "Use this to recall specific past facts — 'what did I say about X', "
            "'what was the regimen/decision/config we settled on' — and reason "
            "over the excerpts yourself. For nuanced questions needing synthesis, "
            "use honcho_reasoning instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look for — a topic, keyword, name, or natural-language description of the fact you're trying to recall.",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Approximate budget for returned excerpts (default 800, max 2000). Larger budgets return more/longer ranked snippets.",
                },
                "peer": {
                    "type": "string",
                    "description": "Whose history to search. Built-in aliases: 'user' (default), 'ai'. Or pass any peer ID from this workspace. Spans every session that peer took part in.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "honcho_reasoning",
        "description": (
            "Ask your memory a natural-language question and get back a SYNTHESIZED "
            "answer. This is the only function that runs an LLM: it retrieves relevant "
            "messages first, reasons over them, and writes a prose answer — so it is "
            "the slowest and most expensive call (seconds + tokens). Reach for it for "
            "nuanced or open-ended questions ('how does this person prefer to receive "
            "feedback?', 'what's their relationship to project X?') where you want the "
            "memory system to do the synthesis. For a specific fact that was stated, "
            "prefer honcho_search (cheap, raw excerpts). For standing profile facts, "
            "prefer honcho_profile / honcho_context (no LLM). "
            "Pass reasoning_level to control depth: minimal (fast/cheap), low "
            "(default), medium, high, max (deep/expensive). Omit for the configured default."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A natural language question.",
                },
                "reasoning_level": {
                    "type": "string",
                    "description": (
                        "Override the default reasoning depth. "
                        "- minimal: quick fact lookup, capped at ~250 tokens total\n"  
                        '- low/medium/high/max: no output token cap of their own\n'
                        '  - low: straightforward answers\n'
                        '  - medium: multi-aspect synthesis\n'
                        '  - high: deep analysis, contradictions resolved\n'
                        '  - max: thorough audit-level investigation'
                    ),
                },
                "peer": {
                    "type": "string",
                    "description": "Peer to query. Built-in aliases: 'user' (default), 'ai'.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "honcho_conclude",
        "description": (
            "Write, delete, or list CONCLUSIONS — persistent, derived facts about a peer that "
            "feed into your long-term profile. Use this when you learn something durable "
            "that should persist across sessions (a preference, a decision, a correction). "
            "You MUST pass exactly one of `conclusion` (create), `delete_id` (remove), or "
            "`list` (view/search); any other combination is an error."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "conclusion": {
                    "type": "string",
                    "description": "A factual statement to persist. Must provide exactly one of: conclusion, delete_id, or list.",
                },
                "delete_id": {
                    "type": "string",
                    "description": "Conclusion ID to remove (PII removal). List first with list=true to get IDs.",
                },
                "list": {
                    "type": "boolean",
                    "description": "List or search stored conclusions instead of creating/deleting. Set true along with optional query parameter.",
                },
                "query": {
                    "type": "string",
                    "description": "Semantic search term, used only when list=true.",
                },
                "peer": {
                    "type": "string",
                    "description": "Peer ID the conclusion is about. Aliases: 'user' (default), 'ai'. Or any peer ID.",
                },
            },
            "required": [],
        },
    },
]


class LocalMemoryPlugin:
    """Hermes plugin adapter — wraps MemoryManager to expose Honcho-compatible tools."""
    
    def __init__(self, memory_manager=None):
        self.memory = memory_manager or None
    
    # ── Tool Handlers (matching honcho API) ──────────────────
            
    def handle_tool_call(self, tool_name: str, args: dict) -> str:
        """Route tool calls to MemoryManager methods."""
        
        handlers = {
            "honcho_profile": self._tool_profile,
            "honcho_search": self._tool_search,  
            "honcho_reasoning": self._tool_reasoning,
            "honcho_conclude": self._tool_conclude,
            "honcho_context": self._tool_context,
        }
        
        handler = handlers.get(tool_name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {tool_name}", "available": list(handlers.keys())})
        
        try:
            return handler(args)
        except Exception as e:
            return json.dumps({
                "result": f"Error: {str(e)}", 
                "hint": "Check backend logs for details"
            })
    
    def _tool_profile(self, args: dict) -> str:
        """Read or update peer card."""
        peer = args.get("peer", "user")
        
        if "card" in args:
            # Update mode
            result = self.memory.update_profile(peer, args["card"])
            return json.dumps(result)
        else:
            # Read mode  
            result = self.memory.get_profile(peer, with_card=True)
            return json.dumps(result)

    def _tool_search(self, args: dict) -> str:
        """Query memory semantically."""
        query = args.get("query", "")
        if not query.strip():
            return json.dumps({"result": "Missing required parameter: query"})
        
        max_tokens = min(int(args.get("max_tokens", 800)), 2000)
        result = self.memory.search(
            query=query, 
            max_tokens=max_tokens,
            peer=args.get("peer", "user")
        )
        return json.dumps(result)

    def _tool_reasoning(self, args: dict) -> str:
        """Synthesized reasoning over retrieved context."""
        query = args.get("query", "")
        if not query.strip():
            return json.dumps({"result": "Missing required parameter: query"})
        
        try:
            result = self.memory.reasoning_query(
                query=query,
                peer=args.get("peer", "user"),
                reasoning_level=args.get("reasoning_level", "low")
            )
            return json.dumps({"result": result or "No result from memory."})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return json.dumps({
                "result": f"Memory query failed ({e})",
                "hint": "This is a backend error, not an empty result — the peer may still have context. Try honcho_search for raw excerpts."
            })

    def _tool_conclude(self, args: dict) -> str:
        """Manage persistent conclusions (facts)."""
        delete_id = (args.get("delete_id") or "").strip()
        conclusion = (args.get("conclusion") or "").strip()
        list_mode = bool(args.get("list"))
        
        if sum([bool(delete_id), bool(conclusion), list_mode]) != 1:
            return json.dumps({
                "result": "Exactly one of conclusion, delete_id, or list must be provided."
            })
        
        peer = args.get("peer", "user")
        query_search = (args.get("query") or "").strip() if args.get("list") else None
        
        if list_mode:
            conclusions = self.memory.list_conclusions(peer_id=peer, query=query_search)
            return json.dumps({"conclusions": conclusions})
        
        if delete_id:
            deleted = self.memory.delete_conclusion(delete_id)
            if deleted:
                return json.dumps({"result": f"Conclusion {delete_id} deleted."})
            return json.dumps({"result": f"Failed to delete conclusion {delete_id}."})
        
        # Create mode
        result = self.memory.create_conclusion(peer, conclusion)
        if result and result.get("id"):
            return json.dumps({
                "result": f"Conclusion saved for peer {peer}: {conclusion}"
            })
        return json.dumps({"result": "Failed to save conclusion."})

    def _tool_context(self, args: dict) -> str:
        """Get session context snapshot."""
        peer = args.get("peer", "user")
        ctx = self.memory.get_context(peer_id=peer)
        
        if not any(ctx.values()):
            return json.dumps({"result": "No context available yet."})
        
        parts = []
        for section, value in [
            ("Summary", ctx.get("summary")),
            ("Representation", ctx.get("representation")), 
            ("Card", "\n".join(f"- {f}" for f in ctx.get("card", [])[:10]))
        ]:
            if value:
                parts.append(f"## {section}\n{value}")
        
        if recent_msgs := ctx.get("recent_messages"):
            last = recent_msgs[-5:]  # Last 5 across sessions
            msg_text = "\n".join(
                f"  [{m['role']}] {m['content'][:200]}" 
                for m in last
            )
            parts.append(f"## Recent messages\n{msg_text}")
        
        return json.dumps({
            "result": "\n\n".join(parts) or "No context available."
        })


def register_tools(registry: dict, memory_mgr: MemoryManager) -> None:
    """Register all honcho tools into a registry.
    
    Usage:
        from local_memory_plugin import LocalMemoryPlugin
        plugin = LocalMemoryPlugin(memory_manager=memory_mgr)
        register_tools(tool_registry, memory_mgr)
    """
    plugin = LocalMemoryPlugin(memory_mgr)
    
    for tool_schema in TOOL_SCHEMAS:
        registry[tool_schema["name"]] = plugin.handle_tool_call


# ── Plugin Entry Point ─────────────────────────────────────

def get_config_schema() -> list[dict]:
    """Return the config schema for Hermes admin panels."""
    return [
        {
            "key": "baseUrl",
            "description": "Local memory server URL (defaults to embedded PostgreSQL+pgvector)",
            "secret": False,
        },
        {
            "key": "ollamaHost", 
            "description": "Ollama endpoint for embeddings (default: http://127.0.0.1:11434)",
            "secret": False,
        }
    ]


def create_plugin_from_env() -> LocalMemoryPlugin:
    """Instantiate a plugin instance from environment or defaults."""
    import os
    
    # Optional env overrides (HONCHO_BASE_URL still works)  
    ollama_host = os.getenv("HONCHO_OLLAMA_HOST", "http://127.0.0.1:11434")
    
    config = MemoryConfig(ollama_host=ollama_host)
    memory_mgr = MemoryManager(config)
    
    plugin = LocalMemoryPlugin(memory_mgr)
    return plugin


def init() -> dict:
    """One-shot initialization — returns status."""
    try:
        config = MemoryConfig()
        mgr = MemoryManager(config)
        health = mgr.initialize()
        
        # Ensure default collection exists
        mgr.store._ensure_collection("default_memory")
        mgr.store._ensure_collection("conclusions")
        
        return {
            "status": "initialized", 
            **health,
            "collections_ready": True,
            "peer_count": len(mgr.list_sessions())
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

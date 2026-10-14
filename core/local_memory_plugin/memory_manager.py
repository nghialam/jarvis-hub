"""Core memory manager — orchestrates vector store + embedding client.

Provides:
- Semantic search with query translation  
- Session/message lifecycle
- Conclusions/persistent facts
- Peer profiles and representations
"""
import uuid
import time
import json
from datetime import datetime
from typing import Optional, Dict, List

try:
    from core.local_memory_plugin.vector_store import VectorStore
    from core.local_memory_plugin.embedding_client import EmbeddingClient
    from core.local_memory_plugin.config import MemoryConfig
except ImportError:
    import sys, os
    _plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if _plugin_dir not in sys.path:
        sys.path.insert(0, _plugin_dir)
    from core.local_memory_plugin.vector_store import VectorStore
    from core.local_memory_plugin.embedding_client import EmbeddingClient
    from core.local_memory_plugin.config import MemoryConfig


class MemoryManager:
    """Main interface for the local memory system. Mirrors Honcho's API surface."""
    
    def __init__(self, config: MemoryConfig = None):
        self.config = config or MemoryConfig()
        self.store = VectorStore(self.config)
        self.embeddings = EmbeddingClient(
            base_url=self.config.ollama_host,
            model=self.config.embedding_model
        )
        
    def initialize(self) -> dict:
        """Verify all components are working."""
        health = self.store.health_check()
        embedding_ok = self.embeddings.verify()
        
        return {
            "database": health["status"],
            "pgvector": health["pgvector_extension"],
            "tables_ready": health["tables_ready"],
            "ollama_ready": embedding_ok,
            "timestamp": datetime.now().isoformat()
        }

    # ── Semantic Search ───────────────────────────────────────
    
    def search(
        self,
        query: str,
        max_tokens: int = 800,
        peer: str = "user",
        collection: Optional[str] = None
    ) -> dict:
        """Hybrid semantic + keyword search over memory.
        
        Returns excerpts from matching documents ranked by relevance.
        Equivalent to honcho_search tool.
        """
        # Get embedding for query
        query_embedding = self.embeddings.embed(query)
        if not query_embedding:
            return {"result": "Embedding failed — Ollama may not be running"}
        
        # Query vector store
        results = self.store.query_collection(
            collection=collection or "default_memory",
            query_embedding=query_embedding,
            n_results=min(self.config.max_query_results, 10)
        )
        
        # Format results to token budget (rough estimate: 4 chars ≈ 1 token)
        formatted = ""
        tokens_used = 0
        
        for i, doc in enumerate(results):
            excerpt = doc.get("content", "")[:200]  # Limit snippet length
            if tokens_used + len(excerpt) <= max_tokens * 4:
                # Parse created_at from PostgreSQL timestamp  
                created_str = doc.get('created_at', '') 
                ts_label = created_str[:10] if isinstance(created_str, str) and len(created_str) > 9 else ''
                
                formatted += f"[{i+1}] Score: {doc['similarity']:.3f} ({ts_label})\n"
                formatted += f"{excerpt}\n\n"
                tokens_used += len(excerpt)
            else:
                break
        
        if not formatted:
            formatted = "No relevant context found."
        
        return {"result": formatted}

    # ── Session & Message Management ────────────────────────
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session metadata."""
        return self.store.get_session(session_id)
    
    def list_sessions(self, peer_id: str = None, limit: int = 20) -> list[dict]:
        """List recent sessions."""
        return self.store.list_sessions(peer_id=peer_id, limit=limit)
    
    def create_session(
        self, 
        peer_id: str, 
        title: str = "",
        metadata: dict = None
    ) -> dict:
        """Create new memory session for a conversation."""
        return self.store.create_session(peer_id, title, metadata or {})
    
    def save_message(self, session_id: str, role: str, content: str, 
                     metadata: dict = None) -> str:
        """Save a message (user/assistant/system) to session AND memdocs for search."""
        msg_meta = metadata or {}
        
        # Save to sessions table  
        inserted = self.store.add_messages([{
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata": msg_meta
        }])
        
        # Also index in memdocs for semantic search (only user/assistant messages)
        if role in ('user', 'assistant') and len(content.strip()) > 10:
            try:
                import uuid as _uuid
                emb_vec = self.embeddings.embed(content.strip()[:500])  
                if emb_vec:
                    doc_id = _uuid.uuid4().hex[:12]
                    self.store.add_documents("default_memory", [Document(
                        id=doc_id, collection="default_memory",
                        content=f"[{role}] {content}",
                        embedding=emb_vec,
                        metadata={"session_id": session_id, "message_role": role},
                        created_at=time.time()
                    )])
            except Exception:
                pass  # Embedding failure won't break message saving
            
        return inserted[0] if inserted else None
    
    def get_session_history(self, session_id: str, limit: int = 50) -> list[dict]:
        """Get message history for a session."""
        return self.store.get_session_history(session_id, limit=limit)
    
    def update_session_title(self, session_id: str, title: str):
        """Update session title (update sessions table directly)."""
        conn = self.store.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE sessions SET title = %s, updated_at = NOW() WHERE id = %s",
                (title, session_id)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.store.pool.putconn(conn)

    # ── Conclusions (persistent facts) ───────────────────────

    def create_conclusion(self, peer_id: str, conclusion_text: str) -> Optional[dict]:
        """Save a persistent fact about a peer to memory store.
        
        These become part of the peer's representation card over time.
        Equivalent of honcho_conclude tool.
        """
        # Embed conclusion for future semantic retrieval  
        embedding = self.embeddings.embed(conclusion_text)
        if not embedding:
            return None
        
        doc_id = str(uuid.uuid4())[:12]
        from core.local_memory_plugin.vector_store import Document
        doc = Document(
            id=doc_id,
            collection="conclusions",
            content=conclusion_text,
            embedding=embedding,
            metadata={"peer_id": peer_id, "type": "conclusion"},
            created_at=time.time())
        stored = self.store.add_documents("conclusions", [doc])

        return stored[0] if stored else None

    def list_conclusions(self, peer_id: str = None, query: str = None) -> list[dict]:
        """List saved conclusions, optionally filtered by peer or searched."""
        conn = self.store.pool.getconn()
        cur = None
        try:
            if query:
                # Semantic search over conclusions
                embedding = self.embeddings.embed(query)
                if not embedding:
                    return []
                results = self.store.query_collection("conclusions", embedding, n_results=20)
                return [r for r in results if r['metadata'].get('peer_id') == peer_id] if peer_id else results
            else:
                # Simple filter by peer
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, content, metadata, created_at FROM memdocs WHERE collection = 'conclusions'",
                )
                rows = cur.fetchall()
                return [{
                    "id": r[0],
                    "content": r[1],
                    "peer_id": (r[2] or {}).get("peer_id", "") if r[2] else "",
                    "created_at": str(r[3])
                } for r in rows[:50]]
        finally:
            if cur:
                cur.close()
            conn.close()
            self.store.pool.putconn(conn)

    def delete_conclusion(self, conclusion_id: str) -> bool:
        """Delete a conclusion by ID."""
        return self.store.delete_documents("conclusions", [conclusion_id]) > 0

    def get_conclusion(self, conclusion_id: str) -> dict | None:
        """Get single conclusion by ID."""
        conn = self.store.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, content, metadata, created_at FROM memdocs WHERE id = %s AND collection = 'conclusions'",
                (conclusion_id,)
            )
            r = cur.fetchone()
            if not r:
                return None
            meta = r[2] or {}
            return {
                "id": r[0],
                "content": r[1],
                "type": meta.get("type", "conclusion"),
                "peer_id": meta.get("peer_id", ""),
                "category": meta.get("category", ""),
                "confidence": meta.get("confidence", 1.0),
                "created_at": str(r[3])
            }
        finally:
            if cur:
                cur.close()
            conn.close()
            self.store.pool.putconn(conn)

    def update_conclusion(self, conclusion_id: str, **fields) -> bool:
        """Update fields on a conclusion by ID. Returns True if updated."""
        allowed = {"type", "category", "content"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        conn = self.store.pool.getconn()
        cur = None
        try:
            # Update metadata JSONB field and optionally content column
            set_clauses = []
            vals = []
            content_val = None
            if "content" in updates:
                content_val = updates.pop("content")

            # Current metadata
            cur = conn.cursor()
            cur.execute("SELECT metadata FROM memdocs WHERE id = %s AND collection = 'conclusions'", (conclusion_id,))
            row = cur.fetchone()
            if not row:
                return False
            old_meta = row[0] or {}
            new_meta = {**old_meta}
            for k in updates:
                new_meta[k] = updates[k]

            # Build query body
            parts = []
            if content_val is not None:
                parts.append("content = %s")
                vals.append(content_val)
            parts.append("metadata = %s")
            vals.append(json.dumps(new_meta))
            parts.append("updated_at = now()")

            query = "UPDATE memdocs SET %s WHERE id = %%s AND collection = 'conclusions'" % ", ".join(parts)
            vals.append(conclusion_id)
            cur.execute(query, vals)
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.store.pool.putconn(conn)

    # ── Context & Profile Retrieval ────────────────────────────
    
    def get_context(self, peer_id: str = "user") -> dict:
        """Get full context snapshot for a peer.
        
        Returns summary, representation (from conclusions), and card data.
        Equivalent of honcho_context tool.
        """
        # Fetch recent session summaries
        sessions = self.list_sessions(peer_id=peer_id, limit=5)
        recent_messages = []
        session_ids = [s['id'] for s in sessions[:3]]
        
        for sid in session_ids:
            history = self.get_session_history(sid, limit=10)
            if history:
                recent_messages.extend(history[-5:])  # Last 5 per session
    
        # Fetch conclusions (representation layer)
        conclusions = self.list_conclusions(peer_id=peer_id)
        
        # Build peer card from conclusions
        card_facts = [c['content'] for c in conclusions[:20]]
        
        return {
            "summary": f"{len(sessions)} active sessions",
            "representation": "\n".join([f"- {c['content']}" for c in conclusions[:10]]) if conclusions else "",
            "card": card_facts,
            "recent_messages": [{"role": m['role'], "content": m['content']} for m in recent_messages[-8:]]
        }

    def get_profile(self, peer_id: str = "user", with_card: bool = False) -> dict:
        """Get or create a peer profile card. 
        Minimal fast read — no LLM synthesis needed.
        Equivalent of honcho_profile tool.
        """
        conclusions = self.list_conclusions(peer_id=peer_id)
        
        # Extract fact patterns from conclusions
        facts = []
        for c in conclusions[:30]:  # Max 30 facts
            text = c['content'][:200]  # Truncate long facts
            if text.strip():
                facts.append(text)
        
        result = {"result": "Peer profile loaded."}
        
        if with_card:
            result["card"] = facts
        
        return result

    def update_profile(self, peer_id: str, card_facts: list[str]) -> dict:
        """Update peer's fact card by adding conclusions.
        Equivalent of honcho_profile(card=[...]) tool.
        """
        ids = []
        for fact in card_facts[:50]:  # Limit card size
            conclusion = self.create_conclusion(peer_id, fact)
            if conclusion and conclusion.get("id"):
                ids.append(conclusion["id"])
        
        return {"result": f"Peer card updated ({len(ids)} facts).", "added_ids": ids}

    # ── Reasoning / Dialectic Layer ──────────────────────────
    
    def reasoning_query(self, query: str, peer_id: str = "user", 
                       reasoning_level: str = "low") -> str:
        """Ask a question and get a synthesized answer from memory.
        
        This is the most expensive operation — combines retrieval + LLM synthesis.
        Equivalent of honcho_reasoning tool.
        
        Uses bge-m3 for understanding and would be followed by a call to qwen3.6
        via Ollama (/api/generate or /api/chat) for synthesis.
        """
        # Phase 1: Retrieve relevant context  
        search_result = self.search(query, max_tokens=3000, peer=peer_id)
        retrieved_context = search_result.get("result", "")
        
        if "No relevant context found" in retrieved_context:
            return f"Not enough info to answer: {query}"
        
        # Phase 2: Synthesize answer using Ollama LLM (to be integrated separately)
        # This is where we'd call qwen3.6 via Ollama chat endpoint with:
        # system prompt + retrieved context + user question → synthesized answer
        
        response = self._synthesize_answer(query, retrieved_context, reasoning_level)
        return response
    
    def _synthesize_answer(self, question: str, context: str, level: str) -> str:
        """Synthesize an answer using Ollama LLM.
        
        In production this calls qwen3.6 via /api/chat endpoint.
        For now, returns a placeholder showing the pattern.
        """
        # Prepare chat messages for Ollama
        system_prompt = (
            f"You are a helpful AI assistant answering questions based on retrieved memory context.\n"
            f"Use ONLY the provided context unless you must ask for clarification.\n"
            f"**Reasoning Level:** {level}\n\n"
            f"---\n"
            f"Context:\n{context[:2000]}\n"
            f"---\n"
            f"Question: {question}\n"
            f"Answer (concise and accurate):"
        )
        
        try:
            # Call Ollama chat endpoint with qwen3.6 or equivalent  
            import requests
            payload = {
                "model": "qwen3.6",  # Or the model configured in config  
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": system_prompt}
                ],
                "stream": False,
                "options": {
                    "num_predict": 1024,
                    "temperature": 0.7
                }
            }
            
            response = requests.post(
                f"{self.config.ollama_host}/api/chat",
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            
            if "message" in result:
                return result["message"]["content"]
                
        except Exception as e:
            return f"(LLM synthesis failed: {e})\n\nRetrieved context:\n{context[:500]}"
        
        return "Could not generate response."

    # ── Lifecycle / Maintenance ────────────────────────────────
    
    def cleanup(self) -> dict:
        """Run periodic maintenance — purge expired sessions."""
        purged = self.store.purge_expired_sessions()
        return {"purged": purged}
    
    def shutdown(self):
        """Close database connection and clean up resources."""
        self.store.close()


# Factory function for quick instantiation
def create_memory_manager(config: MemoryConfig = None) -> MemoryManager:
    mgr = MemoryManager(config or MemoryConfig())
    return mgr

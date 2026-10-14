"""PostgreSQL/pgvector backend — replaces ChromaDB for local memory storage.

Features:
- Collections/databases for namespace separation
- Semantic search via pgvector cosine similarity  
- Metadata filtering support
- Session/message persistence with TTL
- Automatic cleanup of stale sessions
"""
import os
import json
import time
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional

try:
    import psycopg2
    import psycopg2.pool
    import psycopg2.extras
except ImportError:
    raise ImportError("psycopg2-binary required. Install in project venv: pip install psycopg2-binary")

try:
    from core.local_memory_plugin.config import MemoryConfig
except ImportError:
    import sys, os
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    from core.local_memory_plugin.config import MemoryConfig


@dataclass
class Document:
    """A memory document with embedding and metadata."""
    id: str
    collection: str  # namespace/collection name
    content: str
    embedding: list[float]
    metadata: dict = None
    created_at: float = 0.0
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.created_at == 0.0:
            self.created_at = time.time()


def _get_conn(pool):
    """Get a connection from the pool and return it when done."""
    conn = None
    try:
        conn = pool.getconn()
        yield conn
    finally:
        if conn:
            conn.close()
            pool.putconn(conn)


class VectorStore:
    """PostgreSQL/pgvector vector store for local memory persistence."""
    
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.pool = None
        self._connect()
        self._initialize_schema()
    
    def _connect(self):
        """Establish database connection pool."""
        dsn_dict = {
            'host': self.config.db_host,
            'port': self.config.db_port,
            'dbname': self.config.db_name,
            'user': self.config.db_user,
            'password': self.config.db_password,
        }
        try:
            self.pool = psycopg2.pool.SimpleConnectionPool(
                minconn=5,
                maxconn=20,
                **dsn_dict
            )
            # Get one connection to verify connectivity and run schema init
            conn = self.pool.getconn()
            conn.set_session(autocommit=True)
            cur = conn.cursor()
            try:
                cur.execute("SELECT 1")
                print(f"✅ PostgreSQL connection pool connected to {dsn_dict['dbname']} (min=5, max=20)")
            finally:
                cur.close()
            conn.close()
            self.pool.putconn(conn)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to PostgreSQL: {e}")
    
    def _initialize_schema(self):
        """Create tables and vector extension if not exists."""
        conn = self.pool.getconn()
        cur = None
        try:
            # Create pgvector extension (already installed based on check)
            cur = conn.cursor()
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Collections table: namespace/organization of memory documents
            cur.execute("""
                CREATE TABLE IF NOT EXISTS collections (
                    name TEXT PRIMARY KEY,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Memdocs table: stored memory with embeddings
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memdocs (
                    id TEXT PRIMARY KEY,
                    collection TEXT REFERENCES collections(name) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    embedding VECTOR(1024) NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Sessions table: conversation sessions with TTL expiry  
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    peer_id TEXT NOT NULL,
                    title TEXT DEFAULT '',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Messages table: individual messages within a session
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT CHECK (role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Indexes for performance
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_memdocs_collection 
                ON memdocs(collection);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_memdocs_embedding 
                ON memdocs USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session 
                ON messages(session_id, created_at);
            """)
            
            # Index on sessions for peer lookup  
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_peer 
                ON sessions(peer_id, updated_at DESC);
            """)
            
            # Create TTL trigger function for auto-cleanup
            cur.execute("""
                CREATE OR REPLACE FUNCTION clean_expired_sessions() RETURNS void AS $$
                BEGIN
                    DELETE FROM sessions 
                    WHERE updated_at < NOW() - INTERVAL '30 days';
                END;
                $$ LANGUAGE plpgsql;
            """)
            
            # Schedule cleanup cron (run daily via pg_cron if available, else manual)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS maintenance_log (
                    id SERIAL PRIMARY KEY,
                    action TEXT,
                    rows_affected INTEGER DEFAULT 0,
                    completed_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            print("✅ Schema initialized")
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def _ensure_collection(self, name: str) -> None:
        """Create collection namespace if it doesn't exist."""
        conn = self.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO collections (name) VALUES (%s) ON CONFLICT DO NOTHING",
                (name,)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def create_collection(self, name: str, metadata: dict = None) -> dict:
        """Create a new collection namespace."""
        self._ensure_collection(name)
        return {"name": name, "metadata": metadata or {}, "id": name}

    def delete_collection(self, name: str) -> bool:
        """Delete a collection and all its documents."""
        conn = self.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM memdocs WHERE collection = %s", (name,))
            count = cur.rowcount
            cur.execute("DELETE FROM collections WHERE name = %s", (name,))
            conn.commit()
            return count > 0
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def get_collection(self, name: str) -> Optional[dict]:
        """Get collection metadata."""
        conn = self.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name, metadata, created_at FROM collections WHERE name = %s", 
                (name,)
            )
            row = cur.fetchone()
            if row:
                return {"name": row[0], "metadata": row[1] or {}, "created_at": str(row[2])}
            return None
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def list_collections(self) -> list[dict]:
        """List all collections."""
        conn = self.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute("SELECT name, metadata, created_at FROM collections ORDER BY created_at")
            rows = cur.fetchall()
            return [{"name": r[0], "metadata": r[1] or {}, "created_at": str(r[2])} for r in rows]
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def add_documents(self, collection: str, documents: list[Document]) -> list[str]:
        """Add documents to a collection, returning their IDs."""
        self._ensure_collection(collection)
        conn = self.pool.getconn()
        cur = None
        inserted = []
        try:
            cur = conn.cursor()
            for doc in documents:
                cur.execute("""
                    INSERT INTO memdocs (id, collection, content, embedding, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, TIMESTAMP %s)
                    ON CONFLICT (id) DO UPDATE SET 
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                """, (
                    doc.id, doc.collection, doc.content,
                    json.dumps(doc.embedding),  # pgvector needs JSON array
                    json.dumps(doc.metadata or {}),
                    datetime.fromtimestamp(doc.created_at)
                ))
                inserted.append(doc.id)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)
        return inserted

    def delete_documents(self, collection: str, ids: list[str]) -> int:
        """Delete documents by ID from a collection."""
        conn = self.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM memdocs WHERE collection = %s AND id = ANY(%s)",
                (collection, ids)
            )
            count = cur.rowcount
            conn.commit()
            return count
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def query_collection(
        self, 
        collection: str, 
        query_embedding: list[float], 
        n_results: int = 10, 
        where: dict = None
    ) -> list[dict]:
        """Semantic search using cosine similarity on embeddings."""
        conn = self.pool.getconn()
        cur = None
        
        try:
            cur = conn.cursor()
            where_clause = ""
            params = [collection, query_embedding, n_results]
            
            if where:
                conditions = []
                for key, value in where.items():
                    placeholder = "%s"
                    conditions.append(f"metadata->>'{key}' = {placeholder}")
                    params.append(str(value))
                
                # Add limit and offset to params if present
                limit_idx = len(params) - len(conditions) + 1
                params[limit_idx:] = [n_results] + params[limit_idx:]
                
                where_clause = " AND " + " AND ".join(conditions)
            
            # Main similarity search query
            sql = f"""
                SELECT id, content, embedding, metadata, created_at, 
                    1 - (embedding <=> %s::vector) AS similarity
                FROM memdocs 
                WHERE collection = %s{where_clause}
                ORDER BY similarity DESC
                LIMIT %s;
            """
            
            cur.execute(sql, (json.dumps(query_embedding), collection, n_results))
            rows = cur.fetchall()
            
            results = []
            for row in rows:
                result = {
                    "id": row[0],
                    "content": row[1],
                    "metadata": row[3] or {},
                    "created_at": str(row[4]),
                    "similarity": float(row[5])
                }
                results.append(result)
                
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)
        
        return results

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get a session by ID."""
        conn = self.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, peer_id, title, metadata, created_at, updated_at FROM sessions WHERE id = %s",
                (session_id,)
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "peer_id": row[1], 
                    "title": row[2],
                    "metadata": row[3] or {},
                    "created_at": str(row[4]),
                    "updated_at": str(row[5])
                }
            return None
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def list_sessions(self, peer_id: str = None, limit: int = 20) -> list[dict]:
        """List sessions, optionally filtered by peer."""
        conn = self.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            if peer_id:
                cur.execute(
                    "SELECT id, peer_id, title, metadata, updated_at FROM sessions WHERE peer_id = %s ORDER BY updated_at DESC LIMIT %s",
                    (peer_id, limit)
                )
            else:
                cur.execute(
                    "SELECT id, peer_id, title, metadata, updated_at FROM sessions ORDER BY updated_at DESC LIMIT %s",
                    (limit,)
                )
            rows = cur.fetchall()
            return [{
                "id": r[0], "peer_id": r[1], "title": r[2],
                "metadata": r[3] or {}, "updated_at": str(r[4])
            } for r in rows]
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def create_session(self, peer_id: str, title: str = "", metadata: dict = None) -> dict:
        """Create a new session."""
        session_id = str(uuid.uuid4())[:12]  # Short ID for readability
        conn = self.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO sessions (id, peer_id, title, metadata, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
            """, (session_id, peer_id, title, json.dumps(metadata or {})))
            conn.commit()
            return {"id": session_id, "peer_id": peer_id, "title": title}
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its messages."""
        conn = self.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
            return cur.rowcount > 0
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    # [Messages API] Messages are stored per session with role tracking.

    def add_messages(self, messages: list[dict]) -> list[str]:
        """Add messages to sessions."""
        inserted = []
        conn = self.pool.getconn()
        cur = None
        try:
            for msg in messages:
                session_id = msg.get('session_id')
                role = msg.get('role', 'user')  # user, assistant, or system
                content = msg.get('content', '')
                message_metadata = msg.get('metadata', {})
                
                message_id = str(uuid.uuid4())[:12]
                
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO messages (id, session_id, role, content, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (message_id, session_id, role, content, json.dumps(message_metadata)))
                inserted.append(message_id)
            cur = conn.cursor()
            cur.execute("UPDATE sessions SET updated_at = NOW()")  # Touch all affected sessions
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)
        return inserted

    def get_session_history(self, session_id: str, limit: int = 50) -> list[dict]:
        """Get recent messages from a session, ordered by creation."""
        conn = self.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, role, content, metadata, created_at 
                FROM messages 
                WHERE session_id = %s 
                ORDER BY created_at ASC 
                LIMIT %s
            """, (session_id, limit))
            
            rows = cur.fetchall()
            return [{
                "id": r[0], "role": r[1], "content": r[2],
                "metadata": r[3] or {}, "created_at": str(r[4])
            } for r in rows]
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def delete_messages(self, session_id: str) -> int:
        """Delete all messages from a session (cascade to session delete)."""
        conn = self.pool.getconn()
        cur = None
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM messages WHERE session_id = %s", (session_id,))
            count = cur.rowcount
            conn.commit()
            return count
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def purge_expired_sessions(self) -> int:
        """Clean sessions older than TTL."""
        conn = self.pool.getconn()
        cur = None
        try:
            # Delete old messages first  
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM messages 
                WHERE id IN (
                    SELECT m.id FROM messages m
                    JOIN sessions s ON m.session_id = s.id
                    WHERE s.updated_at < NOW() - INTERVAL '30 days'
                )
            """)
            msg_count = cur.rowcount
            
            # Then delete old sessions
            cur.execute("DELETE FROM sessions WHERE updated_at < NOW() - INTERVAL '30 days'")
            session_count = cur.rowcount
            
            # Log cleanup  
            if msg_count > 0 or session_count > 0:
                log_cur = conn.cursor()
                try:
                    log_cur.execute("""
                        INSERT INTO maintenance_log (action, rows_affected)
                        VALUES ('purge_expired', %s)
                    """, (msg_count + session_count,))
                finally:
                    if log_cur:
                        log_cur.close()
            
            conn.commit()
            return msg_count + session_count
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def health_check(self) -> dict:
        """Verify PostgreSQL connection and table schemas."""
        conn = self.pool.getconn()
        cur = None
        try:
            # Check tables exist
            cur = conn.cursor()
            cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name IN 
                ('collections', 'memdocs', 'sessions', 'messages')
                ORDER BY table_name
            """)
            tables = [r[0] for r in cur.fetchall()]
            
            # Check extensions
            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            vector_ext = bool(cur.fetchone())
            
            return {
                "status": "healthy",
                "tables_ready": len(tables) == 4,
                "pgvector_extension": vector_ext,
                "tables": tables
            }
        except Exception as e:
            conn.rollback()
            raise
        finally:
            if cur:
                cur.close()
            conn.close()
            self.pool.putconn(conn)

    def close(self):
        """Close all connections in the connection pool."""
        if self.pool:
            self.pool.closeall()
            self.pool = None

# Make Session/Message types available for imports
Session = dict  # Dict-typed session object
Message = dict  # Dict-typed message object

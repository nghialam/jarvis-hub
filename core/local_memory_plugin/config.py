"""Local-first memory stack — config and constants."""
import os
from dataclasses import dataclass, field


@dataclass
class MemoryConfig:
    """Configuration for local memory system (PostgreSQL + pgvector + Ollama)."""
    
    # PostgreSQL connection
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "jarvis_hub_memory"
    db_user: str = "nghialam"  
    db_password: str = ""  # Trust auth on localhost
    
    # Ollama endpoint for embeddings
    ollama_host: str = "http://127.0.0.1:11434"
    embedding_model: str = "bge-m3"  # 1024 dimensions
    embedding_api_path: str = "/api/embed"
    
    # ChromaDB-style client settings  
    default_collection: str = "default_memory"
    max_query_results: int = 15
    context_token_budget: int = 4000
    
    # Session management
    session_ttl_hours: int = 720  # 30 days
    max_messages_per_session: int = 1000
    flush_interval_seconds: int = 5

    @property
    def connection_string(self) -> str:
        return (
            f"postgresql://{self.db_user}"
            f"{':' + self.db_password if self.db_password else ''}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
    
    @property
    def embedding_url(self) -> str:
        return f"{self.ollama_host}{self.embedding_api_path}"

"""Ollama embedding client — produces vector embeddings using local models."""
import os
import requests
from typing import Optional, Union


class EmbeddingClient:
    """Get embeddings from Ollama running bge-m3 on localhost:11434.
    
    Uses /api/embeddings endpoint which accepts JSON:
    POST http://127.0.0.1:11434/api/embeddings
    Body: {"model": "bge-m3", "input": "text"}
    Returns: {"embedding": [...], "total_tokens": N}
    """
    
    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "bge-m3"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        # bge-m3 uses /api/embed on this instance (not /api/embeddings)  
        self.api_url = f"{self.base_url}/api/embed"
    
    def _preload(self):
        """Ensure model is loaded into Ollama RAM."""
        try:
            requests.post(f"{self.base_url}/api/load",
                         json={"model": self.model}, timeout=5)
        except Exception:
            pass  # Already loading or already loaded

    def _request(self, data: dict) -> Optional[list[float]]:
        """Send embedding request to Ollama API."""
        self._preload()
        try:
            response = requests.post(
                self.api_url,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            # Handle /api/embed format: {"embeddings": [[...]]}
            if isinstance(result, dict):
                if "embeddings" in result and result["embeddings"]:
                    return result["embeddings"][0]  # First embedding from list
                elif "embedding" in result:
                    return result["embedding"]  # /api/embeddings legacy format
            
            
        except requests.exceptions.ConnectionError:
            print(f"❌ Ollama connection failed at {self.base_url}")
        except Exception as e:
            print(f"Ollama embedding error: {e}")
        
        return None

    def embed(self, text: str) -> Optional[list[float]]:
        """Get a single embedding for text."""
        if not text.strip():
            return []
        
        payload = {
            "model": self.model,
            "input": text
        }
        return self._request(payload)

    def embed_many(self, texts: list[str]) -> list[Optional[list[float]]]:
        """Get embeddings for multiple texts (batch)."""
        results = []
        for text in texts[:100]:  # Ollama may have batch size limits
            embedding = self.embed(text)
            results.append(embedding if embedding else [0.0] * 1024)  # Fallback zero vector
        
        return results

    def verify(self) -> bool:
        """Check if Ollama is running and serving the model."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            tags = response.json()
            models = [m.get("name", "") for m in tags.get("models", [])]
            
            if self.model in [m.split("/")[-1] if "/" in m else m for m in models]:
                print(f"✅ Ollama running — model {self.model} available")
                return True
            
            # Check partial match (model name might include tag)
            match = [m for m in models if "bge-m3" in m.lower()]
            if match:
                print(f"✅ bge-m3 found: {match[0]}")
                return True
                
        except requests.exceptions.ConnectionError:
            print("❌ Ollama not running on port 11434")
        except Exception as e:
            print(f"Ollama connection error: {e}")
        
        print("💡 Make sure Ollama is running and bge-m3 model is pulled: ollama pull bge-m3")
        return False

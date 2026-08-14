from abc import ABC, abstractmethod
from typing import List
import hashlib

class EmbeddingProviderInterface(ABC):
    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        pass

class MockEmbeddingProvider(EmbeddingProviderInterface):
    def embed_query(self, text: str) -> List[float]:
        """
        Deterministic mock embedding based on SHA-256 hash.
        Generates a fixed-size pseudo-vector.
        """
        hash_val = hashlib.sha256(text.encode('utf-8')).digest()
        # Convert first 10 bytes into a deterministic list of floats [0, 1]
        vector = [float(b) / 255.0 for b in hash_val[:10]]
        return vector

"""
Embedding Service

Generates text embeddings using Sentence-Transformers for semantic search.
Uses lazy loading to avoid loading the model until needed.
"""

from typing import List, Optional
import threading

from loguru import logger

from app.core.config import settings


class EmbeddingService:
    """
    Text embedding service using Sentence-Transformers.

    Lazy loads the model on first use to avoid slow startup.
    Thread-safe singleton pattern.
    """

    _instance: Optional["EmbeddingService"] = None
    _lock = threading.Lock()
    _model = None
    _model_loaded = False

    def __new__(cls) -> "EmbeddingService":
        """Ensure singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_model_loaded(self) -> None:
        """Load the model if not already loaded."""
        if self._model_loaded:
            return

        with self._lock:
            if self._model_loaded:
                return

            try:
                from sentence_transformers import SentenceTransformer

                logger.info(f"Loading embedding model: {settings.embedding_model_name}")
                self._model = SentenceTransformer(settings.embedding_model_name)
                self._model_loaded = True
                logger.info(
                    f"Embedding model loaded (dim={settings.embedding_dimension})"
                )
            except ImportError:
                logger.warning(
                    "sentence-transformers not installed. "
                    "Semantic search will be disabled. "
                    "Install with: pip install sentence-transformers"
                )
                self._model = None
                self._model_loaded = True
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                self._model = None
                self._model_loaded = True

    @property
    def is_available(self) -> bool:
        """Check if embedding model is available."""
        self._ensure_model_loaded()
        return self._model is not None

    def encode(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            List of floats (embedding vector) or None if unavailable
        """
        if not text or not text.strip():
            return None

        self._ensure_model_loaded()
        if self._model is None:
            return None

        try:
            # Truncate very long text to avoid memory issues
            text = text[:2000]
            embedding = self._model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    def encode_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors (or None for failed items)
        """
        if not texts:
            return []

        self._ensure_model_loaded()
        if self._model is None:
            return [None] * len(texts)

        try:
            # Truncate and filter empty texts
            processed = []
            indices = []
            for i, text in enumerate(texts):
                if text and text.strip():
                    processed.append(text[:2000])
                    indices.append(i)

            if not processed:
                return [None] * len(texts)

            # Batch encode
            embeddings = self._model.encode(
                processed,
                convert_to_numpy=True,
                show_progress_bar=False,
                batch_size=32,
            )

            # Map back to original positions
            result: List[Optional[List[float]]] = [None] * len(texts)
            for i, idx in enumerate(indices):
                result[idx] = embeddings[i].tolist()

            return result
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            return [None] * len(texts)

    def encode_for_search(self, query: str) -> Optional[List[float]]:
        """
        Generate embedding optimized for search queries.

        For most models, this is the same as encode().
        Some models may have query-specific encoders.

        Args:
            query: Search query text

        Returns:
            Embedding vector or None
        """
        return self.encode(query)


# Global instance
embedding_service = EmbeddingService()

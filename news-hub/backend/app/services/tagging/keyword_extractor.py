"""
Keyword Extractor

Jieba-based keyword extraction for Chinese text using TF-IDF and TextRank.
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger

# Lazy import jieba for performance
_jieba_initialized = False


def _init_jieba():
    """Initialize jieba with custom settings."""
    global _jieba_initialized
    if _jieba_initialized:
        return

    import jieba
    import jieba.analyse

    # Set custom stopwords if file exists
    stopwords_path = Path(__file__).parent / "stopwords.txt"
    if stopwords_path.exists():
        jieba.analyse.set_stop_words(str(stopwords_path))
        logger.debug(f"Loaded stopwords from {stopwords_path}")

    # Enable parallel processing for better performance
    try:
        jieba.enable_parallel(4)
    except Exception:
        pass  # Parallel not supported on all platforms

    _jieba_initialized = True


class KeywordExtractor:
    """
    Extract keywords from text using Jieba.

    Supports both TF-IDF and TextRank algorithms.
    """

    def __init__(self, method: str = "tfidf"):
        """
        Initialize keyword extractor.

        Args:
            method: Extraction method ('tfidf' or 'textrank')
        """
        _init_jieba()
        self.method = method

    def extract(
        self,
        text: str,
        top_k: int = 10,
        with_weight: bool = False,
        allow_pos: Optional[Tuple[str, ...]] = None,
    ) -> List[str] | List[Tuple[str, float]]:
        """
        Extract keywords from text.

        Args:
            text: Input text
            top_k: Number of keywords to extract
            with_weight: Whether to include weight scores
            allow_pos: Allowed POS tags (e.g., ('n', 'v', 'ns'))

        Returns:
            List of keywords or (keyword, weight) tuples
        """
        import jieba.analyse

        if not text or not text.strip():
            return []

        # Clean text
        text = text.strip()

        try:
            if self.method == "textrank":
                keywords = jieba.analyse.textrank(
                    text,
                    topK=top_k,
                    withWeight=with_weight,
                    allowPOS=allow_pos or ("n", "ns", "vn", "v"),
                )
            else:
                # Default: TF-IDF
                keywords = jieba.analyse.extract_tags(
                    text,
                    topK=top_k,
                    withWeight=with_weight,
                    allowPOS=allow_pos,
                )

            return keywords

        except Exception as e:
            logger.warning(f"Keyword extraction failed: {e}")
            return []

    def extract_from_news(
        self,
        title: str,
        description: Optional[str] = None,
        content: Optional[str] = None,
        top_k: int = 10,
    ) -> List[str]:
        """
        Extract keywords from news item fields.

        Combines title (weighted higher) with description and content.

        Args:
            title: News title (required)
            description: News description/summary
            content: Full news content
            top_k: Number of keywords to return

        Returns:
            List of keywords
        """
        # Combine text with title weighted higher
        parts = []

        # Title is most important - repeat for weight
        if title:
            parts.extend([title] * 3)

        if description:
            parts.extend([description] * 2)

        if content:
            # Truncate long content
            truncated = content[:2000] if len(content) > 2000 else content
            parts.append(truncated)

        combined_text = " ".join(parts)

        if not combined_text.strip():
            return []

        return self.extract(combined_text, top_k=top_k, with_weight=False)


def extract_keywords(
    text: str,
    top_k: int = 10,
    method: str = "tfidf",
) -> List[str]:
    """
    Convenience function to extract keywords from text.

    Args:
        text: Input text
        top_k: Number of keywords
        method: Extraction method ('tfidf' or 'textrank')

    Returns:
        List of keywords
    """
    extractor = KeywordExtractor(method=method)
    return extractor.extract(text, top_k=top_k, with_weight=False)


def extract_keywords_with_scores(
    text: str,
    top_k: int = 10,
    method: str = "tfidf",
) -> List[Tuple[str, float]]:
    """
    Extract keywords with their weight scores.

    Args:
        text: Input text
        top_k: Number of keywords
        method: Extraction method ('tfidf' or 'textrank')

    Returns:
        List of (keyword, weight) tuples
    """
    extractor = KeywordExtractor(method=method)
    return extractor.extract(text, top_k=top_k, with_weight=True)

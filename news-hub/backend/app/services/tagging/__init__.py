"""
Tagging Services

Auto-tagging system with Jieba keyword extraction and rule matching.
"""

from app.services.tagging.tag_service import TagService
from app.services.tagging.keyword_extractor import (
    KeywordExtractor,
    extract_keywords,
    extract_keywords_with_scores,
)
from app.services.tagging.rule_matcher import RuleMatcher, match_news_to_rules

__all__ = [
    "TagService",
    "KeywordExtractor",
    "extract_keywords",
    "extract_keywords_with_scores",
    "RuleMatcher",
    "match_news_to_rules",
]

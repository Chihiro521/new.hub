"""
Rule Matcher

Matches news items against user-defined tag rules.
"""

from typing import Any, Dict, List, Set, Tuple

from loguru import logger


class RuleMatcher:
    """
    Matches news items against tag rules.

    Supports multiple match modes (any/all) and field-specific matching.
    """

    def __init__(self, rules: List[Dict[str, Any]]):
        """
        Initialize rule matcher with a list of rules.

        Args:
            rules: List of tag rule documents (sorted by priority)
        """
        # Filter only active rules and sort by priority
        self.rules = [r for r in rules if r.get("is_active", True)]
        self.rules.sort(key=lambda x: x.get("priority", 0), reverse=True)

    def match(
        self,
        title: str,
        description: str = "",
        content: str = "",
    ) -> Tuple[List[str], List[str]]:
        """
        Match a news item against all rules.

        Args:
            title: News item title
            description: News item description/summary
            content: Full news content

        Returns:
            Tuple of (matched_tags, matched_rule_ids)
        """
        matched_tags: Set[str] = set()
        matched_rule_ids: List[str] = []

        for rule in self.rules:
            if self._match_rule(rule, title, description, content):
                matched_tags.add(rule["tag_name"])
                matched_rule_ids.append(str(rule.get("_id", "")))

        return list(matched_tags), matched_rule_ids

    def _match_rule(
        self,
        rule: Dict[str, Any],
        title: str,
        description: str,
        content: str,
    ) -> bool:
        """
        Check if a single rule matches the news item.

        Args:
            rule: Tag rule document
            title: News item title
            description: News item description
            content: Full news content

        Returns:
            True if rule matches
        """
        keywords = rule.get("keywords", [])
        if not keywords:
            return False

        match_mode = rule.get("match_mode", "any")
        case_sensitive = rule.get("case_sensitive", False)

        # Build text to search based on rule settings
        texts_to_search: List[str] = []

        if rule.get("match_title", True) and title:
            texts_to_search.append(title)

        if rule.get("match_description", True) and description:
            texts_to_search.append(description)

        if rule.get("match_content", False) and content:
            # Truncate long content for performance
            texts_to_search.append(content[:5000] if len(content) > 5000 else content)

        if not texts_to_search:
            return False

        # Combine texts for matching
        combined_text = " ".join(texts_to_search)

        if not case_sensitive:
            combined_text = combined_text.lower()

        # Match keywords
        if match_mode == "all":
            # All keywords must match
            return self._match_all(keywords, combined_text, case_sensitive)
        else:
            # Any keyword can match
            return self._match_any(keywords, combined_text, case_sensitive)

    def _match_any(
        self,
        keywords: List[str],
        text: str,
        case_sensitive: bool,
    ) -> bool:
        """
        Check if any keyword matches.

        Args:
            keywords: List of keywords
            text: Text to search in
            case_sensitive: Whether to match case

        Returns:
            True if any keyword matches
        """
        for keyword in keywords:
            kw = keyword if case_sensitive else keyword.lower()
            if kw in text:
                return True
        return False

    def _match_all(
        self,
        keywords: List[str],
        text: str,
        case_sensitive: bool,
    ) -> bool:
        """
        Check if all keywords match.

        Args:
            keywords: List of keywords
            text: Text to search in
            case_sensitive: Whether to match case

        Returns:
            True if all keywords match
        """
        for keyword in keywords:
            kw = keyword if case_sensitive else keyword.lower()
            if kw not in text:
                return False
        return True


def match_news_to_rules(
    news_item: Dict[str, Any],
    rules: List[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    """
    Convenience function to match a news item against rules.

    Args:
        news_item: News item document
        rules: List of tag rule documents

    Returns:
        Tuple of (matched_tags, matched_rule_ids)
    """
    matcher = RuleMatcher(rules)
    return matcher.match(
        title=news_item.get("title", ""),
        description=news_item.get("description", ""),
        content=news_item.get("content", ""),
    )

"""Custom tokenizer for Chinese/English BM25."""

import re
from typing import List
import jieba


class CustomTokenizer:
    """
    Custom tokenizer for API documentation.

    Features:
    - Chinese text: use jieba segmentation
    - English identifiers: keep whole, also split camelCase/snake_case
    - Lowercase normalization
    - Preserve numbers and units
    """

    def __init__(self):
        # Initialize jieba
        jieba.initialize()

        # Common API-related terms to add to jieba dictionary
        api_terms = [
            'cellpose', 'rnascope', 'detectpin', 'threshold',
            'flowThreshold', 'cellprobThreshold', 'diameter',
            'segmentation', 'brightfield', 'fluorescence',
            'workplan', 'sessionId', 'stepId', 'targetName'
        ]

        for term in api_terms:
            jieba.add_word(term)

    def split_camel_case(self, word: str) -> List[str]:
        """
        Split camelCase or PascalCase into parts.
        Example: detectpinMin -> [detectpin, min]
        """
        # Insert space before uppercase letters
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', word)
        # Insert space before uppercase letter followed by lowercase
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1 \2', s1)
        return [p.lower() for p in s2.split()]

    def split_snake_case(self, word: str) -> List[str]:
        """
        Split snake_case into parts.
        Example: flow_threshold -> [flow, threshold]
        """
        return [p.lower() for p in word.split('_') if p]

    def is_chinese(self, char: str) -> bool:
        """Check if character is Chinese."""
        return '\u4e00' <= char <= '\u9fff'

    def contains_chinese(self, text: str) -> bool:
        """Check if text contains Chinese characters."""
        return any(self.is_chinese(c) for c in text)

    def tokenize_english_identifier(self, word: str) -> List[str]:
        """
        Tokenize English identifier.
        Returns: original word + split parts
        """
        tokens = []

        # Keep original word
        word_lower = word.lower()
        tokens.append(word_lower)

        # Split camelCase
        if any(c.isupper() for c in word):
            camel_parts = self.split_camel_case(word)
            if len(camel_parts) > 1:
                tokens.extend(camel_parts)

        # Split snake_case
        if '_' in word:
            snake_parts = self.split_snake_case(word)
            if len(snake_parts) > 1:
                tokens.extend(snake_parts)

        # Remove duplicates while preserving order
        seen = set()
        result = []
        for token in tokens:
            if token not in seen and token:
                seen.add(token)
                result.append(token)

        return result

    def tokenize(self, text: str) -> List[str]:
        """
        Tokenize text into terms for BM25.

        Strategy:
        1. Identify segments (Chinese vs English/identifiers)
        2. Chinese segments: use jieba
        3. English identifiers: keep whole + split subwords
        4. Numbers and units: keep as-is
        """
        tokens = []

        # Regex patterns
        # Match English words (including identifiers with numbers, underscores)
        english_pattern = r'[a-zA-Z][a-zA-Z0-9_]*'
        # Match numbers with optional units
        number_pattern = r'\d+\.?\d*[a-zA-Z]*'
        # Match Chinese characters
        chinese_pattern = r'[\u4e00-\u9fff]+'

        # Combine patterns
        pattern = f'({english_pattern}|{number_pattern}|{chinese_pattern})'

        matches = re.finditer(pattern, text)

        for match in matches:
            segment = match.group(0)

            if self.contains_chinese(segment):
                # Chinese text: use jieba
                chinese_tokens = jieba.cut(segment)
                tokens.extend([t.lower() for t in chinese_tokens if t.strip()])

            elif re.match(number_pattern, segment):
                # Numbers and units: keep as-is (lowercase)
                tokens.append(segment.lower())

            elif re.match(english_pattern, segment):
                # English identifier
                identifier_tokens = self.tokenize_english_identifier(segment)
                tokens.extend(identifier_tokens)

        return tokens

    def tokenize_batch(self, texts: List[str]) -> List[List[str]]:
        """Tokenize a batch of texts."""
        return [self.tokenize(text) for text in texts]


class BM25Tokenizer:
    """
    Wrapper for CustomTokenizer compatible with rank_bm25.
    """

    def __init__(self):
        self.tokenizer = CustomTokenizer()

    def __call__(self, text: str) -> List[str]:
        """Make callable for BM25."""
        return self.tokenizer.tokenize(text)

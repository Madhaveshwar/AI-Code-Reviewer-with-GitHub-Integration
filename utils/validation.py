"""Input validation helpers for the code reviewer app."""

from __future__ import annotations

import re


KEYWORD_PATTERNS = [
    r"\bdef\b",
    r"\bclass\b",
    r"\bfunction\b",
    r"\bimport\b",
    r"\breturn\b",
    r"\bif\b",
    r"\bfor\b",
    r"\bwhile\b",
    r"print\s*\(",
    r"console\.log\s*\(",
    r"#include\b",
    r"\bpublic\s+class\b",
]


def is_valid_code(code: str) -> bool:
    """Return True when the input looks like source code.

    The check is intentionally heuristic: it rejects empty, short, numeric, and
    plain-language text while accepting common programming structures.
    """

    if not code:
        return False

    cleaned_code = code.strip()
    if len(cleaned_code) < 12:
        return False

    if cleaned_code.isdigit():
        return False

    alpha_count = sum(char.isalpha() for char in cleaned_code)
    if alpha_count == 0:
        return False

    # Reject obvious plain text when it has very few code indicators.
    structure_hits = 0
    if re.search(r"[{}()\[\];=<>:]", cleaned_code):
        structure_hits += 1
    if re.search(r"\b\w+\s*=\s*.+", cleaned_code):
        structure_hits += 1
    if re.search(r"^\s*#", cleaned_code, flags=re.MULTILINE):
        structure_hits += 1
    if re.search(r"^\s*//", cleaned_code, flags=re.MULTILINE):
        structure_hits += 1

    keyword_hits = sum(1 for pattern in KEYWORD_PATTERNS if re.search(pattern, cleaned_code, flags=re.IGNORECASE))

    line_count = len([line for line in cleaned_code.splitlines() if line.strip()])
    if line_count == 1 and keyword_hits == 0 and structure_hits == 0:
        return False

    if keyword_hits >= 1 and structure_hits >= 1:
        return True

    if structure_hits >= 2 and alpha_count >= 4:
        return True

    return False
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

    keyword_hits = sum(
        1
        for pattern in KEYWORD_PATTERNS
        if re.search(pattern, cleaned_code, flags=re.IGNORECASE)
    )

    line_count = len([line for line in cleaned_code.splitlines() if line.strip()])
    if line_count == 1 and keyword_hits == 0 and structure_hits == 0:
        return False

    if keyword_hits >= 1 and structure_hits >= 1:
        return True

    if structure_hits >= 2 and alpha_count >= 4:
        return True

    return False


def should_skip_file(path: str) -> bool:
    """Return True if the file should be skipped to minimize tokens and noise."""
    ignored_patterns = [
        "node_modules", "dist", "build", ".git", "coverage",
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml"
    ]
    path_lower = path.lower()
    
    # Check ignored directory or file patterns
    for p in ignored_patterns:
        if p in path_lower:
            return True

    import os
    basename = os.path.basename(path).lower()
    ext = os.path.splitext(path)[1].lower()

    # Skip minified files
    if ".min." in basename:
        return True

    # Skip generated files
    if (
        "generated" in basename or
        "webpack" in basename or
        basename.endswith(".map")
    ):
        return True

    # Skip binary files based on common extensions
    binary_extensions = {
        # Images
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff", ".svg",
        # Archives/Compressed
        ".zip", ".tar", ".gz", ".tgz", ".bz2", ".rar", ".7z", ".xz",
        # Executables/Binaries
        ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".lib", ".out",
        # Media (Video/Audio)
        ".mp4", ".mkv", ".avi", ".mov", ".flv", ".mp3", ".wav", ".flac", ".ogg",
        # Fonts
        ".ttf", ".otf", ".woff", ".woff2", ".eot",
        # Documents (non-source)
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        # Databases/Other Binary
        ".db", ".sqlite", ".dat", ".bin",
    }
    if ext in binary_extensions:
        return True

    return False


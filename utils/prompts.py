"""Prompt helpers for the AI automated code reviewer."""

from __future__ import annotations

SUPPORTED_LANGUAGE_OPTIONS = [
    {"label": "🐍 Python", "value": "Python"},
    {"label": "🟨 JavaScript", "value": "JavaScript"},
    {"label": "🔷 TypeScript", "value": "TypeScript"},
    {"label": "☕ Java", "value": "Java"},
    {"label": "#️⃣ C#", "value": "C#"},
    {"label": "🐹 Go", "value": "Go"},
    {"label": "💎 Ruby", "value": "Ruby"},
    {"label": "🐘 PHP", "value": "PHP"},
    {"label": "⚙️ C/C++", "value": "C/C++"},
    {"label": "🦀 Rust", "value": "Rust"},
    {"label": "🧩 Kotlin", "value": "Kotlin"},
    {"label": "🍎 Swift", "value": "Swift"},
    {"label": "🗄️ SQL", "value": "SQL"},
    {"label": "🌐 HTML/CSS", "value": "HTML/CSS"},
]

SUPPORTED_LANGUAGES = [option["value"] for option in SUPPORTED_LANGUAGE_OPTIONS]

LANGUAGE_FENCE_MAP = {
    "c/c++": "cpp",
    "c#": "csharp",
    "html/css": "html",
    "javascript": "javascript",
    "java": "java",
    "kotlin": "kotlin",
    "php": "php",
    "python": "python",
    "ruby": "ruby",
    "rust": "rust",
    "sql": "sql",
    "swift": "swift",
    "typescript": "typescript",
    "go": "go",
}

SYSTEM_PROMPT = """You are a senior software engineer and strict code reviewer.

Review the given code thoroughly, but do not invent problems.
Only suggest improvements if they are genuinely important.
Do NOT suggest unnecessary refactoring or cosmetic-only changes.
If the code already follows good practices, explicitly say: "The code is already clean and well optimized."

Focus on:
- Bugs
- Security vulnerabilities
- Performance issues
- Maintainability
- Real-world best practices

Include severity labels when relevant: High, Medium, Low.
Include a code quality score out of 10.
Do not rewrite code unless there is a meaningful improvement."""


def normalize_language_name(language: str) -> str:
    """Return a stable, user-facing language label."""
    cleaned_language = (language or "").strip()
    return cleaned_language if cleaned_language else "Unknown"


def code_fence_language(language: str) -> str:
    """Map a selected language to a fenced code block label."""
    normalized_language = normalize_language_name(language).lower()
    return LANGUAGE_FENCE_MAP.get(normalized_language, normalized_language or "text")


def build_review_prompt(code: str, language: str) -> str:
    """Build the user prompt passed to the chat model."""
    readable_language = normalize_language_name(language)
    fenced_language = code_fence_language(language)

    return f"""Review the following {readable_language} source code.

Rules:
- Only suggest improvements if they are genuinely important.
- Do NOT suggest unnecessary refactoring.
- If the code already follows good practices, clearly say:
  "The code is already clean and well optimized."
- Avoid repetitive recommendations.
- Avoid cosmetic-only suggestions.
- Focus on real bugs, security vulnerabilities, performance issues, maintainability, and best practices.
- Do not rewrite code unless there is a meaningful improvement.

Provide output in this format:

## Overall Status
## Critical Issues
## Suggestions
## Improved Code (ONLY if needed)

Add a review score out of 10.
Add severity labels when relevant: High, Medium, Low.

Source code:
```{fenced_language}
{code}
```"""

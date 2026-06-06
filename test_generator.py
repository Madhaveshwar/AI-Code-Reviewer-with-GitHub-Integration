"""Test case generator module using LLM to suggest unit, integration, and edge tests."""

from __future__ import annotations

import sys
import os
from typing import Any
from langsmith import traceable

# Ensure the parent directory is on the search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.prompts import SYSTEM_TEST_PROMPT, build_test_prompt
MODEL_NAME = "llama-3.3-70b-versatile"


@traceable(name="Test Suggestions Generation")
def generate_tests(
    client: Any,
    filename: str,
    code: str,
    language: str,
    model_name: str = MODEL_NAME,
    temperature: float = 0.3,
) -> str:
    """Generate Unit, Integration, Edge, and Negative test cases for a file using Groq."""
    if not code.strip():
        return "No code provided to generate tests."

    prompt = build_test_prompt(filename, code, language)

    active_model = "llama-3.3-70b-versatile"
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_TEST_PROMPT},
                {"role": "user", "content": prompt}
            ],
            model=active_model,
            temperature=temperature,
        )
        result_text = chat_completion.choices[0].message.content
    except Exception as e:
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_TEST_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.1-8b-instant",
                temperature=temperature,
            )
            result_text = chat_completion.choices[0].message.content
        except Exception as fallback_e:
            from reviewer import handle_groq_error
            raise handle_groq_error(fallback_e)

    return result_text or "Failed to generate test suggestions."

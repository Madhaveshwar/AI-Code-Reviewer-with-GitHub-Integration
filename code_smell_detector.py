"""Code smell detector module using LLM to spot refactoring candidates in changes."""

from __future__ import annotations

import json
import sys
import os
from typing import Any
from langsmith import traceable

# Ensure the parent directory is on the search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.prompts import SYSTEM_SMELL_PROMPT, build_smell_prompt
from security_scanner import parse_json_from_llm

MODEL_NAME = "llama-3.3-70b-versatile"


@traceable(name="Code Smell Detection")
def detect_code_smells(
    client: Any,
    filename: str,
    code: str,
    patch: str,
    language: str,
    model_name: str = MODEL_NAME,
    temperature: float = 0.2,
) -> list[dict[str, object]]:
    """Analyze code changes for code smells and maintainability violations using Groq."""
    prompt = build_smell_prompt(filename, code, patch, language)

    active_model = "llama-3.3-70b-versatile"
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_SMELL_PROMPT},
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
                    {"role": "system", "content": SYSTEM_SMELL_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.1-8b-instant",
                temperature=temperature,
            )
            result_text = chat_completion.choices[0].message.content
        except Exception as fallback_e:
            from reviewer import handle_groq_error
            raise handle_groq_error(fallback_e)

    findings = parse_json_from_llm(result_text)

    # Ensure findings match target schema
    validated_findings = []
    for item in findings:
        if isinstance(item, dict):
            validated_findings.append({
                "file": item.get("file", filename),
                "line": int(item.get("line", 1)) if str(item.get("line")).isdigit() else 1,
                "severity": item.get("severity", "Low"),
                "category": "Code Smell",
                "issue": item.get("issue", "Code quality smell detected"),
                "suggestion": item.get("suggestion", "Please refactor this code to clean it up."),
            })

    return validated_findings

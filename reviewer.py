"""Groq-backed code review helper."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from utils.prompts import SYSTEM_PROMPT, build_review_prompt

PROJECT_DOTENV = Path(__file__).resolve().with_name(".env")
load_dotenv(dotenv_path=PROJECT_DOTENV, override=False)

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


def review_code(code, language):
    """Analyze code and return a structured markdown review."""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_review_prompt(code, language)
            }
        ],
        temperature=0.3,
        max_tokens=1024
    )

    return response.choices[0].message.content

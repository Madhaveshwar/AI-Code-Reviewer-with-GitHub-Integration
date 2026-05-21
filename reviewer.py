"""Groq-backed code review helper."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq
import streamlit as st

from utils.prompts import SYSTEM_PROMPT, build_review_prompt

PROJECT_DOTENV = Path(__file__).resolve().with_name(".env")
load_dotenv(dotenv_path=PROJECT_DOTENV, override=False)

def _get_api_key() -> str | None:
    """Resolve the Groq API key from Streamlit secrets first, then local env."""
    try:
        api_key = st.secrets.get("GROQ_API_KEY")
        if api_key:
            return api_key
    except Exception:
        pass

    return os.getenv("GROQ_API_KEY")


def _build_client() -> Groq:
    """Create a Groq client after validating the API key."""
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not configured. Add it to Streamlit secrets or your local .env file."
        )

    return Groq(api_key=api_key)


def review_code(code, language):
    """Analyze code and return a structured markdown review."""
    client = _build_client()
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

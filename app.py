"""Streamlit entry point for the AI automated code reviewer."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import streamlit as st
import streamlit.components.v1 as components

from reviewer import review_code
from utils.prompts import SUPPORTED_LANGUAGE_OPTIONS, code_fence_language
from utils.validation import is_valid_code

st.set_page_config(
    page_title="AI Automated Code Reviewer",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    """Apply a lightweight custom theme for a cleaner experience."""
    st.markdown(
        """
        <style>
            :root {
                --page-bg: #0b1120;
                --page-surface: rgba(15, 23, 42, 0.92);
                --page-border: rgba(148, 163, 184, 0.18);
                --page-shadow: 0 18px 48px rgba(2, 6, 23, 0.45);
                --page-text: #e5e7eb;
                --page-muted: #94a3b8;
                --page-accent: #60a5fa;
                --page-accent-2: #14b8a6;
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(96, 165, 250, 0.14), transparent 26%),
                    radial-gradient(circle at top right, rgba(20, 184, 166, 0.10), transparent 24%),
                    linear-gradient(180deg, #111827 0%, var(--page-bg) 100%);
                color: var(--page-text);
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
                color: #e5e7eb;
                border-right: 1px solid rgba(255, 255, 255, 0.08);
            }

            [data-testid="stSidebar"] * {
                color: #e5e7eb !important;
            }

            .hero-card,
            .section-card {
                background: var(--page-surface);
                border: 1px solid var(--page-border);
                border-radius: 18px;
                box-shadow: var(--page-shadow);
                backdrop-filter: blur(14px);
            }

            .hero-card {
                padding: 1.25rem 1.25rem 0.75rem;
            }

            .section-card {
                padding: 1rem 1.1rem;
            }

            .app-subtitle {
                color: var(--page-muted);
                font-size: 1rem;
                line-height: 1.6;
            }

            .stButton > button {
                border-radius: 12px;
                border: 0;
                font-weight: 600;
                background: linear-gradient(135deg, var(--page-accent) 0%, var(--page-accent-2) 100%);
                color: white;
                padding: 0.7rem 1rem;
                box-shadow: 0 10px 24px rgba(37, 99, 235, 0.18);
            }

            .stButton > button:hover {
                opacity: 0.95;
                transform: translateY(-1px);
            }

            .stDownloadButton > button {
                border-radius: 12px;
                font-weight: 600;
                border: 1px solid rgba(96, 165, 250, 0.24);
                color: #e5e7eb;
                background: rgba(30, 41, 59, 0.92);
            }

            .stTextArea textarea {
                border-radius: 16px;
                font-family: "Segoe UI", "SFMono-Regular", Consolas, monospace;
                background: #0f172a;
                color: #f8fafc;
                border: 1px solid rgba(148, 163, 184, 0.22);
                padding: 1rem;
                line-height: 1.6;
                font-size: 0.98rem;
                box-shadow: inset 0 1px 2px rgba(2, 6, 23, 0.35);
            }

            .stTextArea textarea:focus {
                border-color: rgba(96, 165, 250, 0.75);
                box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.12);
            }

            .stTextArea label,
            .stSelectbox label {
                font-weight: 600;
                color: var(--page-text);
            }

            .stInfo,
            .stSuccess,
            .stError,
            .stWarning {
                border-radius: 14px;
            }

            [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
                background: rgba(15, 23, 42, 0.96);
                color: #f8fafc;
                border: 1px solid rgba(148, 163, 184, 0.22);
            }

            [data-testid="stSelectbox"] svg {
                fill: #cbd5e1;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialize_state() -> None:
    """Create default session state values once."""
    defaults = {
        "selected_language_label": "🐍 Python",
        "source_code": "",
        "latest_review": "",
        "review_history": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def clear_state() -> None:
    """Reset the app state and restart the Streamlit script."""
    st.session_state.selected_language_label = "🐍 Python"
    st.session_state.source_code = ""
    st.session_state.latest_review = ""
    st.session_state.review_history = []
    st.rerun()


def render_copy_button(text: str, label: str = "Copy review to clipboard") -> None:
    """Render a browser-based copy button for the generated report."""
    status_id = "copy-status"
    text_literal = json.dumps(text)
    html = f"""
    <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">
        <button
            type="button"
            onclick='navigator.clipboard.writeText({text_literal}).then(() => {{
                const status = document.getElementById("{status_id}");
                if (status) status.textContent = "Copied to clipboard.";
            }}).catch(() => {{
                const status = document.getElementById("{status_id}");
                if (status) status.textContent = "Copy failed.";
            }})'
            style="
                border:none;
                border-radius:10px;
                background:#0f172a;
                color:#ffffff;
                padding:0.6rem 0.9rem;
                font-weight:600;
                cursor:pointer;
            "
        >{label}</button>
        <span id="{status_id}" style="color:#475569;font-size:0.9rem;"></span>
    </div>
    """
    components.html(html, height=55)


inject_styles()
initialize_state()

st.title("AI Automated Code Reviewer")
st.markdown(
    '<div class="app-subtitle">Paste source code, choose a language, and receive a clear AI review covering bugs, security, performance, quality, and best practices.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Controls")
    st.caption("Use the app to review code snippets before merging or deploying.")
    if st.button("Clear", use_container_width=True):
        clear_state()

    st.subheader("Supported Languages")
    for option in SUPPORTED_LANGUAGE_OPTIONS:
        st.write(f"{option['label']}  {option['value']}")

    st.subheader("About")
    st.write(
        "This app uses Streamlit and the Groq API to generate structured code reviews with actionable feedback, severity guidance, and improved code suggestions."
    )

with st.container(border=False):
    st.markdown('<div class="hero-card">', unsafe_allow_html=True)
    language_labels = [option["label"] for option in SUPPORTED_LANGUAGE_OPTIONS]
    default_label = st.session_state.selected_language_label
    selected_language_label = st.selectbox(
        "Programming Language",
        options=language_labels,
        index=language_labels.index(default_label),
        key="selected_language_label",
    )
    selected_language = next(
        option["value"] for option in SUPPORTED_LANGUAGE_OPTIONS if option["label"] == selected_language_label
    )
    source_code = st.text_area(
        "Source Code",
        height=440,
        placeholder="Paste the code you want reviewed here. Longer snippets are fine.",
        key="source_code",
        help="Tip: include enough surrounding code so the reviewer can judge context, bugs, and security issues accurately.",
    )

    preview_language = code_fence_language(selected_language)
    if source_code.strip():
        with st.expander("Code Preview", expanded=False):
            st.code(source_code, language=preview_language)

    review_requested = st.button("Review Code", use_container_width=True, type="primary")
    st.markdown("</div>", unsafe_allow_html=True)

if review_requested:
    if not source_code.strip():
        st.error("Please paste some source code before requesting a review.")
    elif not is_valid_code(source_code):
        st.error("Please enter valid source code.")
    else:
        with st.spinner("Analyzing code and generating the review..."):
            try:
                review_markdown = review_code(source_code, selected_language)
            except Exception as exc:
                st.error(f"Review generation failed: {exc}")
            else:
                st.session_state.latest_review = review_markdown
                st.session_state.review_history.insert(
                    0,
                    {
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                        "language": selected_language,
                        "review": review_markdown,
                    },
                )
                st.session_state.review_history = st.session_state.review_history[:10]
                st.success("Review generated successfully.")

if st.session_state.latest_review:
    st.subheader("Review Results")
    review_text = st.session_state.latest_review
    if "already clean and well optimized" in review_text.lower():
        st.success("✅ Code quality is already good. No major improvements needed.")

    st.markdown(review_text)
    render_copy_button(st.session_state.latest_review)
    st.download_button(
        label="Download review report",
        data=st.session_state.latest_review,
        file_name="code_review.md",
        mime="text/markdown",
        use_container_width=True,
    )
else:
    st.info("Your AI-generated review will appear here after you click Review Code.")

with st.expander("Review History", expanded=False):
    if st.session_state.review_history:
        for item in st.session_state.review_history:
            st.markdown(f"**{item['timestamp']}** | {item['language']}")
            st.markdown(item["review"])
            st.divider()
    else:
        st.write("No reviews yet.")

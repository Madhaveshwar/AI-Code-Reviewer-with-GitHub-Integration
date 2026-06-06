"""Streamlit entry point for the AI Automated Code Reviewer with GitHub Integration."""

from __future__ import annotations

import os
import sys
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

import streamlit as st
import streamlit.components.v1 as components

# Ensure the parent directory is on the search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from reviewer import (
    build_groq_client,
    review_pull_request,
    review_single_code_snippet,
    review_entire_repository,
    GroqAPIError,
)
from github_service import GitHubService, parse_repo_url
from repository_analyzer import analyze_repository
from report_generator import (
    generate_markdown_report,
    generate_json_report,
    generate_pdf_report,
)
from utils.prompts import SUPPORTED_LANGUAGE_OPTIONS

# Set page config
st.set_page_config(
    page_title="AI Automated Code Reviewer",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    """Apply a premium dark GitHub-inspired theme with modern details."""
    st.markdown(
        """
        <style>
            :root {
                --page-bg: #0d1117;
                --page-surface: #161b22;
                --page-border: #30363d;
                --page-text: #c9d1d9;
                --page-muted: #8b949e;
                --page-accent: #1f6feb;
                --page-accent-2: #238636;
                --page-danger: #da3633;
                --page-warning: #d29922;
            }

            .stApp {
                background-color: var(--page-bg);
                color: var(--page-text);
            }

            [data-testid="stSidebar"] {
                background-color: #0d1117;
                border-right: 1px solid var(--page-border);
            }

            [data-testid="stSidebar"] * {
                color: var(--page-text) !important;
            }

            /* Custom GitHub-style UI Cards */
            .gh-card {
                background: var(--page-surface);
                border: 1px solid var(--page-border);
                border-radius: 6px;
                padding: 1.25rem;
                margin-bottom: 1.2rem;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            }

            .gh-card-header {
                font-size: 1.1rem;
                font-weight: 600;
                color: #58a6ff;
                border-bottom: 1px solid var(--page-border);
                padding-bottom: 0.5rem;
                margin-bottom: 0.8rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }

            .metric-value {
                font-size: 1.8rem;
                font-weight: 600;
                color: #ffffff;
                margin-bottom: 0.2rem;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .metric-label {
                font-size: 0.8rem;
                color: var(--page-muted);
                text-transform: uppercase;
                letter-spacing: 0.03em;
            }

            .stButton > button {
                border-radius: 6px;
                border: 1px solid rgba(240, 246, 252, 0.1);
                font-weight: 600;
                background-color: var(--page-accent-2);
                color: white;
                padding: 0.5rem 1.2rem;
                transition: background-color 0.2s ease;
            }

            .stButton > button:hover {
                background-color: #2ea043;
                border-color: rgba(240, 246, 252, 0.2);
            }

            /* Primary Button override */
            div[data-testid="stButton"] button[kind="primary"] {
                background-color: var(--page-accent);
            }
            
            div[data-testid="stButton"] button[kind="primary"]:hover {
                background-color: #388bfd;
            }

            .stDownloadButton > button {
                border-radius: 6px;
                font-weight: 600;
                border: 1px solid var(--page-border);
                color: #c9d1d9;
                background-color: #21262d;
            }

            .stDownloadButton > button:hover {
                background-color: #30363d;
                border-color: #8b949e;
            }

            .stTextArea textarea {
                border-radius: 6px;
                font-family: "SFMono-Regular", Consolas, Menlo, monospace;
                background-color: #0d1117;
                color: #c9d1d9;
                border: 1px solid var(--page-border);
                padding: 0.8rem;
                line-height: 1.6;
            }

            .stTextArea textarea:focus {
                border-color: #58a6ff;
                box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15);
            }

            .finding-row {
                padding: 0.8rem;
                border-radius: 6px;
                margin-bottom: 0.5rem;
                border-left: 4px solid #8b949e;
                background: #161b22;
                border-top: 1px solid var(--page-border);
                border-right: 1px solid var(--page-border);
                border-bottom: 1px solid var(--page-border);
            }
            .severity-Critical { border-left-color: var(--page-danger); }
            .severity-High { border-left-color: var(--page-danger); }
            .severity-Medium { border-left-color: var(--page-warning); }
            .severity-Low { border-left-color: var(--page-accent); }
            .severity-Info { border-left-color: var(--page-muted); }
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialize_state() -> None:
    """Initialize session state parameters."""
    defaults = {
        "repo_url": "",
        "repo_details": None,
        "open_prs": [],
        "selected_pr": None,
        "pr_files": [],
        "review_results": None,
        "repo_analysis": None,
        "review_type": "Pull Request Review",
        # Snippet review state
        "pasted_code": "",
        "pasted_lang": "Python",
        "pasted_review": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def clear_pr_state() -> None:
    """Reset loaded PR information."""
    st.session_state.repo_details = None
    st.session_state.open_prs = []
    st.session_state.selected_pr = None
    st.session_state.pr_files = []
    st.session_state.review_results = None
    st.session_state.repo_analysis = None


# Load Styles and State
inject_styles()
initialize_state()

# Fetch Credentials strictly from Environment (normalise mixed-case)
if not os.getenv("GROQ_API_KEY") and os.getenv("Groq_api_key"):
    os.environ["GROQ_API_KEY"] = os.environ["Groq_api_key"]

github_token = os.getenv("GITHUB_TOKEN", "").strip()
groq_api_key = os.getenv("GROQ_API_KEY", "").strip()

# Sidebar Configuration
with st.sidebar:
    st.image(
        "https://img.icons8.com/external-flatart-icons-flat-flatarticons/128/external-security-cyber-security-flatart-icons-flat-flatarticons.png",
        width=50,
    )
    st.markdown("<h3 style='margin:0.2rem 0;'>AI Code Reviewer</h3>", unsafe_allow_html=True)
    st.caption("Automated Code & PR Review Assistant")

    st.divider()

    # 1. Mode Selection
    mode = st.radio(
        "Operation Mode",
        options=["GitHub PR Review", "Paste Code Snippet"],
        index=0,
    )

    # 2. Render Repository Info in Sidebar
    if mode == "GitHub PR Review" and st.session_state.repo_details:
        st.divider()
        details = st.session_state.repo_details
        st.markdown("#### 📁 Repository Information")
        st.markdown(f"**Slug:** `{details['name']}`")
        st.markdown(f"**Branch:** `{details['default_branch']}`")
        st.markdown(f"*{details['description']}*")

        st.markdown(
            f"""
            <div style="background-color:#161b22; border: 1px solid #30363d; border-radius:6px; padding:10px; margin-top:8px; font-size:0.9rem;">
                <span style="color:#58a6ff; font-weight:600;">⭐ Stars:</span> {details['stars']}<br>
                <span style="color:#58a6ff; font-weight:600;">🍴 Forks:</span> {details['forks']}<br>
                <span style="color:#58a6ff; font-weight:600;">🐛 Issues:</span> {details.get('open_issues_count', 0)}<br>
                <span style="color:#58a6ff; font-weight:600;">📂 Open PRs:</span> {details['open_prs_count']}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 3. Render Review Statistics in Sidebar
    if mode == "GitHub PR Review" and st.session_state.review_results:
        st.divider()
        results = st.session_state.review_results
        sev_counts = results["severity_counts"]
        risk_score = results["risk_score"]

        st.markdown("#### 📊 Review Statistics")
        st.markdown(f"**Type:** `{st.session_state.review_type}`")
        if results.get("pr_number"):
            st.markdown(f"**PR Number:** `#{results['pr_number']}`")

        risk_color = (
            "#da3633"
            if risk_score > 60
            else ("#d29922" if risk_score > 30 else "#238636")
        )

        st.markdown(
            f"""
            <div style="background-color:#161b22; border: 1px solid #30363d; border-radius:6px; padding:10px; font-size:0.9rem;">
                <div style="font-size:0.8rem; color:#8b949e; text-transform:uppercase;">Overall Risk</div>
                <div style="font-size:1.8rem; font-weight:700; color:{risk_color}; margin-bottom:8px;">{risk_score}/100</div>
                <div style="font-size:0.8rem; color:#8b949e; text-transform:uppercase;">Findings Breakdown</div>
                <span style="color:#da3633; font-weight:600;">Crit: {sev_counts['Critical']}</span><br>
                <span style="color:#f77e7e; font-weight:600;">High: {sev_counts['High']}</span><br>
                <span style="color:#d29922; font-weight:600;">Med: {sev_counts['Medium']}</span><br>
                <span style="color:#58a6ff; font-weight:600;">Low: {sev_counts['Low']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    elif mode == "Paste Code Snippet" and st.session_state.pasted_review:
        st.divider()
        res = st.session_state.pasted_review
        sev_counts = res["severity_counts"]
        risk_score = res["risk_score"]

        st.markdown("#### 📊 Snippet Review Stats")

        risk_color = (
            "#da3633"
            if risk_score > 60
            else ("#d29922" if risk_score > 30 else "#238636")
        )

        st.markdown(
            f"""
            <div style="background-color:#161b22; border: 1px solid #30363d; border-radius:6px; padding:10px; font-size:0.9rem;">
                <div style="font-size:0.8rem; color:#8b949e; text-transform:uppercase;">Overall Risk</div>
                <div style="font-size:1.8rem; font-weight:700; color:{risk_color}; margin-bottom:8px;">{risk_score}/100</div>
                <div style="font-size:0.8rem; color:#8b949e; text-transform:uppercase;">Findings Breakdown</div>
                <span style="color:#da3633; font-weight:600;">Crit: {sev_counts['Critical']}</span><br>
                <span style="color:#f77e7e; font-weight:600;">High: {sev_counts['High']}</span><br>
                <span style="color:#d29922; font-weight:600;">Med: {sev_counts['Medium']}</span><br>
                <span style="color:#58a6ff; font-weight:600;">Low: {sev_counts['Low']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()
    if st.button("Reset Dashboard", use_container_width=True):
        st.session_state.clear()
        initialize_state()
        st.rerun()

# Environment Checks
if not groq_api_key:
    st.error("🛑 `GROQ_API_KEY` is missing in your `.env` file. Please configure a valid key to run reviews.")
    st.stop()

if not github_token:
    st.warning("⚠️ `GITHUB_TOKEN` is not configured in your `.env` file. Access will be restricted to public repositories and subject to lower GitHub API rate limits.")

# ----------------- MODE: GITHUB PR REVIEW -----------------
if mode == "GitHub PR Review":
    st.markdown("### 🔌 Connect to GitHub Repository")

    col1, col2 = st.columns([5.5, 1.5])
    with col1:
        repo_url = st.text_input(
            "Repository URL or Slug",
            value=st.session_state.repo_url,
            placeholder="https://github.com/owner/repository",
            label_visibility="collapsed",
        )
        st.session_state.repo_url = repo_url
    with col2:
        connect_btn = st.button("Connect Repo", use_container_width=True, type="primary")

    if connect_btn:
        if not repo_url.strip():
            st.error("Please enter a GitHub repository URL or slug.")
        else:
            repo_name = parse_repo_url(repo_url)
            if not repo_name:
                st.error("Invalid GitHub Repository slug. Use owner/repo or standard GitHub URL.")
            else:
                with st.spinner("Retrieving repository details..."):
                    try:
                        svc = GitHubService(github_token if github_token else None)
                        details = svc.get_repo_details(repo_name)
                        
                        if details.get("is_empty"):
                            st.error("The connected repository is empty (no commits or default branch found).")
                            clear_pr_state()
                        else:
                            st.session_state.repo_details = details

                            prs = svc.get_open_pull_requests(repo_name)
                            st.session_state.open_prs = prs

                            st.success(f"Connected to **{details['name']}**")
                            st.session_state.review_results = None
                            st.session_state.repo_analysis = None
                            
                            # Smart Review Flow Selection
                            if details.get("open_prs_count", 0) > 0:
                                st.session_state.review_type = "Pull Request Review"
                            else:
                                st.session_state.review_type = "Repository Analysis"
                    except Exception as exc:
                        st.error(f"Failed to load repository: {exc}")
                        clear_pr_state()

    # If repo details are available, render dashboard and mode selections
    if st.session_state.repo_details:
        details = st.session_state.repo_details
        repo_name = details["name"]
        
        if details.get("archived"):
            st.warning("⚠️ This GitHub repository is archived (read-only mode).")

        st.divider()

        # ----------------- REPOSITORY DASHBOARD -----------------
        st.markdown("### 📊 Repository Dashboard")
        d_col1, d_col2, d_col3, d_col4 = st.columns(4)
        with d_col1:
            st.markdown(
                f"""
                <div class="gh-card" style="text-align:center;">
                    <div class="metric-value">{details["stars"]}</div>
                    <div class="metric-label">⭐ Stars</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with d_col2:
            st.markdown(
                f"""
                <div class="gh-card" style="text-align:center;">
                    <div class="metric-value">{details["forks"]}</div>
                    <div class="metric-label">🍴 Forks</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with d_col3:
            st.markdown(
                f"""
                <div class="gh-card" style="text-align:center;">
                    <div class="metric-value">{details["open_prs_count"]}</div>
                    <div class="metric-label">📂 Open PRs</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with d_col4:
            st.markdown(
                f"""
                <div class="gh-card" style="text-align:center;">
                    <div class="metric-value">{details.get("open_issues_count", 0)}</div>
                    <div class="metric-label">🐛 Open Issues</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        d_col5, d_col6, d_col7, d_col8 = st.columns(4)
        with d_col5:
            primary_lang = (
                list(details["languages"].keys())[0]
                if details["languages"]
                else "N/A"
            )
            st.markdown(
                f"""
                <div class="gh-card" style="text-align:center;">
                    <div class="metric-value" style="font-size:1.5rem; line-height:2.2rem;">{primary_lang}</div>
                    <div class="metric-label">💻 Main Language</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with d_col6:
            files_count = "N/A"
            if st.session_state.review_results:
                files_count = st.session_state.review_results.get("total_files_analyzed", "N/A")
            st.markdown(
                f"""
                <div class="gh-card" style="text-align:center;">
                    <div class="metric-value">{files_count}</div>
                    <div class="metric-label">🔍 Files Checked</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with d_col7:
            h_score_val = "N/A"
            h_color = "#30363d"
            if st.session_state.repo_analysis:
                h_score_val = f"{st.session_state.repo_analysis['health_score']}/100"
                h_score = st.session_state.repo_analysis["health_score"]
                h_color = "#238636" if h_score > 75 else ("#d29922" if h_score > 40 else "#da3633")
            elif st.session_state.review_results and st.session_state.review_results.get("repo_analysis"):
                repo_an = st.session_state.review_results["repo_analysis"]
                h_score_val = f"{repo_an['health_score']}/100"
                h_score = repo_an["health_score"]
                h_color = "#238636" if h_score > 75 else ("#d29922" if h_score > 40 else "#da3633")

            st.markdown(
                f"""
                <div class="gh-card" style="text-align:center; border-bottom: 3px solid {h_color};">
                    <div class="metric-value" style="color:{h_color};">{h_score_val}</div>
                    <div class="metric-label">🛡️ Health Score</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with d_col8:
            r_score_val = "N/A"
            r_color = "#30363d"
            if st.session_state.review_results:
                r_score_val = f"{st.session_state.review_results['risk_score']}/100"
                r_score = st.session_state.review_results["risk_score"]
                r_color = "#da3633" if r_score > 60 else ("#d29922" if r_score > 30 else "#238636")
            st.markdown(
                f"""
                <div class="gh-card" style="text-align:center; border-bottom: 3px solid {r_color};">
                    <div class="metric-value" style="color:{r_color};">{r_score_val}</div>
                    <div class="metric-label">📊 Risk Score</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.divider()

        # ----------------- REVIEW TYPE SELECTION & FALLBACK -----------------
        st.markdown("### 🔍 Select Analysis Mode")

        # Determine Review Types options
        if details["open_prs_count"] == 0:
            st.info("ℹ️ No open pull requests found in this repository. Defaulting to Repository Analysis Mode.")
            review_type_options = ["Repository Analysis"]
            default_type_idx = 0
        else:
            review_type_options = ["Pull Request Review", "Repository Analysis"]
            # Try to restore previous selection
            try:
                default_type_idx = review_type_options.index(st.session_state.review_type)
            except ValueError:
                default_type_idx = 0

        selected_review_type = st.radio(
            "Review Type",
            options=review_type_options,
            index=default_type_idx,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state.review_type = selected_review_type

        # ----------------- FLOW: PULL REQUEST REVIEW MODE -----------------
        if selected_review_type == "Pull Request Review":
            pr_options = [
                f"#{pr['number']} - {pr['title']} (by @{pr['author']})"
                for pr in st.session_state.open_prs
            ]
            selected_option = st.selectbox("Choose open Pull Request", options=pr_options)

            if selected_option:
                pr_num = int(selected_option.split(" - ")[0].replace("#", ""))

                # Fetch details if selected PR changes
                if (
                    not st.session_state.selected_pr
                    or st.session_state.selected_pr.get("number") != pr_num
                ):
                    with st.spinner("Downloading pull request metadata..."):
                        try:
                            svc = GitHubService(github_token if github_token else None)
                            pr_info = svc.get_pr_details(repo_name, pr_num)
                            pr_files = svc.get_pr_files(repo_name, pr_num)

                            st.session_state.selected_pr = pr_info
                            st.session_state.pr_files = pr_files
                            st.session_state.review_results = None
                            st.session_state.repo_analysis = None
                        except Exception as e:
                            st.error(f"Failed to fetch PR details: {e}")

            if st.session_state.selected_pr:
                pr = st.session_state.selected_pr
                files_changed = st.session_state.pr_files

                # Show selected PR Metadata Card
                st.markdown(
                    f"""
                    <div class="gh-card">
                        <div class="gh-card-header">
                            <img src="https://img.icons8.com/octicons/32/58a6ff/git-pull-request.png" width="16" style="margin-top:-2px;"/>
                            <span>PR #{pr['number']}: {pr['title']}</span>
                        </div>
                        <table style="width:100%; font-size:0.9rem; border-collapse:collapse;">
                            <tr>
                                <td style="color:var(--page-muted); padding:3px 0; width:150px;">Author:</td>
                                <td style="font-weight:600; padding:3px 0;">@{pr['author']}</td>
                            </tr>
                            <tr>
                                <td style="color:var(--page-muted); padding:3px 0;">Created Date:</td>
                                <td style="font-weight:600; padding:3px 0;">{pr.get('created_at', 'N/A')}</td>
                            </tr>
                            <tr>
                                <td style="color:var(--page-muted); padding:3px 0;">Files Modified:</td>
                                <td style="font-weight:600; padding:3px 0;">{pr['files_changed_count']} files</td>
                            </tr>
                            <tr>
                                <td style="color:var(--page-muted); padding:3px 0;">Line Changes:</td>
                                <td style="font-weight:600; padding:3px 0;"><span style="color:#2ea043;">+{pr['additions']}</span> / <span style="color:#da3633;">-{pr['deletions']}</span></td>
                            </tr>
                        </table>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.expander("📝 Changed Files List"):
                    for fc in files_changed:
                        st.markdown(f"- `{fc['filename']}` *(+{fc['additions']} / -{fc['deletions']})*")

                api_ready = bool(groq_api_key)
                review_btn = st.button(
                    "🔍 Run AI Pull Request Code Review",
                    disabled=not api_ready,
                    type="primary",
                    use_container_width=True,
                )

                if review_btn:
                    with st.spinner("Scanning modified lines for security vulnerabilities, bugs, and smells..."):
                        try:
                            svc = GitHubService(github_token if github_token else None)
                            groq_client = build_groq_client(groq_api_key)

                            results = review_pull_request(
                                repo_name=repo_name,
                                pr_number=pr["number"],
                                github_service=svc,
                                client=groq_client,
                            )
                            st.session_state.review_results = results
                            st.success("Review generated!")
                        except GroqAPIError as e:
                            st.error(f"🛑 {str(e)}")
                        except Exception as e:
                            st.error(f"❌ Review pipeline failed: {e}")

        # ----------------- FLOW: REPOSITORY ANALYSIS MODE -----------------
        else:
            st.markdown(
                """
                <div class="gh-card">
                    <div class="gh-card-header">
                        <img src="https://img.icons8.com/octicons/32/58a6ff/repo.png" width="16" style="margin-top:-2px;"/>
                        <span>Full Repository Analysis</span>
                    </div>
                    <div style="font-size:0.9rem; line-height:1.5; color:var(--page-muted);">
                        Auditing code quality directly on repository branch. The analyzer will recursively parse files, 
                        perform security audits on top source codes, look for code smells, generate QA test suggestions, 
                        and score overall repository health.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            api_ready = bool(groq_api_key)
            repo_review_btn = st.button(
                "🔍 Run AI Repository Analysis",
                disabled=not api_ready,
                type="primary",
                use_container_width=True,
            )

            if repo_review_btn:
                with st.spinner("Analyzing repository files recursively..."):
                    try:
                        svc = GitHubService(github_token if github_token else None)
                        groq_client = build_groq_client(groq_api_key)

                        results = review_entire_repository(
                            repo_name=repo_name,
                            github_service=svc,
                            client=groq_client,
                        )
                        st.session_state.review_results = results
                        st.session_state.repo_analysis = results["repo_analysis"]
                        st.success("Repository analysis finished successfully!")
                    except GroqAPIError as e:
                        st.error(f"🛑 {str(e)}")
                    except Exception as e:
                        st.error(f"❌ Repository analysis failed: {e}")

        # ----------------- RENDER TABS FOR CODE REVIEW RESULTS -----------------
        if st.session_state.review_results:
            results = st.session_state.review_results
            findings = results["findings"]
            risk_score = results["risk_score"]
            tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
                [
                    "📊 Summary Dashboard",
                    "🛡️ Security Findings",
                    "🔍 Code Smells",
                    "🧪 Test Suggestions",
                    "📁 Repository Insights",
                    "💬 Inline Comments",
                    "💾 Export & Actions",
                ]
            )

            # Tab 1: Summary Dashboard
            with tab1:
                # Review Completion Status
                completion_time = results.get("timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
                st.success(f"✅ AI Code Review completed successfully at {completion_time}!")

                # Count categories
                sec_count = len([f for f in findings if f.get("category") == "Security"])
                smell_count = len([f for f in findings if f.get("category") == "Code Smell"])
                
                # Count tests
                test_count = 0
                if results.get("test_suggestions"):
                    test_count = len(results["test_suggestions"].split("### File:")) - 1
                    if test_count < 0:
                        test_count = 0

                # Health score resolving
                h_val = "N/A"
                if st.session_state.repo_analysis:
                    h_val = f"{st.session_state.repo_analysis['health_score']}/100"
                elif results.get("repo_analysis"):
                    h_val = f"{results['repo_analysis']['health_score']}/100"

                # 1. Top-level summary cards
                st.markdown("### Executive Summary Metrics")
                tc1, tc2, tc3 = st.columns(3)
                with tc1:
                    st.metric("Files Analyzed", len(results.get("files_analyzed_log", [])))
                with tc2:
                    st.metric("Security Issues", sec_count)
                with tc3:
                    st.metric("Code Smells", smell_count)

                tc4, tc5, tc6 = st.columns(3)
                with tc4:
                    st.metric("Tests Suggested", test_count)
                with tc5:
                    st.metric("Repository Health Score", h_val)
                with tc6:
                    st.metric("Risk Score", f"{risk_score}/100")

                if results.get("scores"):
                    st.markdown("#### 🎯 Platform Quality Scores")
                    sqc1, sqc2, sqc3, sqc4, sqc5 = st.columns(5)
                    scores = results["scores"]
                    sqc1.metric("Code Quality", f"{scores.get('code_quality', 0)}/100")
                    sqc2.metric("Security", f"{scores.get('security', 0)}/100")
                    sqc3.metric("Maintainability", f"{scores.get('maintainability', 0)}/100")
                    sqc4.metric("Performance", f"{scores.get('performance', 0)}/100")
                    sqc5.metric("Technical Debt", f"{scores.get('technical_debt', 0)}/100")

                # 2. Files Analyzed Sub-dashboard
                st.markdown("### Files Analyzed Details")
                files_log = results.get("files_analyzed_log", [])
                total_scanned = len(files_log)
                analyzed_count = len([f for f in files_log if f.get("status") == "Analyzed"])
                scanned_count = len([f for f in files_log if f.get("status") == "Scanned"])
                skipped_count = len([f for f in files_log if f.get("status") == "Skipped"])
                
                coverage_pct = 0.0
                if total_scanned > 0:
                    coverage_pct = round((analyzed_count / total_scanned) * 100, 1)

                fc1, fc2, fc3, fc4 = st.columns(4)
                fc1.metric("Total Files Scanned", total_scanned)
                fc2.metric("Source Files Analyzed", analyzed_count)
                fc3.metric("Files Skipped", skipped_count)
                fc4.metric("Analysis Coverage %", f"{coverage_pct}%")

                st.markdown("#### 🪙 Groq Token & Characters Scan Metrics")
                t_col1, t_col2, t_col3, t_col4, t_col5 = st.columns(5)
                files_analyzed_count = results.get("files_analyzed_count", 0)
                characters_analyzed_count = results.get("characters_analyzed_count", 0)
                estimated_tokens_count = results.get("estimated_tokens_count", 0)
                groq_requests_made = results.get("groq_requests_made", 0)
                cached_results_used = results.get("cached_results_used", 0)
                t_col1.metric("Files Analyzed", files_analyzed_count)
                t_col2.metric("Characters Sent", f"{characters_analyzed_count:,}")
                t_col3.metric("Estimated Tokens", f"{estimated_tokens_count:,}")
                t_col4.metric("Groq Requests Made", groq_requests_made)
                t_col5.metric("Cache Hits", cached_results_used)

                if files_log:
                    st.dataframe(files_log, use_container_width=True)

                # 3. Findings Grouped By File
                st.markdown("### Findings Grouped By File")
                if not findings:
                    st.success("✅ Code is clean! No findings to group.")
                else:
                    by_file = {}
                    for f in findings:
                        by_file.setdefault(f.get("file"), []).append(f)
                    
                    for fidx, (fname, file_findings) in enumerate(by_file.items()):
                        with st.expander(f"📄 {fname} ({len(file_findings)} findings)", key=f"findings_grouped_{fname}*{fidx}"):
                            file_sec = [f for f in file_findings if f.get("category") == "Security"]
                            file_smell = [f for f in file_findings if f.get("category") == "Code Smell"]
                            file_other = [f for f in file_findings if f.get("category") not in ["Security", "Code Smell"]]
                            
                            if file_sec:
                                st.markdown("##### 🛡️ Security Findings")
                                for sf in file_sec:
                                    st.markdown(f"- **Line {sf['line']}**: {sf['issue']}")
                                    st.markdown(f"  *Recommendation:* {sf['suggestion']}")
                            
                            if file_smell:
                                st.markdown("##### 🔍 Code Smells")
                                for s in file_smell:
                                    st.markdown(f"- **Line {s['line']}**: {s['issue']}")
                                    st.markdown(f"  *Recommendation:* {s['suggestion']}")
                                    
                            if file_other:
                                st.markdown("##### ⚙️ General Findings")
                                for o in file_other:
                                    st.markdown(f"- **Line {o['line']}**: {o['issue']}")
                                    st.markdown(f"  *Recommendation:* {o['suggestion']}")

                # 4. Severity Chart
                if len(findings) > 0:
                    st.markdown("#### Severity Distribution Chart")
                    chart_data = {
                        "Severity": list(results["severity_counts"].keys()),
                        "Count": list(results["severity_counts"].values()),
                    }
                    st.bar_chart(data=chart_data, x="Severity", y="Count", color="#1f6feb")

            # Tab 2: Security Findings Panel
            with tab2:
                st.markdown("### 🛡️ Security Vulnerability Audit")
                sec_finds = [f for f in findings if f.get("category") == "Security"]
                
                # Severity breakdown counts
                sec_sevs = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Info": 0}
                for f in sec_finds:
                    sev = f.get("severity", "Info")
                    if sev in sec_sevs:
                        sec_sevs[sev] += 1
                        
                sc1, sc2, sc3, sc4 = st.columns(4)
                sc1.metric("Critical Issues", sec_sevs["Critical"])
                st.markdown(
                    f"""
                    <style>
                    [data-testid="stMetricValue"] {{
                        font-size: 2rem;
                    }}
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                sc2.metric("High Issues", sec_sevs["High"])
                sc3.metric("Medium Issues", sec_sevs["Medium"])
                sc4.metric("Low Issues", sec_sevs["Low"])

                st.divider()

                if not sec_finds:
                    st.success("✅ No security vulnerabilities detected.")
                else:
                    for sf in sec_finds:
                        st.markdown(
                            f"""
                            <div style="background-color:#161b22; border: 1px solid #da3633; border-radius:6px; padding:12px; margin-bottom:10px; font-size:0.92rem;">
                                <strong>File:</strong> {sf['file']}<br>
                                <strong>Line:</strong> {sf['line']}<br>
                                <strong>Issue:</strong> {sf['issue']}<br>
                                <strong>Severity:</strong> <span style="color:#da3633; font-weight:700;">{sf['severity']}</span><br>
                                <strong>Risk Level:</strong> {sf.get('risk_level', sf['severity'])}<br>
                                <strong>Why it matters:</strong> {sf.get('why_it_matters', 'See suggestion details.')}<br>
                                <strong>Recommendation:</strong> {sf['suggestion']}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        before_code = sf.get("before_code")
                        after_code = sf.get("after_code")
                        if before_code or after_code:
                            from utils.prompts import code_fence_language
                            ext = os.path.splitext(sf['file'])[1].lower()
                            ext_map = {
                                ".py": "Python",
                                ".js": "JavaScript",
                                ".jsx": "JavaScript",
                                ".ts": "TypeScript",
                                ".tsx": "TypeScript",
                                ".java": "Java",
                                ".cs": "C#",
                                ".go": "Go",
                                ".rb": "Ruby",
                                ".php": "PHP",
                                ".cpp": "C/C++",
                                ".c": "C/C++",
                                ".h": "C/C++",
                                ".rs": "Rust",
                                ".kt": "Kotlin",
                                ".swift": "Swift",
                            }
                            sf_lang = ext_map.get(ext, "Python")
                            sf_preview_lang = code_fence_language(sf_lang)
                            c1, c2 = st.columns(2)
                            with c1:
                                st.markdown("🔴 **Before (Insecure):**")
                                st.code(before_code or "# No example", language=sf_preview_lang)
                            with c2:
                                st.markdown("🟢 **After (Secured):**")
                                st.code(after_code or "# No example", language=sf_preview_lang)

            # Tab 3: Code Smell Panel
            with tab3:
                st.markdown("### 🔍 Code Quality & Smell Inspector")
                smell_finds = [f for f in findings if f.get("category") == "Code Smell"]

                if not smell_finds:
                    st.success("✅ No code smells identified.")
                else:
                    for s in smell_finds:
                        st.markdown(
                            f"""
                            <div style="background-color:#161b22; border: 1px solid #d29922; border-radius:6px; padding:12px; margin-bottom:10px; font-size:0.92rem;">
                                <strong>File:</strong> {s['file']}<br>
                                <strong>Line:</strong> {s['line']}<br>
                                <strong>Issue:</strong> {s['issue']}<br>
                                <strong>Severity:</strong> <span style="color:#d29922; font-weight:700;">{s['severity']}</span><br>
                                <strong>Risk Level:</strong> {s.get('risk_level', s['severity'])}<br>
                                <strong>Why it matters:</strong> {s.get('why_it_matters', 'See suggestion details.')}<br>
                                <strong>Recommendation:</strong> {s['suggestion']}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        before_code = s.get("before_code")
                        after_code = s.get("after_code")
                        if before_code or after_code:
                            from utils.prompts import code_fence_language
                            ext = os.path.splitext(s['file'])[1].lower()
                            ext_map = {
                                ".py": "Python",
                                ".js": "JavaScript",
                                ".jsx": "JavaScript",
                                ".ts": "TypeScript",
                                ".tsx": "TypeScript",
                                ".java": "Java",
                                ".cs": "C#",
                                ".go": "Go",
                                ".rb": "Ruby",
                                ".php": "PHP",
                                ".cpp": "C/C++",
                                ".c": "C/C++",
                                ".h": "C/C++",
                                ".rs": "Rust",
                                ".kt": "Kotlin",
                                ".swift": "Swift",
                            }
                            s_lang = ext_map.get(ext, "Python")
                            s_preview_lang = code_fence_language(s_lang)
                            c1, c2 = st.columns(2)
                            with c1:
                                st.markdown("🔴 **Before (Smell):**")
                                st.code(before_code or "# No example", language=s_preview_lang)
                            with c2:
                                st.markdown("🟢 **After (Refactored):**")
                                st.code(after_code or "# No example", language=s_preview_lang)

            # Tab 4: Test Suggestions Panel
            with tab4:
                st.markdown("### 🧪 Suggested QA Test Cases")
                if not results.get("test_suggestions"):
                    st.info("No test suggestions generated.")
                else:
                    st.markdown(results["test_suggestions"])

            # Tab 5: Repository Insights Dashboard & Viewer
            with tab5:
                st.markdown("### 📁 Repository Health & Insights")
                
                # Fetch Analyzer details if needed
                if st.session_state.review_type == "Pull Request Review" and not st.session_state.repo_analysis:
                    repo_scan_btn = st.button("🔍 Run Repository Health Scan", use_container_width=True)
                    if repo_scan_btn:
                        with st.spinner("Analyzing repository structure..."):
                            try:
                                svc = GitHubService(github_token if github_token else None)
                                groq_client = build_groq_client(groq_api_key)
                                
                                analysis = analyze_repository(
                                    client=groq_client,
                                    github_service=svc,
                                    repo_name=repo_name,
                                )
                                st.session_state.repo_analysis = analysis
                                st.success("Repository audit completed!")
                                st.rerun()
                            except GroqAPIError as e:
                                st.error(f"🛑 {str(e)}")
                            except Exception as e:
                                st.error(f"❌ Repository scan failed: {e}")

                repo_an = st.session_state.repo_analysis or results.get("repo_analysis")
                if repo_an:
                    h_score = repo_an["health_score"]
                    h_color = "#238636" if h_score > 75 else ("#d29922" if h_score > 40 else "#da3633")

                    st.markdown(
                        f"""
                        <div class="metric-card" style="margin-bottom:1.5rem; border-top: 5px solid {h_color}; background-color:var(--page-surface); border-radius:6px; padding:15px; text-align:center;">
                            <div class="metric-value" style="color:{h_color}; font-size:2.2rem; font-weight:700;">{h_score}/100</div>
                            <div class="metric-label" style="font-size:0.8rem; color:var(--page-muted); text-transform:uppercase;">Repository Health Score</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    rs1, rs2, rs3 = st.columns(3)
                    with rs1:
                        st.metric("Source Files", repo_an["source_files_count"])
                    with rs2:
                        st.metric("Test Files", repo_an["test_files_count"])
                    with rs3:
                        st.metric("Docstring Coverage", f"{repo_an['docstring_coverage']}%")

                    if repo_an.get("deductions"):
                        with st.expander("⚠️ Health Score Deductions", expanded=True):
                            for d in repo_an["deductions"]:
                                st.write(d)

                    # Structure tree viewer
                    if repo_an.get("directory_groups"):
                        st.markdown("#### Repository Structure Tree")
                        groups = repo_an["directory_groups"]
                        for didx, (dir_name, files) in enumerate(groups.items()):
                            with st.expander(f"📁 {dir_name} ({len(files)} files)", key=f"repo_struct_{dir_name}*{didx}"):
                                for f in files:
                                    st.markdown(f"- 📄 `{os.path.basename(f)}`  *(path: `{f}`)*")

                    st.markdown("#### Code Hotspots & Test Coverage")
                    col_l, col_r = st.columns(2)
                    with col_l:
                        st.markdown("**🚨 Security Hotspots**")
                        if not repo_an["security_hotspots"]:
                            st.write("No hotspots identified.")
                        else:
                            for hs in repo_an["security_hotspots"]:
                                st.write(f"- `{hs['path']}` ({hs['size_kb']} KB)")
                    with col_r:
                        st.markdown("**❌ Files Missing Tests**")
                        if not repo_an["missing_tests"]:
                            st.write("All files covered by test matching filenames.")
                        else:
                            for mt in repo_an["missing_tests"][:10]:
                                st.write(f"- `{mt}`")
                            if len(repo_an["missing_tests"]) > 10:
                                st.write(f"... and {len(repo_an['missing_tests']) - 10} more.")

                    st.markdown("#### Qualitative Engineering Report")
                    st.markdown(repo_an["analysis_report"])

            # Tab 6: Inline Review Comments Panel
            with tab6:
                st.markdown("### 💬 Inline Review Comments")
                comments = results.get("inline_comments", [])
                if not comments:
                    st.success("✅ No inline review comments generated.")
                else:
                    by_file_comments = {}
                    for c in comments:
                        by_file_comments.setdefault(c["file"], []).append(c)

                    for fidx, (fname, file_comments) in enumerate(by_file_comments.items()):
                        with st.expander(f"📄 {fname} ({len(file_comments)} comments)", key=f"inline_comments_expander_{fname}*{fidx}"):
                            for idx, c in enumerate(file_comments):
                                st.text_area(
                                    label=f"Line {c['line']}",
                                    value=c["body"],
                                    height=135,
                                    disabled=True,
                                    key=f"inline_comment_{fname}*{c['line']}*{idx}",
                                )

            # Tab 7: Export & Actions Panel
            with tab7:
                st.markdown("### 💾 Export Reports")

                export_data = {
                    "repo_name": repo_name,
                    "pr_number": results.get("pr_number"),
                    "timestamp": results["timestamp"],
                    "risk_score": results["risk_score"],
                    "findings": results["findings"],
                    "test_suggestions": results["test_suggestions"],
                    "repo_analysis": st.session_state.repo_analysis or {},
                    "files_analyzed_log": results.get("files_analyzed_log", []),
                    "inline_comments": results.get("inline_comments", []),
                }

                md_report = generate_markdown_report(export_data)
                json_report = generate_json_report(export_data)

                exp_c1, exp_c2, exp_c3 = st.columns(3)
                with exp_c1:
                    st.download_button(
                        label="⬇️ Download Markdown Report",
                        data=md_report,
                        file_name="repo_review_report.md",
                        mime="text/markdown",
                        use_container_width=True,
                    )
                with exp_c2:
                    st.download_button(
                        label="⬇️ Download JSON Report",
                        data=json_report,
                        file_name="repo_review_report.json",
                        mime="application/json",
                        use_container_width=True,
                    )
                with exp_c3:
                    pdf_path = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "exports",
                        f"review_report_repo.pdf",
                    )
                    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

                    try:
                        generate_pdf_report(export_data, pdf_path)
                        with open(pdf_path, "rb") as pdf_file:
                            pdf_bytes = pdf_file.read()

                        st.download_button(
                            label="⬇️ Download PDF Report",
                            data=pdf_bytes,
                            file_name="repo_review_report.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                    except Exception as p_e:
                        st.error(f"Failed to generate PDF: {p_e}")

                st.divider()

                st.markdown("### 💬 GitHub Actions")
                if st.session_state.review_type == "Repository Analysis":
                    st.info("ℹ️ GitHub Comment Posting is available in Pull Request Review Mode.")
                else:
                    st.info("Write these AI code reviews back to the GitHub PR timeline.")
                    post_c1, post_c2 = st.columns(2)
                    with post_c1:
                        summary_post_btn = st.button(
                            "💬 Post Summary Comment to PR discussion", use_container_width=True
                        )
                        if summary_post_btn:
                            if not github_token:
                                st.error("GITHUB_TOKEN env variable is required to post comments.")
                            else:
                                with st.spinner("Posting summary..."):
                                    summary_body = f"""### 🤖 AI Automated Code Review Summary
- **Overall PR Risk Score:** {risk_score}/100
- **Total Issues Found:** {len(findings)}

#### Severity Summary:
- Critical: {results['severity_counts'].get('Critical', 0)}
- High: {results['severity_counts'].get('High', 0)}
- Medium: {results['severity_counts'].get('Medium', 0)}
- Low: {results['severity_counts'].get('Low', 0)}
- Info: {results['severity_counts'].get('Info', 0)}

*Report generated by AI Code Reviewer.*"""
                                    svc = GitHubService(github_token)
                                    ok = svc.post_comment(repo_name, results["pr_number"], summary_body)
                                    if ok:
                                        st.success("Summary comment posted!")
                                    else:
                                        st.error("Failed to post comment.")

                    with post_c2:
                        inline_post_btn = st.button("💬 Post Inline Comments to Diff", use_container_width=True)
                        if inline_post_btn:
                            if not github_token:
                                st.error("GITHUB_TOKEN env variable is required to post inline comments.")
                            else:
                                with st.spinner("Drafting inline comments..."):
                                    svc = GitHubService(github_token)
                                    posted, failed = svc.post_inline_comments(
                                        repo_name=repo_name,
                                        pr_number=results["pr_number"],
                                        inline_comments=results["inline_comments"],
                                    )
                                    if posted > 0:
                                        st.success(f"Posted {posted} inline review comments to GitHub PR!")
                                    if failed > 0:
                                        st.warning(f"Skipped {failed} comments (unmappable diff lines).")

# ----------------- MODE: PASTE CODE SNIPPET -----------------
else:
    st.subheader("📝 Local Code Snippet Reviewer")
    st.write("Paste source code below, select the target programming language, and receive instant audits.")

    s_col1, s_col2 = st.columns([5, 2])
    with s_col2:
        lang_labels = [option["label"] for option in SUPPORTED_LANGUAGE_OPTIONS]
        selected_lang_label = st.selectbox("Select Language", options=lang_labels, index=0)
        selected_lang = next(
            option["value"]
            for option in SUPPORTED_LANGUAGE_OPTIONS
            if option["label"] == selected_lang_label
        )

        st.markdown("<br>", unsafe_allow_html=True)
        review_snippet_btn = st.button(
            "🔍 Run Review",
            type="primary",
            use_container_width=True,
            disabled=not groq_api_key,
        )

    with s_col1:
        snippet_code = st.text_area(
            "Paste Source Code",
            height=380,
            placeholder="Paste code blocks here...",
            key="pasted_code_area",
            label_visibility="collapsed",
        )

    if review_snippet_btn:
        if not snippet_code.strip():
            st.error("Please paste code before running the review.")
        else:
            with st.spinner("Auditing snippet..."):
                try:
                    groq_client = build_groq_client(groq_api_key)
                    res = review_single_code_snippet(
                        code=snippet_code,
                        language=selected_lang,
                        client=groq_client,
                    )
                    st.session_state.pasted_review = res
                    st.success("Auditing complete!")
                except GroqAPIError as e:
                    st.error(f"🛑 {str(e)}")
                except Exception as e:
                    st.error(f"❌ Snippet review failed: {e}")

    # Display snippet review results
    if st.session_state.pasted_review:
        res = st.session_state.pasted_review
        findings = res["findings"]
        risk_score = res["risk_score"]
        sev_counts = res["severity_counts"]

        ltab1, ltab2, ltab3 = st.tabs(["📊 Review Dashboard", "🧪 Suggested Tests", "💾 Export Report"])

        with ltab1:
            st.markdown("### Snippet Scan Summary")
            lm1, lm2, lm3 = st.columns(3)
            with lm1:
                st.metric("Risk Score", f"{risk_score}/100")
            with lm2:
                st.metric("Quality Score", f"{100 - risk_score}/100")
            with lm3:
                st.metric("Total Issues", len(findings))

            if res.get("scores"):
                st.markdown("#### 🎯 Platform Quality Scores")
                sqc1, sqc2, sqc3, sqc4, sqc5 = st.columns(5)
                scores = res["scores"]
                sqc1.metric("Code Quality", f"{scores.get('code_quality', 0)}/100")
                sqc2.metric("Security", f"{scores.get('security', 0)}/100")
                sqc3.metric("Maintainability", f"{scores.get('maintainability', 0)}/100")
                sqc4.metric("Performance", f"{scores.get('performance', 0)}/100")
                sqc5.metric("Technical Debt", f"{scores.get('technical_debt', 0)}/100")

            st.markdown("#### 🪙 Groq Token & Characters Scan Metrics")
            t_col1, t_col2, t_col3, t_col4, t_col5 = st.columns(5)
            files_analyzed_count = res.get("files_analyzed_count", 0)
            characters_analyzed_count = res.get("characters_analyzed_count", 0)
            estimated_tokens_count = res.get("estimated_tokens_count", 0)
            groq_requests_made = res.get("groq_requests_made", 0)
            cached_results_used = res.get("cached_results_used", 0)
            t_col1.metric("Files Analyzed", files_analyzed_count)
            t_col2.metric("Characters Sent", f"{characters_analyzed_count:,}")
            t_col3.metric("Estimated Tokens", f"{estimated_tokens_count:,}")
            t_col4.metric("Groq Requests Made", groq_requests_made)
            t_col5.metric("Cache Hits", cached_results_used)

            st.markdown("#### Severity Breakdown")
            sev_cols = st.columns(5)
            sev_colors = {
                "Critical": "#da3633",
                "High": "#f77e7e",
                "Medium": "#d29922",
                "Low": "#58a6ff",
                "Info": "#8b949e",
            }
            for i, (severity, count) in enumerate(sev_counts.items()):
                with sev_cols[i]:
                    color = sev_colors.get(severity, "#ffffff")
                    st.markdown(
                        f"""
                        <div class="metric-card" style="border-top:4px solid {color}; padding:0.8rem; background-color:var(--page-surface); border-radius:6px;">
                            <div style="font-size:1.5rem; font-weight:700; color:{color};">{count}</div>
                            <div style="font-size:0.8rem; color:var(--page-muted);">{severity}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            st.markdown("#### Issues List")
            if not findings:
                st.success("✅ Snippet is clean! No issues found.")
            else:
                for f in findings:
                    sev = f["severity"]
                    category = f["category"]
                    st.markdown(
                        f"""
                        <div class="finding-row severity-{sev}">
                            <strong>Line {f['line']}</strong> | 
                            <span style="color:{sev_colors.get(sev, '#ffffff')}; font-weight:600;">{sev}</span> | 
                            <span style="background-color:#21262d; border: 1px solid var(--page-border); padding:2px 6px; border-radius:4px; font-size:0.8rem; color:var(--page-muted);">{category}</span><br>
                            <strong>Risk Level:</strong> {f.get('risk_level', sev)}<br>
                            <strong>Why it matters:</strong> {f.get('why_it_matters', 'See suggestion details.')}<br>
                            <div style="margin-top:0.3rem; font-size:0.95rem;">{f['issue']}</div>
                            <div style="color:#39d353; font-size:0.9rem; margin-top:0.2rem;">💡 <em>Suggestion: {f['suggestion']}</em></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    before_code = f.get("before_code")
                    after_code = f.get("after_code")
                    if before_code or after_code:
                        from utils.prompts import code_fence_language
                        preview_lang = code_fence_language(selected_lang)
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown("🔴 **Before:**")
                            st.code(before_code or "# No example", language=preview_lang)
                        with c2:
                            st.markdown("🟢 **After:**")
                            st.code(after_code or "# No example", language=preview_lang)

        with ltab2:
            st.markdown("### Suggested QA Test Cases")
            st.markdown(res["test_suggestions"])

        with ltab3:
            st.markdown("### Export Reports")
            export_data = {
                "repo_name": "Local Snippet Scan",
                "pr_number": None,
                "timestamp": res["timestamp"],
                "risk_score": res["risk_score"],
                "findings": res["findings"],
                "test_suggestions": res["test_suggestions"],
                "repo_analysis": {},
            }

            md_report = generate_markdown_report(export_data)
            json_report = generate_json_report(export_data)

            exp_c1, exp_c2, exp_c3 = st.columns(3)
            with exp_c1:
                st.download_button(
                    label="⬇️ Download Markdown",
                    data=md_report,
                    file_name="snippet_review_report.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            with exp_c2:
                st.download_button(
                    label="⬇️ Download JSON",
                    data=json_report,
                    file_name="snippet_review_report.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with exp_c3:
                pdf_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "exports", "review_report_snippet.pdf"
                )
                os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
                try:
                    generate_pdf_report(export_data, pdf_path)
                    with open(pdf_path, "rb") as pdf_file:
                        pdf_bytes = pdf_file.read()

                    st.download_button(
                        label="⬇️ Download PDF",
                        data=pdf_bytes,
                        file_name="snippet_review_report.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception as p_e:
                    st.error(f"Failed to generate PDF: {p_e}")

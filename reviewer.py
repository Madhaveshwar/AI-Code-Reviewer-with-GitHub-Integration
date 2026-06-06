"""AI Reviewer engine that coordinates reviews, security audits, and code smell scans."""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from groq import Groq
from langsmith import Client, traceable

# Ensure the parent directory is on the search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.prompts import (
    SYSTEM_COMBINED_PROMPT,
    build_combined_prompt,
    normalize_language_name,
)
from utils.validation import is_valid_code, should_skip_file
from security_scanner import scan_security, parse_json_from_llm
from code_smell_detector import detect_code_smells
from test_generator import generate_tests
from repository_analyzer import analyze_repository

MODEL_NAME = "llama-3.3-70b-versatile"  # Default placeholder
MODEL_TEMPERATURE = 0.3

import hashlib
import json
import re
from typing import Any

class GroqAPIError(Exception):
    """Custom exception for Groq API errors to provide user-friendly messages."""
    pass


def handle_groq_error(exc: Exception) -> Exception:
    """Map Groq API exceptions to user-friendly GroqAPIError exceptions."""
    err_msg = str(exc)
    err_msg_lower = err_msg.lower()
    
    if "api_key" in err_msg_lower or "unauthorized" in err_msg_lower or "401" in err_msg_lower:
        return GroqAPIError("Groq API key is invalid or expired. Please renew the key.")
    
    if "429" in err_msg_lower or "rate_limit" in err_msg_lower or "quota" in err_msg_lower or "limit exceeded" in err_msg_lower:
        return GroqAPIError("Groq quota exceeded. Please try later.")
        
    if "model" in err_msg_lower and ("not found" in err_msg_lower or "unavailable" in err_msg_lower):
        return GroqAPIError("Selected Groq model is unavailable.")
        
    return GroqAPIError(f"Groq API error: {err_msg}")


CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".reviewer_cache.json")


def get_file_hash(content: str) -> str:
    """Compute SHA256 of the content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_cache() -> dict:
    """Load caching findings from JSON file."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache: dict):
    """Save findings cache to JSON file."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Failed to save cache: {e}")


def parse_combined_json_from_llm(content: str) -> dict:
    """Parse the consolidated JSON object from LLM response."""
    if not content:
        return {}

    content = content.strip()
    
    # Strip markdown code fence if present
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if json_match:
        content = json_match.group(1).strip()

    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        # Fallback regex search for JSON object if it has trailing garbage or is not perfectly closed
        object_match = re.search(r"\{\s*\"[^\"]+\"\s*:[\s\S]*\}", content)
        if object_match:
            try:
                data = json.loads(object_match.group(0))
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass
    return {}


def update_findings_file(findings: list, filename: str) -> list:
    """Ensure all findings have the current file path."""
    updated = []
    for item in findings:
        if isinstance(item, dict):
            new_item = dict(item)
            new_item["file"] = filename
            updated.append(new_item)
    return updated


SYSTEM_MULTI_FILE_PROMPT = """You are an expert senior software engineer, application security (AppSec) specialist, QA automation engineer, and code quality coach.
Your job is to perform a comprehensive code review of multiple source files and (optionally) generate a repository-level qualitative engineering report.

For each file, you must identify:
1. Security Findings:
   Identify vulnerabilities (OWASP Top 10 aligned like SQL Injection, Command Injection, XSS, CSRF, SSRF, weak cryptography, weak authentication, insecure deserialization, directory traversal).
   Specifically detect hardcoded secrets, API keys, credentials, tokens, and dangerous functions (e.g., eval, exec, child_process execution, system commands).
2. Code Smells:
   Identify maintainability and code quality concerns such as long methods/functions, complex classes, duplicate/dead code, excessive nesting, magic numbers/strings, poor naming conventions, or missing error handling.
3. Inline Comments (General Review / Performance):
   Identify logic bugs, functional defects, performance inefficiencies (such as inefficient loops, O(N^2) complexity, expensive operations, redundant I/O), resource leaks, or violations of language-specific best practices.
4. Test Suggestions:
   Proposing Unit Tests, Integration Tests, Edge Cases, and Negative Tests for the file.
5. Severity Score:
   A number between 0 and 100 representing the overall risk/severity of the issues found in this file (0 meaning perfectly clean/no issues, 100 meaning extremely critical security or functional bugs).
6. Quality Scores:
   Scores out of 100 representing dimensions of code quality, security, maintainability, performance, and technical debt.

If requested, you must also generate:
- Repository Qualitative Report:
  An overall qualitative engineering report based on the repository folder structure, dependency risks, large files, security hotspots, and docstring coverage provided.

Return ONLY a valid JSON object. Do not include any markdown wrapper (like ```json ... ```) or explanation, just the raw JSON.

The JSON response MUST match this schema exactly:
{
  "files_reviews": {
    "<filename>": {
      "security_findings": [
        {
          "line": line_number,
          "severity": "Critical|High|Medium|Low|Info",
          "issue": "Brief description of the security vulnerability",
          "why_it_matters": "Explanation of WHY this is a problem and its risk impact (OWASP-aligned context)",
          "risk_level": "Critical|High|Medium|Low|Info",
          "suggestion": "Detailed instructions on how to secure the code and provide a safe alternative",
          "before_code": "Language-specific insecure or bad code snippet from the original file",
          "after_code": "Language-specific remediated/secured code example demonstrating the fix"
        }
      ],
      "code_smells": [
        {
          "line": line_number,
          "severity": "Critical|High|Medium|Low|Info",
          "issue": "Brief description of the code smell",
          "why_it_matters": "Explanation of WHY this is a problem (maintainability, cognitive load)",
          "risk_level": "Critical|High|Medium|Low|Info",
          "suggestion": "How to refactor or rewrite the code to eliminate the smell",
          "before_code": "Language-specific code snippet showcasing the smell",
          "after_code": "Language-specific refactored clean code example demonstrating the fix"
        }
      ],
      "inline_comments": [
        {
          "line": line_number,
          "severity": "Critical|High|Medium|Low|Info",
          "category": "Bug|Performance|Maintainability|Best Practice",
          "issue": "Brief description of the logic bug, performance, or best practice issue",
          "why_it_matters": "Explanation of WHY this is a problem (inefficient loop, memory leak, bug impact)",
          "risk_level": "Critical|High|Medium|Low|Info",
          "suggestion": "Specific instructions on how to fix it",
          "before_code": "Language-specific suboptimal code snippet",
          "after_code": "Language-specific optimized/corrected code example"
        }
      ],
      "test_suggestions": "### Unit Tests\\n...\\n### Integration Tests\\n...\\n### Edge Cases\\n...\\n### Negative Tests\\n...",
      "severity_score": severity_score_value,
      "scores": {
        "code_quality": code_quality_value,
        "security": security_value,
        "maintainability": maintainability_value,
        "performance": performance_value,
        "technical_debt": technical_debt_value
      }
    }
  },
  "repository_insights": "Qualitative engineering report markdown string (or null if not requested)"
}

Where:
- severity_score_value is a number between 0 and 100 representing the overall risk/severity of the issues found in this file (0 meaning perfectly clean/no issues, 100 meaning extremely critical security or functional bugs).
- code_quality_value, security_value, maintainability_value, performance_value are values from 0 to 100 representing dimensions of quality (100 being excellent, 0 being terrible).
- technical_debt_value is from 0 to 100 (0 meaning no technical debt, 100 meaning severe technical debt).
"""


def build_multi_file_prompt(files_to_review: list[dict], repo_metadata: dict | None = None) -> str:
    prompt_parts = []
    prompt_parts.append("Please perform a review for the following files:")
    for f in files_to_review:
        prompt_parts.append(f"--- File: {f['filename']} ---")
        prompt_parts.append(f"Language: {f['language']}")
        prompt_parts.append("Diff Patch (what was changed):")
        prompt_parts.append("```diff")
        prompt_parts.append(f["patch"])
        prompt_parts.append("```")
        prompt_parts.append("Full file content (truncated, for context):")
        prompt_parts.append("```")
        prompt_parts.append(f["content"])
        prompt_parts.append("```")
        prompt_parts.append("")
    
    if repo_metadata:
        prompt_parts.append("--- Repository Metadata (for Repository Qualitative Report) ---")
        prompt_parts.append(f"Folder Structure:\n{repo_metadata.get('folder_structure')}")
        prompt_parts.append(f"Dependency Risks / Files:\n{repo_metadata.get('dependency_risks')}")
        prompt_parts.append(f"Large Files:\n{json.dumps(repo_metadata.get('large_files'), indent=2)}")
        prompt_parts.append(f"Security Hotspots:\n{json.dumps(repo_metadata.get('security_hotspots'), indent=2)}")
        prompt_parts.append(f"Documentation Coverage Info:\n{json.dumps(repo_metadata.get('doc_coverage'), indent=2)}")
        prompt_parts.append("\nPlease generate the qualitative engineering report under the 'repository_insights' JSON key based on the metadata above.")
    else:
        prompt_parts.append("Do not generate repository qualitative report. Keep 'repository_insights' key as null.")

    return "\n".join(prompt_parts)


def review_files_combined(
    client: Any,
    files_to_review: list[dict],
    repo_metadata: dict | None = None,
    repo_name: str | None = None,
    model_name: str = MODEL_NAME,
    temperature: float = MODEL_TEMPERATURE,
) -> tuple[dict[str, dict], int, str | None, int, int]:
    """Perform review of multiple files content using a single combined Groq request.
    
    Returns (files_reviews_map, cache_hits, repository_insights, requests_made, characters_sent).
    """
    cache = load_cache()
    files_reviews_map = {}
    uncached_files = []
    
    # 1. Check file-level caching
    for f in files_to_review:
        fname = f["filename"]
        content = f["content"]
        if len(content) > 1000:
            content = content[:1000]
        
        content_hash = get_file_hash(content)
        f["hash"] = content_hash
        f["truncated_content"] = content
        
        if content_hash in cache:
            cached_result = cache[content_hash]
            files_reviews_map[fname] = {
                "security_findings": update_findings_file(cached_result.get("security_findings", []), fname),
                "code_smells": update_findings_file(cached_result.get("code_smells", []), fname),
                "inline_comments": update_findings_file(cached_result.get("inline_comments", []), fname),
                "test_suggestions": cached_result.get("test_suggestions", ""),
                "severity_score": cached_result.get("severity_score", 0),
                "scores": cached_result.get("scores", {})
            }
        else:
            uncached_files.append(f)

    # 2. Check repo-report level caching
    scanned_files_hash = hashlib.sha256("".join(sorted(get_file_hash(f["content"][:1000]) for f in files_to_review)).encode()).hexdigest()
    repo_report_key = f"repo_report_{repo_name}_{scanned_files_hash}" if repo_name else None
    
    repo_insights = None
    if repo_report_key and repo_report_key in cache:
        repo_insights = cache[repo_report_key]
        
    need_repo_insights = (repo_metadata is not None) and (repo_insights is None)
    
    # 3. Call Groq if there are uncached files or if we need repo insights
    requests_made = 0
    characters_sent = 0
    
    if uncached_files or need_repo_insights:
        prompt = build_multi_file_prompt(uncached_files, repo_metadata if need_repo_insights else None)
        
        max_retries = 4
        backoff = 10
        result_text = ""
        
        active_model = "llama-3.3-70b-versatile"
        for attempt in range(max_retries):
            try:
                chat_completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": SYSTEM_MULTI_FILE_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    model=active_model,
                    temperature=temperature,
                )
                result_text = chat_completion.choices[0].message.content
                requests_made += 1
                characters_sent += len(prompt)
                break
            except Exception as e:
                err_msg_lower = str(e).lower()
                is_quota_error = "429" in err_msg_lower or "rate_limit" in err_msg_lower or "quota" in err_msg_lower or "limit exceeded" in err_msg_lower
                if not is_quota_error and active_model == "llama-3.3-70b-versatile":
                    active_model = "llama-3.1-8b-instant"
                    continue
                if is_quota_error and attempt < max_retries - 1:
                    print(f"Quota exceeded. Retrying in {backoff} seconds...")
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    raise handle_groq_error(e)
                    
        parsed = parse_combined_json_from_llm(result_text)
        
        # Save reviewed files to cache
        files_reviews_data = parsed.get("files_reviews", {})
        for f in uncached_files:
            fname = f["filename"]
            fhash = f["hash"]
            
            file_parsed = files_reviews_data.get(fname, {})
            cache[fhash] = {
                "security_findings": file_parsed.get("security_findings", []),
                "code_smells": file_parsed.get("code_smells", []),
                "inline_comments": file_parsed.get("inline_comments", []),
                "test_suggestions": file_parsed.get("test_suggestions", ""),
                "severity_score": file_parsed.get("severity_score", 0),
                "scores": file_parsed.get("scores", {})
            }
            
            files_reviews_map[fname] = {
                "security_findings": update_findings_file(file_parsed.get("security_findings", []), fname),
                "code_smells": update_findings_file(file_parsed.get("code_smells", []), fname),
                "inline_comments": update_findings_file(file_parsed.get("inline_comments", []), fname),
                "test_suggestions": file_parsed.get("test_suggestions", ""),
                "severity_score": file_parsed.get("severity_score", 0),
                "scores": file_parsed.get("scores", {})
            }
            
        if need_repo_insights:
            repo_insights = parsed.get("repository_insights") or ""
            if repo_report_key is not None:
                cache[repo_report_key] = repo_insights
        
        save_cache(cache)
        
    cache_hits = len(files_to_review) - len(uncached_files)
    return files_reviews_map, cache_hits, repo_insights, requests_made, characters_sent


def review_file_combined(
    client: Any,
    filename: str,
    content: str,
    patch: str,
    language: str,
    model_name: str = MODEL_NAME,
    temperature: float = MODEL_TEMPERATURE,
) -> tuple[dict, bool]:
    """Fallback / wrapper for backward compatibility."""
    files_to_review = [{
        "filename": filename,
        "content": content,
        "patch": patch,
        "language": language
    }]
    results_map, was_cached, _, _, _ = review_files_combined(
        client=client,
        files_to_review=files_to_review,
        repo_metadata=None,
        model_name=model_name,
        temperature=temperature
    )
    return results_map.get(filename, {}), was_cached


PLACEHOLDER_VALUES = {
    "your_groq_api_key",
    "your_existing_langsmith_key",
}


def _get_config_value(name: str) -> str | None:
    """Resolve a configuration value from environment or streamlit secrets, normalising mixed-case Groq API key."""
    # Attempt to read from environment first (e.g. .env is loaded)
    value = os.getenv(name)
    if not value and name == "GROQ_API_KEY":
        value = os.getenv("Groq_api_key")
        
    if value:
        if value.strip() in PLACEHOLDER_VALUES or value.strip().startswith("your_"):
            return None
        return value

    # Fallback to streamlit secrets if running inside streamlit
    try:
        import streamlit as st
        val = st.secrets.get(name)
        if not val and name == "GROQ_API_KEY":
            val = st.secrets.get("Groq_api_key")
        if val:
            return val
    except Exception:
        pass

    return None


def _is_truthy(value: str | None) -> bool:
    """Check if value matches truthy representations."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_runtime_status() -> dict[str, object]:
    """Return configured integration status for Groq and LangSmith."""
    langchain_project = _get_config_value("LANGCHAIN_PROJECT") or "Automated_Code_Reviewer"
    return {
        "groq_api_key_present": bool(_get_config_value("GROQ_API_KEY")),
        "langchain_api_key_present": bool(_get_config_value("LANGCHAIN_API_KEY")),
        "langchain_tracing_enabled": _is_truthy(_get_config_value("LANGCHAIN_TRACING_V2")),
        "langchain_project": langchain_project,
    }


def build_groq_client(api_key: str | None = None) -> Groq:
    """Configure and return the Groq client with diagnostics."""
    global MODEL_NAME
    key = api_key or _get_config_value("GROQ_API_KEY")
    api_key_status = "Configured" if key else "Missing"
    print("Startup Diagnostics:")
    print(f"  API Key Status: {api_key_status}")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    
    print(f"  Selected Model: {MODEL_NAME}")
    return Groq(api_key=key)


def build_langsmith_client() -> Client | None:
    """Construct and return a LangSmith client if key is configured."""
    api_key = _get_config_value("LANGCHAIN_API_KEY")
    if not api_key:
        return None
    return Client(api_key=api_key)


@traceable(name="General Code Review")
def scan_general_review(
    client: Any,
    filename: str,
    code: str,
    patch: str,
    language: str,
    model_name: str = MODEL_NAME,
    temperature: float = MODEL_TEMPERATURE,
) -> list[dict[str, object]]:
    """Perform logic, bugs, and performance reviews on code changes."""
    prompt = build_review_prompt(filename, code, patch, language)

    active_model = "llama-3.3-70b-versatile"
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_REVIEW_PROMPT},
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
                    {"role": "system", "content": SYSTEM_REVIEW_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.1-8b-instant",
                temperature=temperature,
            )
            result_text = chat_completion.choices[0].message.content
        except Exception as fallback_e:
            raise handle_groq_error(fallback_e)

    findings = parse_json_from_llm(result_text)

    validated = []
    for item in findings:
        if isinstance(item, dict):
            validated.append({
                "file": item.get("file", filename),
                "line": int(item.get("line", 1)) if str(item.get("line")).isdigit() else 1,
                "severity": item.get("severity", "Medium"),
                "category": item.get("category", "Bug"),
                "issue": item.get("issue", "Quality or logic concern"),
                "suggestion": item.get("suggestion", "Please verify this code."),
            })
    return validated


def calculate_fallback_scores(risk_score: int, severity_counts: dict) -> dict[str, int]:
    """Calculate baseline fallback scores from risk levels."""
    security_penalty = (
        50 * severity_counts.get("Critical", 0)
        + 30 * severity_counts.get("High", 0)
        + 12 * severity_counts.get("Medium", 0)
        + 2 * severity_counts.get("Low", 0)
    )
    maintainability_penalty = (
        20 * severity_counts.get("Critical", 0)
        + 15 * severity_counts.get("High", 0)
        + 8 * severity_counts.get("Medium", 0)
        + 3 * severity_counts.get("Low", 0)
    )
    performance_penalty = (
        15 * severity_counts.get("Critical", 0)
        + 10 * severity_counts.get("High", 0)
        + 6 * severity_counts.get("Medium", 0)
        + 2 * severity_counts.get("Low", 0)
    )
    
    code_quality = max(0, min(100, 100 - risk_score))
    security = max(0, min(100, 100 - security_penalty))
    maintainability = max(0, min(100, 100 - maintainability_penalty))
    performance = max(0, min(100, 100 - performance_penalty))
    technical_debt = max(0, min(100, risk_score))
    
    return {
        "code_quality": code_quality,
        "security": security,
        "maintainability": maintainability,
        "performance": performance,
        "technical_debt": technical_debt
    }


def resolve_scores(file_scores_list: list[dict], risk_score: int, severity_counts: dict) -> dict[str, int]:
    """Average the parsed file quality scores or fall back if empty."""
    fallback = calculate_fallback_scores(risk_score, severity_counts)
    if not file_scores_list:
        return fallback
    
    avg_scores = {}
    keys = ["code_quality", "security", "maintainability", "performance", "technical_debt"]
    for k in keys:
        vals = [s.get(k) for s in file_scores_list if isinstance(s, dict) and s.get(k) is not None]
        if vals:
            avg_scores[k] = int(sum(vals) / len(vals))
        else:
            avg_scores[k] = fallback[k]
    return avg_scores


@traceable(name="PR Review Analysis Pipeline", run_type="chain")
def review_pull_request(
    repo_name: str,
    pr_number: int,
    github_service,
    client: Any,
    language_mapping: dict[str, str] | None = None,
) -> dict[str, object]:
    """Execute the complete AI Review pipeline on a pull request.

    This function scans modified files, filters issues to modified lines,
    computes risk scores, creates inline comments, suggestions, and traces details.
    """
    start_time = time.time()
    pr_details = github_service.get_pr_details(repo_name, pr_number)
    changed_files = github_service.get_pr_files(repo_name, pr_number)

    all_findings = []
    test_suggestions_by_file = {}
    files_analyzed_log = []
    
    files_to_review = []
    if not language_mapping:
        language_mapping = {}

    for f in changed_files:
        filename = f["filename"]
        patch = f["patch"]
        status = f["status"]
        ext = os.path.splitext(filename)[1].lower()

        # Determine file type
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
        detected_lang = ext_map.get(ext, "Other")
        file_type = detected_lang
        if ext in [".md", ".txt"]:
            file_type = "Documentation"
        elif ext in [".json", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".xml"]:
            file_type = "Configuration"

        is_source_ext = detected_lang != "Other"

        if should_skip_file(filename) or status == "removed" or not patch:
            files_analyzed_log.append({
                "file": filename,
                "type": file_type,
                "status": "Skipped",
                "findings": 0
            })
            continue

        if not is_source_ext:
            files_analyzed_log.append({
                "file": filename,
                "type": file_type,
                "status": "Scanned",
                "findings": 0
            })
            continue

        # Get file content
        content = github_service.get_file_content(repo_name, filename, pr_details["head_sha"])
        if not content or not is_valid_code(content):
            files_analyzed_log.append({
                "file": filename,
                "type": file_type,
                "status": "Skipped",
                "findings": 0
            })
            continue

        # Truncate content to max 1000 characters to minimize token usage
        if len(content) > 1000:
            content = content[:1000]

        lang = language_mapping.get(filename, detected_lang)

        files_to_review.append({
            "filename": filename,
            "content": content,
            "patch": patch,
            "language": lang
        })

    # Combined Files Review for PR
    files_reviews_map, cache_hits, _, requests_made, characters_sent = review_files_combined(
        client=client,
        files_to_review=files_to_review,
        repo_metadata=None,
        repo_name=None,
        model_name=MODEL_NAME
    )

    files_analyzed_count = len(files_to_review)
    cached_results_used = cache_hits
    groq_requests_made = requests_made
    characters_analyzed_count = characters_sent

    for f in changed_files:
        filename = f["filename"]
        patch = f["patch"]
        if filename not in files_reviews_map:
            continue

        res_dict = files_reviews_map[filename]
        modified_lines = github_service.get_modified_lines(patch)

        # Reconstruct findings
        general_issues = []
        for item in res_dict.get("inline_comments", []):
            if isinstance(item, dict):
                general_issues.append({
                    "file": filename,
                    "line": int(item.get("line", 1)) if str(item.get("line")).isdigit() else 1,
                    "severity": item.get("severity", "Medium"),
                    "category": item.get("category", "Bug"),
                    "issue": item.get("issue", "Quality or logic concern"),
                    "suggestion": item.get("suggestion", "Please verify this code."),
                    "why_it_matters": item.get("why_it_matters", "No explanation provided."),
                    "risk_level": item.get("risk_level", item.get("severity", "Medium")),
                    "before_code": item.get("before_code", ""),
                    "after_code": item.get("after_code", ""),
                })

        security_issues = []
        for item in res_dict.get("security_findings", []):
            if isinstance(item, dict):
                security_issues.append({
                    "file": filename,
                    "line": int(item.get("line", 1)) if str(item.get("line")).isdigit() else 1,
                    "severity": item.get("severity", "Medium"),
                    "category": "Security",
                    "issue": item.get("issue", "Potential vulnerability found"),
                    "suggestion": item.get("suggestion", "Please verify and secure this code."),
                    "why_it_matters": item.get("why_it_matters", "No explanation provided."),
                    "risk_level": item.get("risk_level", item.get("severity", "Medium")),
                    "before_code": item.get("before_code", ""),
                    "after_code": item.get("after_code", ""),
                })

        smell_issues = []
        for item in res_dict.get("code_smells", []):
            if isinstance(item, dict):
                smell_issues.append({
                    "file": filename,
                    "line": int(item.get("line", 1)) if str(item.get("line")).isdigit() else 1,
                    "severity": item.get("severity", "Low"),
                    "category": "Code Smell",
                    "issue": item.get("issue", "Code quality smell detected"),
                    "suggestion": item.get("suggestion", "Please refactor this code to clean it up."),
                    "why_it_matters": item.get("why_it_matters", "No explanation provided."),
                    "risk_level": item.get("risk_level", item.get("severity", "Low")),
                    "before_code": item.get("before_code", ""),
                    "after_code": item.get("after_code", ""),
                })

        combined = general_issues + security_issues + smell_issues

        # Filter: Review only modified code lines
        file_findings = []
        for issue in combined:
            line_num = issue["line"]
            if line_num in modified_lines or not modified_lines:
                file_findings.append(issue)

        all_findings.extend(file_findings)

        ext = os.path.splitext(filename)[1].lower()
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
        detected_lang = ext_map.get(ext, "Other")
        file_type = detected_lang
        if ext in [".md", ".txt"]:
            file_type = "Documentation"
        elif ext in [".json", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".xml"]:
            file_type = "Configuration"

        files_analyzed_log.append({
            "file": filename,
            "type": file_type,
            "status": "Analyzed",
            "findings": len(file_findings)
        })

        # Save test suggestions
        if len(test_suggestions_by_file) < 3 and res_dict.get("test_suggestions"):
            test_suggestions_by_file[filename] = res_dict["test_suggestions"]

    # Calculate severity counts and Risk Score
    severity_counts = {
        "Critical": 0,
        "High": 0,
        "Medium": 0,
        "Low": 0,
        "Info": 0,
    }
    for f in all_findings:
        sev = f["severity"]
        if sev in severity_counts:
            severity_counts[sev] += 1

    risk_score = min(
        100,
        25 * severity_counts["Critical"]
        + 15 * severity_counts["High"]
        + 6 * severity_counts["Medium"]
        + 1 * severity_counts["Low"]
    )

    # Format Inline Comments
    inline_comments = []
    for f in all_findings:
        # Match back to file's patch to enable posting review comments
        file_patch = next((item["patch"] for item in changed_files if item["filename"] == f["file"]), "")
        
        body_text = f"""File: {f['file']}
Line: {f['line']}
Issue: {f['issue']}
Severity: {f['severity']}
Recommendation: {f['suggestion']}"""

        inline_comments.append({
            "file": f["file"],
            "line": f["line"],
            "body": body_text,
            "patch": file_patch,
        })

    # Compile Test Suggestions Markdown
    test_suggestions_md = []
    for fn, tests in test_suggestions_by_file.items():
        test_suggestions_md.append(f"### File: {fn}\n{tests}\n")
    test_suggestions_compiled = "\n".join(test_suggestions_md)

    latency = round(time.time() - start_time, 2)
    estimated_tokens_count = characters_analyzed_count // 4

    # Resolve averaged quality scores
    file_scores_list = [res_dict.get("scores", {}) for res_dict in files_reviews_map.values() if isinstance(res_dict, dict) and "scores" in res_dict]
    overall_scores = resolve_scores(file_scores_list, risk_score, severity_counts)

    return {
        "repo_name": repo_name,
        "pr_number": pr_number,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "risk_score": risk_score,
        "findings": all_findings,
        "inline_comments": inline_comments,
        "test_suggestions": test_suggestions_compiled,
        "severity_counts": severity_counts,
        "latency_seconds": latency,
        "estimated_token_usage": len(all_findings) * 350 + 500,
        "files_analyzed_log": files_analyzed_log,
        "files_analyzed_count": files_analyzed_count,
        "characters_analyzed_count": characters_analyzed_count,
        "estimated_tokens_count": estimated_tokens_count,
        "groq_requests_made": groq_requests_made,
        "cached_results_used": cached_results_used,
        "scores": overall_scores,
    }


@traceable(name="Single Code Snippet Scan", run_type="chain")
def review_single_code_snippet(
    code: str,
    language: str,
    client: Any,
) -> dict[str, object]:
    """Review a single pasted code snippet, running all analysis engines."""
    start_time = time.time()
    if len(code) > 1000:
        code = code[:1000]

    filename = "snippet.py" if language == "Python" else f"snippet.{language[:3].lower()}"

    # Since there's no patch, we pass full file as patch context so the scanners audit the whole code
    dummy_patch = f"@@ -1,1 +1,{len(code.splitlines())} @@\n" + "\n".join(f"+{line}" for line in code.splitlines())

    groq_requests_made = 0
    cached_results_used = 0

    try:
        res_dict, was_cached = review_file_combined(
            client=client,
            filename=filename,
            content=code,
            patch=dummy_patch,
            language=language,
            model_name=MODEL_NAME
        )
        if was_cached:
            cached_results_used += 1
        else:
            groq_requests_made += 1
    except Exception as e:
        raise handle_groq_error(e)

    # Reconstruct findings
    general_issues = []
    for item in res_dict.get("inline_comments", []):
        if isinstance(item, dict):
            general_issues.append({
                "file": filename,
                "line": int(item.get("line", 1)) if str(item.get("line")).isdigit() else 1,
                "severity": item.get("severity", "Medium"),
                "category": item.get("category", "Bug"),
                "issue": item.get("issue", "Quality or logic concern"),
                "suggestion": item.get("suggestion", "Please verify this code."),
                "why_it_matters": item.get("why_it_matters", "No explanation provided."),
                "risk_level": item.get("risk_level", item.get("severity", "Medium")),
                "before_code": item.get("before_code", ""),
                "after_code": item.get("after_code", ""),
            })

    security_issues = []
    for item in res_dict.get("security_findings", []):
        if isinstance(item, dict):
            security_issues.append({
                "file": filename,
                "line": int(item.get("line", 1)) if str(item.get("line")).isdigit() else 1,
                "severity": item.get("severity", "Medium"),
                "category": "Security",
                "issue": item.get("issue", "Potential vulnerability found"),
                "suggestion": item.get("suggestion", "Please verify and secure this code."),
                "why_it_matters": item.get("why_it_matters", "No explanation provided."),
                "risk_level": item.get("risk_level", item.get("severity", "Medium")),
                "before_code": item.get("before_code", ""),
                "after_code": item.get("after_code", ""),
            })

    smell_issues = []
    for item in res_dict.get("code_smells", []):
        if isinstance(item, dict):
            smell_issues.append({
                "file": filename,
                "line": int(item.get("line", 1)) if str(item.get("line")).isdigit() else 1,
                "severity": item.get("severity", "Low"),
                "category": "Code Smell",
                "issue": item.get("issue", "Code quality smell detected"),
                "suggestion": item.get("suggestion", "Please refactor this code to clean it up."),
                "why_it_matters": item.get("why_it_matters", "No explanation provided."),
                "risk_level": item.get("risk_level", item.get("severity", "Low")),
                "before_code": item.get("before_code", ""),
                "after_code": item.get("after_code", ""),
            })

    findings = general_issues + security_issues + smell_issues

    severity_counts = {
        "Critical": 0,
        "High": 0,
        "Medium": 0,
        "Low": 0,
        "Info": 0,
    }
    for f in findings:
        sev = f["severity"]
        if sev in severity_counts:
            severity_counts[sev] += 1

    risk_score = min(
        100,
        25 * severity_counts["Critical"]
        + 15 * severity_counts["High"]
        + 6 * severity_counts["Medium"]
        + 1 * severity_counts["Low"]
    )

    tests = res_dict.get("test_suggestions", "Failed to generate test suggestions.")

    # Format Inline Comments
    inline_comments = []
    for f in findings:
        body_text = f"""File: {f['file']}
Line: {f['line']}
Issue: {f['issue']}
Severity: {f['severity']}
Recommendation: {f['suggestion']}"""

        inline_comments.append({
            "file": f["file"],
            "line": f["line"],
            "body": body_text,
            "patch": dummy_patch,
        })

    latency = round(time.time() - start_time, 2)

    files_analyzed_count = 1
    characters_analyzed_count = 0 if was_cached else len(code)
    estimated_tokens_count = characters_analyzed_count // 4

    # Resolve quality scores for single code snippet
    snippet_scores = resolve_scores([res_dict.get("scores", {})], risk_score, severity_counts)

    return {
        "repo_name": "Local Snippet",
        "pr_number": None,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "risk_score": risk_score,
        "findings": findings,
        "inline_comments": inline_comments,
        "test_suggestions": tests,
        "severity_counts": severity_counts,
        "latency_seconds": latency,
        "estimated_token_usage": len(findings) * 350 + 500,
        "files_analyzed_count": files_analyzed_count,
        "characters_analyzed_count": characters_analyzed_count,
        "estimated_tokens_count": estimated_tokens_count,
        "groq_requests_made": groq_requests_made,
        "cached_results_used": cached_results_used,
        "scores": snippet_scores,
    }


@traceable(name="LangSmith Metadata Capture")
def capture_langsmith_metadata(
    repo_name: str,
    pr_number: int,
    risk_score: int,
    findings_count: int,
    latency: float,
) -> dict[str, object]:
    """Trace operational execution metadata for reporting."""
    return {
        "repository": repo_name,
        "pr_number": pr_number,
        "risk_score": risk_score,
        "findings_count": findings_count,
        "latency": latency,
    }


@traceable(name="Full Repository Analysis Pipeline", run_type="chain")
def review_entire_repository(
    repo_name: str,
    github_service,
    client: Any,
    language_mapping: dict[str, str] | None = None,
) -> dict[str, object]:
    """Execute AI review scanners across the repository files when no PR exists."""
    start_time = time.time()
    repo = github_service.client.get_repo(repo_name)
    default_branch = repo.default_branch

    # Get the file list recursively from default branch tree
    tree_items = []
    try:
        branch = repo.get_branch(default_branch)
        sha = branch.commit.sha
        git_tree = repo.get_git_tree(sha=sha, recursive=True)
        tree_items = git_tree.tree
    except Exception as exc:
        print(f"Error fetching repo tree: {exc}")

    # Collect source files with sizes
    source_files_with_sizes = []
    for item in tree_items:
        if item.type == "blob":
            path = item.path
            if should_skip_file(path):
                continue
            is_source = any(
                path.endswith(ext)
                for ext in [
                    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cs",
                    ".go", ".rb", ".php", ".cpp", ".c", ".rs", ".kt", ".swift"
                ]
            )
            basename = os.path.basename(path).lower()
            is_test = (
                "test" in basename
                or "spec" in basename
                or path.startswith("tests/")
                or path.startswith("test/")
            )
            if is_source and not is_test:
                source_files_with_sizes.append((path, item.size or 0))

    # Sort by size in descending order
    source_files_with_sizes.sort(key=lambda x: x[1], reverse=True)

    # Take at most 5 source files
    scanned_files = [path for path, size in source_files_with_sizes[:5]]
    source_files = [path for path, size in source_files_with_sizes]
    
    files_to_review = []
    if not language_mapping:
        language_mapping = {}

    for filename in scanned_files:
        content = github_service.get_file_content(repo_name, filename, default_branch)
        if not content or not is_valid_code(content):
            continue

        # Truncate content to max 1000 characters
        if len(content) > 1000:
            content = content[:1000]

        ext = os.path.splitext(filename)[1].lower()
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
        detected_lang = ext_map.get(ext, "Python")
        lang = language_mapping.get(filename, detected_lang)

        # Build dummy patch representing the entire file
        dummy_patch = f"@@ -1,1 +1,{len(content.splitlines())} @@\n" + "\n".join(f"+{line}" for line in content.splitlines())

        files_to_review.append({
            "filename": filename,
            "content": content,
            "patch": dummy_patch,
            "language": lang
        })

    # Get static repository metadata first without triggering a separate Groq request
    try:
        repo_metadata = analyze_repository(
            client=client,
            github_service=github_service,
            repo_name=repo_name,
            qualitative_report="PENDING"
        )
    except Exception as e:
        raise handle_groq_error(e)

    # Run combined files + repoinsights review
    files_reviews_map, cache_hits, repo_insights, requests_made, characters_sent = review_files_combined(
        client=client,
        files_to_review=files_to_review,
        repo_metadata=repo_metadata,
        repo_name=repo_name,
        model_name=MODEL_NAME
    )

    all_findings = []
    test_suggestions_by_file = {}
    files_analyzed_count = len(files_to_review)
    cached_results_used = cache_hits
    groq_requests_made = requests_made
    characters_analyzed_count = characters_sent

    for filename, res_dict in files_reviews_map.items():
        # Reconstruct findings
        general_issues = []
        for item in res_dict.get("inline_comments", []):
            if isinstance(item, dict):
                general_issues.append({
                    "file": filename,
                    "line": int(item.get("line", 1)) if str(item.get("line")).isdigit() else 1,
                    "severity": item.get("severity", "Medium"),
                    "category": item.get("category", "Bug"),
                    "issue": item.get("issue", "Quality or logic concern"),
                    "suggestion": item.get("suggestion", "Please verify this code."),
                    "why_it_matters": item.get("why_it_matters", "No explanation provided."),
                    "risk_level": item.get("risk_level", item.get("severity", "Medium")),
                    "before_code": item.get("before_code", ""),
                    "after_code": item.get("after_code", ""),
                })

        security_issues = []
        for item in res_dict.get("security_findings", []):
            if isinstance(item, dict):
                security_issues.append({
                    "file": filename,
                    "line": int(item.get("line", 1)) if str(item.get("line")).isdigit() else 1,
                    "severity": item.get("severity", "Medium"),
                    "category": "Security",
                    "issue": item.get("issue", "Potential vulnerability found"),
                    "suggestion": item.get("suggestion", "Please verify and secure this code."),
                    "why_it_matters": item.get("why_it_matters", "No explanation provided."),
                    "risk_level": item.get("risk_level", item.get("severity", "Medium")),
                    "before_code": item.get("before_code", ""),
                    "after_code": item.get("after_code", ""),
                })

        smell_issues = []
        for item in res_dict.get("code_smells", []):
            if isinstance(item, dict):
                smell_issues.append({
                    "file": filename,
                    "line": int(item.get("line", 1)) if str(item.get("line")).isdigit() else 1,
                    "severity": item.get("severity", "Low"),
                    "category": "Code Smell",
                    "issue": item.get("issue", "Code quality smell detected"),
                    "suggestion": item.get("suggestion", "Please refactor this code to clean it up."),
                    "why_it_matters": item.get("why_it_matters", "No explanation provided."),
                    "risk_level": item.get("risk_level", item.get("severity", "Low")),
                    "before_code": item.get("before_code", ""),
                    "after_code": item.get("after_code", ""),
                })

        all_findings.extend(security_issues + smell_issues + general_issues)

        # Test suggestions for first scanned file
        if len(test_suggestions_by_file) < 1 and res_dict.get("test_suggestions"):
            test_suggestions_by_file[filename] = res_dict["test_suggestions"]

    # Finalize repository insights structure
    repo_analysis = analyze_repository(
        client=client,
        github_service=github_service,
        repo_name=repo_name,
        qualitative_report=repo_insights or "No qualitative report available."
    )

    # Compute severity counts and Risk Score
    severity_counts = {
        "Critical": 0,
        "High": 0,
        "Medium": 0,
        "Low": 0,
        "Info": 0,
    }
    for f in all_findings:
        sev = f["severity"]
        if sev in severity_counts:
            severity_counts[sev] += 1

    risk_score = min(
        100,
        25 * severity_counts["Critical"]
        + 15 * severity_counts["High"]
        + 6 * severity_counts["Medium"]
        + 1 * severity_counts["Low"]
    )

    # Format Inline Comments
    inline_comments = []
    for f in all_findings:
        body_text = f"""File: {f['file']}
Line: {f['line']}
Issue: {f['issue']}
Severity: {f['severity']}
Recommendation: {f['suggestion']}"""

        inline_comments.append({
            "file": f["file"],
            "line": f["line"],
            "body": body_text,
            "patch": f"@@ -1,1 +1,{f['line']} @@\n+{f['issue']}",
        })

    # Build files_analyzed_log
    files_analyzed_log = []
    for item in tree_items:
        if item.type == "blob":
            path = item.path
            
            ext = os.path.splitext(path)[1].lower()
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
            detected_lang = ext_map.get(ext, "Other")
            file_type = detected_lang
            if ext in [".md", ".txt"]:
                file_type = "Documentation"
            elif ext in [".json", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".xml"]:
                file_type = "Configuration"

            is_source = detected_lang != "Other"
            
            if should_skip_file(path):
                files_analyzed_log.append({
                    "file": path,
                    "type": file_type,
                    "status": "Skipped",
                    "findings": 0
                })
            elif path in scanned_files:
                file_findings_count = len([fn for fn in all_findings if fn["file"] == path])
                files_analyzed_log.append({
                    "file": path,
                    "type": file_type,
                    "status": "Analyzed",
                    "findings": file_findings_count
                })
            elif is_source:
                files_analyzed_log.append({
                    "file": path,
                    "type": file_type,
                    "status": "Scanned",
                    "findings": 0
                })
            else:
                files_analyzed_log.append({
                    "file": path,
                    "type": file_type,
                    "status": "Skipped",
                    "findings": 0
                })

    # Compile Test Suggestions Markdown
    test_suggestions_md = []
    for fn, tests in test_suggestions_by_file.items():
        test_suggestions_md.append(f"### File: {fn}\n{tests}\n")
    test_suggestions_compiled = "\n".join(test_suggestions_md)

    latency = round(time.time() - start_time, 2)
    estimated_tokens_count = characters_analyzed_count // 4

    # Resolve averaged scores across all repository files
    repo_file_scores = [res_dict.get("scores", {}) for res_dict in files_reviews_map.values() if isinstance(res_dict, dict) and "scores" in res_dict]
    overall_repo_scores = resolve_scores(repo_file_scores, risk_score, severity_counts)

    return {
        "repo_name": repo_name,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "risk_score": risk_score,
        "findings": all_findings,
        "inline_comments": inline_comments,
        "test_suggestions": test_suggestions_compiled,
        "repo_analysis": repo_analysis,
        "severity_counts": severity_counts,
        "latency_seconds": latency,
        "total_files_analyzed": len(scanned_files),
        "total_files_count": len(source_files),
        "files_analyzed_log": files_analyzed_log,
        "files_analyzed_count": files_analyzed_count,
        "characters_analyzed_count": characters_analyzed_count,
        "estimated_tokens_count": estimated_tokens_count,
        "groq_requests_made": groq_requests_made,
        "cached_results_used": cached_results_used,
        "scores": overall_repo_scores,
    }

"""Repository analyzer module to evaluate repo health, structure, and hotspots."""

from __future__ import annotations

import sys
import os
import re
from typing import Any
from langsmith import traceable

# Ensure the parent directory is on the search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.prompts import SYSTEM_REPO_PROMPT, build_repo_prompt
from utils.validation import should_skip_file

MODEL_NAME = "llama-3.3-70b-versatile"

@traceable(name="Repository Health Analysis")
def analyze_repository(
    client: Any,
    github_service,
    repo_name: str,
    model_name: str = MODEL_NAME,
    temperature: float = 0.3,
    qualitative_report: str | None = None,
) -> dict[str, object]:
    """Perform a comprehensive repository health analysis by traversing the Git tree."""
    g = github_service.client
    repo = g.get_repo(repo_name)
    default_branch = repo.default_branch

    # 1. Fetch the Git Tree recursively
    tree_items = []
    try:
        branch = repo.get_branch(default_branch)
        sha = branch.commit.sha
        git_tree = repo.get_git_tree(sha=sha, recursive=True)
        tree_items = git_tree.tree
    except Exception as exc:
        print(f"Error fetching repo tree: {exc}")

    # 2. Analyze files from the tree
    files = []
    folders = set()
    large_files = []
    security_hotspots = []
    test_files = []
    source_files = []
    readme_exists = False
    requirements_content = ""

    # Hotspot keywords
    hotspot_keywords = re.compile(
        r"\b(auth|login|password|secret|key|token|db|database|config|credential|jwt|sign|verify)\b",
        re.IGNORECASE,
    )

    for item in tree_items:
        path = item.path
        if should_skip_file(path):
            continue
        if item.type == "tree":
            folders.add(path)
        elif item.type == "blob":
            files.append(item)
            size_kb = (item.size or 0) / 1024
            
            # Check for README
            if os.path.basename(path).lower() in ["readme.md", "readme.txt", "readme"]:
                readme_exists = True
            
            # Check for requirements.txt
            if os.path.basename(path).lower() == "requirements.txt":
                requirements_content = github_service.get_file_content(repo_name, path, default_branch)

            # Categorize source vs tests
            basename = os.path.basename(path).lower()
            is_test = (
                "test" in basename
                or "spec" in basename
                or path.startswith("tests/")
                or path.startswith("test/")
            )
            
            # Check for source file extensions
            is_source = any(
                path.endswith(ext)
                for ext in [
                    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cs",
                    ".go", ".rb", ".php", ".cpp", ".c", ".rs", ".kt", ".swift"
                ]
            )

            if is_test:
                test_files.append(path)
            elif is_source:
                source_files.append(path)
                
                # Check for large files (> 500 KB)
                if size_kb > 500:
                    large_files.append({"path": path, "size_kb": round(size_kb, 2)})

                # Check for security hotspots
                if hotspot_keywords.search(path):
                    security_hotspots.append({"path": path, "size_kb": round(size_kb, 2)})

    # 3. Assess missing tests
    # Basic matching logic: for each source file, look for a test file containing its name
    missing_tests = []
    for src in source_files:
        src_name = os.path.splitext(os.path.basename(src))[0]
        # Ignore files that look like config or entry points
        if src_name in ["setup", "manage", "wsgi", "asgi", "__init__", "app", "main"]:
            continue
        
        has_test = False
        for tst in test_files:
            tst_name = os.path.splitext(os.path.basename(tst))[0]
            if src_name in tst_name or tst_name in src_name:
                has_test = True
                break
        if not has_test:
            missing_tests.append(src)

    # 4. Docstring and documentation coverage estimate
    # We fetch a subset of source files (up to 5 files) to check for docstrings
    sample_files = source_files[:5]
    doc_hits = 0
    total_samples = len(sample_files)
    
    for path in sample_files:
        content = github_service.get_file_content(repo_name, path, default_branch)
        # Check for Python docstrings or JS doc block comments
        if '"""' in content or "'''" in content or "/**" in content or "/*" in content:
            doc_hits += 1

    doc_coverage_pct = round((doc_hits / total_samples) * 100) if total_samples > 0 else 0
    doc_coverage = {
        "readme_exists": readme_exists,
        "sample_checked": total_samples,
        "docstring_coverage_percent": doc_coverage_pct,
    }

    # 5. Format folder structure overview for LLM (depth <= 2)
    folder_tree_lines = []
    # Get top-level structure
    top_level_paths = sorted(list(set(p.split("/")[0] for p in folders | set(f.path for f in files))))
    for p in top_level_paths[:20]: # cap at 20 lines
        is_dir = p in folders
        prefix = "📁 " if is_dir else "📄 "
        folder_tree_lines.append(f"{prefix}{p}")
    folder_tree_str = "\n".join(folder_tree_lines) or "No structure found."

    # 6. Calculate Repository Health Score (0-100)
    # Start at 100 and apply deductions
    score = 100
    deductions = []

    if not readme_exists:
        score -= 20
        deductions.append("Missing README.md (-20)")
    
    if len(test_files) == 0:
        score -= 20
        deductions.append("No test files detected (-20)")
    elif len(missing_tests) > len(source_files) * 0.5:
        score -= 10
        deductions.append("Over 50% of source files lack test cases (-10)")

    if len(large_files) > 0:
        penalty = min(15, len(large_files) * 5)
        score -= penalty
        deductions.append(f"{len(large_files)} large files detected (-{penalty})")

    # Dependency risks check
    dep_risks_desc = "None identified"
    if "requirements.txt" in requirements_content:
        # Simple static checks for old/vulnerable libraries if any
        risky_libraries = ["pycrypto", "requests<2.20.0", "urllib3<1.26.0"]
        found_risky = []
        for lib in risky_libraries:
            if lib in requirements_content.lower():
                found_risky.append(lib)
        if found_risky:
            score -= 10
            deductions.append(f"Outdated/risky dependencies in requirements.txt: {', '.join(found_risky)} (-10)")
            dep_risks_desc = f"Vulnerable dependency patterns found: {', '.join(found_risky)}"
    else:
        dep_risks_desc = "No requirements.txt found or dependencies not specified."

    health_score = max(0, score)

    if qualitative_report is not None:
        analysis_report = qualitative_report
    else:
        # 7. Query LLM to generate qualitative report
        prompt = build_repo_prompt(
            folder_structure=folder_tree_str,
            dependency_risks=requirements_content or dep_risks_desc,
            large_files=large_files[:5],
            security_hotspots=security_hotspots[:5],
            doc_coverage=doc_coverage,
        )

        active_model = "llama-3.3-70b-versatile"
        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_REPO_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                model=active_model,
                temperature=temperature,
            )
            analysis_report = chat_completion.choices[0].message.content
        except Exception as e:
            err_str = str(e).lower()
            if active_model == "llama-3.3-70b-versatile" and "quota" not in err_str and "429" not in err_str:
                try:
                    chat_completion = client.chat.completions.create(
                        messages=[
                            {"role": "system", "content": SYSTEM_REPO_PROMPT},
                            {"role": "user", "content": prompt}
                        ],
                        model="llama-3.1-8b-instant",
                        temperature=temperature,
                    )
                    analysis_report = chat_completion.choices[0].message.content
                except Exception as fallback_e:
                    from reviewer import handle_groq_error
                    raise handle_groq_error(fallback_e)
            else:
                from reviewer import handle_groq_error
                raise handle_groq_error(e)

    # Build directory groups
    directory_groups = {}
    for item in tree_items:
        if item.type == "blob":
            path = item.path
            parts = path.split("/")
            if len(parts) > 1:
                dir_name = parts[0] + "/"
            else:
                dir_name = "root/"
            directory_groups.setdefault(dir_name, []).append(path)

    return {
        "health_score": health_score,
        "deductions": deductions,
        "readme_exists": readme_exists,
        "large_files": large_files,
        "security_hotspots": security_hotspots,
        "missing_tests": missing_tests,
        "test_files_count": len(test_files),
        "source_files_count": len(source_files),
        "docstring_coverage": doc_coverage_pct,
        "analysis_report": analysis_report,
        "directory_groups": directory_groups,
        "folder_structure": folder_tree_str,
        "dependency_risks": requirements_content or dep_risks_desc,
        "doc_coverage": doc_coverage,
    }

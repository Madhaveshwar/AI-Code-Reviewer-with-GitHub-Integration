"""GitHub service layer using PyGithub to fetch PRs, diffs, and post comments."""

from __future__ import annotations

import re
import sys
import os
from github import Github

# Ensure the parent directory is on the search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def parse_repo_url(url: str) -> str | None:
    """Parse a GitHub repository URL or slug into 'owner/repo' format."""
    if not url:
        return None
    url = url.strip()

    # Regex for standard GitHub URLs
    # Matches:
    # https://github.com/owner/repo
    # git@github.com:owner/repo.git
    # owner/repo
    match = re.search(r'(?:github\.com[:/]|git@github\.com:)([^/]+)/([^/.]+)(?:\.git)?', url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"

    # Direct owner/repo split
    parts = [p for p in url.split("/") if p]
    if len(parts) == 2:
        return f"{parts[0]}/{parts[1]}"
    elif len(parts) > 2:
        if "github.com" in parts:
            idx = parts.index("github.com")
            if idx + 2 < len(parts):
                return f"{parts[idx+1]}/{parts[idx+2]}"
        return f"{parts[-2]}/{parts[-1]}"
    return None


class GitHubService:
    """Service class for GitHub API integrations."""

    def __init__(self, token: str | None = None):
        """Initialize the Github client, optionally with a PAT."""
        self.token = token.strip() if token else None
        if self.token:
            self.client = Github(self.token)
        else:
            self.client = Github()  # Unauthenticated, subject to rate limits

    def get_repo_details(self, repo_name: str) -> dict[str, object]:
        """Fetch general metadata about the repository with graceful error handling."""
        from github import GithubException
        try:
            repo = self.client.get_repo(repo_name)
            
            # Check if archived
            is_archived = getattr(repo, "archived", False)
            
            # Check if empty (no default branch)
            is_empty = False
            default_branch = repo.default_branch
            if not default_branch:
                is_empty = True
            
            # Additional check for branch/commit accessibility
            if not is_empty:
                try:
                    repo.get_branch(default_branch)
                except GithubException as ge:
                    if ge.status == 404:
                        is_empty = True
                    else:
                        raise ge

            open_pulls = repo.get_pulls(state="open")
            open_prs_count = open_pulls.totalCount
            
            # Calculate open issues count (open_issues_count includes PRs in PyGithub, so we subtract them)
            total_issues_and_prs = repo.open_issues_count
            open_issues_count = max(0, total_issues_and_prs - open_prs_count)

            return {
                "name": repo.full_name,
                "description": repo.description or "No description provided.",
                "stars": repo.stargazers_count,
                "forks": repo.forks_count,
                "open_prs_count": open_prs_count,
                "open_issues_count": open_issues_count,
                "default_branch": default_branch,
                "languages": repo.get_languages(),
                "archived": is_archived,
                "is_empty": is_empty,
            }
        except GithubException as ge:
            if ge.status == 404:
                raise ValueError("Repository not found. Double check the owner/repo name, or configure a GITHUB_TOKEN in your .env if it is a private repository.")
            elif ge.status == 403:
                raise ValueError("GitHub API rate limit exceeded. Please configure a valid GITHUB_TOKEN in your .env file to run authenticated.")
            else:
                raise ValueError(f"GitHub API Error ({ge.status}): {ge.data.get('message', str(ge))}")

    def get_open_pull_requests(self, repo_name: str) -> list[dict[str, object]]:
        """Fetch all open pull requests for a repository."""
        repo = self.client.get_repo(repo_name)
        pulls = repo.get_pulls(state="open", sort="created", direction="desc")
        pr_list = []
        for pr in pulls:
            pr_list.append({
                "number": pr.number,
                "title": pr.title,
                "author": pr.user.login,
                "created_at": pr.created_at.strftime("%Y-%m-%d"),
            })
        return pr_list

    def get_pr_details(self, repo_name: str, pr_number: int) -> dict[str, object]:
        """Fetch comprehensive details for a specific pull request."""
        repo = self.client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        return {
            "number": pr.number,
            "title": pr.title,
            "author": pr.user.login,
            "files_changed_count": pr.changed_files,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "state": pr.state,
            "head_sha": pr.head.sha,
            "base_sha": pr.base.sha,
            "created_at": pr.created_at.strftime("%Y-%m-%d"),
        }

    def get_pr_files(self, repo_name: str, pr_number: int) -> list[dict[str, object]]:
        """Fetch all files modified in the pull request including their patch diffs."""
        repo = self.client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        files = []
        for f in pr.get_files():
            files.append({
                "filename": f.filename,
                "additions": f.additions,
                "deletions": f.deletions,
                "changes": f.changes,
                "status": f.status,
                "patch": f.patch or "",
                "raw_url": f.raw_url,
            })
        return files

    def get_file_content(self, repo_name: str, path: str, ref: str) -> str:
        """Fetch full content of a file at a specific commit ref or branch."""
        try:
            repo = self.client.get_repo(repo_name)
            content_file = repo.get_contents(path, ref=ref)
            if isinstance(content_file, list):
                return ""  # If it's a directory
            return content_file.decoded_content.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def get_modified_lines(self, patch: str) -> set[int]:
        """Parse a unified diff patch and return the set of added/modified line numbers."""
        if not patch:
            return set()
        modified_lines = set()
        current_line = 0
        hunk_header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

        for line in patch.splitlines():
            match = hunk_header_re.match(line)
            if match:
                current_line = int(match.group(1))
            elif line.startswith("+"):
                modified_lines.add(current_line)
                current_line += 1
            elif line.startswith("-"):
                pass  # Deleted line
            else:
                current_line += 1
        return modified_lines

    def find_diff_position(self, patch: str, target_line: int) -> int | None:
        """Calculate the 1-based diff position index for a target line in the new file.

        The position is the line offset in the diff patch (from the first @@ line).
        """
        if not patch:
            return None

        lines = patch.splitlines()
        diff_line_count = 0
        current_new_line = 0
        first_hunk_found = False

        for line in lines:
            if line.startswith("@@"):
                first_hunk_found = True
                match = re.search(r"\+(\d+)(?:,\d+)?", line)
                if match:
                    current_new_line = int(match.group(1))
                else:
                    current_new_line = 1

            if first_hunk_found:
                diff_line_count += 1

                if not line.startswith("@@"):
                    if not line.startswith("-"):
                        if current_new_line == target_line:
                            return diff_line_count
                        current_new_line += 1
        return None

    def post_comment(self, repo_name: str, pr_number: int, body: str) -> bool:
        """Post a general markdown comment to the pull request discussion page."""
        try:
            repo = self.client.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(body)
            return True
        except Exception:
            return False

    def post_inline_comments(
        self, repo_name: str, pr_number: int, inline_comments: list[dict[str, object]]
    ) -> tuple[int, int]:
        """Post inline review comments onto the pull request changes.

        Returns a tuple (posted_count, failed_count).
        """
        if not self.token:
            return 0, len(inline_comments)

        try:
            repo = self.client.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            commits = list(pr.get_commits())
            if not commits:
                return 0, len(inline_comments)
            latest_commit = commits[-1]

            posted = 0
            failed = 0

            for comment in inline_comments:
                filename = comment.get("file")
                line = comment.get("line")
                body = comment.get("body")

                if not filename or not line or not body:
                    failed += 1
                    continue

                try:
                    # Directly post the comment on the specific file, line, and side of the diff
                    pr.create_review_comment(
                        body=body,
                        commit=latest_commit,
                        path=filename,
                        line=int(line),
                        side="RIGHT"
                    )
                    posted += 1
                except Exception as e:
                    print(f"Failed to post comment for {filename}:{line}: {e}")
                    failed += 1

            return posted, failed
        except Exception as exc:
            print(f"Error posting inline comments: {exc}")
            return 0, len(inline_comments)

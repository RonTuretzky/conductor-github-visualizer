#!/usr/bin/env python3
"""
GitHub Organization Activity Tracker - Data Fetcher

Fetches repository and PR data from a GitHub organization
and outputs JSON for the static 3D visualization.

Usage:
    python fetch_org_data.py [--org ORGANIZATION] [--output FILE]
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


# ============================================================================
# Configuration
# ============================================================================

CONFIG_FILE = Path(__file__).parent / "org_config.json"
OUTPUT_FILE = Path(__file__).parent / "data" / "org_data.json"

DEFAULT_CONFIG = {
    "organization": "BreadchainCoop",
    "stale_minutes": 60,
    "max_repos": 50,
    "fetch_prs": True,
    "fetch_ci": True,
    "ci_cache_pending_seconds": 300,
    "ci_cache_stable_seconds": 900,
    "refresh_interval_minutes": 15,
    "repo_filters": {
        "exclude": [],
        "include_archived": False,
        "min_pushed_days_ago": 365,
    },
}


def load_config() -> dict:
    """Load configuration from org_config.json."""
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                user_config = json.load(f)
                # Deep merge for nested dicts
                for key, value in user_config.items():
                    if isinstance(value, dict) and key in config:
                        config[key].update(value)
                    else:
                        config[key] = value
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load config: {e}", file=sys.stderr)
    return config


def utc_now() -> datetime:
    """Get current time in UTC."""
    return datetime.now(timezone.utc)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class RepoInfo:
    name: str
    full_name: str
    default_branch: str
    html_url: str
    pushed_at: str
    updated_at: str
    description: Optional[str] = None
    is_archived: bool = False


@dataclass
class PRInfo:
    number: int
    title: str
    head_branch: str
    base_branch: str
    author: str
    created_at: str
    updated_at: str
    html_url: str
    ci_status: str = ""
    state: str = "open"
    labels: list = field(default_factory=list)
    draft: bool = False
    mergeable: bool = True


@dataclass
class IssueInfo:
    number: int
    title: str
    author: str
    created_at: str
    updated_at: str
    html_url: str
    state: str = "open"
    labels: list = field(default_factory=list)
    assignees: list = field(default_factory=list)
    comments: int = 0


@dataclass
class CommitInfo:
    sha: str
    short_sha: str
    message: str
    author: str
    date: str
    html_url: str = ""


@dataclass
class TreeNode:
    name: str
    branch: str
    repo_name: str = ""
    pr_number: Optional[int] = None
    pr_title: Optional[str] = None
    pr_url: Optional[str] = None
    pr_author: Optional[str] = None
    last_updated: Optional[str] = None
    ci_status: str = ""
    children: list = field(default_factory=list)
    commits_from_parent: list = field(default_factory=list)
    parent_branch_name: Optional[str] = None
    github_url: str = ""
    is_draft: bool = False
    labels: list = field(default_factory=list)


# ============================================================================
# GitHub API Functions
# ============================================================================

def run_gh_command(args: list, timeout: int = 30) -> Optional[str]:
    """Run a gh CLI command and return stdout."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            if "--json" in args:
                # API calls may fail for permissions or rate limits
                return None
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"Error running gh command: {e}", file=sys.stderr)
        return None


def get_org_repos(org: str, config: dict) -> list[RepoInfo]:
    """Fetch all repositories for an organization."""
    print(f"Fetching repositories for {org}...")

    output = run_gh_command([
        "api", f"orgs/{org}/repos",
        "--paginate",
        "--jq", '.[] | {name, full_name, default_branch, html_url, pushed_at, updated_at, description, archived}'
    ])

    if not output:
        print(f"Failed to fetch repos for {org}", file=sys.stderr)
        return []

    repos = []
    filters = config.get("repo_filters", {})
    exclude_list = filters.get("exclude", [])
    include_archived = filters.get("include_archived", False)
    min_pushed_days = filters.get("min_pushed_days_ago", 365)
    max_repos = config.get("max_repos", 50)

    cutoff_date = utc_now() - timedelta(days=min_pushed_days)

    for line in output.strip().split('\n'):
        if not line:
            continue
        try:
            data = json.loads(line)

            # Apply filters
            if data["name"] in exclude_list:
                continue
            if data.get("archived", False) and not include_archived:
                continue

            # Check pushed_at date
            if data.get("pushed_at"):
                pushed_at = datetime.fromisoformat(data["pushed_at"].replace("Z", "+00:00"))
                if pushed_at < cutoff_date:
                    continue

            repos.append(RepoInfo(
                name=data["name"],
                full_name=data["full_name"],
                default_branch=data.get("default_branch", "main"),
                html_url=data["html_url"],
                pushed_at=data.get("pushed_at", ""),
                updated_at=data.get("updated_at", ""),
                description=data.get("description"),
                is_archived=data.get("archived", False),
            ))
        except json.JSONDecodeError:
            continue

    # Sort by pushed_at descending (most recently active first)
    repos.sort(key=lambda r: r.pushed_at or "", reverse=True)

    # Limit number of repos
    if len(repos) > max_repos:
        print(f"Limiting to {max_repos} most recently active repos (from {len(repos)} total)")
        repos = repos[:max_repos]

    print(f"Found {len(repos)} active repositories")
    return repos


def get_repo_prs(repo_full_name: str) -> list[PRInfo]:
    """Fetch open PRs for a repository."""
    output = run_gh_command([
        "pr", "list",
        "--repo", repo_full_name,
        "--state", "open",
        "--json", "number,title,headRefName,baseRefName,author,createdAt,updatedAt,url,state,labels,isDraft,mergeable"
    ])

    if not output:
        return []

    try:
        prs_data = json.loads(output)
        prs = []
        for pr in prs_data:
            labels = [l.get("name", "") for l in pr.get("labels", [])]
            prs.append(PRInfo(
                number=pr["number"],
                title=pr["title"],
                head_branch=pr["headRefName"],
                base_branch=pr["baseRefName"],
                author=pr.get("author", {}).get("login", "unknown"),
                created_at=pr.get("createdAt", ""),
                updated_at=pr.get("updatedAt", ""),
                html_url=pr.get("url", ""),
                state=pr.get("state", "open"),
                labels=labels,
                draft=pr.get("isDraft", False),
                mergeable=pr.get("mergeable") != "CONFLICTING",
            ))
        return prs
    except json.JSONDecodeError:
        return []


def get_repo_issues(repo_full_name: str) -> list[IssueInfo]:
    """Fetch open issues for a repository (excludes PRs)."""
    output = run_gh_command([
        "issue", "list",
        "--repo", repo_full_name,
        "--state", "open",
        "--json", "number,title,author,createdAt,updatedAt,url,state,labels,assignees,comments"
    ])

    if not output:
        return []

    try:
        issues_data = json.loads(output)
        issues = []
        for issue in issues_data:
            labels = [l.get("name", "") for l in issue.get("labels", [])]
            assignees = [a.get("login", "") for a in issue.get("assignees", [])]
            issues.append(IssueInfo(
                number=issue["number"],
                title=issue["title"],
                author=issue.get("author", {}).get("login", "unknown"),
                created_at=issue.get("createdAt", ""),
                updated_at=issue.get("updatedAt", ""),
                html_url=issue.get("url", ""),
                state=issue.get("state", "open"),
                labels=labels,
                assignees=assignees,
                comments=issue.get("comments", 0),
            ))
        return issues
    except json.JSONDecodeError:
        return []


def get_pr_ci_status(repo_full_name: str, pr_number: int) -> str:
    """Get CI status for a PR."""
    output = run_gh_command([
        "pr", "checks", str(pr_number),
        "--repo", repo_full_name,
        "--json", "bucket"
    ])

    if not output:
        return ""

    try:
        checks = json.loads(output)
        if not checks:
            return ""

        has_fail = any(c.get("bucket") == "fail" for c in checks)
        has_pending = any(c.get("bucket") == "pending" for c in checks)
        has_pass = any(c.get("bucket") == "pass" for c in checks)

        if has_fail:
            return "fail"
        elif has_pending:
            return "pending"
        elif has_pass:
            return "pass"
        return ""
    except json.JSONDecodeError:
        return ""


def get_commits_between_branches(
    repo_full_name: str,
    base_branch: str,
    head_branch: str,
    max_commits: int = 10
) -> list[dict]:
    """Get commits between two branches using GitHub API."""
    # Include author avatar URL in the query
    output = run_gh_command([
        "api", f"repos/{repo_full_name}/compare/{base_branch}...{head_branch}",
        "--jq", '.commits[:10] | .[] | {sha: .sha, message: .commit.message, author: .commit.author.name, date: .commit.author.date, html_url: .html_url, author_login: .author.login, author_avatar_url: .author.avatar_url}'
    ])

    if not output:
        return []

    commits = []
    for line in output.strip().split('\n'):
        if not line:
            continue
        try:
            data = json.loads(line)
            commits.append({
                "sha": data["sha"],
                "short_sha": data["sha"][:7],
                "message": data["message"].split('\n')[0][:80],
                "author": data.get("author") or "",
                "author_login": data.get("author_login") or "",
                "author_avatar_url": data.get("author_avatar_url") or "",
                "date": data["date"][:10],
                "html_url": data["html_url"],
            })
        except json.JSONDecodeError:
            continue

    return commits[:max_commits]


# ============================================================================
# Hierarchy Building
# ============================================================================

def build_repo_tree(
    repo: RepoInfo,
    prs: list[PRInfo],
    fetch_commits: bool = True
) -> dict:
    """Build a tree structure for a repository's PRs."""

    # PR lookup: head_branch -> PR info
    pr_lookup = {pr.head_branch: pr for pr in prs}

    # Create root node for repo (representing default branch)
    root = TreeNode(
        name=repo.name,
        branch=repo.default_branch,
        repo_name=repo.name,
        github_url=repo.html_url,
        last_updated=repo.pushed_at,
    )

    nodes: dict[str, TreeNode] = {}

    # Create nodes for each PR
    for pr in prs:
        node = TreeNode(
            name=pr.title[:60] if len(pr.title) > 60 else pr.title,
            branch=pr.head_branch,
            repo_name=repo.name,
            pr_number=pr.number,
            pr_title=pr.title,
            pr_url=pr.html_url,
            pr_author=pr.author,
            last_updated=pr.updated_at,
            ci_status=pr.ci_status,
            github_url=repo.html_url,
            is_draft=pr.draft,
            labels=pr.labels,
        )
        nodes[pr.head_branch] = node

    # Add intermediate PR branches (PRs that target other PRs)
    branches_to_add = set()
    for branch in list(nodes.keys()):
        current = branch
        visited = set()
        while current in pr_lookup and current not in visited:
            visited.add(current)
            parent_branch = pr_lookup[current].base_branch
            if parent_branch not in nodes and parent_branch != repo.default_branch:
                branches_to_add.add(parent_branch)
            current = parent_branch

    for branch in branches_to_add:
        pr = pr_lookup.get(branch)
        if pr:
            node = TreeNode(
                name=f"({pr.title[:40]}...)" if len(pr.title) > 40 else f"({pr.title})",
                branch=branch,
                repo_name=repo.name,
                pr_number=pr.number,
                pr_title=pr.title,
                pr_url=pr.html_url,
                ci_status=pr.ci_status,
                github_url=repo.html_url,
            )
            nodes[branch] = node

    # Build parent-child relationships
    attached = set()
    for branch, node in nodes.items():
        pr = pr_lookup.get(branch)
        if pr:
            parent_branch = pr.base_branch
            if parent_branch in nodes:
                nodes[parent_branch].children.append(node)
                attached.add(branch)
                node.parent_branch_name = parent_branch
            elif parent_branch == repo.default_branch:
                node.parent_branch_name = repo.default_branch

    # Attach unattached nodes to root
    for branch, node in nodes.items():
        if branch not in attached:
            root.children.append(node)
            if not node.parent_branch_name:
                node.parent_branch_name = repo.default_branch

    # Fetch commits for branches (optional, can be slow)
    if fetch_commits:
        for branch, node in nodes.items():
            if node.parent_branch_name:
                try:
                    commits = get_commits_between_branches(
                        repo.full_name,
                        node.parent_branch_name,
                        branch,
                        max_commits=5
                    )
                    node.commits_from_parent = commits
                except Exception:
                    pass  # Skip commits on error

    return tree_node_to_dict(root)


def tree_node_to_dict(node: TreeNode) -> dict:
    """Convert TreeNode to serializable dict."""
    return {
        "name": node.name,
        "branch": node.branch,
        "repo_name": node.repo_name,
        "pr_number": node.pr_number,
        "pr_title": node.pr_title,
        "pr_url": node.pr_url,
        "pr_author": node.pr_author,
        "last_updated": node.last_updated,
        "ci_status": node.ci_status,
        "github_url": node.github_url,
        "is_draft": node.is_draft,
        "labels": node.labels,
        "commits_from_parent": node.commits_from_parent,
        "parent_branch_name": node.parent_branch_name,
        "children": [tree_node_to_dict(child) for child in node.children],
    }


# ============================================================================
# Main Data Fetching
# ============================================================================

def fetch_org_data(config: dict) -> dict:
    """Fetch all data for an organization."""
    org = config["organization"]
    fetch_prs = config.get("fetch_prs", True)
    fetch_ci = config.get("fetch_ci", True)
    fetch_issues = config.get("fetch_issues", True)

    start_time = time.time()

    # Get all repos
    repos = get_org_repos(org, config)
    if not repos:
        return {"error": f"No repositories found for {org}"}

    trees = {}
    issues_by_repo = {}
    total_prs = 0
    total_issues = 0

    for i, repo in enumerate(repos):
        print(f"[{i+1}/{len(repos)}] Processing {repo.name}...")

        # Get PRs for this repo
        if fetch_prs:
            prs = get_repo_prs(repo.full_name)

            # Get CI status for each PR
            if fetch_ci and prs:
                for pr in prs:
                    pr.ci_status = get_pr_ci_status(repo.full_name, pr.number)
                    time.sleep(0.1)  # Small delay to avoid rate limits

            total_prs += len(prs)
        else:
            prs = []

        # Get issues for this repo
        if fetch_issues:
            issues = get_repo_issues(repo.full_name)
            if issues:
                issues_by_repo[repo.name] = {
                    "repo_name": repo.name,
                    "github_url": repo.html_url,
                    "issues": [
                        {
                            "number": issue.number,
                            "title": issue.title,
                            "author": issue.author,
                            "created_at": issue.created_at,
                            "updated_at": issue.updated_at,
                            "html_url": issue.html_url,
                            "labels": issue.labels,
                            "assignees": issue.assignees,
                            "comments": issue.comments,
                        }
                        for issue in issues
                    ]
                }
                total_issues += len(issues)

        # Build tree for this repo (only if it has PRs)
        if prs:
            fetch_commits = config.get("fetch_commits", True)
            tree = build_repo_tree(repo, prs, fetch_commits=fetch_commits)
            trees[repo.name] = tree

    elapsed = time.time() - start_time

    result = {
        "organization": org,
        "generated_at": utc_now().isoformat(),
        "generation_time_seconds": round(elapsed, 2),
        "stats": {
            "total_repos": len(repos),
            "repos_with_prs": len(trees),
            "repos_with_issues": len(issues_by_repo),
            "total_open_prs": total_prs,
            "total_open_issues": total_issues,
        },
        "trees": trees,
        "issues": issues_by_repo,
        "stale_minutes": config.get("stale_minutes", 60),
    }

    print(f"\nCompleted in {elapsed:.1f}s")
    print(f"Repos processed: {len(repos)}")
    print(f"Repos with open PRs: {len(trees)}")
    print(f"Total open PRs: {total_prs}")
    print(f"Repos with open issues: {len(issues_by_repo)}")
    print(f"Total open issues: {total_issues}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Fetch GitHub organization data for activity tracker"
    )
    parser.add_argument(
        "--org", type=str,
        help="GitHub organization name (overrides config)"
    )
    parser.add_argument(
        "--output", type=str,
        help="Output JSON file path"
    )
    parser.add_argument(
        "--no-commits", action="store_true",
        help="Skip fetching commit data (faster)"
    )

    args = parser.parse_args()

    # Load config
    config = load_config()

    # Override from CLI args
    if args.org:
        config["organization"] = args.org

    # Determine output path
    output_path = Path(args.output) if args.output else OUTPUT_FILE

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Fetch data
    print(f"GitHub Organization Activity Tracker")
    print(f"=" * 40)
    print(f"Organization: {config['organization']}")
    print()

    data = fetch_org_data(config)

    # Write output
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\nData written to: {output_path}")


if __name__ == "__main__":
    main()

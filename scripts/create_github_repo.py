#!/usr/bin/env python3
"""Create the GitHub repository and push the milestone-based commit history.

Reads configuration from `.secrets` (gitignored). Run:

    1. cp .secrets.example .secrets
    2. Fill in GITHUB_PAT, GITHUB_OWNER, GITHUB_REPO in .secrets
    3. python3 scripts/create_github_repo.py
"""

from __future__ import annotations

import configparser
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SECRETS_FILE = REPO_DIR / ".secrets"
GITHUB_API = "https://api.github.com"


def load_secrets() -> dict[str, str]:
    """Load secrets from .secrets file (KEY=value format, # comments)."""
    if not SECRETS_FILE.exists():
        print(f"ERROR: {SECRETS_FILE} not found.")
        print("Run: cp .secrets.example .secrets")
        sys.exit(1)
    cfg: dict[str, str] = {}
    for line in SECRETS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip().strip("'\"")
    return cfg


def gh_api(method: str, path: str, token: str, body: dict | None = None) -> dict:
    """Call the GitHub REST API."""
    url = f"{GITHUB_API}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return {"status": resp.status, "body": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        return {"status": e.code, "body": parsed, "error": parsed.get("message", raw[:200])}


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the repo directory."""
    return subprocess.run(
        ["git", *args], cwd=REPO_DIR, capture_output=True, text=True, check=check,
    )


def main() -> None:
    cfg = load_secrets()
    token = cfg.get("GITHUB_PAT", "")
    owner = cfg.get("GITHUB_OWNER", "")
    repo = cfg.get("GITHUB_REPO", "surp-router")
    visibility = cfg.get("GITHUB_VISIBILITY", "public").lower()

    missing = [k for k, v in [("GITHUB_PAT", token), ("GITHUB_OWNER", owner)] if not v]
    if missing:
        print(f"ERROR: missing required fields in .secrets: {', '.join(missing)}")
        print(f"Edit {SECRETS_FILE} and fill them in.")
        sys.exit(1)

    if not token.startswith(("github_pat_", "ghp_")):
        print("WARNING: GITHUB_PAT doesn't look like a GitHub token (should start with github_pat_ or ghp_).")

    # 1. Create the repository on GitHub
    print(f"\n1. Creating GitHub repository {owner}/{repo} ({visibility})...")
    body = {
        "name": repo,
        "description": "x402-paywalled LLM gateway — cheapest AI inference on the internet. Pay per request in USDC on Base. No account, no API key.",
        "private": visibility == "private",
        "has_issues": True,
        "has_wiki": False,
        "auto_init": False,
    }
    res = gh_api("POST", "/user/repos", token, body)
    if res["status"] == 201:
        clone_url = res["body"].get("clone_url") or res["body"].get("html_url")
        ssh_url = res["body"].get("ssh_url")
        print(f"   ✓ created: {res['body'].get('html_url')}")
    elif res["status"] == 422 and "already exists" in str(res.get("error", "")):
        clone_url = f"https://github.com/{owner}/{repo}.git"
        ssh_url = f"git@github.com:{owner}/{repo}.git"
        print(f"   ℹ repository already exists, will push to it")
    else:
        print(f"   ✗ failed to create repo: {res['status']} {res.get('error', res['body'])}")
        sys.exit(1)

    # 2. Configure git remote
    remote_url = f"https://{owner}:{token}@github.com/{owner}/{repo}.git"
    print(f"\n2. Configuring git remote...")
    remotes = git("remote", check=False).stdout
    if "origin" in remotes:
        git("remote", "set-url", "origin", remote_url)
        print("   ✓ updated existing origin")
    else:
        git("remote", "add", "origin", remote_url)
        print("   ✓ added origin")

    # 3. Push all branches and tags
    print(f"\n3. Pushing commits to GitHub...")
    push = git("push", "-u", "origin", "main", check=False)
    if push.returncode != 0:
        print(f"   pushing main:\n{push.stderr}")
        # Try pushing tags separately
        git("push", "origin", "--tags", check=False)
    else:
        print("   ✓ pushed main")
        git("push", "origin", "--tags", check=False)

    html_url = f"https://github.com/{owner}/{repo}"
    print(f"\n✓ done. Your repo is live at: {html_url}")
    print(f"  commits: {git('rev-list', '--count', 'HEAD').stdout.strip()}")
    print(f"  tags: {len(git('tag', '-l').stdout.strip().splitlines())}")


if __name__ == "__main__":
    main()

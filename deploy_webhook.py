#!/usr/bin/env python3
"""GitHub webhook receiver: triggers auto-deploy on push to main.

Security:
  - Validates X-Hub-Signature-256 (HMAC-SHA256) so only GitHub can trigger deploys.
  - Only acts on push events to refs/heads/main (covers PR merges + direct pushes).
  - Spawns deploy.sh detached (start_new_session) so it survives this process.

Routes:
  POST /webhook/github   — GitHub push webhook
  GET  /webhook/health   — liveness probe for the receiver itself
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
from aiohttp import web

SECRET = os.environ.get("SURP_WEBHOOK_SECRET", "")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
DEPLOY_SCRIPT = os.path.join(REPO_DIR, "scripts", "deploy.sh")
LOG_FILE = "/var/log/surp-deploy.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] surp-deploy: %(message)s",
)
log = logging.getLogger("surp-deploy")

if not SECRET:
    log.warning("SURP_WEBHOOK_SECRET not set — all webhooks will be rejected")


def _valid_signature(body: bytes, sig_header: str) -> bool:
    """Validate GitHub webhook signature (HMAC-SHA256)."""
    if not SECRET or not sig_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig_header, expected)


async def github_webhook(request: web.Request) -> web.Response:
    """Handle GitHub push webhook — trigger deploy if push to main."""
    body = await request.read()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not _valid_signature(body, sig):
        log.warning("rejected webhook: invalid signature from %s",
                    request.remote)
        return web.json_response({"error": "invalid signature"}, status=401)

    event = request.headers.get("X-GitHub-Event", "")

    # GitHub sends a ping event when the webhook is first configured.
    if event == "ping":
        log.info("ping received — webhook configured correctly")
        return web.json_response({"ok": "pong", "message": "webhook configured"})

    if event != "push":
        return web.json_response({"ok": True, "ignored": True, "event": event})

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid JSON"}, status=400)

    ref = payload.get("ref", "")
    if ref != "refs/heads/main":
        return web.json_response({"ok": True, "ignored": True, "ref": ref})

    head = payload.get("after", "")[:7]
    pusher = payload.get("pusher", {}).get("name", "unknown")
    commits = len(payload.get("commits", []))
    log.info("push to main by %s: %s (%d commits) — triggering deploy",
             pusher, head, commits)

    try:
        # Spawn deploy script detached — survives this process and the
        # gateway restart that deploy.sh will trigger.
        subprocess.Popen(
            ["bash", DEPLOY_SCRIPT],
            stdout=open(LOG_FILE, "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as e:
        log.error("failed to spawn deploy: %s", e)
        return web.json_response(
            {"error": f"deploy spawn failed: {e}"}, status=500
        )

    return web.json_response({
        "ok": True,
        "deploying": True,
        "head": head,
        "pusher": pusher,
        "commits": commits,
        "log": LOG_FILE,
    })


async def health(request: web.Request) -> web.Response:
    """Liveness probe for the webhook receiver itself."""
    return web.json_response({
        "ok": True,
        "service": "surp-deploy",
        "secret_configured": bool(SECRET),
    })


def main() -> None:
    app = web.Application(client_max_size=10 * 1024 * 1024)
    app.router.add_post("/webhook/github", github_webhook)
    app.router.add_get("/webhook/health", health)
    log.info("starting surp-deploy webhook receiver on 127.0.0.1:20131")
    web.run_app(app, host="127.0.0.1", port=20131, access_log=None)


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# Auto-deploy script: triggered by GitHub webhook on push to main.
#
# Flow: fetch → reset to origin/main → run tests → restart services →
#       health check → roll back on failure.
#
# Safety rails:
#   1. Lock file prevents concurrent deploys.
#   2. Test gate: if tests fail, roll back and DON'T restart (old code keeps running).
#   3. Health check: if services die after restart, roll back to previous commit.
#   4. All output logged to /var/log/surp-deploy.log.
set -uo pipefail

REPO=/root/.hermes/surp-router
LOG=/var/log/surp-deploy.log
LOCK=/tmp/surp-deploy.lock

cd "$REPO" || { echo "[$(date -u +%FT%TZ)] FATAL: cannot cd to $REPO" >> "$LOG"; exit 1; }

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG"; }

# Prevent concurrent deploys
if [ -f "$LOCK" ]; then
    log "deploy already running (lock exists), skipping"
    exit 0
fi
trap 'rm -f "$LOCK"' EXIT
touch "$LOCK"

PREV=$(git rev-parse HEAD)
log "── deploy started (prev=${PREV:0:7}) ──"

# Fetch + reset to origin/main (forces local tree to match remote)
if ! git fetch origin main >>"$LOG" 2>&1; then
    log "✗ git fetch failed — check network or PAT expiry"
    exit 1
fi
git reset --hard origin/main >>"$LOG" 2>&1
NEW=$(git rev-parse HEAD)

if [ "$PREV" = "$NEW" ]; then
    log "no changes, already at ${NEW:0:7}"
    exit 0
fi
log "pulled: ${NEW:0:7} (was ${PREV:0:7})"

# Dependency + test gate — fail fast, don't touch running services
. venv/bin/activate
if [ -f requirements.txt ]; then
    if ! python -m pip install -r requirements.txt >>"$LOG" 2>&1; then
        log "✗ DEPENDENCY INSTALL FAILED — rolling back to ${PREV:0:7}"
        git reset --hard "$PREV" >>"$LOG" 2>&1
        exit 1
    fi
fi
if ! PYTHONPATH=. pytest tests/ -q >>"$LOG" 2>&1; then
    log "✗ TESTS FAILED — rolling back to ${PREV:0:7}"
    git reset --hard "$PREV" >>"$LOG" 2>&1
    # Don't restart — old code is still running
    exit 1
fi
log "✓ tests passed ($(PYTHONPATH=. pytest tests/ -q 2>&1 | tail -1))"

# Restart services
log "restarting surp-resolver + surp-gateway..."
systemctl restart surp-resolver surp-gateway >>"$LOG" 2>&1
sleep 5

# Health check — are the services alive?
if ! systemctl is-active --quiet surp-gateway surp-resolver; then
    log "✗ SERVICES DIED after restart — rolling back to ${PREV:0:7}"
    git reset --hard "$PREV" >>"$LOG" 2>&1
    systemctl restart surp-resolver surp-gateway >>"$LOG" 2>&1
    sleep 3
    if systemctl is-active --quiet surp-gateway surp-resolver; then
        log "rolled back to ${PREV:0:7} and restarted — services healthy"
    else
        log "✗✗ ROLLBACK ALSO FAILED — manual intervention required"
    fi
    exit 1
fi

# HTTP health check (services active, but can they serve?)
if curl -sf --max-time 10 https://surp.ivc.lol/ -o /dev/null 2>/dev/null; then
    log "✓ HTTP health check passed"
else
    log "⚠ HTTP health check failed (services active — may be warming up)"
fi

log "── deploy successful: ${NEW:0:7} ──"

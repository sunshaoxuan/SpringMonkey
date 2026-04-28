# Repo Sync Timer Baseline

Date: 2026-04-23 (Asia/Tokyo)

## Goal

Allow the OpenClaw host to discover and pull new SpringMonkey commits automatically, without waiting for a manual `git pull`.

## Current Mechanism

Installer:

- `scripts/remote_install_repo_sync_timer.py`

Installed units:

- `openclaw-repo-sync.service`
- `openclaw-repo-sync.timer`

Current schedule:

- `OnBootSec=8min`
- `OnUnitActiveSec=10min`
- `Persistent=true`

## What It Does (current script in `remote_install_repo_sync_timer.py`)

Each run (as `root`):

1. If the worktree is dirty, `git stash push -u` (same family of behavior as `remote_springmonkey_git_pull.py`) so fetch/merge is not blocked.
2. If the current branch is not `main`, `git checkout main` (aligns with `INTENT_TOOL_ROUTING_AND_ACCUMULATION.md`: avoid staying on `bot/openclaw` and missing `main` updates).
3. `git fetch origin --prune`
4. `git merge --ff-only origin/main` — **no** non-fast-forward merge on the timer; if the host has diverged, the unit fails and the log shows the error (operator must repair or reset after review).
5. Append full transcript to `/var/log/openclaw/repo-sync.log`

**Upgrading an existing host:** re-run `python3 scripts/remote_install_repo_sync_timer.py` from a machine with SSH access so `/usr/local/lib/openclaw/repo_sync_springmonkey.sh` is replaced with the new script.

## How to Verify It Is Running

On the gateway host:

```bash
systemctl is-enabled openclaw-repo-sync.timer
systemctl list-timers --all | grep -F openclaw-repo-sync
tail -n 50 /var/log/openclaw/repo-sync.log
```

Optional: `journalctl -u openclaw-repo-sync.service -n 30 --no-pager` (the script logs mainly to the file above).

## Important Boundary

This timer only syncs the repository checkout.

It does **not** automatically:

- restart `openclaw.service`
- re-apply runtime `dist/*.js` patch installers

So it is immediately effective for:

- repo-managed task scripts
- documentation
- host-side helper scripts copied from repo later by dedicated installers

But runtime patch changes still require:

- a manual installer run
- or a restart path where startup guards replay the patch

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

## What It Does

Every cycle it will:

1. `git fetch origin --prune`
2. `git merge --no-edit origin/main`
3. append status to `/var/log/openclaw/repo-sync.log`

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

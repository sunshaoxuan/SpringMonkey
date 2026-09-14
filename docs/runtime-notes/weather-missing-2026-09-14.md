# Missing morning weather report

The authoritative weather schedule is `/etc/cron.d/openclaw-direct-discord`, daily at 07:00 on the host. The disabled OpenClaw cron entry was replaced by this direct task and must stay disabled to avoid duplicate delivery.

The September 14 direct-task record starts at 07:00:01 and ends at 07:00:42 with return code 1 and zero public messages. Weather data was available. The image workflow returned a text report after swallowing the image exception. The public delivery gate requires model PNG images, so it withheld the text result and attempted an owner-DM failure notification.

The image workflow now preserves the underlying exception in stderr for private operational diagnosis. The regression test requires the failed source reason to be retained. The historical generation exception cannot be reconstructed from the original record; the later live generation succeeded.

Live reproduction generated all three city images successfully with the configured model. A second independent defect was verified in the installed public delivery gate: it requires `_image2.png`, while the producer and repository installer use `_model.png`. `scripts/weather/repair_delivery_gate.py` atomically updates only that function's legacy suffix, preserves ownership and permissions, refuses unknown gate formats, and is idempotent. File existence and minimum byte-size checks remain required. Rollback: restore the prior helper from the host backup; the old suffix will again reject current images, so use only for reverting an incorrect migration.

Read task logs through a field allowlist. The installed direct runner includes environment-bearing command arguments in its log; command fields must never be printed or copied into investigation artifacts.

## Acceptance

- Weather tests: 25 passed. Gate migration and installer tests: 9 passed. `git diff --check` passed.
- Production deployed `3b30e7b`. Migration returned `GATE=repaired` followed by `GATE=current` on the second invocation.
- Backup: `/usr/local/lib/openclaw/direct_cron_to_discord.py.weather-gate-20260914.bak`.
- Live generation produced three 1024x1024 model PNG files for Tokyo, Beijing and Dalian. All were viewed locally and passed the production artifact gate.
- The original Discord channel received three images at 21:40 JST. An independent Discord messages read returned three matching attachments, message IDs `1549037027138469960`, `1549037035921342505`, and `1549037047984029757`.
- These were regenerated using current September 14 data, not recovered historical morning images.
- Host timezone is `Asia/Tokyo`; cron is active; the existing daily 07:00 entry remains in place. The next automatic scheduled execution has not yet occurred.

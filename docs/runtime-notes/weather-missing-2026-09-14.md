# Missing morning weather report

The authoritative weather schedule is `/etc/cron.d/openclaw-direct-discord`, daily at 07:00 on the host. The disabled OpenClaw cron entry was replaced by this direct task and must stay disabled to avoid duplicate delivery.

The September 14 direct-task record starts at 07:00:01 and ends at 07:00:42 with return code 1 and zero public messages. Weather data was available. The image workflow returned a text report after swallowing the image exception. The public delivery gate requires model PNG images, so it withheld the text result and attempted an owner-DM failure notification.

The image workflow now preserves the underlying exception in stderr for private operational diagnosis. The regression test requires the failed source reason to be retained. Image-service reproduction and production acceptance are pending.

Live reproduction generated all three city images successfully with the configured model. A second independent defect was verified in the installed public delivery gate: it requires `_image2.png`, while the producer and repository installer use `_model.png`. `scripts/weather/repair_delivery_gate.py` atomically updates only that function's legacy suffix, preserves ownership and permissions, refuses unknown gate formats, and is idempotent. File existence and minimum byte-size checks remain required. Rollback: restore the prior helper from the host backup; the old suffix will again reject current images, so use only for reverting an incorrect migration.

Read task logs through a field allowlist. The installed direct runner includes environment-bearing command arguments in its log; command fields must never be printed or copied into investigation artifacts.

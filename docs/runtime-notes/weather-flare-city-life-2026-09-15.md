# Weather city-life images with Flare

Request: use `gpt-image-2.5-flare`, restore cute proportions, and adapt the supplied busy daytime miniature-neighborhood reference to the existing three-city weather pipeline.

The default and installer select only `openai/gpt-image-2.5-flare`. Prompts describe connected neighborhood streets, cafes, breakfast stalls, buses, commuters and modest local architecture. Local landmarks are contextual rather than oversized central towers. Actual city weather overrides the sunny reference; city labels, date and daily temperature range retain their existing data contract.

The request specifies 1024x1024; the first live Flare response was 1254x1254. Larger square PNGs are uniformly downsampled with Pillow LANCZOS to 1024x1024, preserving the entire composition. Native 1024x1024 bytes remain unchanged. Non-square and undersized images are rejected. Removed legacy crop, padding and horizontal-only resize implementations. This prevents postprocessing distortion; it cannot alone guarantee that the model draws correct object proportions. Install Pillow as specified in `scripts/weather/requirements.txt`, or the compatible distribution `python3-pil` package, before activation. Both activation and the installer check the required Pillow API before changing cron.

## Acceptance

- Implementation commit: `28a3f27`, pushed to origin and fast-forwarded on production from `1aaeb4d`.
- Local weather and installer regression suite: 41 passed. Includes activation backup/idempotence and pixel-for-pixel comparison with uniform LANCZOS resizing.
- Three live city images generated using the existing local Sub2API bridge and exact model ID. All returned 1254x1254 and were uniformly reduced to 1024x1024. Forecasts, actual prompts and file hashes are in `docs/evidence/weather-flare-20260915/local-generation.json`.
- Primary visual review: all three show miniature people, vehicles, shops and layered city scenes without apparent directional stretching. City labels, date and temperature ranges are legible. Exact incidental signage and geographic placement remain generative details.
- Gemini Pro and Flash image-review requests both returned no available accounts; no external visual approval is claimed.
- Production Pillow 11.3.0 installed through the distribution package. Actual installed public delivery gate accepted all three images. Activation returned `flare`, then `already-flare` on repeat.
- Cron is active at 07:00 Asia/Tokyo daily, selecting only `openai/gpt-image-2.5-flare`. No unrelated job schedule or provider routing changes were made. See `docs/evidence/weather-flare-20260915/deployment.json`.
- A fresh catalog read on the production endpoint also lists the exact model. Production-account live generation using the installed source and formal media directory succeeded for Tokyo at 1024x1024, passed the installed delivery gate and primary visual inspection. See `docs/evidence/weather-flare-20260915/production-smoke.json`.
- The first production smoke used a temporary output directory that disappeared while the model request was running, causing a save failure. The repeat used the existing formal weather media directory and completed successfully. Production three-city generation was not rerun; the three-city live sample was generated through the existing local bridge, and the installed production generator was additionally verified with one live city.

Validation commands: `python -m pytest scripts/weather scripts/test_remote_install_direct_discord_cron.py -q -p no:cacheprovider --basetemp=.task-tmp/weather-flare/pytest-acceptance` (41 passed); evidence validation checked actual PNG dimensions, SHA-256 hashes, model IDs, prompt data contracts and deployment fields. The initial default pytest temporary directory was inaccessible on Windows; task-local test directories resolved it. Local temporary-directory cleanup was rejected by the execution policy. The task-owned `.task-tmp/flare-tests`, `.task-tmp/flare-tests-final` and `.task-tmp/weather-flare` directories remain untracked; no bypass was attempted.

No extra public-channel weather message was sent during these checks. The next scheduled delivery remains subject to upstream model and weather-data availability.

Rollback: restore the prior weather source commit and the backed-up weather cron entry, then verify the previous generator and public delivery gate together.

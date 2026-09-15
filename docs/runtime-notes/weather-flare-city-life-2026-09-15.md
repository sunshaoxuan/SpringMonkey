# Weather city-life images with Flare

Request: use `gpt-image-2.5-flare`, restore cute proportions, and adapt the supplied busy daytime miniature-neighborhood reference to the existing three-city weather pipeline.

The default and installer select only `openai/gpt-image-2.5-flare`. Prompts describe connected neighborhood streets, cafes, breakfast stalls, buses, commuters and modest local architecture. Local landmarks are contextual rather than oversized central towers. Actual city weather overrides the sunny reference; city labels, date and daily temperature range retain their existing data contract.

The request specifies 1024x1024; the first live Flare response was 1254x1254. Larger square PNGs are uniformly downsampled with Pillow LANCZOS to 1024x1024, preserving the entire composition. Native 1024x1024 bytes remain unchanged. Non-square and undersized images are rejected. Removed legacy crop, padding and horizontal-only resize implementations. This prevents postprocessing distortion; it cannot alone guarantee that the model draws correct object proportions. Install Pillow as specified in `scripts/weather/requirements.txt`, or the compatible distribution `python3-pil` package, before activation. Both activation and the installer check the required Pillow API before changing cron.

Production switch requires a fresh model catalog read, successful three-city generation, visual inspection, and runtime cron verification. Pending at implementation time. No unrelated job schedule or provider routing changes are included.

Rollback: restore the prior weather source commit and the backed-up weather cron entry, then verify the previous generator and public delivery gate together.

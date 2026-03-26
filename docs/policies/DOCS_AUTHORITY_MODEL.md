# Docs Authority Model

## Source Of Truth Layers

1. Live host configuration
   - systemd units
   - SSH and FRP configuration
   - OpenClaw runtime configuration on host
2. Human-reviewed repository policy documents
3. Bot-generated reports and notes

Higher layers describe lower layers, but do not automatically overwrite them.

## What Bot Documents Are Good For

- preserving context
- reporting health and incidents
- proposing changes
- recording experiments and results

## What Bot Documents Are Not

- an authorization grant
- a replacement for host-side configuration control
- approval for privilege escalation

## Change Classes

- Policy class:
  - branch protections
  - remote-access red lines
  - privilege boundaries
  - runtime safety rules
  - should be reviewed by a human

- Runtime notes class:
  - paths
  - versions
  - known compatible launch shapes
  - may be updated carefully, but changes should remain factual

- Report class:
  - tests
  - traces
  - incident summaries
  - generally safe for autonomous updates when secrets are excluded

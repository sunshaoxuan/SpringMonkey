FROM nousresearch/hermes-agent@sha256:1a355ebc8981a4b72a28f4e47e347ba4f0f172b43dc876e5768d175a07c67b22
USER root
COPY manifest.json verify_image.py requirements-lock.txt /opt/pilot/
RUN /opt/hermes/.venv/bin/python /opt/pilot/verify_image.py before
# Build-time extension only: same upstream lock, binary wheels, no runtime install.
RUN rm -rf /opt/hermes/.venv && /usr/local/bin/python3 -m pm.build_env --source /opt/hermes --python /usr/local/bin/python3 --cache /opt/hermes/uv-cache --out /opt/hermes/.venv --no-install-project --sealed --record-selection --extra all --extra messaging --extra otlp --extra anthropic --extra bedrock --extra azure-identity --extra matrix --extra google-chat --extra fal --extra documents --extra documents-pdf --extra ddgs && /opt/hermes/.venv/bin/python -m docker.build_agent
COPY patched/agent/ /opt/hermes/agent/
RUN chmod 0644 /opt/hermes/tools/facts.json && /opt/hermes/.venv/bin/python /opt/pilot/verify_image.py after
# Narrow the bundled catalog in this image to the reviewed first batch.
RUN rm -rf /opt/hermes/skills && mkdir -p /opt/hermes/skills
COPY skills/ /opt/hermes/skills/
ENV HERMES_DASHBOARD=0 HERMES_HOME=/opt/data PYTHONDONTWRITEBYTECODE=1
WORKDIR /workspace
CMD ["sleep", "infinity"]

# Written for `agents deploy`. Deploys build it as it is.
FROM ghcr.io/astral-sh/uv:0.11-debian-slim

# The agent checks the TLS certificates of Mistral's servers against the system CA certificates, which
# the base image does not ship.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# uv installs the Python version the project asks for, so the image needs none of its own. It goes
# outside /root so that the worker's user can run it.
ENV UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY . .
RUN uv sync --no-dev \
 && useradd --create-home --shell /usr/sbin/nologin agent \
 && chown -R agent:agent /app

# The worker does not need root.
USER agent

# Session persistence limits (deployed maximums): stay alive 24h idle, 7 days total.
# The execution timeout must cover the lifetime limit.
ENV AGENTS_SDK_IDLE_TIMEOUT_SECONDS=86400 \
    AGENTS_SDK_LIFETIME_LIMIT_SECONDS=604800 \
    AGENTS_SDK_EXECUTION_TIMEOUT_SECONDS=608400

CMD ["agents", "run-worker"]

# Alternative to the Smithery Python runtime: self-contained image (~80 MB).
# Build:  docker build -t steam-game-price .
# Run:    docker run -i --rm steam-game-price            # stdio
#         docker run -p 8000:8000 -e MCP_TRANSPORT=http steam-game-price

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MCP_TRANSPORT=stdio

WORKDIR /app

# Copy only what the build needs, so dependency layers cache well.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install .

# Run unprivileged.
RUN useradd --create-home --uid 10001 appuser
USER appuser

ENTRYPOINT ["python", "-m", "mcp_steam_price"]

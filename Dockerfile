FROM python:3.12-slim

WORKDIR /app

# Install git (needed for git+ dependencies) and uv
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Copy project files
COPY pyproject.toml .
COPY app.py .
COPY data/ data/

# Install dependencies (production only, no dev deps)
RUN uv sync --no-dev

# Create non-root user for HuggingFace
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR /app

# Expose port for Panel
EXPOSE 7860

# Run the Panel server
CMD ["uv", "run", "panel", "serve", "app.py", "--address", "0.0.0.0", "--port", "7860", "--allow-websocket-origin", "*", "--num-procs", "1"]

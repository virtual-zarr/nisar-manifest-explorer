FROM python:3.12-slim

# Install git (needed for git+ dependencies) and uv
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Create non-root user for HuggingFace
RUN useradd -m -u 1000 user

# Set up working directory with correct ownership
WORKDIR /app
RUN chown user:user /app

# Switch to non-root user BEFORE installing dependencies
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:/app/.venv/bin:$PATH

# Copy project files (as user)
COPY --chown=user:user pyproject.toml .
COPY --chown=user:user app.py .
COPY --chown=user:user data/ data/

# Install dependencies (as user, so .venv is owned by user)
RUN uv sync --no-dev

# Expose port for Panel
EXPOSE 7860

# Run the Panel server
CMD ["uv", "run", "panel", "serve", "app.py", "--address", "0.0.0.0", "--port", "7860", "--allow-websocket-origin", "*", "--num-procs", "1"]

FROM python:3.12-slim

WORKDIR /app

# Install uv for fast package installation
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY app.py .
COPY data/ data/

# Install dependencies (production only, no dev deps)
RUN uv sync --no-dev --frozen || uv sync --no-dev

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

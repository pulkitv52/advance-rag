# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libmagic-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set work directory
WORKDIR /app

# Copy the project files
COPY pyproject.toml .
COPY README.md .

# Install dependencies using uv
RUN uv sync --no-dev

# Copy the source code
COPY src/ ./src/

# Expose the port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# Startup command
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

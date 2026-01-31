FROM python:3.13

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    ghostscript \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Set Python path to include the src directory
ENV PYTHONPATH=/app/src

# Install Python dependencies
COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Install dev dependencies if DEV_MODE build arg is set
ARG DEV_MODE=false
COPY ./requirements-dev.txt /app/requirements-dev.txt
RUN if [ "$DEV_MODE" = "true" ]; then pip install --no-cache-dir -r /app/requirements-dev.txt; fi

# Copy application code
COPY ./src /app/src

# Create data directories
RUN mkdir -p /app/data/input /app/data/output /app/data/frames /app/data/cache

EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["gunicorn", "--chdir", "/app/src", "-w", "4", "-b", "0.0.0.0:8000", "handout_generator.wsgi:application"]

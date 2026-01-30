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

# Set Python path to include the app directory
ENV PYTHONPATH=/app

# Install Python dependencies
COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /app/data/input /app/data/output /app/data/frames /app/data/cache

EXPOSE 5000

# Default command (can be overridden in docker-compose)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]

# Use slim Python base and install ffmpeg
FROM python:3.11-slim

# Prevent interactive tzdata prompt
ENV DEBIAN_FRONTEND=noninteractive

# Install ffmpeg (for voice OGG/Opus)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy project
COPY . /app

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Render provides PORT env var
ENV PORT=10000

# Start
CMD ["python", "-m", "app.main"]

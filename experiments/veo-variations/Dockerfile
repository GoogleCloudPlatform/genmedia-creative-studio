# Stage 1: Build the UI
FROM node:24-slim as ui-builder
WORKDIR /app/ui
COPY ui/package*.json ./
RUN npm install
COPY ui/ ./
RUN npm run build

# Stage 2: Application
FROM python:3.14-slim
WORKDIR /app

# Install system dependencies and prebuilt Google Credentio C-ABI library
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    git \
    && curl -fSL https://github.com/ghchinoy/credentio-contributions/releases/download/v0.2.1/libcredentio_c-linux-amd64.so \
       -o /usr/local/lib/libcredentio_c.so \
    && chmod 755 /usr/local/lib/libcredentio_c.so \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY api /app/api
COPY core /app/core

# Copy built UI from Stage 1
COPY --from=ui-builder /app/ui/dist /app/ui/dist

# Install app dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-dotenv \
    google-genai \
    google-cloud-storage \
    pyiqa \
    opencv-python-headless \
    cffi \
    "credentio @ git+https://github.com/ghchinoy/credentio-contributions.git@v0.2.1#subdirectory=python" \
    requests \
    google-auth \
    python-multipart \
    pyopenssl \
    marked

# Expose port
EXPOSE 8080

# Run the API
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]

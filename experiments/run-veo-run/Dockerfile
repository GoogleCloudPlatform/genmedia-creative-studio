# Copyright 2025 Google LLC
# Licensed under the Apache License, Version 2.0

# Stage 1: Build Frontend
FROM node:26-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
# Create public dir if missing to avoid copy errors
RUN mkdir -p public
RUN if [ -f ../CHANGELOG.md ]; then cp ../CHANGELOG.md public/; fi
RUN npm run build

# Stage 2: Build Backend
FROM golang:1.27-alpine AS backend-builder
WORKDIR /app/server
COPY server/go.mod server/go.sum ./
RUN go mod download
COPY server/ .
RUN go build -o server main.go

# Stage 3: Final Image
FROM alpine:latest
RUN apk add --no-cache ca-certificates ffmpeg
WORKDIR /app

# Copy binary
COPY --from=backend-builder /app/server/server .

# Copy frontend assets (built to ../server/dist in Stage 1)
COPY --from=frontend-builder /app/server/dist ./dist

# Environment variables
ENV PORT=8080
ENV GOOGLE_CLOUD_PROJECT=genai-blackbelt-fishfooding

EXPOSE 8080
CMD ["./server"]

FROM mcr.microsoft.com/devcontainers/javascript-node:1-22-bookworm

ARG GO_VERSION=1.26.0
ARG TARGETARCH

ENV GOPATH=/home/node/go
ENV GOBIN=/usr/local/bin
ENV PATH=/usr/local/go/bin:${GOPATH}/bin:${PATH}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        gettext-base \
        jq \
        make \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "${arch}" in \
        amd64|arm64) go_arch="${arch}" ;; \
        *) echo "Unsupported Go architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${go_arch}.tar.gz" -o /tmp/go.tar.gz \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm /tmp/go.tar.gz

COPY mcp-genmedia-go /tmp/mcp-genmedia-go

# Build the servers through the module Makefile so each binary carries the
# ldflags-injected VERSION from the single source-of-truth VERSION file
# (see #1595/#1596). `make build` compiles every server into ./bin with
# `-X main.version=$(cat VERSION)`; we then install those onto PATH (GOBIN).
RUN cd /tmp/mcp-genmedia-go \
    && make build \
    && install -m 0755 bin/* "${GOBIN}/" \
    && rm -rf /tmp/mcp-genmedia-go

COPY .devcontainer/scripts /usr/local/share/mcp-genmedia-devcontainer/scripts
COPY .devcontainer/templates /usr/local/share/mcp-genmedia-devcontainer/templates

RUN chmod +x /usr/local/share/mcp-genmedia-devcontainer/scripts/*.sh \
    && printf '%s\n' \
        '#!/usr/bin/env bash' \
        'exec npx --yes https://github.com/google-gemini/gemini-cli "$@"' \
        > /usr/local/bin/gemini \
    && chmod +x /usr/local/bin/gemini \
    && mkdir -p /home/node/go \
    && chown -R node:node /home/node/go

USER node

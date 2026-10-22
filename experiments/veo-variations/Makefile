# Makefile for Veo Variations Studio

.PHONY: help install clean api ui build

help:
	@echo "Usage:"
	@echo "  make install          Install dependencies"
	@echo "  make clean            Remove temporary files"
	@echo "  make api              Run FastAPI backend"
	@echo "  make ui               Run Lit frontend (Dev mode)"
	@echo "  make build            Build frontend for production"

install:
	mkdir -p $(HOME)/.local/lib
	@if [ "$$(uname -s)" = "Darwin" ] && [ ! -f "$(HOME)/.local/lib/libcredentio_c.dylib" ]; then \
		curl -fSL https://github.com/ghchinoy/credentio-contributions/releases/download/v0.2.1/libcredentio_c-darwin-arm64.dylib -o $(HOME)/.local/lib/libcredentio_c.dylib && chmod 755 $(HOME)/.local/lib/libcredentio_c.dylib; \
	elif [ "$$(uname -s)" = "Linux" ] && [ ! -f "$(HOME)/.local/lib/libcredentio_c.so" ]; then \
		curl -fSL https://github.com/ghchinoy/credentio-contributions/releases/download/v0.2.1/libcredentio_c-linux-amd64.so -o $(HOME)/.local/lib/libcredentio_c.so && chmod 755 $(HOME)/.local/lib/libcredentio_c.so; \
	fi
	export UV_DEFAULT_INDEX=https://pypi.org/simple && uv sync
	cd ui && npm install

clean:
	rm -f *.mp4 *.png
	rm -rf __pycache__ core/__pycache__ api/__pycache__ ui/dist
	@echo "Cleaned."

api:
	uv run uvicorn api.main:app --reload --port 8000

ui:
	cd ui && npm run dev

build:
	cd ui && npm run build

# GenMedia Creative Studio | Vertex AI

[![Python Tests CI](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/actions/workflows/python-tests.yml/badge.svg)](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/actions/workflows/python-tests.yml)
[![MCP GenMedia Go CI](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/actions/workflows/mcp-genmedia-go.yml/badge.svg)](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/actions/workflows/mcp-genmedia-go.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](pyproject.toml)

GenMedia Creative Studio is an interactive web application built on [Mesop](https://mesop-dev.github.io/mesop/) and FastAPI for exploring, chaining, and deploying Google Cloud generative media models on Vertex AI — spanning video, image, music, speech, and multimodal creative workflows.

> ###### _This is not an officially supported Google product. This project is not eligible for the [Google Open Source Software Vulnerability Rewards Program](https://bughunters.google.com/open-source-security). This project is intended for demonstration purposes only. It is not intended for use in a production environment._

![GenMedia Creative Studio Home](https://github.com/user-attachments/assets/da5ad223-aa6e-413c-b36e-5d63e5d5b758)

![GenMedia Creative Studio Workflows](https://github.com/user-attachments/assets/61977f3c-dbb6-4002-b8c0-77d57aa03cce)

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Local Development & Smoke Testing](#local-development--smoke-testing)
- [Deploying to Google Cloud](#deploying-to-google-cloud)
- [Documentation Hub](#documentation-hub)
- [Experiments & MCP Tools](#experiments--mcp-tools)
- [Contributing](#contributing)
- [Licensing](#licensing)
- [Disclaimer](#disclaimer)

## Overview

> **Browser Compatibility:** For the best experience, we recommend using Google Chrome. Some features may not work as expected on other browsers, such as Safari or Firefox.

GenMedia Creative Studio showcases Google Cloud's generative media models — Gemini Omni, Veo, Gemini Image Generation (Nano Banana), Lyria, Gemini TTS, Chirp 3 HD, and Gemini Writers Workshop — alongside multi-step creative workflows and a shared media library. We're looking forward to seeing what you create!

Current featureset:

- **Video:** Gemini Omni 1.2 Flash (`gemini-omni-1.2-flash`), Veo 3.1, Veo 3.1 Fast, Veo 3.1 Lite
- **Image:** Gemini Nano Banana 2.1 (default), Gemini 3.1 Flash Image (Nano Banana 2), Gemini 3.1 Flash-Lite Image (Nano Banana 2 Lite), Gemini 3 Pro Image (Nano Banana Pro), plus legacy Imagen 4 (`/imagen`)
- **Music:** Lyria 3 (Pro & Clip), Lyria 2
- **Speech:** Gemini Text-to-Speech (TTS), Chirp 3 HD
- **Text & Ideation:** Gemini Writers Workshop
- **Creative Workflows:** Storyboarder, Character Consistency, Shop the Look, Interior Design, Virtual Try-On, Starter Pack, Motion Portraits, Pixie Compositor
- **Studio Asset Library:** Persistent Firestore & Cloud Storage media browser with provenance inspection

Built using [Mesop](https://mesop-dev.github.io/mesop/), an open-source Python UI framework used at Google for rapid AI app development, and the [Studio-style app scaffold](https://github.com/ghchinoy/studio-scaffold).

---

## Quick Start

The core app requires **Python 3.14+** (installed automatically by [`uv`](https://github.com/astral-sh/uv)) and a Google Cloud project with Vertex AI enabled.

```bash
# 1. Install uv (macOS/Linux) if you don't already have it:
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone the repository:
git clone https://github.com/GoogleCloudPlatform/genmedia-creative-studio.git
cd genmedia-creative-studio

# 3. Authenticate with Application Default Credentials and set your project:
gcloud auth application-default login
cp dotenv.template .env
echo "PROJECT_ID=$(gcloud config get-value project)" >> .env

# 4. Sync dependencies (uv installs Python 3.14 automatically) and start the server:
uv sync
uv run main.py
```

Open <http://localhost:8080/> in Chrome (`/` redirects automatically to `/home`).

---

## Local Development & Smoke Testing

### Cloud Prerequisites for Media Persistence

While the UI boots locally with only `PROJECT_ID` set, saving generated assets and browsing the **Asset Library** use two default Google Cloud resources in your project (configurable via `.env` — see [`dotenv.template`](dotenv.template)):

- **Firestore:** a Standard database named `(default)` (`gcloud firestore databases create --database="(default)" --location=nam5`)
- **Cloud Storage:** a bucket named `${PROJECT_ID}-assets` (`gcloud storage buckets create -l us-central1 gs://${PROJECT_ID}-assets`)

See [Local Setup & Development](https://googlecloudplatform.github.io/genmedia-creative-studio/core/installation/local_setup/), [Environment Variables](https://googlecloudplatform.github.io/genmedia-creative-studio/core/installation/environment_variables/), and the [Developer's Guide](https://googlecloudplatform.github.io/genmedia-creative-studio/core/developers_guide/) for full configuration details.

### Smoke-Test Before You Merge

[`scripts/smoke_test.sh`](scripts/smoke_test.sh) is an automated boot check for the core app: it runs `uv sync`, verifies page/model imports, boots the app under Gunicorn/Uvicorn in `APP_ENV=local` mode on port `8080`, and confirms `GET /` → `/home` (`200`) and `GET /__login` (`200`). Passing `-l` also runs one live Vertex AI `gemini-3.5-flash` `generateContent` check on the `global` endpoint when `PROJECT_ID` and ADC are present.

```bash
./scripts/smoke_test.sh        # boot + import + UI check
./scripts/smoke_test.sh -l     # also run the live Vertex generation check
```

Run this before merging any PR that modifies core-app runtime code (`pages/`, `models/`, `state/`, `config/`, `main.py`), alongside `pytest`:

```bash
uv run pytest
```

It is a fast pre-merge boot check, **not** a replacement for unit tests or Terraform/IAP deployment validation.

---

## Deploying to Google Cloud

Production deployments are provisioned with Terraform and secured behind Identity-Aware Proxy (IAP):

- **Cloud Run (Recommended):** Deploy either behind a Global External Application Load Balancer with a custom domain and managed SSL certificate, or directly using the Cloud Run `.run.app` URL with Cloud Run IAP. After initial Terraform provisioning, build and roll out application updates from the repository root with `./build.sh`. See the **[Cloud Run Deployment Guide](https://googlecloudplatform.github.io/genmedia-creative-studio/core/installation/deploy/)**.
- **Google Kubernetes Engine (Self-Service GKE):** Deploy on GKE Autopilot/Standard with IAP and Workload Identity. See the **[GKE Deployment Guide](https://googlecloudplatform.github.io/genmedia-creative-studio/core/installation/gke/)**.

---

## Documentation Hub

For architecture deep-dives, foundation model guides, workflow walkthroughs, and troubleshooting, visit the **[Documentation Hub](https://googlecloudplatform.github.io/genmedia-creative-studio/)**:

- **[Using the Studio](https://googlecloudplatform.github.io/genmedia-creative-studio/core/usage/)** & **[Architecture](https://googlecloudplatform.github.io/genmedia-creative-studio/core/architecture/)**
- **[FAQ](https://googlecloudplatform.github.io/genmedia-creative-studio/core/faq/)**
- **[Changelog & Notices](https://googlecloudplatform.github.io/genmedia-creative-studio/core/changelog/)**

---

## Experiments & MCP Tools

The [`experiments/`](experiments/) directory houses standalone applications, multimodal pipelines, and **Model Context Protocol (MCP)** servers in Go (`veo`, `omni`, `nanobanana`, `gemini`, `imagen`, `lyria`, `chirp3`, `gemini-transcribe`, and `avtool`).

Install pre-compiled MCP server binaries directly:

```bash
curl -sL https://raw.githubusercontent.com/GoogleCloudPlatform/genmedia-creative-studio/main/experiments/mcp-genmedia/mcp-genmedia-go/install-online.sh | bash
```

Explore all experiments, sample agents, and MCP server guides in the **[Experiments & MCP Documentation](https://googlecloudplatform.github.io/genmedia-creative-studio/experiments/overview/)**.

---

## Contributing

Contributions and bug fixes are welcome! For larger features or architectural changes, please open an issue first to discuss the proposed design. All contributions require signing the Google Contributor License Agreement (CLA).

- Contributor workflow & CLA details: **[CONTRIBUTING.md](CONTRIBUTING.md)**
- Maintainer operations, review discipline, and recurring hygiene: **[docs/repo-management/README.md](docs/repo-management/README.md)**

## Licensing

Code in this repository is licensed under the Apache License, Version 2.0. See **[LICENSE](LICENSE)**.

## Disclaimer

> [!CAUTION]
> This is **not** an officially supported Google product.
> This project is not eligible for the [Google Open Source Software Vulnerability Rewards Program](https://bughunters.google.com/open-source-security).

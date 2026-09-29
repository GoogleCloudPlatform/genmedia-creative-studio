# GenMedia Creative Studio | Vertex AI

> ###### _This is not an officially supported Google product. This project is not eligible for the [Google Open Source Software Vulnerability Rewards Program](https://bughunters.google.com/open-source-security). This project is intended for demonstration purposes only. It is not intended for use in a production environment._

![GenMedia Creative Studio v.next](https://github.com/user-attachments/assets/da5ad223-aa6e-413c-b36e-5d63e5d5b758)

![GenMedia Creative Studio v.next](https://github.com/user-attachments/assets/61977f3c-dbb6-4002-b8c0-77d57aa03cce)

## Table of Contents

- [GenMedia Creative Studio | Vertex AI](#genmedia-creative-studio--vertex-ai)
- [Table of Contents](#table-of-contents)
- [GenMedia Creative Studio](#genmedia-creative-studio)
- [Documentation Hub](#documentation-hub)
  - [Quick Start](#quick-start)
  - [Deploying to Google Cloud](#deploying-to-google-cloud)
- [Experiments & MCP Tools](#experiments--mcp-tools)
- [Contributing changes](#contributing-changes)
- [Licensing](#licensing)
- [Disclaimer](#disclaimer)

## GenMedia Creative Studio

> **Browser Compatibility:** For the best experience, we recommend using Google Chrome. Some features may not work as expected on other browsers, such as Safari or Firefox.

GenMedia Creative Studio is a web application showcasing Google Cloud's generative media - Gemini Omni, Veo, Lyria, Gemini Image Generation (Nano Banana), Chirp 3 HD, and Gemini TTS along with custom workflows and techniques for creative exploration and inspiration. We're looking forward to see what you create!

Current featureset:

- **Image:** Gemini 3.1 Flash-Lite Image (Nano Banana 2 Lite), Gemini Flash Image Generation (Nano Banana 2), Gemini 3 Pro Image (Nano Banana Pro), Virtual Try-On
- **Video:** Gemini Omni Flash, Veo 3.1, Veo 3
- **Music:** Lyria 3 & 2
- **Speech:** Chirp 3 HD, Gemini Text to Speech
- **Workflows:** Character Consistency, Shop the Look, Starter Pack Moodboard, Interior Designer
- **Asset Library**

This is built using [Mesop](https://mesop-dev.github.io/mesop/), an open source Python framework used at Google for rapid AI app development, and the [scaffold for Studio style apps](https://github.com/ghchinoy/studio-scaffold).

---

## 📖 Documentation Hub

**For comprehensive guides, deployment instructions, architecture details, and developer workflows, please visit our [Documentation Hub](https://googlecloudplatform.github.io/genmedia-creative-studio/).**

> [!IMPORTANT]
> **Git History Reset Notice**: The repository history on `main` was scrubbed in August 2026 to remove legacy compiled binaries, reducing clone size by ~60%. If you have an existing clone, please see the [Git History Reset Instructions on our Changelog](https://googlecloudplatform.github.io/genmedia-creative-studio/core/changelog/) for steps to synchronize your local checkout.

Stay up-to-date with upcoming breaking changes and releases on our **[Changelog & Notices](https://googlecloudplatform.github.io/genmedia-creative-studio/core/changelog/)** page.


---

### Quick Start

#### Run it locally

The app is a Python ([Mesop](https://mesop-dev.github.io/mesop/) on FastAPI) application that requires **Python 3.14+** and uses [`uv`](https://github.com/astral-sh/uv) for dependency management. You also need a Google Cloud project with Vertex AI access — the UI calls Vertex (Gemini, Veo, Imagen, Lyria) regardless of where the web server runs.

```bash
# 1. Install uv (macOS/Linux) if you don't have it:
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Authenticate to Google Cloud (provides Application Default Credentials):
gcloud auth application-default login
export PROJECT_ID=$(gcloud config get-value project)

# 3. Sync dependencies (uv installs Python 3.14 automatically) and run:
uv sync
uv run main.py
```

Then open <http://localhost:8080/> — `/` redirects to `/home`. See [Local Setup & Development](https://googlecloudplatform.github.io/genmedia-creative-studio/core/installation/local_setup/) on the Documentation Hub for `.env` configuration and available environment variables.

Prefer a fully hosted environment? Use Cloud Shell and follow the tutorial:

[![Open in Cloud Shell](https://gstatic.com/cloudssh/images/open-btn.svg)](https://shell.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/GoogleCloudPlatform/genmedia-creative-studio.git&cloudshell_tutorial=tutorial.md)

#### Smoke-test before you merge

`scripts/smoke_test.sh` is a quick, automated boot check for the core app: it runs `uv sync`, boots the app under gunicorn/uvicorn in `APP_ENV=local` mode, and verifies the UI serves (`GET /` → `/home` → 200, `GET /__login` → 200). An optional, env-gated leg (`-l`) makes one live Vertex `gemini-3.8-flash` generation call (in the `global` location — the gemini-3.x flash family is global-only) when a `PROJECT_ID` and Application Default Credentials are present.

```bash
./scripts/smoke_test.sh        # boot + UI check
./scripts/smoke_test.sh -l     # also run the live Vertex generation leg
```

Run it **before merging any PR that touches core-app runtime code** (`pages/`, `models/`, `state/`, `config/`, `main.py`) to catch boot-health regressions early. It is a fast pre-merge sanity check, **not** a substitute for the test suite and **not** a deploy/IAP/Load-Balancer validation (that's the [Terraform deployment path](https://googlecloudplatform.github.io/genmedia-creative-studio/core/installation/deploy/)). To click around the running app yourself, use the local run above; the script is for a quick, hands-off "does it still boot and serve?" answer.

### Deploying to Google Cloud

The application is designed to be deployed using Terraform and Cloud Run. You have the flexibility to deploy using a custom domain (with Identity Aware Proxy and a Load Balancer) or using the autogenerated Cloud Run domain. 

For detailed, step-by-step instructions on setting up your environment, configuring custom domains, and managing Identity Aware Proxy (IAP), please see the [Deployment Guide on our Documentation Hub](https://googlecloudplatform.github.io/genmedia-creative-studio/core/installation/deploy/).

## Experiments & MCP Tools

The `experiments/` folder contains a variety of stand-alone applications, new workflows, and Model Context Protocol (MCP) servers that showcase cutting-edge capabilities with generative AI. This includes combined workflows for video generation, advanced prompting techniques, image recontextualization, and audio exploration.

To explore the available experiments, view architecture diagrams, and find installation instructions for our MCP tools, head over to the [Experiments Section of our Documentation Hub](https://googlecloudplatform.github.io/genmedia-creative-studio/experiments/overview/).

## Contributing changes

Interested in contributing? Please open an issue describing the intended change. Additionally, bug fixes are welcome, either as pull requests or as GitHub issues.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute.

Maintainers: see [docs/repo-management/](docs/repo-management/README.md) for the repository-management system (recurring jobs, review discipline, and branch-hygiene policy).

## Licensing

Code in this repository is licensed under the Apache 2.0. See [LICENSE](LICENSE).

## Disclaimer

> [!CAUTION]
> This is **not** an officially supported Google product.
> This project is not eligible for the [Google Open Source Software Vulnerability Rewards Program](https://bughunters.google.com/open-source-security).
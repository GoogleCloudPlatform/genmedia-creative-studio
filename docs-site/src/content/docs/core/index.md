---
title: "GenMedia Creative Studio | Google Cloud AI"
---

> ###### _This is not an officially supported Google product. This project is not eligible for the [Google Open Source Software Vulnerability Rewards Program](https://bughunters.google.com/open-source-security). This project is intended for demonstration purposes only. It is not intended for use in a production environment._

![GenMedia Creative Studio v.next](https://github.com/user-attachments/assets/da5ad223-aa6e-413c-b36e-5d63e5d5b758)

![GenMedia Creative Studio v.next](https://github.com/user-attachments/assets/61977f3c-dbb6-4002-b8c0-77d57aa03cce)

## Table of Contents

- [GenMedia Creative Studio | Google Cloud AI](#genmedia-creative-studio--google-cloud-ai)
- [Table of Contents](#table-of-contents)
- [GenMedia Creative Studio](#genmedia-creative-studio)
  - [Experiments](#experiments)
- [Deploying GenMedia Creative Studio](#deploying-genmedia-creative-studio)
  - [Prerequisites](#prerequisites)
    - [1. Download the source code for this project](#1-download-the-source-code-for-this-project)
    - [2. Export Environment Variables](#2-export-environment-variables)
  - [Deploying with Custom Domain](#deploying-with-custom-domain)
    - [1. Initialize Terraform](#1-initialize-terraform)
    - [2. Create a DNS A record for the domain name](#2-create-a-dns-a-record-for-the-domain-name)
    - [3. Build and Deploy Container Image](#3-build-and-deploy-container-image)
    - [4. Wait for certificate to go to provisioned state](#4-wait-for-certificate-to-go-to-provisioned-state)
  - [Deploying using Cloud Run Domain](#deploying-using-cloud-run-domain)
    - [1. Initialize Terraform](#1-initialize-terraform-1)
    - [2. Build and Deploy Container Image](#2-build-and-deploy-container-image)
    - [3. Edit Cloud Run's IAP Policy to provide initial user's access](#3-edit-cloud-runs-iap-policy-to-provide-initial-users-access)
  - [Deploying to Cloud Shell for Testing](#deploying-to-cloud-shell-for-testing)
- [Adding Additional Users](#adding-additional-users)
- [Solution Design](#solution-design)
  - [Custom Domain Using Identity Aware Proxy w/Load Balancer](#custom-domain-using-identity-aware-proxy-wload-balancer)
  - [Cloud Run Domain Using Identity Aware Proxy w/Cloud Run](#cloud-run-domain-using-identity-aware-proxy-wcloud-run)
  - [Solution Components](#solution-components)
    - [Runtime Components](#runtime-components)
    - [Build time Components](#build-time-components)
  - [Setting up your development environment](#setting-up-your-development-environment)
    - [Python virtual environment](#python-virtual-environment)
    - [Application Environment variables](#application-environment-variables)
  - [GenMedia Creative Studio - Developing](#genmedia-creative-studio---developing)
    - [Running](#running)
    - [Developing](#developing)
  - [Contributing changes](#contributing-changes)
  - [Licensing](#licensing)
- [Disclaimer](#disclaimer)

## GenMedia Creative Studio

> [!IMPORTANT]
> **Git History Reset Notice**: The repository history on `main` was scrubbed in August 2026 to remove legacy compiled binaries, reducing clone size by ~60%. If you have an existing clone, please see the [Git History Reset Instructions on our Changelog](/core/changelog/) for steps to synchronize your local checkout.

> **Browser Compatibility:** For the best experience, we recommend using Google Chrome. Some features may not work as expected on other browsers, such as Safari or Firefox.


GenMedia Creative Studio is a web application showcasing Google Cloud's generative media - Gemini Omni, Veo, Lyria, Chirp, Gemini Image Generation (Nano Banana), and Gemini TTS along with custom workflows and techniques for creative exploration and inspiration. We're looking forward to see what you create!

Current featureset

- Image: Gemini 3.1 Flash-Lite Image (Nano Banana 2 Lite), Gemini 3.1 Flash Image Generation (Nano Banana 2), Gemini 3 Pro Image (Nano Banana Pro), Virtual Try-On. (Imagen was [deprecated across Google, including Vertex AI, around August 17, 2026](https://firebase.google.com/docs/ai-logic/imagen-models-migration?api=dev) — use Nano Banana instead.)
- Video: Gemini Omni Flash, Veo 3.1, Veo 3
- Music: Lyria
- Speech: Chirp 3 HD, Gemini Text to Speech
- Workflows: Character Consistency, Shop the Look, Starter Pack Moodboard, Interior Designer
- Asset Library

This is built using [Mesop](https://mesop-dev.github.io/mesop/), an open source Python framework used at Google for rapid AI app development, and the [scaffold for Studio style apps](https://github.com/ghchinoy/studio-scaffold).

## Experiments

The [Experimental folder](./experiments/) contains a variety of stand-alone applications and new and upcoming features that showcase cutting-edge capabilities with generative AI.

Here's a glimpse of what you'll find:

**MCP Tools**

- **MCP Tools for Genmedia:** Model Context Protocol servers for Veo, Imagen, Lyria, Chirp, and Gemini to bring creativity to your agents.
  - ⚡ **Instant Installation:** You can now install all MCP servers directly using our pre-compiled binaries:
    ```bash
    curl -sL https://raw.githubusercontent.com/GoogleCloudPlatform/genmedia-creative-studio/main/experiments/mcp-genmedia/mcp-genmedia-go/install-online.sh | bash
    ```

**Combined Workflows**

- **Countdown Workflow:** An automated two-stage pipeline to create branded countdown videos.
- **Storycraft:** An AI-powered video storyboard generation platform that transforms text descriptions into complete video narratives. (Now maintained at [mblanc/storycraft](https://github.com/mblanc/storycraft).)
    - **Creative GenMedia Workflow:** An end-to-end workflow to produce high-quality, on-brand creative media.
    - **Run, Veo, Run:** A real-time, multimodal video generation experiment that creates a branching narrative loop using Veo 3.1 for video extension and Gemini 3 for context awareness.

**Prompting Techniques**

- **Promptlandia:** A powerful web app to analyze, refine, and improve your prompts.
- **Veo Genetic Prompt Optimizer:** An automated system to evolve and refine high-level "metaprompts" for Veo.
- **Character & Item Consistency:** Workflows for maintaining consistency for characters and items across video scenes.

**Image Generation & Analysis**

- **Virtual Try-On:** A notebook for virtually trying on outfits at scale.
- **Imagen Product Recontextualization:** Tools for large-scale product image recontextualization.

**Audio & Video**

- **Creative Podcast Assistant:** A notebook for creating a podcast with generative media.
- **Babel:** An experimental app for Chirp 3 HD voices.

...and much more! For a full, detailed list of all experiments, please see the [Experiments README](./experiments/README.md).

## Contributing changes

Interested in contributing? Please open an issue describing the intended change. Additionally, bug fixes are welcome, either as pull requests or as GitHub issues.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute.

## Licensing

Code in this repository is licensed under the Apache 2.0. See [LICENSE](LICENSE).

# Disclaimer

This is not an officially supported Google product. This project is not eligible for the [Google Open Source Software Vulnerability Rewards Program](https://bughunters.google.com/open-source-security).
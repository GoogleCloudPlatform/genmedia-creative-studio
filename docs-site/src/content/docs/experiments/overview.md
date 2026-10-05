---
title: "Experiments Overview"
---

The experimental folder contains stand-alone applications, demos, and features not yet ready for inclusion into the main app. We'd love to hear your feedback on these!

## Combined Workflows

* [Veo Variations](/genmedia-creative-studio/experiments/veo-variations) - Generates creative variations of a video concept and evaluates them technically using Nano Banana, Gemini, and Veo 3.1 Lite.
* [Countdown Workflow](/genmedia-creative-studio/experiments/countdown-workflow) - An automated two-stage pipeline to create branded countdown videos.
* [Creative GenMedia Workflow](/genmedia-creative-studio/experiments/creative-genmedia-workflow) - A workflow which takes various inputs to create prompts for Veo 3, plus a showcase of output videos.
* [Run, Veo, Run](/genmedia-creative-studio/experiments/run-veo-run) - A near-real time, multimodal video extension and generation experiment.

## Prompting Techniques

* [Promptlandia](/genmedia-creative-studio/experiments/promptlandia) - A powerful web application that helps you analyze, refine, and improve your prompts using AI-powered feedback.
* [Veo Genetic Prompt Optimizer](/genmedia-creative-studio/experiments/veo-genetic-prompt-optimizer) - An automated system that uses a genetic algorithm to evolve and refine high-level "metaprompts".
* [Veo 3 Character Consistency](/genmedia-creative-studio/experiments/veo3-character-consistency) - A workflow for generating a video of a person in a new scene while maintaining character consistency.
* [Veo 3 Item Consistency](/genmedia-creative-studio/experiments/veo3-item-consistency) - A workflow for generating a video of an item in a new scene while maintaining item consistency.

## Image Generation & Comparison

* [Imagen Product Recontextualization at Scale](/genmedia-creative-studio/experiments/imagen_product_recontext) - A set of notebooks for the Imagen Product Recontext model to run at scale.
* [Virtual Try-On](/genmedia-creative-studio/experiments/vto) - A notebook example for virtually trying on outfits at scale.
* [Brand Consistency](/genmedia-creative-studio/experiments/brand_consistency) - Maintain brand identity in generated media.
* [Arena](/genmedia-creative-studio/experiments/arena) - Rate your images within a visual arena. **(Archived 2026-09-13 — source moved to `archive/arena`; retained for reference, no longer maintained. Decommissioned 2026-10-05 — `Dockerfile`/`Procfile` removed; no longer deployable.)**

## Audio & Voice

* [Babel](/genmedia-creative-studio/experiments/babel) - Experiment with Chirp 3 HD voices.
* [Creative Podcast Assistant](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/tree/main/experiments/creative_podcast_assistant) - A demo notebook showcasing speech-to-text and text-to-speech features for creating a podcast with generative media.

## Developer Tools & MCP

* [Agent Tools for Genmedia](/genmedia-creative-studio/experiments/agent-tools) - The entry point for agent-facing genmedia tooling: the MCP Servers, plus a generate-and-verify smoke test, with Agent Skills and Agent Plugins as an area under exploration.
* [MCP GenMedia](/genmedia-creative-studio/experiments/mcp-genmedia) - Model Context Protocol servers for Genmedia services for AI applications to utilize Veo, Imagen, Lyria, Chirp 3 HD.

## Relocated Experiments

These experiments have moved to their own repositories and are no longer maintained in this repo:

* [Storycraft](https://github.com/mblanc/storycraft) - An AI-powered video storyboard generation platform that transforms text descriptions into complete video narratives.
* [V-Start (formerly VeoStart)](https://github.com/GoogleCloudPlatform/generative-ai/tree/main/vision/sample-apps/V-Start) - A toolkit that helps users quickly create effective prompts for Veo and evaluate how well generated videos align with their intended prompts.

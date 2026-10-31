# genmedia-collection-manager (`genmedia`)

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

An interactive terminal UI (TUI) and agent-aware command-line interface (CLI) for inspecting, searching, aggregating, bulk-ingesting, and exporting generative media asset records (`MediaItem`) across Google Cloud Firestore and Google Cloud Storage (GCS) for **GenMedia Creative Studio**.

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Global Configuration](#global-configuration)
- [Commands & Usage](#commands--usage)
  - [`ingest` — Bulk GCS Bucket Ingestion & Automated CSV Generation](#ingest--bulk-gcs-bucket-ingestion--automated-csv-generation)
  - [`list` — Browse & Export Firestore Library Assets](#list--browse--export-firestore-library-assets)
  - [`get` — Fetch a Single Document by ID](#get--fetch-a-single-document-by-id)
  - [`search` — Query Documents by Field Equality](#search--query-documents-by-field-equality)
  - [`list-errors` — Inspect Failed Generation Records](#list-errors--inspect-failed-generation-records)
  - [`top-users` & `top-models` — Aggregate Collection Usage](#top-users--top-models--aggregate-collection-usage)
  - [`add`, `update`, & `delete` — Mutate Documents Safely](#add-update--delete--mutate-documents-safely)
  - [`check-operation` — Inspect Long-Running Vertex AI Operations](#check-operation--inspect-long-running-vertex-ai-operations)
- [Agent-Aware (A2A) CLI Features](#agent-aware-a2a-cli-features)
- [Development](#development)
- [License](#license)

---

## Overview

When working with thousands of AI-generated or reference media assets (Imagen, Nano Banana / Gemini Image, Veo, Lyria, Chirp), uploading files one-by-one through a browser UI or hand-crafting CSV manifests is slow and error-prone. `genmedia` provides direct programmatic and interactive access to the GenMedia Creative Studio datastore:

1. **Direct GCS Bucket Ingestion (`genmedia ingest`):** Point directly at any `gs://<bucket>/<prefix>` to generate batch CSV manifests (`generic`, `batch-prompt`, `vto-models`, `vto-catalog`) or bulk-register objects into the GMCS Firestore `genmedia` collection (`--register`) with deterministic, idempotent IDs (`gcs_<sha256>`).
2. **Bulk Export to CSV / JSON (`genmedia list`, `genmedia search`):** Filter thousands of Library records by media type or field equality and export their `gcsuri` / `gcs_uris` and metadata directly to CSV or JSON.
3. **Interactive TUI & Headless Agent Modes:** Navigate records interactively with [Bubble Tea](https://github.com/charmbracelet/bubbletea), or pass `--json`, `--view=csv`, `--no-tui` (`GENMEDIA_NO_TUI=1`), `--limit`, and `--dry-run` for deterministic CI and AI agent workflows.

---

## Installation

Build from the monorepo directory (requires Go `1.26+`):

```bash
cd experiments/genmedia-collection-manager
go build -o genmedia .
```

Or install directly with `go install`:

```bash
go install github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/genmedia-collection-manager@latest
```

---

## Quick Start

1. Authenticate with Google Cloud Application Default Credentials:

   ```bash
   gcloud auth application-default login
   ```

2. Set your Google Cloud project ID and launch the interactive document browser:

   ```bash
   export PROJECT_ID=$(gcloud config get-value project)
   ./genmedia list
   ```

   Use `↑`/`↓` to navigate rows, `Enter` to inspect the full JSON document in a scrollable viewport, `Esc`/`Backspace` to return to the table, and `q` to quit.

---

## Global Configuration

Global flags apply to every command and automatically fall back to GenMedia Creative Studio environment variables:

| Flag | Shorthand | Environment Variables | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `--project-id` | `-p` | `PROJECT_ID`, `GOOGLE_CLOUD_PROJECT` | *(required for Firestore)* | Google Cloud project ID hosting Firestore. |
| `--collection` | `-c` | `GENMEDIA_COLLECTION`, `GENMEDIA_COLLECTION_NAME` | `genmedia` | Firestore collection name. |
| `--database-id` | `-d` | `GENMEDIA_DATABASE`, `GENMEDIA_FIREBASE_DB` | `(default)` | Firestore database ID (empty or `(default)` for default database). |
| `--json` | | | `false` | Force machine-readable JSON output (overrides `--view`). |
| `--no-tui` | | `GENMEDIA_NO_TUI=1` | `false` | Disable interactive TUI tables and fall back to plain text output. |

---

## Commands & Usage

### `ingest` — Bulk GCS Bucket Ingestion & Automated CSV Generation

Scan a GCS bucket and optional prefix for media objects (`image/*`, `video/*`, `audio/*`), generate workflow-ready CSV manifests, or bulk-register assets into the GMCS Firestore Library:

```bash
# 1. Generate a generic batch CSV manifest of all images in a GCS folder
./genmedia ingest gs://my-campaign-bucket/summer-shoot/ --media-type=image --view=csv > summer_images.csv

# 2. Generate a prompt-ready CSV manifest for Gemini / Nano Banana batch workflows
./genmedia ingest gs://my-campaign-bucket/product-shots/ \
  --media-type=image \
  --csv-preset=batch-prompt \
  --prompt="Place product on a sunlit marble countertop" \
  --output=nanobanana_batch.csv

# 3. Generate Shop the Look VTO model & catalog CSVs directly from GCS prefixes
./genmedia ingest gs://my-campaign-bucket/vto/models/ --csv-preset=vto-models --model-group=casual --output=models.csv
./genmedia ingest gs://my-campaign-bucket/vto/apparel/ --csv-preset=vto-catalog --model-group=casual --output=catalog.csv

# 4. Preview Firestore MediaItem registration without writing (--dry-run)
./genmedia ingest gs://my-campaign-bucket/summer-shoot/ --register --dry-run --json

# 5. Bulk-register existing GCS assets into the GMCS Firestore library (idempotent)
./genmedia ingest gs://my-campaign-bucket/summer-shoot/ \
  --register \
  --user-email="alice@example.com" \
  --model="external-ingest"
```

### `list` — Browse & Export Firestore Library Assets

Browse documents in the collection with smart default columns based on media type (`image`, `video`, `audio`), or export to CSV, JSON, or plain text:

```bash
# Interactive TUI table (default)
./genmedia list

# Filter by media type (adjusts default columns automatically)
./genmedia list --media-type=image
./genmedia list --media-type=video
./genmedia list --media-type=audio

# Bulk-export GCS URIs and prompts from the Library to CSV
./genmedia list --media-type=image --fields="id,gcsuri,gcs_uris,mime_type,model,prompt,timestamp" --view=csv > library_images.csv

# Export the 25 most recent records as JSON
./genmedia list --limit=25 --json
```

### `get` — Fetch a Single Document by ID

Retrieve and pretty-print the full JSON document for a given Firestore document ID:

```bash
./genmedia get <DOCUMENT_ID>
```

### `search` — Query Documents by Field Equality

Search for documents matching a specific field and value (`--view` / `-o` supports `table`, `json`, `text`, or `csv`):

```bash
./genmedia search --key="user_email" --value="alice@example.com"
./genmedia search -k="model" -v="gemini-3-pro-image-preview" -o=csv > pro_images.csv
./genmedia search -k="mode" -v="ingested" --json
```

### `list-errors` — Inspect Failed Generation Records

Find all documents containing a non-empty `error_message` field, sorted newest first:

```bash
./genmedia list-errors
./genmedia list-errors --view=csv > failed_generations.csv
./genmedia list-errors --limit=10 --json
```

### `top-users` & `top-models` — Aggregate Collection Usage

Analyze asset generation volume across users and models:

```bash
# Interactive table of top users (press Enter on a user to drill into their documents)
./genmedia top-users

# Breakdown of user activity grouped by model
./genmedia top-models --view=table
./genmedia top-models --view=csv > model_usage.csv
./genmedia top-models --json
```

### `add`, `update`, & `delete` — Mutate Documents Safely

Create, merge-update, or delete documents in the collection (all support `--dry-run` and `--json`):

```bash
# Add a new document from inline JSON
./genmedia add --data='{"model":"veo-3.1-fast-generate-001","mime_type":"video/mp4","prompt":"ocean waves"}'

# Merge-update an existing document from inline JSON or a JSON file
./genmedia update <DOCUMENT_ID> --data='{"rewritten_prompt":"calm ocean waves at sunset"}'
./genmedia update <DOCUMENT_ID> --data-file=patch.json --dry-run

# Delete a document by ID
./genmedia delete --id="<DOCUMENT_ID>" --dry-run
```

### `check-operation` — Inspect Long-Running Vertex AI Operations

Inspect the status of a long-running Vertex AI video generation operation via `gcloud`:

```bash
./genmedia check-operation <OPERATION_ID> --location=us-central1
./genmedia check-operation <OPERATION_ID> --json
```

---

## Agent-Aware (A2A) CLI Features

`genmedia` is designed for both human developers and autonomous AI coding agents:

- **Logical Command Groups:** Commands are organized under `Browse & Query`, `Analytics`, `Ingest & Mutation`, and `Operations`.
- **Deterministic Machine Output (`--json`):** Every command supports `--json` to emit structured JSON to `stdout`.
- **Non-Interactive Fallback (`--no-tui` / `GENMEDIA_NO_TUI=1`):** Prevents agents from hanging on interactive Bubble Tea prompts.
- **Mutative Safety (`--dry-run`):** `ingest`, `add`, `update`, and `delete` support `--dry-run` to preview payloads before writing to Firestore.
- **Context Window Protection (`--limit` / `-n`):** Scope query results on `list`, `search`, `list-errors`, `top-users`, `top-models`, and `ingest`.

---

## Development

```bash
cd experiments/genmedia-collection-manager
gofmt -s -w .
go vet ./...
go build ./...
go test -race -v ./...
```

See [`developers_guide.md`](developers_guide.md) for architecture details on the Cobra command layout and shared Bubble Tea TUI components.

## License

Licensed under the **Apache License 2.0** (see source file headers for full license details).

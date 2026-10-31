# Genmedia Collection Manager (`genmedia`) — Agent Instructions

## Overview

`genmedia-collection-manager` (`genmedia`) is a dual-mode (Interactive TUI + Agent-Aware CLI) tool in Go for inspecting, searching, aggregating, exporting, and bulk-ingesting generative media asset records (`MediaItem`) in Google Cloud Firestore and Google Cloud Storage (GCS).

## Key Capabilities & Commands

- **Browse & Query (`GroupBrowse`):**
  - `genmedia list` — List and export documents (`--media-type`, `--fields`, `--view=table|json|text|csv`, `--limit`).
  - `genmedia get [DOCUMENT_ID]` — Fetch a single document as JSON.
  - `genmedia search -k <field> -v <value>` — Query documents by equality (`-o=table|json|text|csv`, `--limit`).
  - `genmedia list-errors` — List documents with a non-empty `error_message` (`--view`, `--limit`).
- **Analytics (`GroupAnalytics`):**
  - `genmedia top-users` — Rank users by document count (`--view`, `--limit`).
  - `genmedia top-models` — Group user generation counts by model (`--view`, `--limit`).
- **Ingest & Mutation (`GroupMutate`):**
  - `genmedia ingest gs://<bucket>/<prefix>` — Scan a GCS prefix, generate batch CSV manifests (`--csv-preset=generic|batch-prompt|vto-models|vto-catalog`), or bulk-register `MediaItem` documents in Firestore (`--register`, `--dry-run`).
  - `genmedia add --data='{...}'` — Create a document (`--dry-run`).
  - `genmedia update <id> --data='{...}' | --data-file=...` — Merge-update a document (`--dry-run`).
  - `genmedia delete --id=<id>` — Delete a document (`--dry-run`).
- **Operations (`GroupOps`):**
  - `genmedia check-operation <op-id>` — Check Vertex AI LRO status via `gcloud`.

## Development Standards

- Follow Google Go readability conventions (`gofmt -s -w .`, `go vet ./...`, `golangci-lint run`).
- Always use `--json` or `--no-tui` (`GENMEDIA_NO_TUI=1`) when invoking commands from automated scripts or agent sessions.
- Use `--dry-run` before running mutative commands (`ingest --register`, `add`, `update`, `delete`).

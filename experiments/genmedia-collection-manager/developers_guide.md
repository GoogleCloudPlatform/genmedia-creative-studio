# Developer's Guide

This guide provides architecture and development guidance for contributors to `genmedia-collection-manager` (`genmedia`).

## Architecture

The application is built in Go using [Cobra](https://github.com/spf13/cobra) for CLI routing and the [Charm Bracelet](https://github.com/charmbracelet) ecosystem for interactive terminal UI (TUI) views:

*   **[Bubble Tea](https://github.com/charmbracelet/bubbletea):** Model-View-Update (MVU) framework for interactive tables and document pagers.
*   **[Bubbles](https://github.com/charmbracelet/bubbles):** Reusable table and viewport components.
*   **[Lipgloss](https://github.com/charmbracelet/lipgloss):** Semantic terminal styling (`AccentStyle`, `PassStyle`, `WarnStyle`, `FailStyle`, `MutedStyle`, `IDStyle`).

### Datastore Clients (`cmd/firestore.go` & `cmd/ingest.go`)

*   **Firestore (`cmd/firestore.go`):** `NewFirestoreClient` connects to either the default Firestore database or a named database (`--database-id` / `GENMEDIA_DATABASE` / `GENMEDIA_FIREBASE_DB`). `validateDocID` guards against empty IDs and path-traversal segments (`..`, `/`).
*   **Cloud Storage (`cmd/ingest.go`):** `scanGCSMediaObjects` uses `cloud.google.com/go/storage` to iterate objects under a `gs://<bucket>/<prefix>`, infer MIME types (`image/*`, `video/*`, `audio/*`), generate deterministic IDs (`gcs_<16-hex-sha256>`), export workflow CSV manifests (`generic`, `batch-prompt`, `vto-models`, `vto-catalog`), and optionally bulk-register `MediaItem` documents into Firestore via `firestore.BulkWriter`.

### Shared UI & Agent-Aware Output (`cmd/ui.go`)

*   `resolveEffectiveView` enforces `--json` and `--no-tui` (`GENMEDIA_NO_TUI=1`) overrides so automated agents never block on an interactive TUI program.
*   `applyLimit` caps returned slices when `--limit` (`-n`) is specified.
*   `writeCSV` and `writeJSON` serialize tabular and structured outputs cleanly to `os.Stdout` or a target file.

## Development & Verification

Run formatting, static analysis, build, and tests from `experiments/genmedia-collection-manager`:

```bash
gofmt -s -w .
go vet ./...
go build ./...
go test -race -v ./...
```

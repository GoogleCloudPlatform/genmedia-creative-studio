# Agent Guidelines for GenMedia Creative Studio

This document provides guidelines for AI agents working on the GenMedia Creative Studio codebase (`GoogleCloudPlatform/genmedia-creative-studio`, formerly `vertex-ai-creative-studio`).

## Scope of Work

- Do not modify code within the `experiments/` directory when refactoring or updating the main application. If a global change (like a model deprecation) impacts an experiment, add an inline `# TODO:` or `// TODO:` comment near the affected code in the experiment rather than attempting to refactor its logic.
- **Repository & Module Naming:** The canonical GitHub repository is `GoogleCloudPlatform/genmedia-creative-studio`. All Go module paths and internal imports must use `github.com/GoogleCloudPlatform/genmedia-creative-studio/...` (never the legacy `vertex-ai-creative-studio` name).

## Styling

- Prefer using shared styles from `components/styles.py` for common UI elements and layout structures.
- Page-specific or component-specific styles that are not reusable can be defined locally within those files.

## Google Cloud Storage (GCS)

- All interactions with GCS for storing media or other assets should use the `store_to_gcs` utility function located in `common/storage.py`.
- This function is configurable via `config/default.py` for bucket names.

## Configuration

- Application-level configuration values, such as model IDs, API keys (though avoid hardcoding keys directly), GCS bucket names, and feature flags, should be defined in `config/default.py`.
- Access these configurations by importing `cfg = Default()` from `config.default`.

## State Management

- Global application state (e.g., theme, user information) is managed in `state/state.py`.
- Page-specific UI state should be defined in corresponding files within the `state/` directory (e.g., `state/imagen_state.py`, `state/veo_state.py`).

## Error Handling

- For errors that occur during media generation processes and need to be communicated to the user, use the `GenerationError` custom exception defined in `common/error_handling.py`.
- Display these errors to the user via dialogs or appropriate UI elements.
- Log detailed errors to the console/server logs for debugging.

## Adding New Generative Models

- When adding a new generative model capability (e.g., a new type of image model, a different video model):
  - Add model interaction logic (API calls, request/response handling) to a new file in the `models/` directory (e.g., `models/new_model_name.py`).
  - Create UI components for controlling the new model in a subdirectory under `components/` (e.g., `components/new_model_name/generation_controls.py`).
  - Create a new page for the model in `pages/` (e.g., `pages/new_model_name.py`), utilizing the page scaffold and new components.
  - Define any page-specific state in `state/new_model_name_state.py`.
  - Add relevant configurations to `config/default.py`.
  - Update navigation in `config/navigation.json`.

## Metadata

- When storing metadata for generated media, use the `MediaItem` dataclass from `common/metadata.py` and the `add_media_item_to_firestore` function.
- Ensure all relevant fields in `MediaItem` are populated.

## Testing

- Write unit tests for utility functions and model interaction logic.
- Aim to mock external API calls during unit testing.
- Use `pytest` as the testing framework.

## Code Quality

- Use `ruff` for code formatting and linting. Ensure code is formatted (`ruff format .`) and linted (`ruff check --fix .`) before submitting changes.

## Issue Tracking

This project uses **bd (beads)** for issue tracking.
Run `bd prime` for workflow context, or install hooks (`bd hooks install`) for auto-injection.

**Quick reference:**
- `bd ready` - Find unblocked work
- `bd create "Title" --type task --priority 2` - Create issue
- `bd close <id>` - Complete work
- `bd dolt push` - Sync with git (run at session end)

For full workflow details: `bd prime`



## Issue Tracking with Beads (`bd`)

When working with issues using the `bd` (beads) command-line tool, adhere to the following tactical guidelines:

*   **Continuous Synchronization:** Always run `bd dolt push` at the beginning of a session to ensure your local issue tracker is aligned with the remote git repository. Run `bd dolt push` again at the very end of your session before your final `git push`.
*   **State Awareness:** When analyzing a bug or feature request, first run `bd ready` to check if there is already an existing, unblocked issue tracking the work. Do not create duplicate issues.
*   **Atomic Updates:** When you complete a task or fix a bug, immediately close the corresponding issue (`bd close <id>`) in the same commit or PR as the fix. Do not leave issues dangling.
*   **Clear Descriptions:** If you discover a new bug during your workflow that is out of scope for your current task, log it immediately using `bd create "Title" --type bug --priority <level>`. Ensure the description clearly outlines the reproduction steps and the context in which it was found.
*   **Force-Syncing JSONL to Database:** In sandbox or CLI-restricted environments, the Beads auto-import process (which parses `.beads/issues.jsonl` on startup) only triggers if it detects the database is completely empty. If the database state falls out of sync with `.beads/issues.jsonl` due to consecutive automated writes or interrupted sessions, you must explicitly run `bd import` to sync the disk-based JSONL state back into the Dolt database. If you need to clean up or recover from a bad tracking state, you can surgically edit the `.beads/issues.jsonl` file directly on disk, and then execute `bd import` to cleanly refresh the tracking system.

## 🤖 GitHub Automation Agents

This repository uses **Google's Gemini CLI** to automate software engineering tasks. Our AI agents assist with code reviews, issue triage, and general maintenance to keep the project moving efficiently.

## Automatic Behaviors

These agents run automatically based on events in the repository.

### 🔎 Code Reviewer

- **Trigger:** When a **Pull Request** is opened.

- **Action:** The agent reviews the code changes (diff), looking for bugs, security issues, and style improvements.
- **Output:** It posts review comments directly on the PR.
- **Note:** The agent focuses on the *diff* only and provides constructive feedback. It does not replace human review.

### 📋 Issue Triage

- **Trigger:** When a new **Issue** is opened.

- **Action:** The agent analyzes the title and body of the issue.
- **Output:** It automatically applies relevant **Labels** (e.g., `bug`, `enhancement`, `question`) to help organize the backlog.

---

## Maintainer Commands

Project maintainers (Owners, Members, Collaborators) can manually invoke the agents using comment commands.

| Command | Description |
| :--- | :--- |
| `@gemini-cli /review` | Manually triggers a full code review on the current Pull Request. |
| `@gemini-cli /triage` | Manually triggers label analysis on the current Issue or PR. |
| `@gemini-cli [question]` | Ask the agent a question about the codebase or request a specific task.  

*Example:* `@gemini-cli Explain how the authentication flow works.` |

> **Note:** These commands are restricted to project maintainers to prevent abuse and manage costs.

---

## Workflow Architecture

The automation is built on GitHub Actions using a "Router-Worker" pattern:

1. **Dispatch Router (`gemini-dispatch.yml`):** The entry point. It listens for events, validates permissions, and routes the request to the correct worker.
2. **Worker Workflows:**
    - `gemini-review.yml`: Handles code analysis.
    - `gemini-triage.yml`: Handles labeling.
    - `gemini-invoke.yml`: Handles general Q&A.

This system is powered by the [Gemini CLI](https://github.com/google-github-actions/run-gemini-cli) action.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
- **SSH PASSPHRASE**: If a `git push` command hangs or fails asking for an SSH passphrase, ABORT the automated push attempt and explicitly instruct the user to execute the push manually.
<!-- END BEADS INTEGRATION -->

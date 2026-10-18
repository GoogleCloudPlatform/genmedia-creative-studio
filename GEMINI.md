---

## 7. Documentation Workflows

### Updating Documentation for New Features/Experiments

When new code, features, or experiments are added, it's crucial to update the relevant documentation to ensure discoverability and maintainability.

1.  **Identify Relevant Docs:** Determine which documentation files need updating (e.g., main `README.md`, `experiments/README.md`, `developers_guide.md`).
2.  **Analyze Existing Conventions:** Read the target documentation to understand its structure, tone, and formatting conventions for similar items.
3.  **Synthesize New Content:** Extract key information from the new feature's source code or its own README to create a concise and accurate description.
4.  **Propose Changes:** Present the proposed documentation changes to the user for review and approval before applying them. Use markdown blocks to clearly show the additions or modifications.
5.  **Apply Changes:** Use the `replace` or `write_file` tool to apply the approved changes.

### Integrating External Agent Skills

When importing, copying, or adding a new Agent Skill to the repository:

1.  **Verify Structure**: Ensure the skill folder has a conforming `SKILL.md` file with YAML frontmatter at its root.
2.  **Metadata Extraction**: Read the `SKILL.md` file to extract the `name`, `description`, and other relevant attributes from its YAML frontmatter.
3.  **Synchronize READMEs**: Dynamically and consistently update both the main workspace `README.md` (or the component-level README) and the skills directory `README.md` with the extracted skill name and description to ensure discoverability.
4.  **Issue Tracking**: Log the skill addition in the beads (`bd`) issue tracker by creating, claiming, and closing a dedicated issue for the work.


## 8. Mesop Development Practices

### Refactoring and State Management
*   **Dynamic UI Binding:** UI components must never hardcode lists of available models for specific modes. Instead, add helper functions to the respective `config/*_models.py` file (e.g., `get_models_by_mode`) and dynamically generate UI dropdowns based on the model configuration's declared capabilities.
*   **Component Modularity:** Mesop pages can quickly grow to thousands of lines. Proactively refactor UI sections (e.g., `upload_ui`, `controls`, `gallery`) into separate files within a `components/` directory to keep page files tractable.
*   **Event Handler Factories:** When sharing UI components across multiple pages that maintain their own `PageState` classes, use closure factories (e.g., `def get_on_click_handler(state_class): ...`) to generate reusable event handlers. This avoids duplicating state-mutation logic across pages.
*   **Safe Python Refactoring:** When executing large refactors via CLI tools, be extremely cautious with string replacements (`sed` or python scripts) on nested Mesop structures (`with me.box():`). Missing or extra spaces will cause fatal `IndentationError`s. Prefer targeted replacements or abstracting the block into a function first. When using python scripts to modify large configuration lists or Mesop component trees, avoid greedy regex replacements (`re.sub`). Rely on exact string matching or AST manipulation to prevent accidentally corrupting adjacent, structurally identical blocks.

### Component Styling Gotchas
*   **Button Types:** The `me.content_button` component strictly enforces the `type` argument as a literal: `'raised'`, `'flat'`, `'stroked'`, or `'icon'`. Using invalid MD3 concepts like `'tonal'` will cause a Pydantic `ValidationError` and crash the UI block.
*   **Interactive Toggles:** When changing the background of a button dynamically (e.g., to indicate selection), ensure you also dynamically update the `color` property of its children (e.g., `me.theme_var("on-primary") if is_selected else me.theme_var("on-surface")`) so icons and text don't become invisible.
*   **Consistent Workflow Page Layouts:** When designing multi-step generative workflows (like Storyboarder, Veo, or Interior Design), prefer a balanced two-column top row: placing the main story concept or text prompter in a wider left column (e.g., 60% width) and optional reference media uploaders/character setups in a narrower right column (e.g., 40% width). Nested configuration/settings selectors should reside below them inside a collapsible panel.
*   **Divider Styling Constraint:** The `me.divider` component strictly rejects the `style` argument. To apply margins, padding, or custom alignment around a line divider, wrap `me.divider()` inside a styled `me.box`.
*   **Auto-dismissing Snackbars:** Do not leave `state.show_snackbar = True` active indefinitely. Always implement a generator helper function to auto-dismiss snackbars:
    ```python
    def show_snackbar(state: PageState, message: str):
        state.snackbar_message = message
        state.show_snackbar = True
        yield
        time.sleep(3)
        state.show_snackbar = False
        yield
    ```

### SDK Integration Nuances
*   **Model Parameter Probing:** The `google-genai` SDK and Vertex AI backend can be incredibly strict. For example, `types.ImageConfig(image_size="512PX")` will fail validation; it must be `"512"`. `types.ThinkingConfig` expects `thinking_budget` (not `thinking_level`), and setting `include_thoughts=True` without a budget throws a `400 INVALID_ARGUMENT`. Always write a short `test_probe.py` script to verify exact SDK payload shapes before wiring them into the Mesop UI state.



### Mesop Serialization Bug (`list[dataclass]` / `__annotations__` crash)
*   **The Problem:** Mesop `1.2+` has a severe bug in its state deserialization logic when running on Python 3.10+. If a `@me.stateclass` contains a field defined as a list of complex objects (e.g., `list[dict]`, `list[MediaItem]`), Mesop will crash with `AttributeError: 'PageState' object has no attribute '__annotations__'` when the frontend attempts to sync state back to the backend.
*   **The Fix:** NEVER store `list[dataclass]` or `list[dict]` directly in a Mesop state class if that state needs to be sent back and forth during interactions. Instead, store the data as a serialized JSON string: `my_items_json: str = "[]"`. 
*   **The Pattern:** 
    1. During data hydration (e.g., fetching from Firestore), serialize your list to JSON: `state.my_items_json = json.dumps([asdict(i) for i in items], default=str)`.
    2. During the UI render loop, safely unpack it back into python objects before generating your components.
    3. **Warning (Firestore & DatetimeWithNanoseconds):** Watch out for `datetime` and Firestore `DatetimeWithNanoseconds` objects. They serialize to ISO strings cleanly, but standard `json.dumps()` without a default handler will crash with `TypeError: Object of type DatetimeWithNanoseconds is not JSON serializable`. **You MUST always pass `default=str` or a custom date serializer (e.g., `default=json_default_serializer`) to any `json.dumps` call that processes Firestore data or dictionary payloads stored in the Mesop state.**

### Cloud Run Deployment & CSRF
*   **The Problem:** When deploying Mesop to Cloud Run behind a Google Cloud load balancer, the proxy rewrites the `Host` header (often to `127.0.0.1:8080`). Mesop's strict CSRF protection compares the browser's `Origin` header to this internal `Host` header, resulting in a silent `403 Forbidden` block on the `/__ui__` POST endpoint.
*   **The Fix:** You must instruct Gunicorn to trust the proxy headers. In your `Dockerfile` and `Procfile`, append `--forwarded-allow-ips="*"` to the gunicorn command. Additionally, ensure FastAPI is configured with a `BaseHTTPMiddleware` that intercepts `X-Forwarded-Host` and rewrites the `request.scope["headers"]` before the request hits Mesop.

### Lit WebComponents Interop
Mesop allows integrating custom Lit WebComponents, but the bridge between JavaScript and Python is highly specific. When creating custom components like `<banana-button>`:
1. **Property Binding:** Declare properties explicitly in your Lit element's `static properties = { ... }`. Mesop dynamically sets these from the `properties={}` dict in the python wrapper.
2. **Event Dispatching (The Mesop Pattern):** Mesop does **not** rely on standard DOM `CustomEvent` string matching. Instead:
   - In Python, map the event string: `events={"myEventName": on_click}`
   - In JS, define a property to receive the generated event ID: `static properties = { myEventName: { type: String } };`
   - In JS, dispatch using Mesop's global class: `this.dispatchEvent(new MesopEvent(this.myEventName, { value: this.myValue }));`
3. **Python Type Hinting & Linter Suppressions (Critical):** In the python wrapper function (e.g. `@me.web_component(...) def my_component():`):
   - The event handler arguments *must* be strictly typed as a callable accepting a `WebEvent` (e.g., `on_click: Callable[[me.WebEvent], object]`). **Do not use `Any` as the return type of the callback** as it triggers linter warnings (`ANN401`); use `object` or `None`. If you type it as `None` or `Any`, Mesop's reflection engine will silently fail to register the listener, and the events will be dropped over the websocket bridge.
   - Omit the return type annotation of the wrapper function and append `# noqa: ANN201`.
   - Add `# noqa: PLR0913` to suppress "too many arguments" warnings, as Mesop component wrappers naturally require many arguments to bind UI properties and event callbacks.

### Top-Level vs. Local Imports (`PLC0415`)
*   **Top-Level Preference:** In Mesop page files and event generators, always declare standard library and project imports (such as `json`, `uuid`, or utility functions) at the top of the file rather than locally inside event handler functions. This satisfies Ruff's `PLC0415` rule and prevents linting failures during CI/pre-commit checks.

### 🚨 The `git restore` Trap (Data Loss)
When performing iterative, multi-step refactoring in a single session without intermediate commits, **do not use `git restore <file>` or `git checkout -- <file>`** to recover from a botched regex or Python script edit.
*   **Why:** `git restore` resets the file to the last *commit*. This instantly wipes out *all* uncommitted progress you made earlier in the session (such as adding new variables to a `@me.stateclass`, importing new modules, or fixing specific bugs).
*   **The Bug Cycle:** If you `git restore` to fix an indentation error in a UI component, but forget to manually re-add the state variables you defined 10 minutes ago, the app will compile but crash at runtime with `AttributeError: 'PageState' object has no attribute '...'`.
*   **The Solution:** 
    1. Always run `cp file.py file.py.bak` *before* executing a risky string replacement script. If it fails, restore from the local backup: `mv file.py.bak file.py`.
    2. Alternatively, use `git add file.py` to stage known-good intermediate states, allowing you to `git checkout -- file.py` safely back to the *index* rather than the last commit.
## Go Modules & CI Environments

**golangci-lint in go.work Monorepos:**
When configuring `golangci-lint` to run in a CI environment (like GitHub Actions) across a multi-module `go.work` repository that uses local `replace` directives (e.g., `replace github.com/.../mcp-common => ../mcp-common`), do **not** use the official `golangci/golangci-lint-action` at the root. The GitHub runner filesystem boundaries will cause the Go typechecker to fail with `context loading failed: no go files to analyze`.

Instead, you MUST:
1. Physically delete `go.work` and `go.work.sum` in the CI pipeline before linting so Go treats the modules as fully isolated.
2. Manually install `golangci-lint` via curl.
3. Run the linter in a bash loop, explicitly changing directories into each submodule (`cd $dir && golangci-lint run ./...`).

**CI Verification Scripts (mcptools):**
If a Go application initializes network-dependent clients (like Google Cloud `genai.NewClient` or `texttospeech.NewClient`) on startup, it will hang indefinitely inside headless CI runners that lack ADC (Application Default Credentials). To allow tools like `mcptools` to verify the STDIO handshake in CI, you MUST make global client initialization non-fatal during `main()` and defer the strict credential check until the client is actually invoked inside the tool handler.

**Monorepo Dependency Synchronization & Isolated CI:**
When a shared internal library (e.g., `experiments/mcp-genmedia/mcp-genmedia-go/mcp-common`) is updated in a multi-module repository, all dependent submodules must have their dependencies synchronized.
Even if local development runs successfully using `go.work`, CI pipelines isolate modules by deleting `go.work` and running `go mod tidy` + `git diff --exit-code -- go.mod go.sum` + `golangci-lint run --config ../.golangci.yml ./...` within each module directory individually.
Therefore:
1. **Always run `go mod tidy` with `GOWORK=off`** across all 10 submodules (never `go work sync`, which pushes workspace indirect versions into unrelated modules and fails the isolated CI tidiness gate):
   ```bash
   for d in mcp-*; do (cd "$d" && GOWORK=off go mod tidy && GOWORK=off go mod verify); done
   ```
2. **Pin `mcp-common` to `v0.0.0` (never a commit pseudo-version):** Every sibling `mcp-*-go/go.mod` must require `github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common v0.0.0` paired with `replace ... => ../mcp-common`. Do not commit a `v0.0.0-<timestamp>-<sha>` pseudo-version, as Renovate treats it as a git digest and opens a `fix(deps)` PR after every commit on `main`.
3. **Watch out for the `.gitignore` `**/mcp-*-go/mcp-*-go` rule:** Because `.gitignore` ignores compiled server binaries whose names match their directory names (`mcp-*-go`), gitignore-aware searchers (`rg` / `ripgrep`) silently skip `experiments/mcp-genmedia/mcp-genmedia-go/mcp-*-go/` unless `--no-ignore` is passed (or use `git grep`), and staging files in those directories requires `git add -f`.

## 9. Linting and Code Quality

### Selective Linting
*   **Targeted Execution:** To avoid massive, unintended changes across the entire project, always run linting and formatting tools (e.g., `ruff`, `black`, `isort`) on **only the files you have modified**.
*   **Command Pattern:** Prefer `ruff check --fix path/to/file.py` and `ruff format path/to/file.py` over running them on the project root (`.`).

### Python Refactoring Risk: Automated Tooling
*   **The Problem:** Running `ruff check --fix .` or similar automated formatters globally on a large codebase can sometimes aggressively strip out "unused" imports that are actually load-bearing. For example, in Mesop applications, `import pages.my_page` might not be explicitly called but is required for its `@me.page` decorators to register routes. **This is also highly dangerous for configuration files (like `config/` or `__init__.py`) which often "re-export" variables for other modules to use.**
*   **The Fix:** 
    1. **Never run global formatting commands.** If you modify 3 files, run `ruff format` and `ruff check --fix` *only* on those 3 files.
    2. Before committing, always run `git diff` and manually verify that no unexpected imports were deleted or critical structure was modified.
    3. If a linter warns about an unused import that you know is required for registration, append `# noqa: F401` to the import line instead of deleting it.


### Mesop Import Protection
*   **Critical Imports:** In Mesop applications, imports in `main.py` (and other entry points) are often required for route registration via decorators (e.g., `@me.page`). Linters may incorrectly flag these as unused.
*   **Preservation:** ALWAYS preserve these imports by adding a `# noqa: F401` comment to the end of the import line. NEVER allow a linter to remove them, as this will break the application's routing.

### Transitive Dependency Awareness
*   **OpenSSL Errors:** If you encounter `ModuleNotFoundError: No module named 'OpenSSL'`, this usually indicates that `pyOpenSSL` is missing. 
*   **Resolution:** While not always directly imported, `pyOpenSSL` is a common transitive dependency for secure transport in Google SDKs and `google-auth`. Add `pyOpenSSL` to `pyproject.toml` and run `uv sync` to resolve the issue.

### 10. Dependency and Version Management
*   **Version Bumping:** When updating the application version number in `pyproject.toml`, you **MUST** also update the hardcoded `VERSION` fallback string in `config/default.py` (e.g., `VERSION: str = "1.7.4"`). This fallback is critical for local development environments where the package is not installed as an editable module via `uv`, which causes `importlib.metadata` to fail.

## 11. Starlight Documentation Workflows

The project uses Starlight (Astro) for its primary documentation site, located in the `docs-site/` directory. When asking Gemini to create or update documentation, adhere to these guidelines:

### Modifying Starlight Documentation
*   **Target Directory:** All Starlight markdown files reside in `docs-site/src/content/docs/`.
*   **Mirrored Documentation Files (Crucial):** Certain key documentation files exist at both the root level and within the Starlight directory. When updating one, you MUST update its twin in tandem to prevent documentation drift:
    *   `README.md` ↔ `docs-site/src/content/docs/core/index.md` (Primary landing page and featureset list)
    *   `environment_variables.md` ↔ `docs-site/src/content/docs/core/installation/environment_variables.md`
    *   `FAQ.md` ↔ `docs-site/src/content/docs/core/FAQ.md`
    *   `developers_guide.md` ↔ `docs-site/src/content/docs/core/developers_guide.md`
*   **Feature Hierarchy & Usage:** When adding a new model or capability, ensure it is added to the featureset list in both `README.md`/`core/index.md` and detailed under the appropriate section in `docs-site/src/content/docs/core/usage.md`.
*   **Frontmatter Requirement:** Every markdown file within the Starlight content directory MUST have YAML frontmatter with a `title` attribute. Example:
    ```markdown
    ---
    title: "Your Document Title"
    ---
    ```
*   **Relative Paths:** When linking to local images (e.g., `assets/image.png`), you MUST use correct relative paths based on the file's final location in the Starlight directory structure, not the original source code location.
*   **Sidebar Configuration:** If you add a new page or section, you must update `docs-site/astro.config.mjs` to include the new `slug` in the sidebar configuration so it appears in the site navigation.
*   **Local Development:** Instruct the user to run `npm run dev` inside `docs-site/` to preview changes locally. If images break or frontmatter schemas fail, restart the dev server to clear the Vite cache.

### The "Minimal Stub" Pattern for Source READMEs
When fully documenting an experiment or module, move the detailed content (architecture, tutorials, guides) into the Starlight `docs-site/` structure. Replace the original `README.md` file (e.g., `experiments/my-app/README.md`) with a "Minimal Stub" that provides basic local setup instructions and a prominent link pointing developers to the centralized Starlight documentation site.

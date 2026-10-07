---
title: "Changelog & Notices"
---

Stay up-to-date with the latest releases, upcoming breaking changes, and major architectural improvements to GenMedia Creative Studio.

## ⚠️ Developer Notices & Action Items

### ✅ Git History Scrub Completed (August 2026)
**Impact:** High (Requires local branch resets for existing clones)

We have completed a repository-wide Git history scrub using `git-filter-repo` to remove historical compiled Go binaries and large orphaned media assets, reducing repository clone size by **~60% (from ~400MB to ~160MB)**.

Because this operation rewrote historical commit hashes on `main`, existing local clones will fail to pull normally due to diverged commit histories.

#### 🛠️ Instructions for Existing Clones

##### Option 1: Fast Reset (No uncommitted local changes)
If you have no uncommitted local work:
```bash
git fetch origin
git checkout main
git reset --hard origin/main
git clean -fd
```

##### Option 2: Fresh Clone (Recommended for a clean slate)
The easiest way to get the smaller packfile size immediately:
```bash
git clone git@github.com:GoogleCloudPlatform/genmedia-creative-studio.git
```

##### Option 3: Preserving In-Flight Feature Branches
If you have an active local feature branch with unmerged commits:
1. Rebase your feature branch commits onto the new `origin/main`:
   ```bash
   git fetch origin
   git rebase --onto origin/main <old-base-commit> <your-feature-branch>
   ```
2. Or cherry-pick your work onto a fresh branch cut from new `origin/main`:
   ```bash
   git checkout -b my-feature-branch-rebased origin/main
   git cherry-pick <your-commit-shas>
   ```

## Recent Updates

### Removed `gemini-2.5-flash-image` as a Selectable Image Model (October 2026)
* **Models:** `gemini-2.5-flash-image` has been removed as a selectable image generation model. `gemini-nano-banana-2.1` is now the current default for image generation, with the Gemini 3.1 series (`gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`) and `gemini-3-pro-image` retained as supported options.

### Transitioning to Nano Banana as Imagen is Deprecated (August 2026)
* **Models:** We are in the process of transitioning to Nano Banana (Gemini Image Generation, `gemini-2.5-flash-image`) as Imagen has been deprecated. All Imagen models were shut down across Google — including Vertex AI — around August 17, 2026. See the [Imagen models migration guide](https://firebase.google.com/docs/ai-logic/imagen-models-migration?api=dev) for the replacement mapping.

### Starlight Documentation Hub (May 2026)
* **Docs:** Migrated all deployment guides, architecture diagrams, and MCP tool instructions to a centralized Starlight (Astro) documentation hub.
* **UI:** Streamlined the root `README.md` to serve as a clean landing page pointing to the new docs.


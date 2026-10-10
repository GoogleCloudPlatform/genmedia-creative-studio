# Changelog

## Unreleased

*   **Removal:** Removed `gemini-2.5-flash-image` (alias "Nano Banana") as a supported Gemini image model. It is no longer selectable in `gemini_image_generation` (`mcp-gemini-go`) or `nanobanana_image_generation` (`mcp-nanobanana-go`); the current default remains `gemini-nano-banana-2.1` and the `gemini-3.x` image models are unaffected.
*   **Feature:** Add `gemini-nano-banana-2.1` (Nano Banana 2.1) as a supported Gemini image model and make it the default for both `nanobanana_image_generation` (`mcp-nanobanana-go`) and `gemini_image_generation` (`mcp-gemini-go`). The model supports 15 aspect ratios (including `9:21`) and `1K`/`2K`/`4K` sizes. Because Nano Banana 2.1 rejects the `seed` parameter (the API errors if it is set), any caller-supplied `seed` is now dropped for this model instead of being forwarded.
*   **Fix:** `install-online.sh` and `install.sh` now ad-hoc codesign (and clear the quarantine attribute on) macOS binaries after install. Previously, downloaded and locally-built darwin binaries could be silently killed by Gatekeeper (`SIGKILL`, exit 137) on launch with no error output, causing MCP clients to report failed/unresponsive server starts.

## [3.21.0](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/compare/mcp-v3.20.1...mcp-v3.21.0) (2026-10-10)


### Features

* **mcp:** add gemini-nano-banana-2.1 as default image model ([#1985](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1985)) ([f80ec57](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/f80ec573493fc6eb719b1395afc67551598dcb08))
* **mcp:** remove gemini-2.5-flash-image from genmedia MCP servers ([#1994](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1994)) ([c9ccadd](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/c9ccadd862cb4158ac0de12856f44c53a84d8b55))


### Bug Fixes

* add application-layer OIDC auth to mcp-avtool-go HTTP/SSE (b/565096167) ([#1981](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1981)) ([1bbb1ca](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/1bbb1ca936593e6ccd0d878f964acda5294ecab6))
* **deps:** update all non-major dependencies ([#1968](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1968)) ([0a718c5](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/0a718c540aad0cda6e1568f7350feece5921eba7))
* **deps:** update all non-major dependencies ([#1984](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1984)) ([1cb9679](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/1cb9679e3f40b86cdce6a604d78dce5e15c994d3))
* **deps:** update all non-major dependencies ([#1991](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1991)) ([7ea75d7](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/7ea75d790467823086363e70c84458b28e7cd00f))
* **deps:** update all non-major dependencies ([#2005](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/2005)) ([23ca975](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/23ca9756e54ebf000b5ebe47bf06907bc3318437))
* **deps:** update all non-major dependencies ([#2006](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/2006)) ([d40319d](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/d40319d818058df067a0f83636d3790979b3edf7))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 0e7f9d2 ([#1917](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1917)) ([0eabe0b](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/0eabe0b77e263332ae933b4f9da60e8397d357a1))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 124173d ([#1961](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1961)) ([1e192aa](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/1e192aa25517e43a1fc2b2cca42cd99706d3f1d9))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 18e17ce ([#1966](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1966)) ([9631b26](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/9631b26d05fd3a9d93d40339cd8b631cd77ac8fd))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 1c298c5 ([#1933](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1933)) ([d3b5a57](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/d3b5a57afca010001c2a115067b89166f7a44a18))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 1e192aa ([#1964](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1964)) ([dc5a92d](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/dc5a92ddfa32d86624bf99eeb5b73a6179f52fdb))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 255c50d ([#1948](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1948)) ([2da4a67](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/2da4a67a466770ae9bad6bf8526a76e5bc812300))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 2da4a67 ([#1951](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1951)) ([daa2575](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/daa25757d0be7e5f11487d14a23a0493414838dc))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 4d3c42f ([#1957](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1957)) ([b78c96e](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/b78c96e836916e84f83e50e65460bbb8ce7fbb5f))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 50a918c ([#1989](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1989)) ([a5f5ba4](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/a5f5ba4352aedac0018788080148771f3144ef68))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 60fd64b ([#1928](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1928)) ([6465bcf](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/6465bcf999828833c28c2e295f36197e266806eb))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 7367ff5 ([#1919](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1919)) ([33bab51](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/33bab513d8324ec3ed6304ae0eaca3ed7f1628a3))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 8fd965a ([#1944](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1944)) ([015a304](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/015a3047ed934c82aabf3fdc1844c3f646d19b8e))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 9631b26 ([#1972](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1972)) ([19f33cc](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/19f33cc7b49dfe9d94dbfd725d98859d56763961))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 96ed797 ([#1909](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1909)) ([ce294ac](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/ce294ac39185bdc7980079db625f942bcfabdffb))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to a7f6308 ([#1947](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1947)) ([255c50d](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/255c50d1dc3277c16957b6564dfa613360f8775d))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to cac85e9 ([#1913](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1913)) ([0e7f9d2](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/0e7f9d28295a9a0b675f7507d6503c60b0e246c0))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to d3b5a57 ([#1938](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1938)) ([c1ddc7e](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/c1ddc7ef4a20921e3635aa6619440b5784c3a583))
* **deps:** update github.com/googlecloudplatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to f80ec57 ([#1978](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1978)) ([b42ba6f](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/b42ba6f5d150001ad32db0d785f6698c10ed11b0))
* **mcp-chirp3-go:** go mod tidy to fix CI build-and-test ([#1987](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1987)) ([17562eb](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/17562eb066db53976fcf002753abfbed2d312ede))
* **mcp-genmedia:** confine caller-supplied output directories (CWE-22 path traversal) ([#1921](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1921)) ([2bf604e](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/2bf604e920f5ec9ac375be5587e2e2b612cd3b53))

## [3.20.1](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/compare/mcp-v3.20.0...mcp-v3.20.1) (2026-09-21)


### Bug Fixes

* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 3087a62 ([#1894](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1894)) ([5b45f52](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/5b45f5254d628a9a72357f47ab34dc9b88695d95))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 40e142b ([#1881](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1881)) ([caedecc](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/caedecc7b51dc6f2016ab81b93f38b635b651fba))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 4fdae31 ([#1853](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1853)) ([d4ca01e](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/d4ca01ef4c0d4666335529a416fcdd27c797d9cf))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 5b45f52 ([#1907](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1907)) ([ed83d96](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/ed83d96b033825e5d0ab5bfacd18d8db8bee3b7e))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 7589d38 ([#1843](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1843)) ([47e9d6e](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/47e9d6e56cc5047b14b5889e235c0e8de67fb2e5))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 763e337 ([#1857](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1857)) ([c2461da](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/c2461dad4bb008c355eac9d693c3cd3530ff8c13))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 88c354f ([#1890](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1890)) ([c2031ac](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/c2031ac972b73973d3cbd1a5fb6fd7122f7c2338))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 8e0620e ([#1877](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1877)) ([9d54fee](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/9d54feef5475208fb8ee905c4c2be487bde92137))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to ae4be8c ([#1860](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1860)) ([5dfe30d](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/5dfe30d4c5feed8bb541a3af5554215a082e44e1))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to b0287be ([#1885](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1885)) ([283a001](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/commit/283a00124c08f847076decb5b23153bc61c1b680))

## [3.20.0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.19.0...mcp-v3.20.0) (2026-09-12)


### Features

* **mcp-gemini-go:** add gemini_transcribe speech-to-text tool ([#1849](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1849)) ([6e70c05](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/6e70c0502e19524a6167e91359e1a654b95b2e3a))
* **mcp-gemini-transcribe-go:** add standalone Gemini 3.5 Transcribe MCP server ([#1850](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1850)) ([dc2f182](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/dc2f182e07f9af5bbe9301b829e37facf7c5e226))


### Bug Fixes

* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to d5cee2d ([#1840](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1840)) ([adb02ea](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/adb02ea03bbb890056c9669ca6d9830b0fb4e840))

## [3.19.0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.18.2...mcp-v3.19.0) (2026-09-10)


### Features

* **mcp-avtool-go:** add EBU R128 loudness normalization tool ([#1838](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1838)) ([65e3cab](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/65e3cab8a3ea641b530b8f40fb52390c425fc8fb))
* **mcp-avtool-go:** add media trim/cut tool ([#1836](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1836)) ([39d70e0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/39d70e07f47071069f0a5af1094ea4774e37ae24))
* **mcp-avtool-go:** add resize/reframe tool for images and video ([#1839](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1839)) ([48d16d5](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/48d16d5a83970e8810ddcb98c430f29c8f261ebb))


### Bug Fixes

* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 39d70e0 ([#1833](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1833)) ([0755fa1](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/0755fa1e1c8de40dc2e99f6ee2742d855e724c51))

## [3.18.2](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.18.1...mcp-v3.18.2) (2026-09-10)


### Bug Fixes

* **deps:** update all non-major dependencies ([#1764](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1764)) ([195d8c4](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/195d8c4e43f8e1439e153c715d9bc394709fd977))
* **deps:** update all non-major dependencies ([#1798](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1798)) ([254d2f3](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/254d2f30f55d6080d93e591a43e08cf656c1ba30))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 05a061f ([#1800](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1800)) ([26a28d6](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/26a28d6d4ef27cf23d8b7c953957dbfde2832067))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 13e7157 ([#1783](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1783)) ([bee1309](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/bee13098ac9a7bb2ddbae4f94335e2dd283ccedc))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 2d2693a ([#1774](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1774)) ([13e7157](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/13e7157aa773ee4812a6bc57a3b48bbb3e8a1df3))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 31f00b0 ([#1801](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1801)) ([d0ba61e](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/d0ba61e5d291726e0636507c263c5a227207274d))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 4cf3347 ([#1795](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1795)) ([26ddf24](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/26ddf24301f33de51d48039ce7d9fe03965e9a6f))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 4e71935 ([#1826](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1826)) ([ccc0fab](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/ccc0fabed6332e42b2703acadc3947d2fb33c0c8))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 8eb22ce ([#1799](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1799)) ([05a061f](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/05a061f647ad8c34586360989f806db702e94a1a))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to b0791b1 ([#1791](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1791)) ([62ecd7f](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/62ecd7f5f2ff3e45e49a10c2b23ae327b3f719ab))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to bee1309 ([#1790](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1790)) ([b0791b1](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/b0791b1dd61463991434aba311d68d15f3c12de3))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to ccc0fab ([#1827](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1827)) ([99c071d](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/99c071d5dc87d6caa65c2c236fc14c4d4bedfa14))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to eb4acba ([#1797](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1797)) ([8eb22ce](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/8eb22cefbb3d17e3fd0359b83d68fd59e515b6a1))
* **deps:** update module github.com/mark3labs/mcp-go to v1 ([#1796](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1796)) ([ed61373](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/ed61373c6ecbc0f01ece661786b6c073d42f52b5))

## [3.18.1](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.18.0...mcp-v3.18.1) (2026-08-29)


### Bug Fixes

* **mcp-lyria-go:** preserve MP3/C2PA container when saving generated audio ([#1777](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1777)) ([#1778](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1778)) ([323fc2b](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/323fc2b4d4334546b83ecf95067b4b671babe181))

## [3.18.0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.17.0...mcp-v3.18.0) (2026-08-29)


### Features

* **mcp-genmedia-go:** support 0/all for Install All in install.sh ([#1769](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1769)) ([#1771](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1771)) ([cd41524](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/cd4152433f2b935d0503c0ea49b0a10def3ab5a3))


### Bug Fixes

* **deps:** update all non-major dependencies ([#1749](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1749)) ([9b1fb75](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/9b1fb75270729578dec68a083f31db50b4d07220))
* **deps:** update all non-major dependencies ([#1761](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1761)) ([3fd9da9](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/3fd9da9747950a857b36adb1d3628037320249d8))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 9b1fb75 ([#1762](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1762)) ([1546cf6](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/1546cf6a7c8de545e02e01d3b371d505488d43ab))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to eaa1e8c ([#1755](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1755)) ([c7a2743](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/c7a2743c99f2c45bf0d8a4f75d7742015d193375))
* **mcp-lyria-go:** parse nested model_output audio content ([#1768](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1768)) ([#1770](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1770)) ([98ded2c](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/98ded2ce6d75431e42791a9efdcfd4c5ec5b6d64))

## [3.17.0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.16.0...mcp-v3.17.0) (2026-08-27)


### Features

* **mcp-genmedia:** default omni MCP to gemini-omni-1.1-flash-preview ([#1754](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1754)) ([400cc50](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/400cc50fca5f204985b9823559667beb6406a34d))


### Bug Fixes

* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 93a5e6e ([#1747](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1747)) ([5a595d6](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/5a595d624b0fcd0bb8ace9d5e9ef67ed0a2a7d7e))
* **mcp-genmedia:** add SupportedImageSizes and validate Gemini image params ([#1746](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1746)) ([#1750](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1750)) ([5a1d11c](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/5a1d11cdda2a92f409e81d6c6cfde24c28e56a2a))

## [3.16.0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.15.0...mcp-v3.16.0) (2026-08-26)


### Features

* **mcp-genmedia:** expose image_size for Gemini image generation ([#1733](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1733)) ([1376a95](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/1376a959da1048ebf87b44cffe9e9d3d1cd6f917))


### Bug Fixes

* **deps:** update all non-major dependencies ([#1636](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1636)) ([c579b71](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/c579b71d5ddf79d45a7ce602f3475a9b09f43cb7))
* **deps:** update all non-major dependencies ([#1718](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1718)) ([2f7cdae](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/2f7cdae6411cb329f81da223506730ee84aa2a5d))
* **deps:** update all non-major dependencies ([#1738](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1738)) ([a6ec8a2](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/a6ec8a2a7bb868f986f2c501445a94036fca15ee))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 667d963 ([#1721](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1721)) ([e6a930f](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/e6a930f7e2b7d41ba9657ab00df40bcda2ba1cb4))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 69e1a53 ([#1735](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1735)) ([0a94a2b](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/0a94a2b3e36d616e442713f8421634ffc67f3f90))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to c579b71 ([#1666](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1666)) ([42c90b0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/42c90b0d52d5b748024c0ebb935decb07f12dbf9))
* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to d95296d ([#1737](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1737)) ([a81a47d](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/a81a47d325f829233bc2557637dab4d414ead674))
* **mcp-genmedia:** tidy go.mod/go.sum drift in avtool & chirp3 ([#1748](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1748)) ([aba9532](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/aba9532265b18f5f88b8245ce3a6de0e9e30cf6e))

## [3.15.0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.14.1...mcp-v3.15.0) (2026-08-11)


### Features

* **mcp-common:** add resource_link content helper for GCS media output ([#483](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/483)) ([#1635](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1635)) ([4222578](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/42225787ee50f7e2228a60cf8118da1db23ee16e))
* **mcp-genmedia:** add output_filename with deterministic suffixing (nanobanana slice) ([#1628](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1628)) ([1de67aa](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/1de67aabf0dcc63d3ea651582e38d00c1ee64e35))
* **mcp-genmedia:** fan out output_filename across genmedia servers ([#1630](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1630)) ([80852d1](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/80852d1c616686df9c36a2bfe6fbaffc1560573c)), closes [#842](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/842)
* **mcp-genmedia:** output_filename for imagen via GCS copy-rename (imagen slice) ([#1631](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1631)) ([79770b9](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/79770b994be1f35509ea98858e591a351b250fce))
* **mcp-genmedia:** output_filename for veo via GCS copy-rename ([#1632](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1632)) ([1d68493](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/1d68493b80f6594c85cbdf2077fc818a22ad89bc))
* **mcp:** add resource_link content for GCS output across media servers ([#483](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/483)) ([#1637](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1637)) ([9007d4d](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/9007d4d3d56ddc7d611bb48d386a150d7fb80f11))


### Bug Fixes

* **deps:** update module github.com/ghchinoy/cloud-interactions-go to v0.2.1 ([#1629](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1629)) ([58b1b0e](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/58b1b0e7fefa8de618e81c42d68a2a4e9c8de0a9))
* **mcp-genmedia:** tidy modules after cloud-interactions-go v0.2.1 ([#1629](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1629)) ([#1634](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1634)) ([d5ddcc1](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/d5ddcc17f58330316e1aa1dbc3eb5f3743b8fc59))
* **mcp:** incorporate cloud-interactions-go v0.2.0 (carry flat media + sherlog through mcp-common seam) ([#1622](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1622)) ([e681601](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/e6816016e84ea9284ec76f2d58a3c6ae69ceea63))

## [3.14.1](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.14.0...mcp-v3.14.1) (2026-08-10)


### Bug Fixes

* **deps:** update all non-major dependencies ([#1614](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1614)) ([cd23951](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/cd239514baa1bedb6e192d5ea4103a86268f0189))

## [3.14.0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.13.0...mcp-v3.14.0) (2026-08-10)


### Features

* **mcp:** add full omni_video_generation tool surface and shared media persistence ([#1615](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1615)) ([2f5f874](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/2f5f874ade521bfea3618e55c36af5179d99f7f8))
* **mcp:** add omni_video_generation to mcp-gemini-go + Omni contract/drift tests ([#1617](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1617)) ([6fd49c2](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/6fd49c2ae7671dab6f1a28e5ae8324fc22a8dd6a))

## [3.13.0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.12.1...mcp-v3.13.0) (2026-08-10)


### Features

* **mcp:** add Gemini Omni video generation server and Interactions client ([#1613](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1613)) ([37fe970](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/37fe9708f0f3c7698f121bd13316e12c557d4fd8))


### Bug Fixes

* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to 58c6df0 ([#1610](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1610)) ([705341d](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/705341d88e13ba98041c50020e4884abc18f8489))

## [3.12.1](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.12.0...mcp-v3.12.1) (2026-08-10)


### Bug Fixes

* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to cc56082 ([#1604](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1604)) ([361e254](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/361e254605d5093ad082dfff68da42e4ce31551e))

## [3.12.0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.11.1...mcp-v3.12.0) (2026-08-10)


### Features

* **mcp-gemini:** return generated images (inline bytes + gcs_bucket_uri) ([#1605](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1605)) ([cc56082](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/cc560827802345708ca44cbb42e6093ab24567e9))

## [3.11.1](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.11.0...mcp-v3.11.1) (2026-08-10)


### Bug Fixes

* **deps:** update github.com/googlecloudplatform/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common digest to f1af5db ([#1590](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1590)) ([44e0987](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/44e0987acae576ad4527f1e5f10dc5ee880665fb))

## [3.11.0](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/compare/mcp-v3.10.0...mcp-v3.11.0) (2026-08-10)


### Features

* **mcp-genmedia:** optional seed for Nano Banana + Veo tools ([#1599](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/issues/1599)) ([7bc840a](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/commit/7bc840a2c05341a4c18035a0574a6dc1a08ae782))

## 2026-08-09 (v3.10.0)

*   **Feat:** `mcp-nanobanana-go` now saves generated images to Google Cloud Storage via a new optional `gcs_bucket_uri` tool argument, with fallback to the `GENMEDIA_BUCKET` environment variable, and returns V4 signed HTTPS URLs for the uploaded objects. Signed URL lifetime is configurable via the new `NANOBANANA_SIGNED_URL_EXPIRY_HOURS` environment variable (default: 24 hours). (Thanks @danielamigos, #1592.)
*   **Fix:** `mcp-nanobanana-go` no longer silently drops generated image bytes when no output directory is configured.
*   **Chore:** Bumped versions for all MCP servers to `3.10.0` to synchronize the release (`mcp-chirp3-go` resynced from `3.9.0`).

## 2026-07-10 (v3.9.1)

*   **Feat:** Added support for `gemini-3.1-flash-lite-image` ("Nano Banana 2 Lite") with 1K resolution aspect ratios in `mcp-nanobanana-go` and `mcp-gemini-go`.
*   **Fix:** Aligned default model fallbacks in `mcp-nanobanana-go` and `mcp-gemini-go` handlers to match `gemini-3.1-flash-image`.
*   **Chore:** Bumped patch versions for all MCP servers to `3.9.1` to synchronize the release.

## 2026-06-01 (v3.9.0)

*   **Feat:** Promoted Gemini Image models to GA (`gemini-3.1-flash-image` and `gemini-3-pro-image`) in `mcp-gemini-go` and `mcp-nanobanana-go` defaults and model registry.
*   **Feat:** Enhanced `inferMimeType` to support video (`.mp4`, `.mov`, `.webm`, `.avi`, `.mkv`) and document (`.pdf`) formats in `mcp-gemini-go` and `mcp-nanobanana-go`.
*   **Chore:** Bumped minor versions for all MCP servers to `3.9.0` to synchronize the release.

## 2026-04-15 (v3.8.0)

*   **Feat:** Added support for `gemini-3.1-flash-tts-preview` to the `gemini_audio_tts` tool in `mcp-gemini-go` and set it as the default model.
*   **Chore:** Bumped minor versions for all MCP servers to synchronize the release.

## 2026-04-14 (v3.7.2)

*   **Fix:** Removed `duration` from the `veo_extend_video` tool schema in `mcp-veo-go`. Because the extension duration is strictly hardcoded to 7 seconds by the backend API, exposing it as an optional parameter confused LLM agents, leading them to falsely assume a conflict between the API requirements and the model's standard limits.

## 2026-04-14 (v3.7.1)

*   **Fix:** Corrected parameter parsing in `mcp-veo-go`'s `veo_extend_video` tool to correctly bypass standard duration validation and supply the required 7-second duration to the Vertex AI API.
*   **Chore:** Bumped minor versions for all MCP servers to synchronize the release.

## 2026-04-14 (v3.7.0)

*   **Feat:** Upgraded `google.golang.org/genai` SDK to `v1.54.0` across all MCP servers.
*   **Feat:** Migrated `mcp-veo-go` to use the new `GenerateVideosFromSource` API, enabling new features.
*   **Feat:** Added `veo_extend_video` tool to `mcp-veo-go` to support extending MP4 videos up to 30s. Supported by Veo 3.1 models.
*   **Chore:** Bumped minor versions for all MCP servers to synchronize the release.

## 2026-04-14 (v3.6.0)

*   **Feat:** Updated `ffmpeg_combine_audio_and_video` in `mcp-avtool-go` to check if the input video already contains an audio stream. If it does, the tool now uses the `amix` filter to mix the tracks properly instead of appending a secondary audio track.
*   **Feat:** Added optional `input_video_volume_db_change` and `input_audio_volume_db_change` parameters to `ffmpeg_combine_audio_and_video` to allow for independent volume control during mixing.

## 2026-04-08 (v3.5.2)

*   **Fix:** Corrected the `SupportedAspectRatios` for `veo-3.1-lite-generate-001` in `mcp-veo-go` to use standard `"16:9"` and `"9:16"` instead of `"720p"` and `"1080p"` (which were rejected by the API).
*   **Fix:** Removed hardcoded defaults for `duration` and `aspect_ratio` in `mcp-veo-go` tool schemas, allowing model-specific fallbacks (like the strict 4/6/8 second constraints of Veo 3.1 Lite) to function correctly.
*   **Fix:** Added an explicit 120-second timeout context for the `gemini_audio_tts` API call in `mcp-gemini-go` to prevent long-running generative prompts from hanging indefinitely.
*   **Docs:** Updated Gemini CLI integration documentation to explicitly call out the necessity of increasing the global `toolExecutionTimeout` for long-running media generation tools (like Veo and TTS).
*   **Chore:** Incremented versions for all `mcp-*` servers to `3.5.2` to synchronize the release.

## 2026-04-08 (v3.5.1)

*   **Chore:** Initial preparation for the 3.5.x release line.

## 2026-04-02 (v3.5.0)

*   **Feat:** Add support for the `veo-3.1-lite-generate-001` model.

## 2026-04-01 (v3.4.2)

*   **Feat:** Support `GOOGLE_CLOUD_LOCATION` as the primary environment variable for location, with `LOCATION` as a fallback.
*   **Feat:** Enhanced configuration flexibility for mixed-region deployments with prefix-based overrides (e.g., `CHIRP3_LOCATION`).

## 2026-04-01 (v3.4.1)

*   **Feat:** Introduce `ALLOW_UNSAFE_MODELS` environment variable to bypass strict model validation for experimental testing.
*   **Fix:** Enforce correct regional routing and fallback logic for Chirp3-HD based on the `LOCATION` parameter.
*   **Feat:** Implement optional header capture (`ENABLE_OPTIONAL_HEADER_CAPTURE`) to surface `x-goog-sherlog-link` debug links for Gemini, Imagen, NanoBanana, and Lyria.
*   **Feat:** Allow per-server LOCATION overrides (e.g., `CHIRP3_LOCATION`, `VEO_LOCATION`) to isolate server environments and support mixed-region deployments.

## 2026-03-30 (v3.3.0)

*   **Feat:** Support `GOOGLE_CLOUD_PROJECT` as primary project env var across all tools, with fallback to `PROJECT_ID`.
*   **Feat:** Allow per-server Google Cloud Project overrides (e.g., `VEO_PROJECT_ID`, `LYRIA_PROJECT_ID`) to isolate server environments.
*   **Feat:** Allow per-server custom PATH override (`MCP_CUSTOM_PATH`) for dependencies like `ffmpeg` and `ffprobe` in `mcp-avtool-go`.

## 2026-03-28 (v3.2.0)

*   **Feat:** Added `veo_first_last_to_video` tool to support First-Last Frame video generation modality in `mcp-veo-go`.
*   **Feat:** Added `veo_reference_to_video` tool (with `veo_ingredients_to_video` alias) to support video generation with up to 3 reference images in `mcp-veo-go`.
*   **Feat:** Added optional `person_generation` parameter to all Veo tools (defaulting to `allow_adult`) to prevent silent filtering of humans.
*   **Feat:** Registered Veo preview models (`veo-2.0-generate-exp`, `veo-2.0-generate-preview`, `veo-3.1-generate-preview`, `veo-3.1-fast-generate-preview`) and updated output constraints.
*   **Fix:** Added explicit optional MIME type parameters (`first_mime_type`, `last_mime_type`, `reference_mime_types`) to new Veo modalities to prevent unsafe inference fallbacks.

## 2026-03-26 (v3.1.3)

*   **Fix:** Added missing `mcp.Items` to `mcp.WithArray` definitions in `mcp-gemini-go`, `mcp-imagen-go`, and `mcp-avtool-go` to fix JSON Schema validation errors (HTTP 400 Bad Request) when used as Function Declarations in Vertex AI/Gemini API backends.
*   **Chore:** Incremented versions for `mcp-gemini-go` (3.1.3), `mcp-imagen-go` (3.1.3), `mcp-avtool-go` (3.1.3), `mcp-chirp3-go` (3.1.3), `mcp-lyria-go` (3.1.3), `mcp-nanobanana-go` (3.1.3), and `mcp-veo-go` (3.1.3).

## 2026-03-25 (v3.1.2)

## 2026-03-25 (v3.1.1)

*   **Fix:** Resolved a routing issue where Lyria 3 models were inadvertently hitting the legacy Prediction API instead of the new Interactions API.
*   **Fix:** Enforced `global` region strictly for the Lyria 3 Interactions API to prevent `NotFound` errors when `us-central1` is used as a fallback.
*   **Feat:** Added native support for the [Antigravity](https://antigravity.google) AI editor.
*   **Feat:** The `install-online.sh` and `install.sh` scripts now interactively offer to install the expert `genmedia-producer` Agent Skill globally for Antigravity.
*   **Docs:** Provided an Antigravity `mcp_config.json` template and instructions for connecting the GenMedia MCP suite.

## 2026-03-25 (v3.1.0)

*   **Feat:** Added support for `lyria-3-clip-preview` (30s) and `lyria-3-pro-preview` (2:30s) music generation models to `mcp-lyria-go`.
*   **Feat:** Implemented a new, lightweight Go port of the Vertex AI Interactions API to support the Lyria 3 backends.
*   **Feat:** Set `lyria-3-clip-preview` as the new default model for the `lyria_generate_music` tool.
*   **Config:** Added the Lyria model registry to `mcp-common/models.go` to provide self-describing model options to the LLM agent via the MCP tool description.

## 2026-03-24

*   **Feat:** Added a new `mcp-nanobanana-go` server dedicated to Google Gemini Image models.
*   **Feat:** Added `gemini-3.1-flash-image-preview` (Nano Banana 2) support to `mcp-gemini-go` and `mcp-nanobanana-go`, setting it as the new default model.
*   **Feat:** Added `SupportedAspectRatios` to Gemini Image model definitions and updated `mcp-gemini-go` and `mcp-nanobanana-go` to accept an `aspect_ratio` parameter.
*   **Feat:** Set `veo-3.1-fast-generate-001` as the new default model for `mcp-veo-go`.
*   **Deprecation:** Removed deprecated Veo models (`veo-2.0-generate-exp`, `veo-2.0-generate-preview`, `veo-3.0-generate-preview`, `veo-3.0-fast-generate-preview`, `veo-3.1-generate-preview`, `veo-3.1-fast-generate-preview`) from supported lists.
*   **Deprecation:** Excluded `mcp-imagen-go` from the standard `install.sh` installation loop (Imagen models set to be deprecated by June 30, 2026).
*   **Chore:** Updated Go GenAI SDK (`google.golang.org/genai`) from `v1.22.0` to `v1.51.0` and bumped all other module dependencies to latest versions.
*   **Fix:** Resolved numerous `golangci-lint` issues (errcheck, unused variables, string formatting) across all modules to ensure zero linting warnings.
*   **CI:** Added `.golangci.yml` configuration and a dedicated GitHub Actions workflow (`mcp-genmedia-go.yml`) for linting, building, and verifying tests for the MCP servers on PRs/pushes.
*   **Refactor:** Centralized OpenTelemetry initialization and configuration loading into a unified `common.Init` function in `mcp-common`.
*   **Docs:** Added a PATH reminder output to `install.sh` upon successful server installation.

## 2025-11-23

*   **Feat:** Added support for `gemini-3-pro-image-preview` (alias: "Nano Banana Pro") and `gemini-2.5-flash-image` (alias: "Nano Banana") to the `gemini_image_generation` tool in `mcp-gemini-go`.
*   **Feat:** Added `gemini-2.5-flash-lite-preview-tts` to the supported models in the `gemini_audio_tts` tool in `mcp-gemini-go`.
*   **Refactor:** Centralized Gemini Image model definitions in `mcp-common/models.go`, matching the architectural pattern used for Imagen and Veo.
*   **Chore:** Incremented `mcp-gemini-go` version to 0.5.1.

## 2025-10-09

*   **Feat:** Standardized network port configuration across all MCP servers (`avtool`, `chirp3`, `imagen`, `lyria`, `veo`, `gemini`). All servers now follow a consistent precedence: `--port` flag, `PORT` environment variable, and then transport-specific defaults (`8080` for `http`, `8081` for `sse`).
*   **Feat:** Added full HTTP transport support to the `mcp-gemini-go` server, making it accessible via HTTP in addition to `stdio`.
*   **Fix:** Corrected the port configuration logic in `mcp-avtool-go` to align with the new standard, including support for the `-p` short flag and a centralized `determinePort` function.
*   **Chore:** Incremented the version number for all MCP servers.

## 2025-10-01

*   **Feat:** Disabled OpenTelemetry tracing by default across all MCP servers. It can be re-enabled by setting the `OTEL_ENABLED=true` environment variable.
*   **Fix:** Removed the unused `-otel` command-line flag from the `mcp-veo-go` server.
*   **Test:** Added `verify.sh` scripts to `mcp-chirp3-go`, `mcp-avtool-go`, and `mcp-lyria-go` to provide a consistent, post-build liveness check.
*   **Chore:** Incremented the version number for all MCP servers.

## 2025-08-31

*   **Feat:** Added `gemini_audio_tts` and `list_gemini_voices` tools to the `mcp-gemini-go` server to provide speech synthesis capabilities using Gemini TTS models.
*   **Feat:** The new tools support all 30 voices available in the Gemini TTS documentation.
*   **Feat:** Added a `gemini://language_codes` resource to the `mcp-gemini-go` server to list supported languages.
*   **Docs:** Updated the `mcp-gemini-go/README.md` with documentation and usage examples for the new TTS tools and resource.

## 2025-08-29

*   **Feat:** Added a new `mcp-gemini-go` server to provide an MCP interface for Google's Gemini models.
*   **Feat:** The new server includes a `gemini_image_generation` tool for multimodal (text and image) content generation.
*   **Fix:** Resolved multiple build and dependency issues in the new server, including correcting Go module versions and fixing compilation errors.
*   **Docs:** Updated the main project `README.md` to include the `mcp-gemini-go` server in the installation instructions and the list of available servers.
*   **Chore:** Improved the `install.sh` script to verify that the `PROJECT_ID` environment variable is set, preventing a common installation failure.

## 2025-08-14

*   **Feat:** The `mcp-veo-go` tool now generates descriptive, unique filenames for downloaded videos (e.g., `veo-veo-2.0-generate-001-20250814-153000-0.mp4`), matching the behavior of the Imagen tool.
*   **Fix:** The `mcp-veo-go` tool now automatically prepends `gs://` to the GCS bucket name if it is missing, preventing an "Unsupported output storage uri" error.
*   **Feat:** Added a new `EnsureGCSPathPrefix` helper function to `mcp-common` to provide a consistent way to normalize GCS paths.
*   **Chore:** Incremented the version number for `mcp-veo-go`.
*   **Fix:** Improved logging in `mcp-common` to clarify fallback behavior for environment variables.
*   **Feat:** Updated Imagen 4 model names to production versions.
*   **Chore:** Incremented the version number for `mcp-imagen-go`.

## 2025-07-31

*   **Feat:** Added prompt support to all MCP servers to eliminate the `prompts not supported` error.
*   **Feat:** Implemented a `list-voices` prompt in `mcp-chirp3-go` that lists available voices and can be filtered by language.
*   **Feat:** Added a `chirp://language_codes` resource to `mcp-chirp3-go` to expose the supported language codes.
*   **Feat:** Implemented a `generate-image` prompt in `mcp-imagen-go` that wraps the `imagen_t2i` tool.
*   **Feat:** Implemented a `generate-video` prompt in `mcp-veo-go` that wraps the `veo_t2v` tool.
*   **Feat:** Implemented a `generate-music` prompt in `mcp-lyria-go` that wraps the `lyria_generate_music` tool.
*   **Feat:** Implemented a `create-gif` prompt in `mcp-avtool-go` that wraps the `ffmpeg_video_to_gif` tool.
*   **Refactor:** Refactored the voice listing logic in `mcp-chirp3-go` into a reusable helper function.
*   **Chore:** Incremented the version number for all MCP servers.

## 2025-07-19

*   **Feat:** Implemented dynamic, model-specific constraints for `mcp-imagen-go` and `mcp-veo-go`. This includes support for model aliases (e.g., "Imagen 4", "Veo 3") and validation of parameters like image count, video duration, and aspect ratios based on the selected model.
*   **Refactor:** Centralized all model definitions and constraints for both Imagen and Veo into a new `mcp-common/models.go` file. This creates a single source of truth and simplifies future maintenance.
*   **Fix:** Restored the server startup logic in `mcp-imagen-go` to prevent the server from exiting prematurely.
*   **Refactor:** Updated `mcp-imagen-go` and `mcp-veo-go` to use the new centralized model configuration.
*   **Docs:** Updated the tool descriptions for `mcp-imagen-go` and `mcp-veo-go` to be self-describing, dynamically listing all supported models and their constraints.
*   **Docs:** Updated the `README.md` files for `mcp-imagen-go` and `mcp-veo-go` to refer to the new `mcp-common/models.go` file as the single source of truth.
*   **Docs:** Added a new "Architectural Pattern" section to the `GEMINI.md` file to document the new configuration-driven approach for model constraints.
*   **Docs:** Added detailed instructions for testing MCP servers with `mcptools` to the project's `GEMINI.md`.
*   **Test:** Added `verify.sh` scripts to `mcp-imagen-go` and `mcp-veo-go` to provide a mandatory, post-build liveness check.

## 2025-06-10

*   **Docs:** Added comprehensive Go documentation to all public functions and methods in the `mcp-avtool-go`, `mcp-chirp3-go`, `mcp-common`, `mcp-imagen-go`, `mcp-lyria-go`, and `mcp-veo-go` packages to improve code clarity and maintainability.

## 2025-06-07

*   **Refactor:** Simplified the shared `mcp-common` configuration by removing redundant and service-specific fields (`LyriaLocation`, `LyriaModelPublisher`, `DefaultLyriaModelID`).
*   **Refactor:** Updated `mcp-lyria-go` to use the general `Location` and manage its own constants for model publisher and ID, decoupling it from the shared config.
*   **Fix:** Removed incorrect and unreachable error handling for `common.LoadConfig()` from `veo-go`, `mcp-imagen-go`, and `mcp-lyria-go`.
*   **Feat:** Added support for custom API endpoints in `mcp-imagen-go` and `veo-go` via the `VERTEX_API_ENDPOINT` environment variable. This allows for easier testing against preview or sandbox environments.
*   **Fix:** Resolved build errors in all MCP modules.
*   **Refactor:** Refactored `mcp-avtool-go`, `mcp-imagen-go`, `mcp-lyria-go`, and `veo-go` to use the shared `mcp-common` module.
*   **Feat:** Instrumented `mcp-avtool-go`, `mcp-imagen-go`, `mcp-lyria-go`, and `veo-go` with OpenTelemetry for tracing.
*   **Fix:** Resolved `go mod tidy` dependency issues in `mcp-avtool-go` and `mcp-imagen-go`.
*   **Fix:** Corrected errors in `mcp-chirp3-go` and refactored to use the `mcp-common` package.
*   **Docs:** Added a `README.md` to the `mcp-common` package.
*   **Docs:** Updated the `README.md` in `mcp-avtool-go` to reflect the current capabilities of the service.
*   **Docs:** Added `compositing_recipes.md` to `mcp-avtool-go` to document the `ffmpeg` and `ffprobe` commands used.
*   **Docs:** Updated the root `README.md` with a "Developing MCP Servers for Genmedia" section.

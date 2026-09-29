// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Command tier1-video is Tier 1 of the Genkit Go genmedia series: a
// deterministic genkit.DefineFlow that chains TWO genmedia tools in a fixed Go
// order — nanobanana (text->image) then veo_i2v (image->video) — into one
// reproducible, traced unit.
//
// The flow "image-to-clip" runs four ordered steps:
//
//	generate-image  -> nanobanana_image_generation writes a still to GCS
//	verify-image    -> LIST the destination to confirm the still and learn its gs:// URI
//	generate-video  -> veo_i2v turns that still into a clip (explicit Veo-3 model)
//	verify-video    -> LIST the destination to confirm the clip
//
// The intermediate image URI is obtained by LISTING (verify-by-listing), never by
// trusting the tool's resource_link — the same discipline Tier 0 established, now
// carrying an artifact from one step into the next.
//
// Run it with the Dev UI to read the trace:
//
//	export GOOGLE_CLOUD_PROJECT=your-project
//	export GENMEDIA_BUCKET=gs://your-bucket/tier1   # veo_i2v requires a gs:// destination
//	export GOOGLE_CLOUD_LOCATION=us-central1
//	genkit start -- go run ./tier1-video
//
// then open http://localhost:4000 and read the "image-to-clip" flow span with the
// two nested generate spans (nanobanana + veo) and the GCS writes between them.
// See README.md for the full walkthrough.
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/firebase/genkit/go/ai"
	"github.com/firebase/genkit/go/genkit"
	"github.com/firebase/genkit/go/plugins/googlegenai"

	"github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/sample-agents/genkit-go/internal/genmedia"
	"github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/sample-agents/genkit-go/internal/verify"
)

// modelName is the Vertex Gemini model that orchestrates the tool calls. The
// gemini-3.x flash family is newer than the googlegenai plugin's curated catalog
// (models.go stops at gemini-3.7-flash), but the plugin resolves unknown IDs
// dynamically with default options, so "vertexai/gemini-3.8-flash" is accepted.
// Runs in the global region (see orchestratorLocation). Single-sourced here;
// bump in one place. Matches Tier 0.
const modelName = "vertexai/gemini-3.8-flash"

// veoModel is the explicit Veo-3 model passed to veo_i2v. This is load-bearing:
// with no model the veo server falls back to "veo-2.0-generate-001", which
// REJECTS generate_audio=true (the default) and the call fails. The quirks prompt
// tells the model this; naming the id here keeps it single-sourced and greppable.
const veoModel = "veo-3.1-fast-generate-001"

// Default prompts. A single positional arg (if any) overrides only the image
// subject; the video prompt is always defaultVideoPrompt (it is
// subject-agnostic, describing camera/motion rather than content).
const (
	defaultImageSubject = "a photorealistic red panda sitting on a moss-covered rock in a misty forest at dawn"
	defaultVideoPrompt  = "Animate this scene with a slow, gentle camera push-in; drifting mist and subtle movement."
)

// ClipRequest is the flow input: what to draw, then how to animate it.
type ClipRequest struct {
	ImageSubject string `json:"imageSubject"`
	VideoPrompt  string `json:"videoPrompt"`
}

// ClipResult is the flow output: the confirmed (verified-by-listing) artifacts.
type ClipResult struct {
	ImageDest string `json:"imageDest"` // per-run prefix the still was written to
	ImageURI  string `json:"imageUri"`  // the confirmed gs:// URI of the still
	VideoDest string `json:"videoDest"` // per-run prefix the clip was written to
	VideoURI  string `json:"videoUri"`  // the confirmed gs:// URI of the clip
}

func main() {
	if err := run(context.Background()); err != nil {
		log.Fatalf("tier1-video: %v", err)
	}
}

func run(ctx context.Context) error {
	project := firstEnv("GOOGLE_CLOUD_PROJECT", "PROJECT_ID")
	if project == "" {
		return fmt.Errorf("set GOOGLE_CLOUD_PROJECT (or PROJECT_ID) to your Google Cloud project")
	}
	// The orchestrator (text) model runs in the GLOBAL region: the gemini-3.x
	// flash family is global-only, so pinning it to a regional endpoint (e.g.
	// us-central1) makes Vertex return NOT_FOUND. This mirrors the main app, whose
	// GEMINI_LOCATION defaults to "global". The genmedia MCP media servers are
	// separate processes that inherit GOOGLE_CLOUD_LOCATION and stay regional
	// (us-central1) for Veo/Imagen/nanobanana — keep that env set for them.
	orchestratorLocation := firstEnv("GEMINI_LOCATION")
	if orchestratorLocation == "" {
		orchestratorLocation = "global"
	}

	// Base destination for both the still and the clip. veo_i2v requires its
	// input image on GCS (the server rejects a non-gs:// image_uri), so Tier 1
	// needs a gs:// bucket — unlike Tier 0, a local dir will not carry an image
	// into the video step.
	base := os.Getenv("GENMEDIA_BUCKET")
	if base == "" {
		return fmt.Errorf("set GENMEDIA_BUCKET to a gs:// URI for the generated still + clip")
	}
	if !verify.IsGCS(base) {
		return fmt.Errorf("GENMEDIA_BUCKET must be a gs:// URI for Tier 1: veo_i2v only accepts a GCS input image (got %q)", base)
	}

	// Initialize Genkit with the Vertex AI (Gemini) plugin. genkit.Init also wires
	// the Dev UI / tracing exporter when launched via `genkit start`.
	g := genkit.Init(ctx, genkit.WithPlugins(&googlegenai.VertexAI{
		ProjectID: project,
		Location:  orchestratorLocation,
	}))

	// Connect to BOTH genmedia servers over stdio (launched through
	// bin/genmedia-launch). The shared genmedia package owns the launch wiring;
	// "veo" resolves to mcp-veo-go via the same interface Tier 0 established.
	nano, err := genmedia.NewClient(ctx, g, "nanobanana")
	if err != nil {
		return fmt.Errorf("connecting to nanobanana MCP server: %w", err)
	}
	defer nano.Disconnect()

	veo, err := genmedia.NewClient(ctx, g, "veo")
	if err != nil {
		return fmt.Errorf("connecting to veo MCP server: %w", err)
	}
	defer veo.Disconnect()

	nanoTools, err := nano.GetActiveTools(ctx, g)
	if err != nil {
		return fmt.Errorf("listing nanobanana tools: %w", err)
	}
	veoTools, err := veo.GetActiveTools(ctx, g)
	if err != nil {
		return fmt.Errorf("listing veo tools: %w", err)
	}
	if len(nanoTools) == 0 || len(veoTools) == 0 {
		return fmt.Errorf("a genmedia server exposed no tools (nanobanana=%d, veo=%d)", len(nanoTools), len(veoTools))
	}
	log.Printf("connected: nanobanana=%d tool(s), veo=%d tool(s)", len(nanoTools), len(veoTools))

	// The flow is the reproducible, traced unit. Two generate steps in a fixed Go
	// order (deterministic — not LLM-sequenced), each giving the LLM only the one
	// server's tools so the step calls exactly the tool it must. genkit.Init must
	// run before DefineFlow so the flow registers and shows up in the Dev UI.
	flow := genkit.DefineFlow(g, "image-to-clip",
		func(ctx context.Context, req ClipRequest) (ClipResult, error) {
			// One run id, two sibling per-run subprefixes, so verify-by-listing
			// confirms THIS run's still and clip, not a leftover from a prior run.
			id := runID()
			imageDest := join(base, id, "image")
			videoDest := join(base, id, "video")
			log.Printf("run %s: image -> %s ; video -> %s", id, imageDest, videoDest)

			// Step 1: generate the still. RunWithContext so the nanobanana
			// generate span nests under this named step in the trace.
			if _, err := genkit.RunWithContext(ctx, "generate-image",
				func(ctx context.Context) (string, error) {
					resp, err := genkit.Generate(ctx, g,
						ai.WithModelName(modelName),
						ai.WithSystem(genmedia.QuirksPrompt),
						ai.WithPrompt(fmt.Sprintf(
							"Generate an image of %s. Use the nanobanana image tool and write it to Google Cloud Storage with gcs_bucket_uri set to %q.",
							req.ImageSubject, imageDest)),
						ai.WithTools(genmedia.ToolRefs(nanoTools)...),
						ai.WithToolChoice(ai.ToolChoiceAuto),
					)
					if err != nil {
						return "", err
					}
					return resp.Text(), nil
				}); err != nil {
				return ClipResult{}, fmt.Errorf("generate-image: %w", err)
			}

			// Step 2: verify-by-listing. The still's confirmed gs:// URI (NOT the
			// resource_link) is what we carry into veo_i2v.
			imageURI, err := genkit.RunWithContext(ctx, "verify-image",
				func(ctx context.Context) (string, error) {
					return confirmOne(ctx, imageDest)
				})
			if err != nil {
				return ClipResult{}, fmt.Errorf("verify-image: %w", err)
			}
			log.Printf("verified still: %s", imageURI)

			// Step 3: image -> video with veo_i2v. Pass the confirmed image URI,
			// an explicit Veo-3 model, and the GCS destination (veo uses "bucket").
			if _, err := genkit.RunWithContext(ctx, "generate-video",
				func(ctx context.Context) (string, error) {
					resp, err := genkit.Generate(ctx, g,
						ai.WithModelName(modelName),
						ai.WithSystem(genmedia.QuirksPrompt),
						ai.WithPrompt(fmt.Sprintf(
							"Using the veo image-to-video tool (veo_i2v), generate a short video from the input image. "+
								"Set image_uri to %q. %s "+
								"Use the Veo-3 model %q and write the output to Google Cloud Storage with bucket set to %q.",
							imageURI, req.VideoPrompt, veoModel, videoDest)),
						ai.WithTools(genmedia.ToolRefs(veoTools)...),
						ai.WithToolChoice(ai.ToolChoiceAuto),
					)
					if err != nil {
						return "", err
					}
					return resp.Text(), nil
				}); err != nil {
				return ClipResult{}, fmt.Errorf("generate-video: %w", err)
			}

			// Step 4: verify-by-listing the clip.
			videoURI, err := genkit.RunWithContext(ctx, "verify-video",
				func(ctx context.Context) (string, error) {
					return confirmOne(ctx, videoDest)
				})
			if err != nil {
				return ClipResult{}, fmt.Errorf("verify-video: %w", err)
			}
			log.Printf("verified clip: %s", videoURI)

			return ClipResult{
				ImageDest: imageDest,
				ImageURI:  imageURI,
				VideoDest: videoDest,
				VideoURI:  videoURI,
			}, nil
		})

	// Invoke the flow once so `go run ./tier1-video` executes end to end. Under
	// `genkit start` the same flow is also invocable from the Dev UI.
	//
	// Teaching-material caveat: the positional arg is passed as free text into the
	// model prompt, which can then call tools — i.e. it is a (benign here, local
	// dev) prompt-injection surface. A production caller should treat any
	// untrusted input as adversarial: constrain it and/or validate the tool
	// arguments the model chooses, rather than trusting free text.
	req := ClipRequest{ImageSubject: defaultImageSubject, VideoPrompt: defaultVideoPrompt}
	if len(os.Args) > 1 {
		req.ImageSubject = strings.Join(os.Args[1:], " ")
	}

	res, err := flow.Run(ctx, req)
	if err != nil {
		return err
	}
	log.Printf("DONE: still=%s clip=%s", res.ImageURI, res.VideoURI)
	return nil
}

// confirmOne verifies an artifact exists at dest by listing it (never by trusting
// a tool result) and returns the first confirmed entry — the handoff value carried
// from one flow step to the next. For nanobanana the entry is a leaf object (the
// still fed to veo_i2v); for veo it is the output subfolder prefix veo writes into
// (e.g. .../video/<id>/), which is still a valid non-empty listing confirming the
// clip exists — the success gate is "the destination is non-empty", not the leaf name.
func confirmOne(ctx context.Context, dest string) (string, error) {
	result, err := verify.Verify(ctx, dest)
	if err != nil {
		return "", fmt.Errorf("verifying %s: %w", dest, err)
	}
	log.Printf("verify: %s", result)
	for _, e := range result.Entries {
		log.Printf("  - %s", e)
	}
	if !result.Exists || len(result.Entries) == 0 {
		return "", fmt.Errorf("no artifact found at %s — the step did not produce output there", dest)
	}
	return result.Entries[0], nil
}

// join appends per-run segments to a base destination. gs:// URIs join with "/";
// local paths use the OS separator. The base is normalized (trailing slash
// trimmed) first. Tier 1 requires gs://, but join handles both for parity with
// the shared verify helpers.
func join(base string, segments ...string) string {
	if verify.IsGCS(base) {
		return strings.TrimRight(base, "/") + "/" + strings.Join(segments, "/")
	}
	return filepath.Join(append([]string{base}, segments...)...)
}

// runID returns a per-run segment: a UTC timestamp plus a short random suffix so
// two runs in the same second do not collide.
func runID() string {
	ts := time.Now().UTC().Format("20060102-150405")
	var b [2]byte
	if _, err := rand.Read(b[:]); err != nil {
		return ts // timestamp alone is good enough if randomness is unavailable
	}
	return ts + "-" + hex.EncodeToString(b[:])
}

// firstEnv returns the value of the first set (non-empty) environment variable.
func firstEnv(keys ...string) string {
	for _, k := range keys {
		if v := os.Getenv(k); v != "" {
			return v
		}
	}
	return ""
}

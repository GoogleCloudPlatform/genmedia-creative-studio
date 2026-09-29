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

// Command tier0-image is Tier 0 of the Genkit Go genmedia series: the minimal
// program that lets a Gemini model call ONE genmedia tool
// (nanobanana_image_generation) in ONE genkit.Generate turn, then confirms the
// result by listing the destination rather than trusting the tool output.
//
// Run it with the Dev UI to read the trace:
//
//	export GOOGLE_CLOUD_PROJECT=your-project
//	export GENMEDIA_BUCKET=gs://your-bucket/tier0     # where the image is written
//	genkit start -- go run ./tier0-image
//
// then open http://localhost:4000 and read the single generate span with its
// nested nanobanana tool-call span. See README.md for the full walkthrough.
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

// modelName is the Vertex Gemini model that orchestrates the tool call. The
// gemini-3.x flash family is newer than the googlegenai plugin's curated catalog
// (models.go stops at gemini-3.7-flash), but the plugin does not hard-block
// unknown IDs — it resolves them dynamically with default options — so the
// "vertexai/" provider prefix + gemini-3.8-flash is accepted. Runs in the global
// region (see orchestratorLocation). Single-sourced here; bump in one place.
const modelName = "vertexai/gemini-3.8-flash"

// defaultPrompt is used when no positional prompt argument is supplied.
const defaultPrompt = "a photorealistic red panda sitting on a moss-covered rock in a misty forest at dawn"

func main() {
	if err := run(context.Background()); err != nil {
		log.Fatalf("tier0-image: %v", err)
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

	// Destination the image is written to and later verified by listing.
	// gs:// URI -> nanobanana gcs_bucket_uri; a bare/local path -> output_directory.
	base := os.Getenv("GENMEDIA_BUCKET")
	if base == "" {
		return fmt.Errorf("set GENMEDIA_BUCKET to a gs:// URI (or local dir) for the generated image")
	}
	// Write each run to a UNIQUE per-run subprefix so verify-by-listing confirms
	// THIS run's output, not a leftover object from a prior run at the same prefix.
	dest := perRunDest(base)
	log.Printf("this run writes to %s", dest)

	subject := defaultPrompt
	if len(os.Args) > 1 {
		subject = strings.Join(os.Args[1:], " ")
	}

	// Initialize Genkit with the Vertex AI (Gemini) plugin. genkit.Init also
	// wires the Dev UI / tracing exporter when launched via `genkit start`.
	g := genkit.Init(ctx, genkit.WithPlugins(&googlegenai.VertexAI{
		ProjectID: project,
		Location:  orchestratorLocation,
	}))

	// Connect to the nanobanana genmedia server over stdio (launched through
	// bin/genmedia-launch). The shared genmedia package owns the launch wiring.
	client, err := genmedia.NewClient(ctx, g, "nanobanana")
	if err != nil {
		return fmt.Errorf("connecting to nanobanana MCP server: %w", err)
	}
	defer client.Disconnect()

	tools, err := client.GetActiveTools(ctx, g)
	if err != nil {
		return fmt.Errorf("listing nanobanana tools: %w", err)
	}
	if len(tools) == 0 {
		return fmt.Errorf("nanobanana server exposed no tools")
	}
	log.Printf("connected to nanobanana: %d tool(s) available", len(tools))

	// One generate turn. The Quirks system prompt tells the model the genmedia
	// constraints the tool schema does not (here: use gcs_bucket_uri / prompt).
	destParam := destInstruction(dest)
	resp, err := genkit.Generate(ctx, g,
		ai.WithModelName(modelName),
		ai.WithSystem(genmedia.QuirksPrompt),
		ai.WithPrompt(fmt.Sprintf(
			"Generate an image of %s. Use the nanobanana image tool and %s.",
			subject, destParam)),
		ai.WithTools(genmedia.ToolRefs(tools)...),
		ai.WithToolChoice(ai.ToolChoiceAuto),
	)
	if err != nil {
		return fmt.Errorf("generate: %w", err)
	}
	log.Printf("model response: %s", resp.Text())

	// resource_link discipline: DO NOT trust the tool result. Confirm success by
	// listing the destination.
	result, err := verify.Verify(ctx, dest)
	if err != nil {
		return fmt.Errorf("verifying %s: %w", dest, err)
	}
	log.Printf("verify: %s", result)
	for _, e := range result.Entries {
		log.Printf("  - %s", e)
	}
	if !result.Exists {
		return fmt.Errorf("no artifact found at %s — the generation did not produce output there", dest)
	}
	return nil
}

// destInstruction phrases the destination for the prompt using the correct
// nanobanana parameter name for the destination kind.
func destInstruction(dest string) string {
	if verify.IsGCS(dest) {
		return fmt.Sprintf("write it to Google Cloud Storage with gcs_bucket_uri set to %q", dest)
	}
	return fmt.Sprintf("write it locally with output_directory set to %q", dest)
}

// perRunDest appends a unique per-run segment to the base destination so each
// run verifies its own output. gs:// URIs join with "/"; local paths use the OS
// separator. The base is normalized (trailing slash trimmed) first.
func perRunDest(base string) string {
	id := runID()
	if verify.IsGCS(base) {
		return strings.TrimRight(base, "/") + "/" + id
	}
	return filepath.Join(base, id)
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

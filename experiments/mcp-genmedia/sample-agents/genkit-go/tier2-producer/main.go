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

// Command tier2-producer is Tier 2 of the Genkit Go genmedia series: the
// multi-server "producer" capstone. Where Tier 1 chained TWO servers with each
// step handed only that one server's tools, Tier 2 connects FOUR genmedia MCP
// servers into a SINGLE Genkit tool host and exposes ALL of their tools to every
// Gemini-orchestrated generate step at once. One toolset, many servers.
//
// The flow "produce-scored-clip" runs an end-to-end production line:
//
//	generate-image  -> nanobanana writes a still to GCS
//	verify-image    -> LIST the destination; carry the confirmed still URI forward
//	generate-video  -> veo_i2v turns that still into a clip (explicit Veo-3 model)
//	verify-video    -> LIST recursively; carry the confirmed .mp4 leaf forward
//	generate-music  -> lyria composes a score to GCS
//	verify-music    -> LIST recursively; carry the confirmed audio leaf forward
//	generate-final  -> avtool muxes the clip + the score into one scored video
//	verify-final    -> LIST the destination to confirm the finished artifact
//
// THE IN-PROMPT CROSSWALK (the deliberate design contrast of this tier):
// four servers put overlapping, similarly named tools into one toolset
// (veo alone contributes six). Tier 2 does NOT rename or prefix them behind a
// disambiguation layer. Instead it tells the MODEL — in the system prompt
// (producerCrosswalk) — which namespaced tool does which job. The MCP client's
// "<server>_<tool>" namespacing keeps the names unique; the prompt tells the
// model which name to pick. Contrast the ADK genmedia sibling, which resolves the
// same collision structurally with `tool_name_prefix` on each toolset. Same
// problem, two philosophies: ADK renames the tools, Tier 2 instructs the model.
//
// Run it with the Dev UI to read the trace:
//
//	export GOOGLE_CLOUD_PROJECT=your-project
//	export GENMEDIA_BUCKET=gs://your-bare-bucket   # bare bucket, NO path — see below
//	export GOOGLE_CLOUD_LOCATION=us-central1
//	genkit start -- go run ./tier2-producer
//
// then open http://localhost:4000 and read the "produce-scored-clip" flow span:
// eight nested steps, four generate spans each showing which tool the model chose
// from the shared toolset, and the GCS writes verified by listing between them.
// See README.md for the full walkthrough.
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/firebase/genkit/go/ai"
	"github.com/firebase/genkit/go/genkit"
	"github.com/firebase/genkit/go/plugins/googlegenai"

	"github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/sample-agents/genkit-go/internal/genmedia"
	"github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/sample-agents/genkit-go/internal/verify"
)

// modelName is the Vertex Gemini model that orchestrates the tool calls. The
// gemini-3.x flash family is newer than the plugin's curated catalog, but the
// googlegenai plugin resolves unknown IDs dynamically with default options, so
// the "vertexai/" provider prefix + gemini-3.8-flash is accepted. Runs in the
// global region (see orchestratorLocation). Single-sourced here; matches Tiers 0-1.
const modelName = "vertexai/gemini-3.8-flash"

// Model ids passed explicitly to the genmedia tools. These are load-bearing and
// single-sourced here (the quirks prompt tells the model WHY; naming the ids in
// code keeps them greppable and bump-in-one-place):
//
//   - veoModel: with no model veo falls back to "veo-2.0-generate-001", which
//     REJECTS generate_audio=true (the default) and the call fails.
//   - lyriaModel: the clip-preview model routes through the global Interactions
//     API (region-independent), which is what lets lyria run alongside the
//     us-central1 image/video steps without a per-server location dance.
const (
	veoModel   = "veo-3.1-fast-generate-001"
	lyriaModel = "lyria-3-clip-preview"
)

// producerServers are the four genmedia servers this tier composes, by their
// friendly nicknames (resolved to binaries by the shared genmedia package).
var producerServers = []string{"nanobanana", "veo", "lyria", "avtool"}

// requiredTools are the exact namespaced tool names the flow depends on — one per
// server. mcp.NewMCPHost logs-and-continues when a server fails to connect, so
// the flow must PROVE every server it needs is actually present rather than
// discovering a missing tool mid-run. These names are "<server>_<tool>"; note
// veo and lyria carry a doubled segment because the server's own name is already
// part of the tool name (e.g. tool "veo_i2v" on server "veo" -> "veo_veo_i2v").
var requiredTools = []string{
	"nanobanana_nanobanana_image_generation",
	"veo_veo_i2v",
	"lyria_lyria_generate_music",
	"avtool_ffmpeg_combine_audio_and_video",
}

// producerCrosswalk is the IN-PROMPT disambiguation layer — the heart of Tier 2.
// It is appended to the shared QuirksPrompt so the model sees, in one system
// prompt, both the genmedia footguns AND which of the four servers' tools to use
// for each job. This is the deliberate contrast with the ADK genmedia sibling,
// which disambiguates the same colliding tool names STRUCTURALLY via
// `tool_name_prefix`. Here there is no rename layer: the tools keep their native
// "<server>_<tool>" names and the model is TOLD which to pick.
const producerCrosswalk = `

MULTI-SERVER TOOLSET (Tier 2 producer):
You have the tools of FOUR genmedia servers in ONE toolset at the same time
(image, video, music, and audio/video muxing). Several names look alike and veo
alone offers six variants. Use EXACTLY the tool named below for each job, and no
other — do not substitute a similarly named tool:

- IMAGE (text -> still): nanobanana_nanobanana_image_generation
- VIDEO (still -> clip): veo_veo_i2v
  Do NOT use veo_veo_t2v, veo_veo_extend_video, veo_veo_first_last_to_video,
  veo_veo_ingredients_to_video, or veo_veo_reference_to_video for this job.
- MUSIC (text -> score): lyria_lyria_generate_music
- MUX (clip + score -> scored video): avtool_ffmpeg_combine_audio_and_video

Call one tool per turn, the one the instruction names. The parameter names differ
per server — follow the 3-WAY NAMING CROSSWALK above for each tool you call.`

// ProduceRequest is the flow input: what to draw, how to animate it, and the mood
// of the score.
type ProduceRequest struct {
	ImageSubject string `json:"imageSubject"`
	VideoPrompt  string `json:"videoPrompt"`
	MusicPrompt  string `json:"musicPrompt"`
}

// ProduceResult is the flow output: every confirmed (verified-by-listing)
// artifact along the production line, ending in the scored video.
type ProduceResult struct {
	ImageURI string `json:"imageUri"` // confirmed still (nanobanana)
	VideoURI string `json:"videoUri"` // confirmed clip leaf (veo_i2v)
	MusicURI string `json:"musicUri"` // confirmed score leaf (lyria)
	FinalURI string `json:"finalUri"` // confirmed scored video (avtool mux)
}

// Default prompts. Positional args, if any, override only the image subject; the
// video and music prompts stay subject-agnostic (camera/motion, mood/instrument).
const (
	defaultImageSubject = "a photorealistic red panda sitting on a moss-covered rock in a misty forest at dawn"
	defaultVideoPrompt  = "Animate this scene with a slow, gentle camera push-in; drifting mist and subtle movement."
	defaultMusicPrompt  = "A calm, warm ambient piece: soft piano and airy strings, unhurried, gently hopeful."
)

func main() {
	if err := run(context.Background()); err != nil {
		log.Fatalf("tier2-producer: %v", err)
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

	// Tier 2 needs a BARE GCS bucket (gs://bucket with NO path). This is a genmedia
	// footgun worth teaching: nanobanana and veo accept a bucket+prefix and write
	// under it, but lyria and avtool take a bucket NAME only (they strip gs:// and
	// upload the object at the bucket root using just the filename) — a prefixed
	// value would become an invalid bucket name and the upload would fail. So the
	// producer standardizes on a bare bucket and adds per-run structure itself:
	// nanobanana/veo get "<bucket>/<runID>/..." prefixes, while lyria/avtool write
	// at the root with runID-stamped filenames.
	base := os.Getenv("GENMEDIA_BUCKET")
	if base == "" {
		return fmt.Errorf("set GENMEDIA_BUCKET to a gs:// bucket for the generated artifacts")
	}
	bucket, err := bareBucket(base)
	if err != nil {
		return err
	}

	// Initialize Genkit with the Vertex AI (Gemini) plugin. genkit.Init also wires
	// the Dev UI / tracing exporter when launched via `genkit start`. Use
	// googlegenai.VertexAI (NOT a vertexai.* type): this is the plugin the whole
	// series orchestrates through.
	g := genkit.Init(ctx, genkit.WithPlugins(&googlegenai.VertexAI{
		ProjectID: project,
		Location:  orchestratorLocation,
	}))

	// Connect to ALL FOUR genmedia servers at once through the shared multi-server
	// host. This is Tier 2's fan-out: one host aggregating four servers' tools,
	// launched over stdio through bin/genmedia-launch by the same interface Tier 0
	// established. The caller owns Disconnect for each server.
	host, err := genmedia.NewHost(ctx, g, producerServers...)
	if err != nil {
		return fmt.Errorf("creating multi-server genmedia host: %w", err)
	}
	for _, s := range producerServers {
		defer host.Disconnect(ctx, s)
	}

	// One shared toolset drawn from every connected server. Because NewMCPHost
	// logs-and-continues on a failed connection, an empty-ish toolset here would
	// otherwise surface only as a confusing "no tool found" mid-flight — so we
	// confirm each required tool is actually present before defining the flow.
	tools, err := host.GetActiveTools(ctx, g)
	if err != nil {
		return fmt.Errorf("listing multi-server tools: %w", err)
	}
	if err := requireTools(tools, requiredTools); err != nil {
		return err
	}
	allTools := genmedia.ToolRefs(tools)
	log.Printf("connected: %d server(s), %d tool(s) total in one shared toolset", len(producerServers), len(tools))

	// systemPrompt is the shared quirks fragment PLUS the in-prompt crosswalk that
	// tells the model which of the four servers' tools to use for each job. Every
	// generate step gets this same system prompt and the SAME full toolset — the
	// prompt, not a rename layer, is what disambiguates.
	systemPrompt := genmedia.QuirksPrompt + producerCrosswalk

	// generate is the shared per-step call: same model, same system prompt, same
	// full multi-server toolset every time. Only the user instruction changes per
	// step, naming the one tool + parameters that step must use. Wrapping it keeps
	// each flow step to its essence (what to ask) and proves the point of the tier:
	// the model, not the code, selects the tool from a single shared toolset.
	generate := func(ctx context.Context, instruction string) (string, error) {
		resp, err := genkit.Generate(ctx, g,
			ai.WithModelName(modelName),
			ai.WithSystem(systemPrompt),
			ai.WithPrompt(instruction),
			ai.WithTools(allTools...),
			ai.WithToolChoice(ai.ToolChoiceAuto),
		)
		if err != nil {
			return "", err
		}
		return resp.Text(), nil
	}

	// The flow is the reproducible, traced unit: eight ordered steps in a fixed Go
	// order (deterministic sequencing — the MODEL picks each step's tool, the CODE
	// picks the order), each artifact carried forward only after verify-by-listing.
	flow := genkit.DefineFlow(g, "produce-scored-clip",
		func(ctx context.Context, req ProduceRequest) (ProduceResult, error) {
			// One run id threads through every destination so verify-by-listing
			// confirms THIS run's artifacts, not leftovers from a prior run.
			id := runID()
			imageDest := gcsJoin(base, id, "image")           // nanobanana: bucket+prefix OK
			videoDest := gcsJoin(base, id, "video")           // veo: bucket+prefix OK
			musicName := id + "-score"                        // lyria: root filename only
			musicPrefix := "gs://" + bucket + "/" + musicName // where lyria writes (ext forced)
			finalName := id + "-final.mp4"                    // avtool: root filename only
			finalURI := "gs://" + bucket + "/" + finalName    // where avtool writes
			log.Printf("run %s: image=%s video=%s music=%s final=%s", id, imageDest, videoDest, musicPrefix, finalURI)

			// Step 1: still. nanobanana writes to GCS via gcs_bucket_uri.
			if _, err := genkit.RunWithContext(ctx, "generate-image", func(ctx context.Context) (string, error) {
				return generate(ctx, fmt.Sprintf(
					"Generate an image of %s. Use the tool nanobanana_nanobanana_image_generation and "+
						"write it to Google Cloud Storage with gcs_bucket_uri set to %q.",
					req.ImageSubject, imageDest))
			}); err != nil {
				return ProduceResult{}, fmt.Errorf("generate-image: %w", err)
			}

			// Step 2: verify the still and carry its confirmed leaf URI (NOT the
			// resource_link) into veo_i2v.
			imageURI, err := verifyLeaf(ctx, "verify-image", imageDest, "")
			if err != nil {
				return ProduceResult{}, err
			}

			// Step 3: still -> clip with veo_i2v (explicit Veo-3 model; bucket+prefix).
			if _, err := genkit.RunWithContext(ctx, "generate-video", func(ctx context.Context) (string, error) {
				return generate(ctx, fmt.Sprintf(
					"Using the tool veo_veo_i2v, generate a short video from the input image. "+
						"Set image_uri to %q. %s Use the Veo-3 model %q and write the output to "+
						"Google Cloud Storage with bucket set to %q.",
					imageURI, req.VideoPrompt, veoModel, videoDest))
			}); err != nil {
				return ProduceResult{}, fmt.Errorf("generate-video: %w", err)
			}

			// Step 4: verify the clip RECURSIVELY (veo writes into a server-assigned
			// <jobid>/ subfolder) and carry the .mp4 leaf into the mux.
			videoURI, err := verifyLeaf(ctx, "verify-video", videoDest, ".mp4")
			if err != nil {
				return ProduceResult{}, err
			}

			// Step 5: score with lyria. output_gcs_bucket is a BARE bucket; the
			// output_filename base is runID-stamped and predictable (lyria forces the
			// extension to the true audio type, so we do not guess .mp3 vs .wav).
			if _, err := genkit.RunWithContext(ctx, "generate-music", func(ctx context.Context) (string, error) {
				return generate(ctx, fmt.Sprintf(
					"Compose music: %s Use the tool lyria_lyria_generate_music with model_id %q, "+
						"set output_gcs_bucket to %q, and set output_filename to %q.",
					req.MusicPrompt, lyriaModel, bucket, musicName))
			}); err != nil {
				return ProduceResult{}, fmt.Errorf("generate-music: %w", err)
			}

			// Step 6: verify the score RECURSIVELY by its known filename prefix (the
			// extension was decided by lyria from the audio bytes).
			musicURI, err := verifyLeaf(ctx, "verify-music", musicPrefix, "")
			if err != nil {
				return ProduceResult{}, err
			}

			// Step 7: mux the confirmed clip + score into one scored video. avtool
			// reads both gs:// inputs, muxes with ffmpeg, and uploads to the bare
			// bucket at the runID-stamped output filename.
			if _, err := genkit.RunWithContext(ctx, "generate-final", func(ctx context.Context) (string, error) {
				return generate(ctx, fmt.Sprintf(
					"Combine a video and an audio track into one scored video using the tool "+
						"avtool_ffmpeg_combine_audio_and_video. Set input_video_uri to %q, set "+
						"input_audio_uri to %q, set output_gcs_bucket to %q, and set output_filename to %q.",
					videoURI, musicURI, bucket, finalName))
			}); err != nil {
				return ProduceResult{}, fmt.Errorf("generate-final: %w", err)
			}

			// Step 8: verify the finished scored video.
			finalConfirmed, err := verifyLeaf(ctx, "verify-final", finalURI, "")
			if err != nil {
				return ProduceResult{}, err
			}

			return ProduceResult{
				ImageURI: imageURI,
				VideoURI: videoURI,
				MusicURI: musicURI,
				FinalURI: finalConfirmed,
			}, nil
		})

	// Invoke the flow once so `go run ./tier2-producer` executes end to end. Under
	// `genkit start` the same flow is also invocable from the Dev UI.
	//
	// Teaching-material caveat: the positional arg is fed as free text into the
	// model prompt, which then calls tools — a (benign here, local dev)
	// prompt-injection surface. A production caller should treat untrusted input as
	// adversarial: constrain it and/or validate the tool arguments the model picks.
	req := ProduceRequest{
		ImageSubject: defaultImageSubject,
		VideoPrompt:  defaultVideoPrompt,
		MusicPrompt:  defaultMusicPrompt,
	}
	if len(os.Args) > 1 {
		req.ImageSubject = strings.Join(os.Args[1:], " ")
	}

	res, err := flow.Run(ctx, req)
	if err != nil {
		return err
	}
	log.Printf("DONE: image=%s video=%s music=%s final=%s",
		res.ImageURI, res.VideoURI, res.MusicURI, res.FinalURI)
	return nil
}

// verifyLeaf is the shared verify-by-listing step: it LISTS dest (never trusts a
// tool result), logs what it found, and returns the leaf URI to carry forward.
//
// wantSuffix selects which leaf to hand on when a step writes into a subfolder
// that may contain several objects: veo writes gs://.../<jobid>/ with the sample
// mp4 plus siblings, so the mux needs the ".mp4" specifically. An empty
// wantSuffix means "the destination is a single artifact (or a prefix that
// resolves to one); return the first leaf." A recursive listing is used whenever
// a suffix is requested or the destination is a known-prefix (not a full object
// path), so a server-assigned subfolder or an unknown extension is matched.
func verifyLeaf(ctx context.Context, step, dest, wantSuffix string) (string, error) {
	uri, err := genkit.RunWithContext(ctx, step, func(ctx context.Context) (string, error) {
		result, err := verify.VerifyRecursive(ctx, dest)
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
		if wantSuffix != "" {
			for _, e := range result.Entries {
				if strings.HasSuffix(e, wantSuffix) {
					return e, nil
				}
			}
			return "", fmt.Errorf("no %s artifact found under %s (found %d other entr%s)",
				wantSuffix, dest, len(result.Entries), plural(len(result.Entries)))
		}
		return result.Entries[0], nil
	})
	if err != nil {
		return "", fmt.Errorf("%s: %w", step, err)
	}
	log.Printf("%s -> %s", step, uri)
	return uri, nil
}

// requireTools confirms every required namespaced tool name is present in the
// aggregated toolset. NewMCPHost swallows per-server connect failures, so this is
// the guard that turns a silently-missing server into an explicit, actionable
// error before the flow runs.
func requireTools(tools []ai.Tool, required []string) error {
	present := make(map[string]bool, len(tools))
	for _, t := range tools {
		present[t.Name()] = true
	}
	var missing []string
	for _, name := range required {
		if !present[name] {
			missing = append(missing, name)
		}
	}
	if len(missing) > 0 {
		return fmt.Errorf("required genmedia tool(s) not available (a server failed to connect?): %s",
			strings.Join(missing, ", "))
	}
	return nil
}

// bareBucket validates that base is a gs:// URI naming a bucket with NO path, and
// returns the bare bucket name (no gs://, no trailing slash). lyria and avtool
// require a bucket name only; a prefixed value is a footgun that fails at upload.
func bareBucket(base string) (string, error) {
	if !verify.IsGCS(base) {
		return "", fmt.Errorf("GENMEDIA_BUCKET must be a gs:// URI (got %q)", base)
	}
	name := strings.Trim(strings.TrimPrefix(base, "gs://"), "/")
	if name == "" {
		return "", fmt.Errorf("GENMEDIA_BUCKET must name a bucket (got %q)", base)
	}
	if strings.Contains(name, "/") {
		return "", fmt.Errorf("GENMEDIA_BUCKET must be a BARE bucket with no path for Tier 2: "+
			"lyria and avtool take a bucket name only and write at the root (got %q)", base)
	}
	return name, nil
}

// gcsJoin appends per-run segments to a gs:// base, normalizing the trailing
// slash. Tier 2 is GCS-throughout, so unlike Tier 1's join this is gs://-only.
func gcsJoin(base string, segments ...string) string {
	return strings.TrimRight(base, "/") + "/" + strings.Join(segments, "/")
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

// plural renders the entry-count suffix for log/error messages.
func plural(n int) string {
	if n == 1 {
		return "y"
	}
	return "ies"
}

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

// ============================================================================
// PREVIEW — Tier 3 uses EXPERIMENTAL Genkit `.../exp` packages behind
// genkit.WithExperimental(). The API is NOT stable, is pinned to
// github.com/firebase/genkit/go v1.13.1, and MAY BREAK on upgrade. This tier is
// additive and self-contained: NOTHING in Tiers 0-2 depends on it. It is a
// flourish, not the series' foundation.
// ============================================================================
//
// Command tier3-preview is the PREVIEW capstone of the Genkit Go genmedia
// series: an "agentic producer". Where Tier 2 sequenced four servers in a fixed
// Go order (the CODE picks the order, the MODEL picks each tool's arguments),
// Tier 3 hands the sequencing to an ORCHESTRATOR agent that DELEGATES to
// specialist sub-agents, and PAUSES for human approval (a tool interrupt) before
// the expensive Veo render.
//
// The distinctively-Genkit shape this tier shows in the Dev-UI trace:
//
//	producer (agent, Agents middleware)
//	  ├─ delegate_to_image-agent   -> image-agent : generate_image (nanobanana)
//	  ├─ approve_video_render       -> INTERRUPT: pause for human approve/reject
//	  ├─ delegate_to_video-agent   -> video-agent : veo_render (GATED, Veo 3)
//	  ├─ delegate_to_music-agent   -> music-agent : compose_music (lyria)
//	  └─ delegate_to_av-agent      -> av-agent    : combine_av (avtool mux)
//
// THREE EXPERIMENTAL-API / INTEGRATION CORRECTIONS vs the design (verified
// against the real v1.13.1 source and proven by the live run; see
// tier3-dev-notes.md for the full list):
//
//  1. FileSessionStore is constructed with
//     localstore.NewFileSessionStore[State](dir) from
//     github.com/firebase/genkit/go/ai/exp/localstore — not a bare struct
//     literal. The store is generic over the agent's session-state type.
//
//  2. INTERACTIVE SUB-AGENT INTERRUPTS ARE NOT SUPPORTED in v1.13.1. The Agents
//     middleware turns a sub-agent's interrupt into a plain tool response to the
//     orchestrator ("Interactive sub-agent interrupts are not currently
//     supported" — plugins/middleware/exp/agents.go). So the human-in-the-loop
//     interrupt CANNOT live inside the video sub-agent. It lives on the
//     ORCHESTRATOR as an interruptible tool (approve_video_render), which is
//     where interrupts DO surface to the client. The Veo render is then made
//     impossible-without-approval by a process-level gate the approval flips
//     (see renderGate): the video-agent's veo_render tool refuses until the gate
//     is open. This is the honest, bulletproof adaptation of "an interrupt on
//     the video step".
//
//  3. MCP TOOLS ARE DYNAMIC (unregistered) AND DO NOT RESOLVE BY NAME INSIDE A
//     SUB-AGENT. plugins/mcp builds each tool with ai.NewTool, which sets
//     metadata["dynamic"]=true and does NOT register it in the Genkit registry.
//     A top-level genkit.Generate (Tiers 0-2) works because the tool OBJECT is
//     passed directly, but an exp sub-agent resolves its tools by NAME from the
//     registry, so a delegated agent reports the MCP tool "not found" (observed
//     live on the first run). The fix used here: wrap each genmedia MCP tool in
//     a REGISTERED genkitx.DefineTool that invokes the underlying MCP tool via
//     ai.Tool.RunRaw with footgun-correct arguments, then verifies the output by
//     LISTING it. The wrappers are what the sub-agents call; this also moves the
//     Tier 2 footguns from fragile prompt text into code (the honest place for
//     them) and pins the write destinations so the run is deterministic and
//     provable.
//
// Run it with the Dev UI to watch the delegation + the interrupt pause/resume:
//
//	export GOOGLE_CLOUD_PROJECT=your-project
//	export GOOGLE_CLOUD_LOCATION=us-central1               # NOT "global"
//	export GENMEDIA_BUCKET=gs://your-bare-bucket           # bare bucket, NO path
//	genkit start -- go run ./tier3-preview                 # open localhost:4000
//
// Or headless (this program drives the approve/reject resume programmatically,
// so no genkit CLI is required to run it):
//
//	go run ./tier3-preview            # approve path: renders the video
//	go run ./tier3-preview -reject    # reject path: halts before the render
//
// See README.md for the full walkthrough and the PREVIEW banner.
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/firebase/genkit/go/ai"
	aix "github.com/firebase/genkit/go/ai/exp"
	"github.com/firebase/genkit/go/ai/exp/localstore"
	"github.com/firebase/genkit/go/ai/exp/tool"
	"github.com/firebase/genkit/go/genkit"
	genkitx "github.com/firebase/genkit/go/genkit/exp"
	"github.com/firebase/genkit/go/plugins/googlegenai"
	middlewarex "github.com/firebase/genkit/go/plugins/middleware/exp"

	"github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/sample-agents/genkit-go/internal/genmedia"
	"github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/sample-agents/genkit-go/internal/verify"
)

// defaultModel orchestrates delegation and drives each specialist. The gemini-3.x
// flash family is newer than the googlegenai plugin's curated catalog, but the
// plugin resolves unknown IDs dynamically with default options, so
// "vertexai/gemini-3.8-flash" is accepted. Runs in the global region (see
// orchestratorLocation). Single-sourced here; matches Tiers 0-2. Overridable via
// TIER3_MODEL for experimentation.
const defaultModel = "vertexai/gemini-3.8-flash"

// Load-bearing genmedia model ids (same footguns as Tier 2). veo with no model
// falls back to veo-2.0, which rejects generate_audio=true; lyria's clip-preview
// routes through the global Interactions API so it runs alongside the
// us-central1 image/video steps.
const (
	veoModel   = "veo-3.1-fast-generate-001"
	lyriaModel = "lyria-3-clip-preview"
)

// producerServers are the four genmedia servers, partitioned across sub-agents.
var producerServers = []string{"nanobanana", "veo", "lyria", "avtool"}

// requiredTools are the exact namespaced MCP tool names the wrappers depend on.
// mcp.NewMCPHost logs-and-continues on a failed connect, so we PROVE every
// server is present before defining any agent (same guard as Tier 2).
var requiredTools = []string{
	"nanobanana_nanobanana_image_generation",
	"veo_veo_i2v",
	"lyria_lyria_generate_music",
	"avtool_ffmpeg_combine_audio_and_video",
}

// renderGate is the process-level approval gate that makes the Veo render
// impossible without human approval. The orchestrator's approve_video_render
// interrupt flips it open; the video-agent's veo_render tool refuses until it
// is. This compensates for the v1.13.1 limitation that a sub-agent cannot itself
// hold an interactive interrupt (see the package banner, correction #2).
type renderGate struct {
	mu       sync.Mutex
	approved bool
}

func (g *renderGate) open()        { g.mu.Lock(); g.approved = true; g.mu.Unlock() }
func (g *renderGate) isOpen() bool { g.mu.Lock(); defer g.mu.Unlock(); return g.approved }

// RenderApproval is the typed payload the approval interrupt hands the client so
// a human knows what they are approving before the expensive render.
type RenderApproval struct {
	ImageURI    string `json:"imageUri"`
	VideoPrompt string `json:"videoPrompt"`
	Model       string `json:"model"`
}

// ApprovalDecision is the resume payload the client sends back into the
// approve_video_render tool when it resolves the interrupt.
type ApprovalDecision struct {
	Approved bool `json:"approved"`
}

// ApproveInput / ApproveOutput are the approval tool's model-facing contract.
type ApproveInput struct {
	ImageURI    string `json:"imageUri" jsonschema_description:"The confirmed gs:// URI of the still to animate"`
	VideoPrompt string `json:"videoPrompt" jsonschema_description:"The motion/camera description for the clip"`
}
type ApproveOutput struct {
	Decision string `json:"decision"`
	Detail   string `json:"detail"`
}

// ImageInput is the image specialist's generate_image contract. The write
// destination is fixed by the code (closure), so the model supplies only the
// creative prompt.
type ImageInput struct {
	Prompt string `json:"prompt" jsonschema_description:"The full text prompt describing the still image to generate"`
}

// RenderInput is the video specialist's veo_render contract.
type RenderInput struct {
	ImageURI string `json:"imageUri" jsonschema_description:"The confirmed gs:// URI of the still to animate"`
	Motion   string `json:"motion" jsonschema_description:"The motion/camera description for the clip (e.g. 'slow push-in with drifting mist')"`
}

// MusicInput is the music specialist's compose_music contract.
type MusicInput struct {
	Prompt string `json:"prompt" jsonschema_description:"The text prompt describing the music to compose (mood, instruments, tempo)"`
}

// CombineInput is the av specialist's combine_av contract. Both URIs are
// runtime values threaded from the video and music steps.
type CombineInput struct {
	VideoURI string `json:"videoUri" jsonschema_description:"The confirmed gs:// URI of the rendered video clip"`
	AudioURI string `json:"audioUri" jsonschema_description:"The confirmed gs:// URI of the composed music score"`
}

// URIOutput is the shared, confirmed-by-listing result every specialist tool
// returns. The URI is proven to exist (the tool listed it) — never a bare
// resource_link.
type URIOutput struct {
	URI string `json:"uri"`
}

func main() {
	reject := flag.Bool("reject", false, "resolve the video-render interrupt by REJECTING it (demonstrates the halt-before-render path)")
	flag.Parse()

	subject := ""
	if args := flag.Args(); len(args) > 0 {
		subject = strings.Join(args, " ")
	}

	if err := run(context.Background(), *reject, subject); err != nil {
		log.Fatalf("tier3-preview: %v", err)
	}
}

func run(ctx context.Context, reject bool, subject string) error {
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
	base := os.Getenv("GENMEDIA_BUCKET")
	if base == "" {
		return fmt.Errorf("set GENMEDIA_BUCKET to a gs:// bucket for the generated artifacts")
	}
	// Same bare-bucket footgun as Tier 2: lyria and avtool take a bucket NAME
	// only (they strip gs:// and write at the root), while nanobanana/veo accept
	// a bucket+prefix. Standardize on a bare bucket and add per-run structure.
	bucket, err := bareBucket(base)
	if err != nil {
		return err
	}
	modelName := firstEnv("TIER3_MODEL")
	if modelName == "" {
		modelName = defaultModel
	}

	// Per-run destinations. The CODE owns these so it can prove every artifact by
	// listing at the end, independent of what the LLM reports, and so the wrapper
	// tools write deterministically.
	id := runID()
	imageDest := gcsJoin(base, id, "image")           // nanobanana: gcs_bucket_uri (bucket+prefix OK)
	videoDest := gcsJoin(base, id, "video")           // veo: bucket (bucket+prefix OK; writes <jobid>/ under it)
	musicName := id + "-score"                        // lyria: output_filename base (ext forced by server)
	musicPrefix := "gs://" + bucket + "/" + musicName // where lyria writes
	finalName := id + "-final.mp4"                    // avtool: output_filename
	finalURI := "gs://" + bucket + "/" + finalName    // where avtool writes

	// EXPERIMENTAL: genkit.WithExperimental() is REQUIRED for the exp agent APIs
	// (genkitx.DefineAgent / DefineTool / DefineInterruptibleTool, the
	// Agents/Artifacts middleware). Registering the middleware plugin keeps the
	// Dev-UI reflection tidy.
	g := genkit.Init(ctx,
		genkit.WithPlugins(
			&googlegenai.VertexAI{ProjectID: project, Location: orchestratorLocation},
			&middlewarex.Middleware{},
		),
		genkit.WithExperimental(),
	)

	// Connect to all four genmedia servers through the shared multi-server host
	// (reused from Tier 2), then confirm every required tool is present.
	host, err := genmedia.NewHost(ctx, g, producerServers...)
	if err != nil {
		return fmt.Errorf("creating multi-server genmedia host: %w", err)
	}
	for _, s := range producerServers {
		defer host.Disconnect(ctx, s)
	}
	tools, err := host.GetActiveTools(ctx, g)
	if err != nil {
		return fmt.Errorf("listing multi-server tools: %w", err)
	}
	if err := requireTools(tools, requiredTools); err != nil {
		return err
	}
	log.Printf("connected: %d server(s), %d tool(s) total", len(producerServers), len(tools))

	imageMCP := findTool(tools, "nanobanana_nanobanana_image_generation")
	veoMCP := findTool(tools, "veo_veo_i2v")
	lyriaMCP := findTool(tools, "lyria_lyria_generate_music")
	avMCP := findTool(tools, "avtool_ffmpeg_combine_audio_and_video")
	if imageMCP == nil || veoMCP == nil || lyriaMCP == nil || avMCP == nil {
		return fmt.Errorf("a required MCP tool was missing after requireTools passed (should be impossible)")
	}

	gate := &renderGate{}

	// ------------------------------------------------------------ specialist tools
	// Each is a REGISTERED wrapper (see banner correction #3) that invokes its
	// genmedia MCP tool via RunRaw with footgun-correct arguments, then proves
	// the output by LISTING it and returns the confirmed leaf gs:// URI.

	// generate_image: nanobanana still -> fixed imageDest (bucket+prefix OK).
	generateImageTool := genkitx.DefineTool(g, "generate_image",
		"Generate ONE still image from a text prompt and return its confirmed gs:// URI (verified by listing).",
		func(ctx context.Context, in ImageInput) (URIOutput, error) {
			log.Printf("generate_image: nanobanana -> %s", imageDest)
			args := map[string]any{
				"prompt":          in.Prompt,
				"gcs_bucket_uri":  imageDest,
				"output_filename": "still.png",
			}
			if _, err := imageMCP.RunRaw(ctx, args); err != nil {
				return URIOutput{}, fmt.Errorf("nanobanana image generation failed: %w", err)
			}
			uri, err := confirmLeaf(ctx, "image", imageDest, "")
			if err != nil {
				return URIOutput{}, err
			}
			return URIOutput{URI: uri}, nil
		})

	// veo_render: GATED Veo 3 render -> fixed videoDest. Refuses until a human has
	// approved via approve_video_render. This is what guarantees the render only
	// runs post-approval even though the interrupt itself lives on the
	// orchestrator (v1.13.1 limitation, correction #2).
	renderTool := genkitx.DefineTool(g, "veo_render",
		"Render a short video clip from an input still using Veo 3. REQUIRES prior human approval; "+
			"it refuses if the render has not been approved. Returns the confirmed gs:// URI of the clip.",
		func(ctx context.Context, in RenderInput) (URIOutput, error) {
			if !gate.isOpen() {
				return URIOutput{}, fmt.Errorf("veo_render refused: the human has not approved this render. " +
					"The orchestrator must call approve_video_render and receive approval first")
			}
			log.Printf("veo_render: APPROVED — veo_veo_i2v (image=%s -> %s)", in.ImageURI, videoDest)
			args := map[string]any{
				"image_uri":      in.ImageURI,
				"prompt":         in.Motion,
				"model":          veoModel,
				"bucket":         videoDest,
				"num_videos":     1,
				"generate_audio": true,
			}
			if _, err := veoMCP.RunRaw(ctx, args); err != nil {
				return URIOutput{}, fmt.Errorf("veo render failed: %w", err)
			}
			// veo writes into a server-assigned <jobid>/ subfolder; list recursively
			// for the .mp4 leaf.
			uri, err := confirmLeaf(ctx, "video", videoDest, ".mp4")
			if err != nil {
				return URIOutput{}, err
			}
			return URIOutput{URI: uri}, nil
		})

	// compose_music: lyria score -> fixed BARE bucket + musicName (ext forced by
	// server; model_id must be the clip-preview to route through global).
	composeMusicTool := genkitx.DefineTool(g, "compose_music",
		"Compose ONE short instrumental music score from a text prompt and return its confirmed gs:// URI (verified by listing).",
		func(ctx context.Context, in MusicInput) (URIOutput, error) {
			log.Printf("compose_music: lyria -> gs://%s/%s.*", bucket, musicName)
			args := map[string]any{
				"prompt":            in.Prompt,
				"output_gcs_bucket": bucket, // BARE bucket name (footgun)
				"output_filename":   musicName,
				"model_id":          lyriaModel,
			}
			if _, err := lyriaMCP.RunRaw(ctx, args); err != nil {
				return URIOutput{}, fmt.Errorf("lyria music generation failed: %w", err)
			}
			uri, err := confirmLeaf(ctx, "music", musicPrefix, "")
			if err != nil {
				return URIOutput{}, err
			}
			return URIOutput{URI: uri}, nil
		})

	// combine_av: avtool mux of the clip + score -> fixed BARE bucket + finalName.
	combineTool := genkitx.DefineTool(g, "combine_av",
		"Mux a video clip and a music score into ONE scored video and return its confirmed gs:// URI (verified by listing).",
		func(ctx context.Context, in CombineInput) (URIOutput, error) {
			log.Printf("combine_av: avtool %s + %s -> %s", in.VideoURI, in.AudioURI, finalURI)
			args := map[string]any{
				"input_video_uri":   in.VideoURI,
				"input_audio_uri":   in.AudioURI,
				"output_gcs_bucket": bucket, // BARE bucket name (footgun)
				"output_filename":   finalName,
			}
			if _, err := avMCP.RunRaw(ctx, args); err != nil {
				return URIOutput{}, fmt.Errorf("avtool combine failed: %w", err)
			}
			uri, err := confirmLeaf(ctx, "final", finalURI, "")
			if err != nil {
				return URIOutput{}, err
			}
			return URIOutput{URI: uri}, nil
		})

	// approve_video_render: the ORCHESTRATOR's interruptible tool. On the first
	// call (res==nil) it PAUSES with a typed RenderApproval payload; the client
	// resolves the interrupt with an ApprovalDecision. On approval it OPENS the
	// gate; on rejection it leaves it shut. This is the human-in-the-loop step,
	// on the orchestrator because that is where interrupts surface.
	approveTool := genkitx.DefineInterruptibleTool(g, "approve_video_render",
		"Ask a human to approve the expensive Veo video render before it runs. Call this AFTER the still "+
			"is ready and BEFORE delegating to the video agent. Pass the still URI and the motion prompt.",
		func(ctx context.Context, in ApproveInput, res *ApprovalDecision) (ApproveOutput, error) {
			if res == nil {
				log.Printf("approve_video_render: PAUSING for human approval (image=%s)", in.ImageURI)
				return ApproveOutput{}, tool.Interrupt(RenderApproval{
					ImageURI:    in.ImageURI,
					VideoPrompt: in.VideoPrompt,
					Model:       veoModel,
				})
			}
			if res.Approved {
				gate.open()
				log.Printf("approve_video_render: APPROVED by human — render gate opened")
				return ApproveOutput{Decision: "approved", Detail: "The human APPROVED the render. You may now delegate to the video agent."}, nil
			}
			log.Printf("approve_video_render: REJECTED by human — render gate stays shut")
			return ApproveOutput{Decision: "rejected", Detail: "The human REJECTED the render. Do NOT delegate to the video agent; stop and report that the render was declined."}, nil
		})

	// ------------------------------------------------------------ sub-agents
	// Each specialist gets the shared quirks fragment (context on the genmedia
	// footguns the wrappers already enforce), its own wrapper tool, and the
	// Artifacts middleware so its output can be merged into the orchestrator's
	// session (ArtifactStrategySession). Sub-agents have NO session store: each
	// delegation runs them one-shot (client-managed), which is what lets the
	// orchestrator forward recent history to them (Agents.HistoryLength).
	imageAgent := genkitx.DefineAgent(g, "image-agent",
		aix.InlinePrompt{
			ai.WithModelName(modelName),
			ai.WithSystem(genmedia.QuirksPrompt + "\n\nYOU ARE THE IMAGE SPECIALIST. Generate ONE still image by calling the " +
				"generate_image tool with a vivid, detailed prompt for the subject in your task. The tool writes to Google Cloud " +
				"Storage and returns the CONFIRMED gs:// URI (it has already verified the file by listing). Report that URI on its own " +
				"line as: IMAGE_URI=<uri>. Be brief."),
			ai.WithTools(generateImageTool),
			ai.WithToolChoice(ai.ToolChoiceAuto),
			ai.WithMaxTurns(6),
			ai.WithUse(&middlewarex.Artifacts{}),
		},
		aix.WithDescription[any]("Generates a still image from a prompt and returns a listing-confirmed gs:// URI."),
	)

	videoAgent := genkitx.DefineAgent(g, "video-agent",
		aix.InlinePrompt{
			ai.WithModelName(modelName),
			ai.WithSystem(genmedia.QuirksPrompt + "\n\nYOU ARE THE VIDEO SPECIALIST. Render ONE clip from the input still by calling " +
				"the veo_render tool with imageUri and motion exactly as given in your task. veo_render is human-gated and will refuse " +
				"if the render was not approved; if it refuses, report the refusal and stop. On success it returns the CONFIRMED clip " +
				"URI — report it on its own line as: VIDEO_URI=<uri>. Be brief."),
			ai.WithTools(renderTool),
			ai.WithToolChoice(ai.ToolChoiceAuto),
			ai.WithMaxTurns(6),
			ai.WithUse(&middlewarex.Artifacts{}),
		},
		aix.WithDescription[any]("Renders a video clip from a still with Veo 3 — human-gated before the render."),
	)

	musicAgent := genkitx.DefineAgent(g, "music-agent",
		aix.InlinePrompt{
			ai.WithModelName(modelName),
			ai.WithSystem(genmedia.QuirksPrompt + "\n\nYOU ARE THE MUSIC SPECIALIST. Compose ONE short instrumental score by calling " +
				"the compose_music tool with a prompt for the mood in your task. The tool returns the CONFIRMED gs:// URI. Report it on " +
				"its own line as: MUSIC_URI=<uri>. Be brief."),
			ai.WithTools(composeMusicTool),
			ai.WithToolChoice(ai.ToolChoiceAuto),
			ai.WithMaxTurns(6),
			ai.WithUse(&middlewarex.Artifacts{}),
		},
		aix.WithDescription[any]("Composes a music score from a prompt and returns a listing-confirmed gs:// URI."),
	)

	avAgent := genkitx.DefineAgent(g, "av-agent",
		aix.InlinePrompt{
			ai.WithModelName(modelName),
			ai.WithSystem(genmedia.QuirksPrompt + "\n\nYOU ARE THE AUDIO/VIDEO SPECIALIST. Mux the given clip and score into one scored " +
				"video by calling the combine_av tool with videoUri and audioUri exactly as given in your task. The tool returns the " +
				"CONFIRMED gs:// URI. Report it on its own line as: FINAL_URI=<uri>. Be brief."),
			ai.WithTools(combineTool),
			ai.WithToolChoice(ai.ToolChoiceAuto),
			ai.WithMaxTurns(6),
			ai.WithUse(&middlewarex.Artifacts{}),
		},
		aix.WithDescription[any]("Muxes a clip and a score into one scored video with avtool and returns a listing-confirmed gs:// URI."),
	)

	// ---------------------------------------------------------- orchestrator
	// The orchestrator uses the Agents middleware (auto-injects delegate_to_<name>
	// tools + lists the sub-agents in its system prompt) with ArtifactStrategySession
	// (merge sub-agent artifacts into this session), plus the Artifacts middleware
	// read-only and the approve_video_render interrupt. A FileSessionStore persists
	// the conversation so the Dev UI can resume it.
	store, err := localstore.NewFileSessionStore[any]("./.genkit/snapshots/producer")
	if err != nil {
		return fmt.Errorf("creating session store: %w", err)
	}

	orchestratorSystem := `You are an agentic video PRODUCER. You do not call media tools yourself; you
DELEGATE to specialist sub-agents (image, video, music, av) via their
delegate_to_<name> tools, and you PAUSE for human approval before the expensive
video render.

Follow these steps IN ORDER, one tool call per turn, and copy each returned
gs:// URI VERBATIM into the next step:

1. delegate to the image agent: ask it to generate the still (use the subject in
   the user's request). It reports IMAGE_URI.
2. approve_video_render: pass imageUri=<the IMAGE_URI> and the motion/camera
   videoPrompt. This PAUSES for a human.
   - If the result decision is "approved": continue to step 3.
   - If the result decision is "rejected": STOP. Do not delegate to the video
     agent. Give a brief final answer saying the render was declined and list
     the still you did produce.
3. delegate to the video agent: pass the still's imageUri and the motion. It
   returns VIDEO_URI.
4. delegate to the music agent: ask it to compose a score (use the mood in the
   user's request). It returns MUSIC_URI.
5. delegate to the av agent: pass videoUri=<VIDEO_URI> and audioUri=<MUSIC_URI>.
   It returns FINAL_URI.
6. Give a brief final answer listing IMAGE_URI, VIDEO_URI, MUSIC_URI, FINAL_URI.

Before each delegation or the approval call, send one short sentence saying what
you are about to do. Never skip the approval step, and never delegate to the
video agent before approval.`

	orchestrator := genkitx.DefineAgent(g, "producer",
		aix.InlinePrompt{
			ai.WithModelName(modelName),
			ai.WithSystem(orchestratorSystem),
			ai.WithTools(approveTool),
			ai.WithToolChoice(ai.ToolChoiceAuto),
			ai.WithMaxTurns(24),
			ai.WithUse(
				&middlewarex.Agents{
					Agents:           []aix.AgentRef{imageAgent.Ref(), videoAgent.Ref(), musicAgent.Ref(), avAgent.Ref()},
					MaxDelegations:   10,
					HistoryLength:    12,
					ArtifactStrategy: middlewarex.ArtifactStrategySession,
				},
				&middlewarex.Artifacts{Readonly: true},
			),
		},
		aix.WithSessionStore(store),
		aix.WithDescription[any]("Agentic producer: delegates to image/video/music/av specialists and gates the Veo render on human approval."),
	)

	// ------------------------------------------------------------------ drive
	if subject == "" {
		subject = "a photorealistic red panda sitting on a moss-covered rock in a misty forest at dawn"
	}
	userTask := fmt.Sprintf("Produce a short scored video. Subject for the still: %s. "+
		"Motion for the clip: a slow, gentle camera push-in with drifting mist and subtle movement. "+
		"Mood for the score: a calm, warm ambient piece — soft piano and airy strings, unhurried and gently hopeful.", subject)

	approve := !reject
	log.Printf("run %s: driving orchestrator (interrupt will be %s); image=%s video=%s music=%s final=%s",
		id, decisionWord(approve), imageDest, videoDest, musicPrefix, finalURI)

	out, err := driveOrchestrator(ctx, orchestrator, approveTool, userTask, approve)
	if err != nil {
		return err
	}
	log.Printf("orchestrator finished: reason=%s snapshot=%s", out.FinishReason, out.SnapshotID)
	if out.Error != nil {
		log.Printf("orchestrator error: %s: %s", out.Error.Status, out.Error.Message)
	}
	if out.Message != nil {
		if txt := strings.TrimSpace(out.Message.Text()); txt != "" {
			log.Printf("orchestrator final answer:\n%s", txt)
		}
	}

	// -------------------------------------------------- authoritative evidence
	// Prove artifacts by LISTING the destinations the code owns — independent of
	// the LLM's textual report. This is the success gate, same discipline as
	// Tiers 0-2.
	log.Printf("==== VERIFY-BY-LISTING (authoritative) ====")
	imageURI, imgErr := confirmLeaf(ctx, "image", imageDest, "")
	if !approve {
		// Reject path: the video, and therefore the mux, must NOT exist.
		videoRes, _ := verify.VerifyRecursive(ctx, videoDest)
		if videoRes.Exists {
			return fmt.Errorf("REJECT PATH VIOLATED: a video artifact exists at %s despite rejection: %v", videoDest, videoRes.Entries)
		}
		log.Printf("reject path OK: no video at %s (the gate held; the Veo render never ran)", videoDest)
		if imgErr != nil {
			log.Printf("note: image not confirmed on reject path (%v) — acceptable if the orchestrator stopped early", imgErr)
		} else {
			log.Printf("reject path produced only the still: %s", imageURI)
		}
		if gate.isOpen() {
			return fmt.Errorf("REJECT PATH VIOLATED: render gate is open after a rejection")
		}
		return nil
	}

	// Approve path: every artifact must exist.
	videoURI, err := confirmLeaf(ctx, "video", videoDest, ".mp4")
	if err != nil {
		return err
	}
	musicURI, err := confirmLeaf(ctx, "music", musicPrefix, "")
	if err != nil {
		return err
	}
	finalConfirmed, err := confirmLeaf(ctx, "final", finalURI, "")
	if err != nil {
		return err
	}
	if imgErr != nil {
		return imgErr
	}
	log.Printf("==== DONE (approve path) ====")
	log.Printf("image=%s", imageURI)
	log.Printf("video=%s", videoURI)
	log.Printf("music=%s", musicURI)
	log.Printf("final=%s", finalConfirmed)
	return nil
}

// driveOrchestrator opens a connection to the orchestrator, sends the task, and
// consumes the stream — logging delegation/tool calls and, when the
// approve_video_render tool interrupts, resolving it programmatically with the
// approve/reject decision (the stand-in for a human at the Dev UI). It loops
// because a resumed turn can interrupt again. This mirrors what the Dev UI does
// interactively; here it is headless so the live run needs no CLI installed.
func driveOrchestrator(ctx context.Context, a *aix.Agent[any], approveTool *aix.InterruptibleTool[ApproveInput, ApproveOutput, ApprovalDecision], task string, approve bool) (*aix.AgentOutput[any], error) {
	conn, err := a.Connect(ctx)
	if err != nil {
		return nil, fmt.Errorf("connecting to orchestrator: %w", err)
	}
	defer conn.Close()

	if err := conn.SendText(task); err != nil {
		return nil, fmt.Errorf("sending task: %w", err)
	}

	for {
		var interrupts []*ai.Part
		for chunk, rerr := range conn.Receive() {
			if rerr != nil {
				return nil, fmt.Errorf("receiving from orchestrator: %w", rerr)
			}
			if mc := chunk.ModelChunk; mc != nil {
				if t := strings.TrimSpace(mc.Text()); t != "" {
					log.Printf("[producer] %s", t)
				}
				for _, p := range mc.Content {
					switch {
					case p.IsInterrupt():
						interrupts = append(interrupts, p)
					case p.IsToolRequest() && !p.ToolRequest.Partial:
						log.Printf("[producer] -> tool %s %s", p.ToolRequest.Name, compactArgs(p.ToolRequest.Input))
					}
				}
			}
			if chunk.Artifact != nil {
				log.Printf("[producer] artifact: %s", chunk.Artifact.Name)
			}
			if chunk.TurnEnd != nil {
				break
			}
		}
		if len(interrupts) == 0 {
			break
		}
		// Resolve every interrupt with the approve/reject decision.
		resume := &aix.ToolResume{}
		for _, ip := range interrupts {
			if meta, ok := tool.InterruptAs[RenderApproval](ip); ok {
				log.Printf("[human] approval requested: render %s (%s); deciding: %s",
					meta.ImageURI, meta.Model, decisionWord(approve))
			}
			part, perr := approveTool.Resume(ip, ApprovalDecision{Approved: approve})
			if perr != nil {
				return nil, fmt.Errorf("building resume part: %w", perr)
			}
			resume.Restart = append(resume.Restart, part)
		}
		if err := conn.SendResume(resume); err != nil {
			return nil, fmt.Errorf("sending resume: %w", err)
		}
		// Loop to consume the resumed continuation.
	}

	return conn.Output()
}

// confirmLeaf lists dest and returns the chosen leaf URI (by suffix, else
// first), erroring if nothing is there. It is used in two places, both proving
// output by listing rather than by a resource_link: inside each specialist tool
// (so a tool's success is a real object), and in the final authoritative,
// code-owned verify pass in run (independent of what the LLM reported).
func confirmLeaf(ctx context.Context, label, dest, wantSuffix string) (string, error) {
	res, err := verify.VerifyRecursive(ctx, dest)
	if err != nil {
		return "", fmt.Errorf("verify %s at %s: %w", label, dest, err)
	}
	log.Printf("verify %s: %s", label, res)
	for _, e := range res.Entries {
		log.Printf("  - %s", e)
	}
	if !res.Exists || len(res.Entries) == 0 {
		return "", fmt.Errorf("no %s artifact found at %s (listing returned nothing)", label, dest)
	}
	if wantSuffix != "" {
		for _, e := range res.Entries {
			if strings.HasSuffix(e, wantSuffix) {
				return e, nil
			}
		}
		return "", fmt.Errorf("no %s%s artifact found under %s", label, wantSuffix, dest)
	}
	return res.Entries[0], nil
}

// findTool returns the aggregated tool with the exact namespaced name, or nil.
func findTool(tools []ai.Tool, name string) ai.Tool {
	for _, t := range tools {
		if t.Name() == name {
			return t
		}
	}
	return nil
}

// requireTools confirms every required namespaced tool name is present.
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

// bareBucket validates base is a gs:// URI naming a bucket with NO path and
// returns the bare bucket name (lyria/avtool take a bucket name only).
func bareBucket(base string) (string, error) {
	if !verify.IsGCS(base) {
		return "", fmt.Errorf("GENMEDIA_BUCKET must be a gs:// URI (got %q)", base)
	}
	name := strings.Trim(strings.TrimPrefix(base, "gs://"), "/")
	if name == "" {
		return "", fmt.Errorf("GENMEDIA_BUCKET must name a bucket (got %q)", base)
	}
	if strings.Contains(name, "/") {
		return "", fmt.Errorf("GENMEDIA_BUCKET must be a BARE bucket with no path: "+
			"lyria and avtool take a bucket name only and write at the root (got %q)", base)
	}
	return name, nil
}

// gcsJoin appends per-run segments to a gs:// base, normalizing the slash.
func gcsJoin(base string, segments ...string) string {
	return strings.TrimRight(base, "/") + "/" + strings.Join(segments, "/")
}

// runID returns a per-run segment: a UTC timestamp plus a short random suffix.
func runID() string {
	ts := time.Now().UTC().Format("20060102-150405")
	var b [2]byte
	if _, err := rand.Read(b[:]); err != nil {
		return ts
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

func decisionWord(approve bool) string {
	if approve {
		return "APPROVED"
	}
	return "REJECTED"
}

// compactArgs renders a tool input as compact single-line text for logs. It is
// deliberately not JSON: fmt's %v gives Go map syntax (e.g. map[task:...]),
// which is enough to see what the model asked for without a marshal step.
func compactArgs(v any) string {
	if v == nil {
		return "{}"
	}
	s := fmt.Sprintf("%v", v)
	const max = 200
	if r := []rune(s); len(r) > max {
		return string(r[:max]) + "…"
	}
	return s
}

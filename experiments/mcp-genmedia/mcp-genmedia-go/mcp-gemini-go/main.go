// Copyright 2025 Google LLC
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

// Package main implements an MCP server for Google's Gemini models.

package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
	"google.golang.org/genai"
)

var (
	appConfig   *common.Config
	genAIClient *genai.Client
	transport   string
	port        int
)

const (
	serviceName = "mcp-gemini-go"
)

// version is overridden at build time via -ldflags "-X main.version=...".
// The single source of truth for the version is the VERSION file at the root
// of the mcp-genmedia-go tree (injected by the Makefile locally and by the git
// tag through goreleaser for releases). Defaults to "dev" for un-injected builds.
var version = "dev"

func init() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)
	flag.StringVar(&transport, "t", "stdio", "Transport type (stdio, sse, or http)")
	flag.StringVar(&transport, "transport", "stdio", "Transport type (stdio, sse, or http)")
	flag.IntVar(&port, "p", 0, "Port for SSE/HTTP server (defaults to PORT env var or 8080/8081)")
	flag.IntVar(&port, "port", 0, "Port for SSE/HTTP server (defaults to PORT env var or 8080/8081)")
}

func main() {
	flag.Parse() // Parse in main (not init) so `go test` flags are not consumed; matches sibling servers.

	var cleanup func()
	appConfig, cleanup = common.Init(serviceName, version)
	defer cleanup()

	// Override default location for Gemini models if not explicitly set
	if os.Getenv("LOCATION") == "" {
		log.Printf("LOCATION environment variable not set. Defaulting to 'global' for mcp-gemini-go.")
		appConfig.Location = "global"
	}
	var err error

	log.Printf("Initializing global GenAI client...")
	clientCtx, clientCancel := context.WithTimeout(context.Background(), 1*time.Minute)
	defer clientCancel()

	clientConfig := &genai.ClientConfig{
		Backend:  genai.BackendVertexAI,
		Project:  appConfig.ProjectID,
		Location: appConfig.Location,
	}
	if appConfig.ApiEndpoint != "" {
		log.Printf("Using custom Vertex AI endpoint: %s", appConfig.ApiEndpoint)
		clientConfig.HTTPOptions.BaseURL = appConfig.ApiEndpoint
	}

	if err := common.InjectCaptureHeaders(clientCtx, appConfig, clientConfig); err != nil {
		log.Printf("Warning: Failed to inject capture headers: %v", err)
	}

	genAIClient, err = genai.NewClient(clientCtx, clientConfig)
	if err != nil {
		log.Printf("Warning: Error creating global GenAI client: %v. Deferring initialization to runtime.", err)
	} else {
		log.Printf("Global GenAI client initialized successfully.")
	}

	s := server.NewMCPServer("Gemini", version, server.WithResourceCapabilities(true, false))

	tool := mcp.NewTool("gemini_image_generation",
		mcp.WithDescription("Generates content (text and/or images) based on a multimodal prompt using Gemini Image generation models."),
		mcp.WithString("prompt", mcp.Required(), mcp.Description("The text prompt for content generation.")),
		mcp.WithString("model", mcp.DefaultString("gemini-nano-banana-2.1"), mcp.Description(common.BuildGeminiImageModelDescription())),
		mcp.WithString("aspect_ratio", mcp.DefaultString("1:1"), mcp.Description("Aspect ratio of the generated images. Note: supported aspect ratios are model-dependent.")),
		mcp.WithString("image_size", mcp.Description("Optional. Size of the generated images: 1K, 2K, or 4K. Defaults to 1K when unset. Note: supported sizes are model-dependent.")),
		mcp.WithArray("images", mcp.Description("Optional. A list of local file paths or GCS URIs for input images."), mcp.Items(map[string]any{"type": "string"})),
		mcp.WithString("output_directory", mcp.Description("Optional. Local directory to save generated image(s) to.")),
		mcp.WithString("gcs_bucket_uri", mcp.Description("Optional. GCS URI prefix to store generated images (e.g., your-bucket/outputs/).")),
		mcp.WithString("output_filename", mcp.Description("Optional. Client-predictable base name for the generated file(s). The extension is forced to the true output media type (e.g. .png). When a single image is produced the name is used as-is (e.g. 'hero.png'); when multiple images are produced they are suffixed '_1', '_2', ... before the extension (e.g. 'hero_1.png', 'hero_2.png'). An existing file/object of the same name is overwritten.")),
	)

	handlerWithClient := func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return geminiGenerateContentHandler(genAIClient, ctx, request)
	}
	s.AddTool(tool, handlerWithClient)

	// --- Register Gemini TTS Tools ---
	listVoicesTool := mcp.NewTool("list_gemini_voices",
		mcp.WithDescription("Lists the available single-speaker voices for use with the Gemini-TTS models."),
	)
	s.AddTool(listVoicesTool, listGeminiVoicesHandler)

	ttsTool := mcp.NewTool("gemini_audio_tts",
		mcp.WithDescription("Synthesizes speech from text using Gemini models, allowing for granular control over style, pace, tone, and emotional expression through natural-language prompts."),
		mcp.WithString("text",
			mcp.Required(),
			mcp.Description("The text to synthesize (up to 800 characters)."),
		),
		mcp.WithString("prompt",
			mcp.Description("Stylistic instructions on how to synthesize the content. You can adapt delivery, adopt specific accents, and produce a range of tones and expressions."),
		),
		mcp.WithString("voice_name",
			mcp.DefaultString(defaultGeminiTTSVoice),
			mcp.Description("The voice to use. Use 'list_gemini_voices' to see available voices."),
			mcp.Enum(availableGeminiVoices...),
		),
		mcp.WithString("model_name",
			mcp.DefaultString(defaultGeminiTTSModel),
			mcp.Description("The model to use."),
			mcp.Enum("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-tts", "gemini-2.5-pro-tts", "gemini-2.5-flash-lite-preview-tts"),
		),
		mcp.WithString("language_code",
			mcp.DefaultString("en-US"),
			mcp.Description("Optional. The language code to use for the synthesis. Defaults to en-US."),
		),
		mcp.WithString("output_filename",
			mcp.Description("Optional. Client-predictable base name for the saved audio file. The extension is forced to the true audio media type of the selected audio_encoding (e.g. .wav, .mp3, .ogg). Used as-is for a single file (e.g. 'speech.wav'); multiple artifacts are suffixed '_1', '_2', ... before the extension. Takes precedence over the deprecated output_filename_prefix. An existing file of the same name is overwritten."),
		),
		mcp.WithString("output_filename_prefix",
			mcp.DefaultString("gemini_tts_audio"),
			mcp.Description("Optional (deprecated; use output_filename). A prefix for the output audio filename if saving locally. A voice name, timestamp and extension will be appended."),
		),
		mcp.WithString("output_directory",
			mcp.Description("Optional. If provided, specifies a local directory to save the generated audio file to. If not provided, audio data is returned in the response."),
		),
		mcp.WithString("audio_encoding",
			mcp.DefaultString("LINEAR16"),
			mcp.Description("The format of the audio byte stream. Supported values: LINEAR16, MP3, OGG_OPUS, MULAW, ALAW, PCM, M4A."),
			mcp.Enum("LINEAR16", "MP3", "OGG_OPUS", "MULAW", "ALAW", "PCM", "M4A"),
		),
	)
	s.AddTool(ttsTool, geminiAudioTTSHandler)
	// --- End of TTS Tools ---

	// --- Register Gemini Omni Video Tool ---
	// Same param surface as the standalone mcp-omni-go server; the handler is a
	// thin wrapper over the shared common.GenerateOmniVideo entry point, so the
	// two servers can never drift. No second client is created on this binary —
	// the Interactions path is fully encapsulated in mcp-common.
	omniTool := mcp.NewTool("omni_video_generation",
		mcp.WithDescription("Generates video (with optional embedded audio) from a text prompt, optionally conditioned on input images and/or videos, using Google's Gemini Omni model via the Vertex Interactions API. Returns MP4(s) saved locally and/or to GCS."),
		mcp.WithString("prompt", mcp.Required(), mcp.Description("The text prompt describing the video to generate.")),
		mcp.WithString("model", mcp.Description(common.BuildOmniModelDescription())),
		mcp.WithArray("images",
			mcp.Items(map[string]any{"type": "string"}),
			mcp.Description("Optional. Up to 10 input images to condition generation on. Each entry is a local file path or a gs:// URI (image/png, image/jpeg, image/webp).")),
		mcp.WithArray("videos",
			mcp.Items(map[string]any{"type": "string"}),
			mcp.Description("Optional. Input videos to reference or edit. Each entry is a local file path or a gs:// URI (e.g. video/mp4, video/webm, video/quicktime).")),
		mcp.WithNumber("sample_count", mcp.Description("Optional. Number of videos to generate (1-3, default 1). Clamped to the model maximum of 3.")),
		mcp.WithNumber("temperature", mcp.Description("Optional. Sampling temperature, 0.0-2.0 (higher = more varied). Sent in generation_config.")),
		mcp.WithNumber("top_p", mcp.Description("Optional. Nucleus sampling probability mass, 0.0-1.0. Sent in generation_config.")),
		mcp.WithString("output_directory", mcp.Description("Optional. Local directory to save the generated video(s) to.")),
		mcp.WithString("gcs_bucket_uri", mcp.Description("Optional. GCS URI prefix to store generated video(s) (e.g., your-bucket/outputs/). Falls back to GENMEDIA_BUCKET+/omni_outputs/ if set.")),
		mcp.WithString("output_filename", mcp.Description("Optional. Client-predictable base name for the generated file(s). The extension is forced to the true output media type (e.g. .mp4). When a single video is produced the name is used as-is (e.g. 'clip.mp4'); when multiple videos are produced they are suffixed '_1', '_2', ... before the extension (e.g. 'clip_1.mp4'). An existing file/object of the same name is overwritten.")),
	)
	s.AddTool(omniTool, omniVideoGenerationHandler)
	// --- End of Gemini Omni Video Tool ---

	// --- Register Gemini Transcribe Tool ---
	// Synchronous speech-to-text via Gemini 3.5 Transcribe (the generate_content
	// path on gemini-3.5-transcribe-preview, NOT the live/streaming API). The
	// handler is a thin wrapper over the shared common.Transcribe helpers, so it
	// stays in lockstep with the standalone mcp-gemini-transcribe-go server.
	transcribeTool := mcp.NewTool("gemini_transcribe",
		mcp.WithDescription("Transcribes a pre-recorded audio file to text using Google's Gemini 3.5 Transcribe model (synchronous mode). Supports language hints, custom vocabulary biasing, speaker diarization, word-level timestamps, and smart formatting. Audio must be <=15 minutes."),
		mcp.WithString("input_audio",
			mcp.Required(),
			mcp.Description("The audio to transcribe: either a local file path or a gs:// URI. Supported formats include WAV, MP3, OGG/Opus, FLAC, M4A/AAC, AIFF, AMR, WEBM, and PCM."),
		),
		mcp.WithString("mime_type",
			mcp.Description("Optional. The MIME type of the audio (e.g. audio/wav, audio/mpeg, audio/ogg). Inferred from the file extension when omitted."),
		),
		mcp.WithString("model",
			mcp.DefaultString(common.DefaultTranscribeModel),
			mcp.Description("Optional. The transcription model to use. Defaults to the synchronous gemini-3.5-transcribe-preview."),
		),
		mcp.WithArray("language_codes",
			mcp.Items(map[string]any{"type": "string"}),
			mcp.Description("Optional. BCP-47 language code hints (e.g. [\"en-US\", \"es-ES\"]). Omit for automatic language detection."),
		),
		mcp.WithArray("custom_vocabulary",
			mcp.Items(map[string]any{"type": "string"}),
			mcp.Description("Optional. Up to 1000 phrases (brand names, proper nouns, domain terms) that bias recognition. Most reliable when language_codes is also set."),
		),
		mcp.WithBoolean("enable_diarization",
			mcp.Description("Optional. Label individual speakers (up to 8). Incompatible with smart_formatting."),
		),
		mcp.WithBoolean("enable_word_timestamps",
			mcp.Description("Optional. Return word-level start/end offsets. Incompatible with smart_formatting."),
		),
		mcp.WithBoolean("smart_formatting",
			mcp.Description("Optional. Use SMART mode: filler-word removal, light grammatical cleanup, and automatic formatting. Incompatible with enable_diarization and enable_word_timestamps."),
		),
		mcp.WithString("output_directory",
			mcp.Description("Optional. Local directory to save the transcription result (JSON) to. When omitted, the transcript is returned in the response only."),
		),
		mcp.WithString("gcs_bucket_uri",
			mcp.Description("Optional. GCS URI prefix to store the transcription result (JSON), e.g. your-bucket/transcripts/."),
		),
		mcp.WithString("output_filename",
			mcp.Description("Optional. Client-predictable base name for the saved transcript. The extension is forced to .json. An existing file/object of the same name is overwritten."),
		),
	)
	s.AddTool(transcribeTool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return geminiTranscribeHandler(genAIClient, ctx, request)
	})
	// --- End of Gemini Transcribe Tool ---

	// --- Register Gemini Resources ---
	s.AddResource(mcp.NewResource(
		"gemini://language_codes",
		"Gemini TTS Language Codes",
		mcp.WithResourceDescription("A list of supported languages and their BCP-47 codes for Gemini TTS."),
		mcp.WithMIMEType("application/json"),
	), geminiLanguageCodesHandler)
	// --- End of Gemini Resources ---

	switch transport {
	case "sse":
		ssePort := 8081 // Default SSE port
		if port != 0 {
			ssePort = port
		} else if p, err := strconv.Atoi(os.Getenv("PORT")); err == nil {
			ssePort = p
		}
		log.Printf("Starting %s MCP Server (Version: %s, Transport: sse, Port: %d)", serviceName, version, ssePort)
		sseServer := server.NewSSEServer(s, server.WithBaseURL(fmt.Sprintf("http://localhost:%d", ssePort)))
		if err := sseServer.Start(fmt.Sprintf(":%d", ssePort)); err != nil {
			log.Fatalf("SSE Server error: %v", err)
		}
	case "http":
		httpPort := 8080 // Default HTTP port
		if port != 0 {
			httpPort = port
		} else if p, err := strconv.Atoi(os.Getenv("PORT")); err == nil {
			httpPort = p
		}
		log.Printf("Starting %s MCP Server (Version: %s, Transport: http, Port: %d)", serviceName, version, httpPort)
		http.Handle("/mcp", server.NewStreamableHTTPServer(s))
		if err := http.ListenAndServe(fmt.Sprintf(":%d", httpPort), nil); err != nil {
			log.Fatalf("HTTP Server error: %v", err)
		}
	case "stdio":
		log.Printf("Starting %s MCP Server (Version: %s, Transport: stdio)", serviceName, version)
		if err := server.ServeStdio(s); err != nil {
			log.Fatalf("STDIO Server error: %v", err)
		}
	default:
		log.Fatalf("Unsupported transport type: %s. Please use 'stdio', 'sse', or 'http'.", transport)
	}
}

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

// Package main implements an MCP server for Google's Gemini Omni video model.
//
// Omni (gemini-omni-1.1-flash-preview) is reachable only through the Vertex
// Interactions API, so this server calls the shared common.GenerateOmniVideo
// helper (which owns the Interactions client) rather than the shared genai.Client.

package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
)

var (
	appConfig *common.Config
	transport string
	port      int
)

const (
	serviceName = "mcp-omni-go"
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
	flag.Parse()

	var cleanup func()
	appConfig, cleanup = common.Init(serviceName, version)
	defer cleanup()

	// Omni is global-only via the Interactions API. Default the location to
	// "global" if not explicitly set (mirrors nanobanana/gemini main.go). The
	// interactions call hard-pins "global" regardless; this keeps config coherent.
	if os.Getenv("LOCATION") == "" && os.Getenv("OMNI_LOCATION") == "" && os.Getenv("GOOGLE_CLOUD_LOCATION") == "" {
		log.Printf("LOCATION not set. Defaulting to 'global' for %s.", serviceName)
		appConfig.Location = "global"
	}

	s := server.NewMCPServer("Gemini Omni", version, server.WithResourceCapabilities(true, true))

	s.AddResource(mcp.NewResource(
		"omni://models",
		"Supported Gemini Omni Models",
		mcp.WithResourceDescription("A machine-readable capability matrix of supported Gemini Omni video models, aliases, resolutions, aspect ratios, duration bounds, and input limits."),
		mcp.WithMIMEType("application/json"),
	), func(ctx context.Context, request mcp.ReadResourceRequest) ([]mcp.ResourceContents, error) {
		return common.MarshalModelsResource("omni://models", common.SupportedOmniModels)
	})

	tool := mcp.NewTool("omni_video_generation",
		mcp.WithDescription("Generates video (with optional embedded audio) from a text prompt, optionally conditioned on input images and/or videos, using Google's Gemini Omni model via the Vertex Interactions API. Returns MP4(s) saved locally and/or to GCS."),
		mcp.WithString("prompt", mcp.Required(), mcp.Description("The text prompt describing the video to generate.")),
		mcp.WithString("model", mcp.Description(common.BuildOmniModelDescription())),
		mcp.WithString("resolution", mcp.Description("Optional. Video output resolution: 360p, 720p, 1080p, or 4k (gemini-omni-1.1-flash-preview supports all four; gemini-omni-flash-preview supports 720p). Sent in response_format.")),
		mcp.WithString("aspect_ratio", mcp.Description("Optional. Video output aspect ratio: 16:9 or 9:16. Sent in response_format.")),
		mcp.WithNumber("duration_seconds", mcp.Description("Optional. Video output duration in seconds (3-10, maximum 10s). Sent in response_format.")),
		mcp.WithArray("images",
			mcp.Items(map[string]any{"type": "string"}),
			mcp.Description("Optional. Up to 10 input images to condition generation on. Each entry is a local file path (<=20 MB) or a gs:// URI (<=30 MB; image/png, image/jpeg, image/webp, image/heic, image/heif).")),
		mcp.WithArray("videos",
			mcp.Items(map[string]any{"type": "string"}),
			mcp.Description("Optional. Up to 3 input videos to reference, edit, or extend. Each entry is a local file path (<=20 MB) or a gs:// URI (video/mp4, video/webm, video/quicktime, video/mpeg, video/x-flv, video/wmv, video/3gpp).")),
		mcp.WithNumber("sample_count", mcp.Description("Optional. Number of videos to generate (1-3, default 1). Clamped to the model maximum of 3.")),
		mcp.WithNumber("temperature", mcp.Description("Optional. Sampling temperature, 0.0-2.0 (default 1.0; higher = more varied). Sent in generation_config.")),
		mcp.WithNumber("top_p", mcp.Description("Optional. Nucleus sampling probability mass, 0.0-1.0 (default 0.95). Sent in generation_config.")),
		mcp.WithString("output_directory", mcp.Description("Optional. Local directory to save the generated video(s) to.")),
		mcp.WithString("gcs_bucket_uri", mcp.Description("Optional. GCS URI prefix to store generated video(s) (e.g., your-bucket/outputs/). Falls back to GENMEDIA_BUCKET+/omni_outputs/ if set.")),
		mcp.WithString("output_filename", mcp.Description("Optional. Client-predictable base name for the generated file(s). The extension is forced to the true output media type (e.g. .mp4). When a single video is produced the name is used as-is (e.g. 'clip.mp4'); when multiple videos are produced they are suffixed '_1', '_2', ... before the extension (e.g. 'clip_1.mp4'). An existing file/object of the same name is overwritten.")),
	)
	s.AddTool(tool, omniVideoGenerationHandler)

	switch transport {
	case "sse":
		ssePort := 8081
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
		httpPort := 8080
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

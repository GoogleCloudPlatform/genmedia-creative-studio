// Package main implements an MCP server for audio and video processing.

package main

import (
	"flag"
	"fmt"
	"log"
	"net/http"
	"strconv"

	"github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
	"github.com/mark3labs/mcp-go/server"
	"github.com/rs/cors"
)

const (
	serviceName = "mcp-avtool-go"
)

// version is overridden at build time via -ldflags "-X main.version=...".
// The single source of truth for the version is the VERSION file at the root
// of the mcp-genmedia-go tree (injected by the Makefile locally and by the git
// tag through goreleaser for releases). Defaults to "dev" for un-injected builds.
var version = "dev"

var (
	transport string
	port      int
)

// init handles command-line flags and initial logging setup.
// It configures the log package to include standard flags and the short file name
// of the caller in log messages, which is useful for debugging.
func init() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)
	flag.StringVar(&transport, "t", "stdio", "Transport type (stdio, sse, or http)")
	flag.StringVar(&transport, "transport", "stdio", "Transport type (stdio, sse, or http)")
	flag.IntVar(&port, "p", 0, "Port for SSE/HTTP server (defaults to PORT env var or 8080/8081)")
	flag.IntVar(&port, "port", 0, "Port for SSE/HTTP server (defaults to PORT env var or 8080/8081)")
}

// determinePort resolves the final listening port based on a defined order of precedence:
// 1. The `--port` or `-p` command-line flag.
// 2. The `PORT` environment variable.
// 3. A transport-specific default value (8080 for HTTP, 8081 for SSE).
// It logs the selection process for clarity.
func determinePort(transport string, portFlag int) int {
	if portFlag != 0 {
		log.Printf("Using port %d from --port/-p flag.", portFlag)
		return portFlag
	}

	envPortStr := common.GetEnv("PORT", "")
	if envPortStr != "" {
		if envPort, err := strconv.Atoi(envPortStr); err == nil {
			log.Printf("Using port %d from PORT environment variable.", envPort)
			return envPort
		}
		log.Printf("Warning: Could not parse PORT environment variable '%s'. Falling back to default.", envPortStr)
	}

	if transport == "http" {
		log.Println("Using default port 8080 for http transport.")
		return 8080
	}
	if transport == "sse" {
		log.Println("Using default port 8081 for sse transport.")
		return 8081
	}
	return 0 // Should not happen for http/sse
}

// main is the entry point of the application. It initializes the configuration,
// sets up OpenTelemetry for tracing, creates a new MCP server, registers all the
// available AV (Audio/Video) tools, and starts the server based on the specified
// transport mechanism (stdio, sse, or http).
func main() {
	flag.Parse() // Ensure flags are parsed before use

	// Initialize OpenTelemetry
	var cleanup func()
	cfg, cleanup := common.Init(serviceName, version)
	defer cleanup()

	s := server.NewMCPServer(
		"AV Compositing Tool", // More general name
		version,
	)

	// Register tools - these functions are now in mcp_handlers.go
	// and now require the config to be passed.
	addConvertAudioTool(s, cfg)
	addCombineAudioVideoTool(s, cfg)
	addOverlayImageOnVideoTool(s, cfg)
	addConcatenateMediaTool(s, cfg)
	addAdjustVolumeTool(s, cfg)
	addLayerAudioTool(s, cfg)
	addCreateGifTool(s, cfg)
	addGetMediaInfoTool(s, cfg)
	addTrimMediaTool(s, cfg)
	addExtractFrameTool(s, cfg)
	addNormalizeLoudnessTool(s, cfg)
	addResizeReframeTool(s, cfg)

	// Resolve the application-layer auth policy once, before serving any
	// network transport. This fails closed: it refuses to serve an HTTP/SSE
	// transport unless an expected OIDC audience is configured or the explicit
	// local-dev bypass is set. This defends the service independently of the
	// Cloud Run --no-allow-unauthenticated deployment flag (b/565096167).
	authCfg, authErr := newAuthConfig()

	switch transport {
	case "sse":
		if authErr != nil {
			log.Fatalf("Refusing to start SSE server: %v", authErr)
		}
		ssePort := determinePort("sse", port)
		log.Printf("Starting AV Compositing Tool (avtool) MCP Server (Version: %s, Transport: sse, Port: %d)", version, ssePort)
		sseServer := server.NewSSEServer(s, server.WithBaseURL(fmt.Sprintf("http://localhost:%d", ssePort)))
		listenAddr := fmt.Sprintf(":%d", ssePort)
		if err := http.ListenAndServe(listenAddr, authCfg.middleware(sseServer)); err != nil {
			log.Fatalf("SSE Server error: %v", err)
		}
	case "http":
		if authErr != nil {
			log.Fatalf("Refusing to start HTTP server: %v", authErr)
		}
		httpPort := determinePort("http", port)
		log.Printf("Starting AV Compositing Tool (avtool) MCP Server (Version: %s, Transport: http, Port: %d)", version, httpPort)
		mcpHTTPHandler := server.NewStreamableHTTPServer(s) // Base path /mcp
		c := cors.New(cors.Options{
			AllowedOrigins:   []string{"*"}, // Consider making this configurable
			AllowedMethods:   []string{http.MethodGet, http.MethodPost, http.MethodPut, http.MethodDelete, http.MethodOptions, http.MethodHead},
			AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-CSRF-Token", "X-MCP-Progress-Token"},
			ExposedHeaders:   []string{"Link"},
			AllowCredentials: true,
			MaxAge:           300,
		})
		// Order: CORS outermost (so preflight OPTIONS still work), then the
		// auth gate, then the MCP handler.
		handler := c.Handler(authCfg.middleware(mcpHTTPHandler))
		listenAddr := fmt.Sprintf(":%d", httpPort)
		if err := http.ListenAndServe(listenAddr, handler); err != nil {
			log.Fatalf("HTTP Server error: %v", err)
		}
	case "stdio":
		log.Printf("Starting AV Compositing Tool (avtool) MCP Server (Version: %s, Transport: stdio)", version)
		if err := server.ServeStdio(s); err != nil {
			log.Fatalf("STDIO Server error: %v", err)
		}
	default:
		log.Fatalf("Unsupported transport type '%s' specified. Please use 'stdio', 'http', or 'sse'.", transport)
	}
	log.Println("AV Compositing Tool (avtool) Server has stopped.")
}

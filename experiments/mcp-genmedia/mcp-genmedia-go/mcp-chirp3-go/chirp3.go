// Package main implements an MCP server for Google's Chirp3 text-to-speech models.

package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	texttospeech "cloud.google.com/go/texttospeech/apiv1"
	"cloud.google.com/go/texttospeech/apiv1/texttospeechpb"
	"github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
	"github.com/rs/cors"
	"golang.org/x/text/cases"
	"golang.org/x/text/language"
	"google.golang.org/api/option"
)

var (
	ttsClient       *texttospeech.Client // Global Text-to-Speech client
	availableVoices []*texttospeechpb.Voice
	transport       string
	port            int
	// version is overridden at build time via -ldflags "-X main.version=...".
	// Single source of truth is the VERSION file at the root of the
	// mcp-genmedia-go tree. Defaults to "dev" for un-injected builds.
	version = "dev"

	// writeFileFn is the local-file-write seam. It is a package-level variable so
	// the handler's naming/collision wiring is unit-testable without touching the
	// real filesystem — mirroring the writeFileFn indirection in mcp-gemini-go.
	writeFileFn = os.WriteFile
)

const (
	serviceName           = "mcp-chirp3-go"
	timeFormatForFilename = "20060102-150405"
	defaultChirpVoiceName = "en-US-Chirp3-HD-Zephyr"
)

// validChirpRegions maps the supported Chirp3-HD regions to a boolean for quick validation.
var validChirpRegions = map[string]bool{
	"global":          true,
	"us":              true,
	"eu":              true,
	"asia-southeast1": true,
	"europe-west2":    true,
	"asia-northeast1": true,
}

// LanguageNameToCodeMap maps descriptive language names (lowercase) to BCP-47 codes (canonical casing).
var LanguageNameToCodeMap = map[string]string{
	"german (germany)":         "de-DE",
	"english (australia)":      "en-AU",
	"english (united kingdom)": "en-GB",
	"english (india)":          "en-IN",
	"english (united states)":  "en-US",
	"spanish (united states)":  "es-US",
	"french (france)":          "fr-FR",
	"hindi (india)":            "hi-IN",
	"portuguese (brazil)":      "pt-BR",
	"arabic (generic)":         "ar-XA",
	"spanish (spain)":          "es-ES",
	"french (canada)":          "fr-CA",
	"indonesian (indonesia)":   "id-ID",
	"italian (italy)":          "it-IT",
	"japanese (japan)":         "ja-JP",
	"turkish (turkey)":         "tr-TR",
	"vietnamese (vietnam)":     "vi-VN",
	"bengali (india)":          "bn-IN",
	"gujarati (india)":         "gu-IN",
	"kannada (india)":          "kn-IN",
	"malayalam (india)":        "ml-IN",
	"marathi (india)":          "mr-IN",
	"tamil (india)":            "ta-IN",
	"telugu (india)":           "te-IN",
	"dutch (netherlands)":      "nl-NL",
	"korean (south korea)":     "ko-KR",
	"mandarin chinese (china)": "cmn-CN",
	"polish (poland)":          "pl-PL",
	"russian (russia)":         "ru-RU",
	"thai (thailand)":          "th-TH",
}

// OriginalLanguageNames is used to get the original casing for display in disambiguation messages.
var OriginalLanguageNames = make(map[string]string) // map[lowercase_name]Original_Cased_Name

func init() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)
	flag.StringVar(&transport, "t", "stdio", "Transport type (stdio, sse, or http)")
	flag.StringVar(&transport, "transport", "stdio", "Transport type (stdio, sse, or http)")
	flag.IntVar(&port, "p", 0, "Port for SSE/HTTP server (defaults to PORT env var or 8080/8081)")
	flag.IntVar(&port, "port", 0, "Port for SSE/HTTP server (defaults to PORT env var or 8080/8081)")

	titleCaser := cases.Title(language.Und)
	for k := range LanguageNameToCodeMap {
		OriginalLanguageNames[k] = titleCaser.String(k)
	}
}

// getChirpClientOptions determines the appropriate endpoint option based on the configured Location.
func getChirpClientOptions(location string) []option.ClientOption {
	var opts []option.ClientOption

	loc := strings.ToLower(strings.TrimSpace(location))

	// Handle the default us-central1 fallback gracefully
	if loc == "us-central1" {
		log.Printf("Warning: 'us-central1' is not a supported region for Chirp3-HD. Automatically mapping to 'us'.")
		loc = "us"
	}

	if !validChirpRegions[loc] {
		log.Printf("Warning: Unsupported Chirp3-HD region '%s'. Falling back to 'global'. Supported regions: global, us, eu, asia-southeast1, europe-west2, asia-northeast1", loc)
		loc = "global"
	}

	if loc != "global" {
		endpoint := fmt.Sprintf("%s-texttospeech.googleapis.com:443", loc)
		log.Printf("Routing Chirp API calls to regional endpoint: %s", endpoint)
		opts = append(opts, option.WithEndpoint(endpoint))
	} else {
		log.Printf("Routing Chirp API calls to global endpoint.")
	}

	return opts
}

// listAndCacheChirpHDVoices fetches the list of available voices from the
// Google Cloud Text-to-Speech API and caches those that are identified as
// Chirp3-HD voices. This cached list is used by other functions to validate
// voice selections and provide voice options.
func listAndCacheChirpHDVoices(ctx context.Context, location string) error {
	log.Println("Fetching available Chirp3-HD voices...")

	opts := getChirpClientOptions(location)
	tempClient, err := texttospeech.NewClient(ctx, opts...)
	if err != nil {
		return fmt.Errorf("texttospeech.NewClient for voice listing: %w", err)
	}
	defer func() { _ = tempClient.Close() }()

	resp, err := tempClient.ListVoices(ctx, &texttospeechpb.ListVoicesRequest{})
	if err != nil {
		return fmt.Errorf("ListVoices: %w", err)
	}

	var foundVoices []*texttospeechpb.Voice
	for _, voice := range resp.Voices {
		if strings.Contains(voice.Name, "Chirp3-HD") {
			foundVoices = append(foundVoices, voice)
		}
	}
	availableVoices = foundVoices

	if len(availableVoices) == 0 {
		log.Println("Warning: No Chirp3-HD voices found. TTS functionality might be limited.")
	} else {
		log.Printf("Found and cached %d Chirp3-HD voices.", len(availableVoices))
	}
	return nil
}

// parseMcpPronunciations processes custom pronunciation parameters provided in an MCP request.
// It takes the raw `pronunciations` parameter (expected as an array of strings)
// and an encoding string ('ipa' or 'xsampa'). Each string in the array should be in
// the format 'phrase:phonetic_form'. The function validates the inputs and converts
// them into the appropriate protobuf message structure required by the Text-to-Speech API.
func parseMcpPronunciations(pronunciationsParam interface{}, encodingStr string) (*texttospeechpb.CustomPronunciations, error) {
	if pronunciationsParam == nil {
		return nil, nil // No pronunciations provided
	}

	pronunciationItems, ok := pronunciationsParam.([]interface{})
	if !ok {
		return nil, fmt.Errorf("pronunciations parameter is not a valid array, got %T", pronunciationsParam)
	}

	if len(pronunciationItems) == 0 {
		return nil, nil
	}

	var encodingType texttospeechpb.CustomPronunciationParams_PhoneticEncoding
	switch strings.ToLower(encodingStr) {
	case "ipa":
		encodingType = texttospeechpb.CustomPronunciationParams_PHONETIC_ENCODING_IPA
	case "xsampa", "x-sampa": // Allow for x-sampa as well
		encodingType = texttospeechpb.CustomPronunciationParams_PHONETIC_ENCODING_X_SAMPA
	default:
		return nil, fmt.Errorf("unsupported pronunciation_encoding: %s. Must be 'ipa' or 'xsampa'", encodingStr)
	}

	var parsedParams []*texttospeechpb.CustomPronunciationParams
	for i, item := range pronunciationItems {
		entryStr, ok := item.(string)
		if !ok {
			return nil, fmt.Errorf("pronunciation item at index %d is not a string, got %T", i, item)
		}

		trimmedEntry := strings.TrimSpace(entryStr)
		if trimmedEntry == "" {
			continue
		}
		parts := strings.SplitN(trimmedEntry, ":", 2)
		if len(parts) != 2 {
			return nil, fmt.Errorf("malformed pronunciation entry at index %d: %q. Expected format 'phrase:pronunciation'", i, trimmedEntry)
		}
		phrase := strings.TrimSpace(parts[0])
		pronunciation := strings.TrimSpace(parts[1])

		if phrase == "" || pronunciation == "" {
			return nil, fmt.Errorf("empty phrase or pronunciation in entry at index %d: %q", i, trimmedEntry)
		}

		params := &texttospeechpb.CustomPronunciationParams{
			Phrase:           &phrase,
			Pronunciation:    &pronunciation,
			PhoneticEncoding: &encodingType,
		}
		parsedParams = append(parsedParams, params)
	}

	if len(parsedParams) == 0 {
		return nil, nil
	}

	return &texttospeechpb.CustomPronunciations{
		Pronunciations: parsedParams,
	}, nil
}

// main is the entry point for the mcp-chirp3-go service.
// It initializes the OpenTelemetry provider, the Google Cloud Text-to-Speech client,
// and caches the available Chirp3-HD voices. It then sets up an MCP server, registers
// the 'chirp_tts' and 'list_chirp_voices' tools, and starts listening for requests
// on the configured transport (stdio, sse, or http).
func main() {
	flag.Parse() // Parse in main (not init) so `go test` flags are not consumed; matches sibling servers.

	// Initialize OpenTelemetry
	var cleanup func()
	_, cleanup = common.Init(serviceName, version)
	defer cleanup()
	log.Printf("Initializing global Text-to-Speech client... (Deferred to runtime)")
	// In order to allow mcptools to verify the schema without Google Cloud credentials,
	// we defer the actual client initialization to the first tool invocation.

	s := server.NewMCPServer(
		serviceName, // Standardized name
		version,
	)

	chirpTool := mcp.NewTool("chirp_tts",
		mcp.WithDescription("Synthesizes speech from text using Google Cloud TTS with Chirp3-HD voices. Returns audio data and optionally saves it locally."),
		mcp.WithString("text",
			mcp.Required(),
			mcp.Description("The text to synthesize into speech."),
		),
		mcp.WithString("voice_name",
			mcp.Description(fmt.Sprintf("Optional. The specific Chirp3-HD voice name to use (e.g., '%s'). If not provided, defaults to '%s' if available, otherwise the first available Chirp3-HD voice.", defaultChirpVoiceName, defaultChirpVoiceName)),
		),
		mcp.WithString("output_filename",
			mcp.Description("Optional. Client-predictable base name for the saved audio file. The extension is forced to the true audio media type (.wav). Used as-is for a single file (e.g. 'greeting.wav'); multiple artifacts are suffixed '_1', '_2', ... before the extension. Takes precedence over the deprecated output_filename_prefix. An existing file of the same name is overwritten."),
		),
		mcp.WithString("output_filename_prefix",
			mcp.DefaultString("chirp_audio"),
			mcp.Description("Optional (deprecated; use output_filename). A prefix for the output WAV filename if saving locally. A voice name, timestamp and .wav extension will be appended."),
		),
		mcp.WithString("output_directory",
			mcp.Description("Optional. If provided, specifies a local directory to save the generated audio file to. Filenames will be generated automatically using the prefix. If not provided, audio data is returned in the response."),
		),
		mcp.WithArray("pronunciations", // New array parameter for pronunciations
			mcp.Description("Optional. An array of custom pronunciations. Each item should be a string in the format 'phrase:phonetic_representation' (e.g., 'tomato:təˈmeɪtoʊ'). All items must use the same encoding specified by 'pronunciation_encoding'."),
			mcp.Items(map[string]any{"type": "string"}), // Specify that array items are strings
		),
		mcp.WithString("pronunciation_encoding", // New string parameter for encoding type
			mcp.DefaultString("ipa"), // Default to IPA
			mcp.Description("Optional. The phonetic encoding used for the 'pronunciations' array. Can be 'ipa' or 'xsampa'. Defaults to 'ipa'."),
			mcp.Enum("ipa", "xsampa"), // Specify allowed values
		),
	)
	s.AddTool(chirpTool, func(toolCtx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		if ttsClient == nil {
			log.Printf("Initializing global Text-to-Speech client...")
			cfg := common.LoadConfig(serviceName)
			opts := getChirpClientOptions(cfg.Location)
			client, err := texttospeech.NewClient(context.Background(), opts...)
			if err != nil {
				return nil, fmt.Errorf("failed to initialize Text-to-Speech client: %w", err)
			}
			ttsClient = client

			if len(availableVoices) == 0 {
				if err := listAndCacheChirpHDVoices(context.Background(), cfg.Location); err != nil {
					log.Printf("Warning: Failed to fetch voices during initialization: %v", err)
				}
			}
		}

		return chirpTTSHandler(ttsClient, toolCtx, request)
	})

	listVoicesTool := mcp.NewTool("list_chirp_voices",
		mcp.WithDescription("Lists Chirp3-HD voices, filtered by the provided language (either descriptive name or BCP-47 code)."),
		mcp.WithString("language",
			mcp.Required(),
			mcp.Description("The language to filter voices by. Can be a descriptive name (e.g., 'English (United States)') or a BCP-47 code (e.g., 'en-US')."),
		),
	)
	s.AddTool(listVoicesTool, func(toolCtx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		if ttsClient == nil {
			log.Printf("Initializing global Text-to-Speech client for list voices...")
			cfg := common.LoadConfig(serviceName)
			opts := getChirpClientOptions(cfg.Location)
			client, err := texttospeech.NewClient(context.Background(), opts...)
			if err != nil {
				return nil, fmt.Errorf("failed to initialize Text-to-Speech client: %w", err)
			}
			ttsClient = client

			if len(availableVoices) == 0 {
				if err := listAndCacheChirpHDVoices(context.Background(), cfg.Location); err != nil {
					log.Printf("Warning: Failed to fetch voices during initialization: %v", err)
				}
			}
		}

		return listChirpVoicesHandler(toolCtx, request)
	})

	// Add the new list-voices prompt
	s.AddPrompt(mcp.NewPrompt("list-voices",
		mcp.WithPromptDescription("Lists available Chirp3-HD voices, with an option to filter by language."),
		mcp.WithArgument("language",
			mcp.ArgumentDescription("Optional. The language to filter voices by (e.g., 'English (United States)', 'en-US')."),
		),
	), func(ctx context.Context, request mcp.GetPromptRequest) (*mcp.GetPromptResult, error) {
		if ttsClient == nil {
			log.Printf("Initializing global Text-to-Speech client for prompt...")
			cfg := common.LoadConfig(serviceName)
			opts := getChirpClientOptions(cfg.Location)
			client, err := texttospeech.NewClient(context.Background(), opts...)
			if err != nil {
				return nil, fmt.Errorf("failed to initialize Text-to-Speech client: %w", err)
			}
			ttsClient = client

			if len(availableVoices) == 0 {
				if err := listAndCacheChirpHDVoices(context.Background(), cfg.Location); err != nil {
					log.Printf("Warning: Failed to fetch voices during initialization: %v", err)
				}
			}
		}

		languageParam, langProvided := request.Params.Arguments["language"]
		if !langProvided || strings.TrimSpace(languageParam) == "" {
			// If no language is provided, ask the user to specify one.
			return mcp.NewGetPromptResult(
				"Specify Language",
				[]mcp.PromptMessage{
					mcp.NewPromptMessage(
						mcp.RoleAssistant,
						mcp.NewTextContent("What language would you like to list the voices for? You can see available languages by using the resource 'chirp://language_codes'"),
					),
				},
			), nil
		}

		summary, jsonData, err := getFilteredVoices(languageParam)
		if err != nil {
			return mcp.NewGetPromptResult(
				"Error",
				[]mcp.PromptMessage{
					mcp.NewPromptMessage(
						mcp.RoleAssistant,
						mcp.NewTextContent(err.Error()),
					),
				},
			), nil
		}

		return mcp.NewGetPromptResult(
			"Voice List",
			[]mcp.PromptMessage{
				mcp.NewPromptMessage(
					mcp.RoleAssistant,
					mcp.NewTextContent(summary+"\n"+jsonData),
				),
			},
		), nil
	})

	// Add the language codes resource
	s.AddResource(mcp.NewResource(
		"chirp://language_codes",
		"Chirp Language Codes",
		mcp.WithResourceDescription("A list of supported languages and their BCP-47 codes."),
		mcp.WithMIMEType("application/json"),
	), func(ctx context.Context, request mcp.ReadResourceRequest) ([]mcp.ResourceContents, error) {
		jsonData, err := json.MarshalIndent(LanguageNameToCodeMap, "", "  ")
		if err != nil {
			return nil, fmt.Errorf("failed to marshal language codes: %w", err)
		}
		return []mcp.ResourceContents{
			mcp.TextResourceContents{
				URI:      "chirp://language_codes",
				MIMEType: "application/json",
				Text:     string(jsonData),
			},
		}, nil
	})

	switch transport {
	case "sse":
		ssePort := 8081 // Default SSE port
		if port != 0 {
			ssePort = port
		} else if p, err := strconv.Atoi(common.GetEnv("PORT", "")); err == nil {
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
		} else if p, err := strconv.Atoi(common.GetEnv("PORT", "")); err == nil {
			httpPort = p
		}
		log.Printf("Starting %s MCP Server (Version: %s, Transport: http, Port: %d)", serviceName, version, httpPort)
		mcpHTTPHandler := server.NewStreamableHTTPServer(s) // Base path /mcp
		c := cors.New(cors.Options{
			AllowedOrigins:   []string{"*"},
			AllowedMethods:   []string{http.MethodGet, http.MethodPost, http.MethodPut, http.MethodDelete, http.MethodOptions, http.MethodHead},
			AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-CSRF-Token", "X-MCP-Progress-Token"},
			ExposedHeaders:   []string{"Link"},
			AllowCredentials: true,
			MaxAge:           300,
		})
		handlerWithCORS := c.Handler(mcpHTTPHandler)
		listenAddr := fmt.Sprintf(":%d", httpPort)
		if err := http.ListenAndServe(listenAddr, handlerWithCORS); err != nil {
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

	log.Printf("%s Server has stopped.", serviceName)
	if ttsClient != nil {
		_ = ttsClient.Close()
	}
}

// chirpTTSHandler is the core logic for the 'chirp_tts' tool.
// It handles requests to synthesize speech from text. The function extracts parameters
// from the request, selects an appropriate voice, and calls the Text-to-Speech API.
// It can save the resulting audio to a local file or return it directly in the
// response as base64-encoded data.
// chirpAudioMIMEType is the true media type chirp3 always emits (LINEAR16 WAV).
const chirpAudioMIMEType = "audio/wav"

// resolveChirpOutputFilename decides the saved audio filename. The canonical
// output_filename wins over the deprecated output_filename_prefix:
// when set, it yields a client-predictable base name with the extension forced to
// the true audio MIME — a single artifact is used as-is (<stem>.wav),
// multiple would be suffixed _1..n by the shared helper. When only the legacy
// prefix (or neither) is provided, the historical <prefix>-<voice>-<timestamp>.wav
// scheme is preserved byte-for-byte.
func resolveChirpOutputFilename(args map[string]any, voiceName string) (string, error) {
	if base := common.ResolveOutputFilename(args); base != "" {
		names, err := common.BuildOutputFilenames(base, 1, chirpAudioMIMEType)
		if err != nil {
			return "", err
		}
		return names[0], nil
	}
	prefix, _ := args["output_filename_prefix"].(string)
	if strings.TrimSpace(prefix) == "" {
		prefix = "chirp_audio"
	}
	safeVoiceName := strings.ReplaceAll(voiceName, "/", "_")
	safeVoiceName = strings.ReplaceAll(safeVoiceName, ":", "_")
	return fmt.Sprintf("%s-%s-%s.wav", prefix, safeVoiceName, time.Now().Format(timeFormatForFilename)), nil
}

// saveChirpAudio wires the resolved output_filename through to the local file
// write: it resolves the client-predictable name (via
// resolveChirpOutputFilename), joins it under outputDir, applies the
// collision-overwrite warning, and writes the bytes through the injectable
// writeFileFn seam. It returns the cleaned saved path. A name-resolution failure is
// returned as nameErr (fatal to the caller); a write failure as writeErr (the
// caller falls back to returning the audio inline). Splitting the two errors
// mirrors the handler's original behavior.
func saveChirpAudio(args map[string]any, audioBytes []byte, outputDir, voiceName string) (savedFilename string, nameErr, writeErr error) {
	genFilename, err := resolveChirpOutputFilename(args, voiceName)
	if err != nil {
		return "", err, nil
	}
	// Confine the caller-supplied output directory to the configured output root
	// before creating it or writing into it (CWE-22 directory traversal). filepath.Clean
	// alone does NOT confine (it neither strips a leading "/" nor prevents ".." from
	// escaping), so it is replaced by ResolveConfinedOutputDir. A traversal attempt is
	// fatal (nameErr); a directory creation failure is non-fatal (writeErr).
	confinedDir, confErr := common.ResolveConfinedOutputDir(outputDir)
	if confErr != nil {
		return "", confErr, nil
	}
	if mkErr := os.MkdirAll(confinedDir, 0755); mkErr != nil {
		return "", nil, mkErr
	}
	savedFilename = filepath.Join(confinedDir, genFilename)
	// Collision policy: overwrite with a warning.
	if _, statErr := os.Stat(savedFilename); statErr == nil {
		log.Printf("Warning: output file %q already exists in %s; overwriting (collision policy).", genFilename, outputDir)
	}
	if werr := writeFileFn(savedFilename, audioBytes, 0644); werr != nil {
		return savedFilename, nil, werr
	}
	return savedFilename, nil, nil
}

func chirpTTSHandler(client *texttospeech.Client, ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	var contentItems []mcp.Content

	if err := ctx.Err(); err != nil {
		log.Printf("chirpTTSHandler: Incoming context (ctx) is already canceled or has an error upon entry: %v. Will attempt to proceed with TTS using a background context.", err)
	} else {
		log.Printf("chirpTTSHandler: Incoming context (ctx) is active upon entry.")
	}

	log.Printf("Handling chirp_tts request with arguments: %v", request.GetArguments())

	text, ok := request.GetArguments()["text"].(string)
	if !ok || strings.TrimSpace(text) == "" {
		errMsg := "text parameter must be a non-empty string and is required"
		contentItems = append(contentItems, mcp.TextContent{Type: "text", Text: errMsg})
		return &mcp.CallToolResult{Content: contentItems}, nil
	}

	// Handle custom pronunciations
	pronunciationsParam := request.GetArguments()["pronunciations"] // This will be []interface{} or nil
	pronunciationEncodingStr, _ := request.GetArguments()["pronunciation_encoding"].(string)
	if pronunciationEncodingStr == "" { // Apply default if not provided
		pronunciationEncodingStr = "ipa"
	}

	customPronos, err := parseMcpPronunciations(pronunciationsParam, pronunciationEncodingStr)
	if err != nil {
		errMsg := fmt.Sprintf("Error parsing custom pronunciations: %v", err)
		log.Print(errMsg)
		contentItems = append(contentItems, mcp.TextContent{Type: "text", Text: errMsg})
		return &mcp.CallToolResult{Content: contentItems}, nil
	}
	if customPronos != nil {
		log.Printf("Applying %d custom pronunciations with %s encoding.", len(customPronos.Pronunciations), pronunciationEncodingStr)
	}

	var selectedVoice *texttospeechpb.Voice
	voiceNameParam, voiceNameProvided := request.GetArguments()["voice_name"].(string)

	if voiceNameProvided && strings.TrimSpace(voiceNameParam) != "" {
		voiceNameParam = strings.TrimSpace(voiceNameParam)
		found := false
		for _, v := range availableVoices {
			if v.Name == voiceNameParam {
				selectedVoice = v
				found = true
				break
			}
		}
		if !found {
			log.Printf("Requested voice_name '%s' not found among available Chirp3-HD voices. Attempting default.", voiceNameParam)
		} else {
			log.Printf("Using requested voice: %s", selectedVoice.Name)
		}
	}

	if selectedVoice == nil {
		for _, v := range availableVoices {
			if v.Name == defaultChirpVoiceName {
				selectedVoice = v
				log.Printf("Voice_name not provided or invalid/not found. Defaulting to preferred voice: %s", selectedVoice.Name)
				break
			}
		}
		if selectedVoice == nil && len(availableVoices) > 0 {
			selectedVoice = availableVoices[0]
			log.Printf("Preferred default voice '%s' not found. Defaulting to first available Chirp3-HD voice: %s", defaultChirpVoiceName, selectedVoice.Name)
		} else if selectedVoice == nil {
			errMsg := "No Chirp3-HD voices available for synthesis. Please check server logs for voice fetching issues at startup."
			log.Println("Error: " + errMsg)
			contentItems = append(contentItems, mcp.TextContent{Type: "text", Text: errMsg})
			return &mcp.CallToolResult{Content: contentItems}, nil
		}
	}

	outputDir := ""
	if dir, ok := request.GetArguments()["output_directory"].(string); ok && strings.TrimSpace(dir) != "" {
		outputDir = strings.TrimSpace(dir)
	}
	attemptLocalSave := outputDir != ""
	log.Printf("Output directory: '%s', Attempt local save: %t", outputDir, attemptLocalSave)

	synthesisAPICallCtx, synthesisAPICallCancel := context.WithTimeout(ctx, 30*time.Second)
	defer synthesisAPICallCancel()

	log.Printf("Synthesizing speech for text: \"%s\" with voice: %s. API call using independent context with timeout: 30s", text, selectedVoice.Name)
	// Pass customPronos to synthesizeWithVoice
	audioContentBytes, err := synthesizeWithVoice(synthesisAPICallCtx, client, selectedVoice, text, customPronos)

	if err != nil {
		errMsg := fmt.Sprintf("Error synthesizing speech: %v", err)
		log.Print(errMsg)
		if errors.Is(err, context.DeadlineExceeded) && synthesisAPICallCtx.Err() == context.DeadlineExceeded {
			errMsg = "Speech synthesis API call timed out."
			log.Printf("SynthesizeSpeech call timed out after 30 seconds (independent synthesisAPICallCtx).")
		} else if errors.Is(err, context.Canceled) && synthesisAPICallCtx.Err() == context.Canceled {
			errMsg = "Speech synthesis API call was canceled."
			log.Printf("SynthesizeSpeech call canceled (independent synthesisAPICallCtx).")
		}
		contentItems = append(contentItems, mcp.TextContent{Type: "text", Text: errMsg})
		return &mcp.CallToolResult{Content: contentItems}, nil
	}

	if len(audioContentBytes) == 0 {
		errMsg := fmt.Sprintf("Synthesized audio is empty for voice %s.", selectedVoice.Name)
		log.Print(errMsg)
		contentItems = append(contentItems, mcp.TextContent{Type: "text", Text: errMsg})
		return &mcp.CallToolResult{Content: contentItems}, nil
	}

	var fileSaveMessage string
	var savedFilename string

	if attemptLocalSave {
		// Directory confinement + creation now happen inside saveChirpAudio so the
		// caller-supplied directory is validated before any filesystem write.
		savedName, nameErr, writeErr := saveChirpAudio(request.GetArguments(), audioContentBytes, outputDir, selectedVoice.Name)
		if nameErr != nil {
			return mcp.NewToolResultError(nameErr.Error()), nil
		}
		if writeErr != nil {
			fileSaveMessage = fmt.Sprintf("Error writing audio file %s: %v. Audio data will be returned in response instead.", savedName, writeErr)
			log.Print(fileSaveMessage)
			base64AudioData := base64.StdEncoding.EncodeToString(audioContentBytes)
			audioItem := mcp.AudioContent{Type: "audio", Data: base64AudioData, MIMEType: "audio/wav"}
			contentItems = append(contentItems, audioItem)
			savedFilename = ""
		} else {
			savedFilename = savedName
			fileSaveMessage = fmt.Sprintf("Audio saved to: %s (%d bytes).", savedName, len(audioContentBytes))
			log.Printf("Audio content (%d bytes) written to file: %s", len(audioContentBytes), savedName)
		}
	} else {
		base64AudioData := base64.StdEncoding.EncodeToString(audioContentBytes)
		audioItem := mcp.AudioContent{Type: "audio", Data: base64AudioData, MIMEType: "audio/wav"}
		contentItems = append(contentItems, audioItem)
		fileSaveMessage = "Audio data is included in the response."
	}

	resultText := fmt.Sprintf("Speech synthesized successfully with voice %s. %s",
		selectedVoice.Name,
		fileSaveMessage,
	)
	textItem := mcp.TextContent{Type: "text", Text: strings.TrimSpace(resultText)}

	finalContentItems := []mcp.Content{textItem}
	// Only append audio to finalContentItems if it's meant to be returned in the response
	if !attemptLocalSave || (attemptLocalSave && savedFilename == "") {
		// Find the audioItem in contentItems (it should be the only one if it exists)
		for _, item := range contentItems {
			if _, ok := item.(mcp.AudioContent); ok {
				finalContentItems = append(finalContentItems, item)
				break
			}
		}
	}

	return &mcp.CallToolResult{Content: finalContentItems}, nil
}

// synthesizeWithVoice encapsulates the call to the Google Cloud Text-to-Speech API.
// It constructs the synthesis request with the specified voice, text, and custom pronunciations,
// sends it to the API, and returns the raw audio content as a byte slice.
func synthesizeWithVoice(ctx context.Context, client *texttospeech.Client, voice *texttospeechpb.Voice, textToSynthesize string, customPronos *texttospeechpb.CustomPronunciations) ([]byte, error) {
	req := texttospeechpb.SynthesizeSpeechRequest{
		Input: &texttospeechpb.SynthesisInput{
			InputSource:          &texttospeechpb.SynthesisInput_Text{Text: textToSynthesize},
			CustomPronunciations: customPronos, // Set custom pronunciations here
		},
		Voice: &texttospeechpb.VoiceSelectionParams{
			LanguageCode: voice.GetLanguageCodes()[0],
			Name:         voice.GetName(),
		},
		AudioConfig: &texttospeechpb.AudioConfig{
			AudioEncoding: texttospeechpb.AudioEncoding_LINEAR16, // WAV format
		},
	}

	resp, err := client.SynthesizeSpeech(ctx, &req)
	if err != nil {
		return nil, fmt.Errorf("SynthesizeSpeech: %w", err)
	}
	return resp.AudioContent, nil
}

type VoiceInfo struct {
	Name         string `json:"name"`
	LanguageCode string `json:"language_code"`
	Gender       string `json:"gender"`
}

func getFilteredVoices(languageQuery string) (string, string, error) {
	if strings.TrimSpace(languageQuery) == "" {
		return "", "", errors.New("language query must not be empty")
	}

	normalizedInput := strings.ToLower(strings.TrimSpace(languageQuery))
	var targetLangCode string
	var directlyResolved bool

	bcp47Code, isNameMatch := LanguageNameToCodeMap[normalizedInput]
	if isNameMatch {
		targetLangCode = bcp47Code
		directlyResolved = true
	} else {
		for _, codeInMap := range LanguageNameToCodeMap {
			if strings.ToLower(codeInMap) == normalizedInput {
				targetLangCode = codeInMap
				directlyResolved = true
				break
			}
		}
	}

	if !directlyResolved {
		potentialMatches := make(map[string]bool)
		for lcNameKey, originalCasedName := range OriginalLanguageNames {
			bcp47ForThisName := LanguageNameToCodeMap[lcNameKey]
			if strings.Contains(lcNameKey, normalizedInput) || strings.Contains(strings.ToLower(bcp47ForThisName), normalizedInput) {
				potentialMatches[originalCasedName] = true
			}
		}

		if len(potentialMatches) == 0 {
			return "", "", fmt.Errorf("unsupported language query: '%s'. No matching language names or BCP-47 codes found", languageQuery)
		}

		if len(potentialMatches) > 1 {
			var displayNames []string
			for name := range potentialMatches {
				displayNames = append(displayNames, name)
			}
			sort.Strings(displayNames)
			return "", "", fmt.Errorf("your language query '%s' is ambiguous. Please be more specific by choosing one of the following: %s", languageQuery, strings.Join(displayNames, ", "))
		}

		for name := range potentialMatches {
			targetLangCode = LanguageNameToCodeMap[strings.ToLower(name)]
		}
	}

	if len(availableVoices) == 0 {
		return "", "", errors.New("no Chirp3-HD voices are currently available or cached")
	}

	var filteredVoiceInfos []VoiceInfo
	var voiceNameSuffixes []string
	filterLangCodeNormalized := strings.ToLower(targetLangCode)

	for _, v := range availableVoices {
		voiceMatches := false
		for _, lc := range v.GetLanguageCodes() {
			if strings.ToLower(lc) == filterLangCodeNormalized {
				voiceMatches = true
				break
			}
		}
		if voiceMatches {
			var primaryLangCode string
			if len(v.GetLanguageCodes()) > 0 {
				primaryLangCode = v.GetLanguageCodes()[0]
			}
			info := VoiceInfo{
				Name:         v.GetName(),
				LanguageCode: primaryLangCode,
				Gender:       v.GetSsmlGender().String(),
			}
			filteredVoiceInfos = append(filteredVoiceInfos, info)

			nameSuffix := v.GetName()
			if primaryLangCode != "" {
				expectedPrefix := strings.ToLower(primaryLangCode) + "-chirp3-hd-"
				if strings.HasPrefix(strings.ToLower(v.GetName()), expectedPrefix) {
					potentialSuffix := v.GetName()[len(expectedPrefix):]
					if potentialSuffix != "" {
						nameSuffix = potentialSuffix
					}
				}
			}
			voiceNameSuffixes = append(voiceNameSuffixes, nameSuffix)
		}
	}

	if len(filteredVoiceInfos) == 0 {
		return "", "", fmt.Errorf("no Chirp3-HD voices found for the specified language filter: '%s' (resolved to %s)", languageQuery, targetLangCode)
	}

	sort.Strings(voiceNameSuffixes)

	summaryText := fmt.Sprintf("I've resolved your request for '%s' to the language code '%s'. Found %d voice(s): %s",
		languageQuery,
		targetLangCode,
		len(filteredVoiceInfos),
		strings.Join(voiceNameSuffixes, ", "),
	)

	jsonData, err := json.MarshalIndent(filteredVoiceInfos, "", "  ")
	if err != nil {
		return "", "", fmt.Errorf("error marshalling filtered voice list to JSON: %w", err)
	}

	return summaryText, string(jsonData), nil
}

func listChirpVoicesHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	if err := ctx.Err(); err != nil {
		log.Printf("listChirpVoicesHandler: Incoming context (ctx) is already canceled or has an error upon entry: %v. Attempting to proceed with listing.", err)
	} else {
		log.Printf("listChirpVoicesHandler: Incoming context (ctx) is active upon entry.")
	}
	log.Println("Handling list_chirp_voices request.")

	languageParam, langProvided := request.GetArguments()["language"].(string)
	if !langProvided || strings.TrimSpace(languageParam) == "" {
		return mcp.NewToolResultError("'language' parameter must be provided and non-empty."), nil
	}

	summary, jsonData, err := getFilteredVoices(languageParam)
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}

	return &mcp.CallToolResult{
		Content: []mcp.Content{
			mcp.TextContent{
				Type: "text",
				Text: summary,
			},
			mcp.TextContent{
				Type: "text",
				Text: jsonData,
			},
		},
	}, nil
}

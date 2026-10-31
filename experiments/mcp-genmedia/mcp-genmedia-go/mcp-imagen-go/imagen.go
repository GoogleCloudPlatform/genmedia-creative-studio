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

// Package main implements an MCP server for Google's Imagen models.

package main

import (
	"context"
	"encoding/base64"
	"errors"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
	"github.com/rs/cors"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"google.golang.org/genai"
)

var (
	appConfig   *common.Config
	genAIClient *genai.Client // Global GenAI client
	transport   string
	port        int
)

const (
	serviceName = "mcp-imagen-go"
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

// main is the entry point for the mcp-imagen-go service.
func main() {
	// Parse flags here (not in init) so `go test` flags are not consumed at
	// package init, matching the sibling genmedia servers.
	flag.Parse()

	var cleanup func()
	appConfig, cleanup = common.Init(serviceName, version)
	defer cleanup()
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

	s := server.NewMCPServer("Imagen", version, server.WithResourceCapabilities(true, true))
	registerImagenEditingTools(s, genAIClient, appConfig)

	s.AddResource(mcp.NewResource(
		"imagen://models",
		"Supported Imagen Models",
		mcp.WithResourceDescription("A machine-readable capability matrix of supported Imagen models, aliases, max images, aspect ratios, and image sizes."),
		mcp.WithMIMEType("application/json"),
	), func(ctx context.Context, request mcp.ReadResourceRequest) ([]mcp.ResourceContents, error) {
		return common.MarshalModelsResource("imagen://models", common.SupportedImagenModels)
	})

	tool := mcp.NewTool("imagen_t2i",
		mcp.WithDescription("Generates an image based on a text prompt using Google's Imagen models. The image can be returned as base64 data, saved to a local directory, or stored in a Google Cloud Storage bucket."),
		mcp.WithString("prompt", mcp.Required(), mcp.Description("Prompt for text to image generation")),
		mcp.WithString("model",
			mcp.DefaultString("imagen-4.0-fast-generate-001"),
			mcp.Description(common.BuildImagenModelDescription()),
		),
		mcp.WithNumber("num_images",
			mcp.DefaultNumber(1),
			mcp.Min(1),
			mcp.Max(4),
			mcp.Description("Number of images to generate (1-4). Note: the maximum is model-dependent."),
		),
		mcp.WithString("aspect_ratio",
			mcp.DefaultString("1:1"),
			mcp.Description("Aspect ratio of the generated images (e.g., \"1:1\", \"16:9\", \"9:16\")."),
		),
		mcp.WithString("image_size",
			mcp.DefaultString("1K"),
			mcp.Description("Optional. The size of the largest dimension of the generated image. Supported sizes are 1K and 2K (not supported for Imagen 3 models)."),
		),
		mcp.WithString("gcs_bucket_uri", mcp.Description("Optional. GCS URI prefix to store the generated images (e.g., your-bucket/outputs/ or gs://your-bucket/outputs/).")),
		mcp.WithString("output_directory", mcp.Description("Optional. Local directory to save the generated image(s) to.")),
		mcp.WithString("output_filename", mcp.Description("Optional. Base name for the output file(s). The extension is forced to the true image type (e.g. .png). For a single image the name is used as-is (foo.png); for multiple images a 1-based suffix is inserted before the extension (foo_1.png, foo_2.png, ...). For GCS output the API-written objects are copy-renamed to this name after generation (adds a short GCS copy latency).")),
	)

	handlerWithClient := func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		return imagenGenerationHandler(genAIClient, ctx, request)
	}
	s.AddTool(tool, handlerWithClient)

	s.AddPrompt(mcp.NewPrompt("generate-image",
		mcp.WithPromptDescription("Generates an image from a text prompt."),
		mcp.WithArgument("prompt", mcp.ArgumentDescription("The text prompt to generate an image from."), mcp.RequiredArgument()),
		mcp.WithArgument("model", mcp.ArgumentDescription("The model to use for generation.")),
		mcp.WithArgument("num_images", mcp.ArgumentDescription("The number of images to generate.")),
		mcp.WithArgument("aspect_ratio", mcp.ArgumentDescription("The aspect ratio of the generated images.")),
	), func(ctx context.Context, request mcp.GetPromptRequest) (*mcp.GetPromptResult, error) {
		prompt, ok := request.Params.Arguments["prompt"]
		if !ok || strings.TrimSpace(prompt) == "" {
			return mcp.NewGetPromptResult(
				"Missing Prompt",
				[]mcp.PromptMessage{
					mcp.NewPromptMessage(mcp.RoleAssistant, mcp.NewTextContent("What would you like to create an image of?")),
				},
			), nil
		}

		// Call the existing handler logic
		args := make(map[string]interface{}, len(request.Params.Arguments))
		for k, v := range request.Params.Arguments {
			args[k] = v
		}
		toolRequest := mcp.CallToolRequest{
			Params: mcp.CallToolParams{Arguments: args},
		}
		result, err := imagenGenerationHandler(genAIClient, ctx, toolRequest)
		if err != nil {
			return nil, err
		}

		var responseText string
		for _, content := range result.Content {
			if textContent, ok := content.(mcp.TextContent); ok {
				responseText += textContent.Text + "\n"
			}
		}

		return mcp.NewGetPromptResult(
			"Image Generation Result",
			[]mcp.PromptMessage{
				mcp.NewPromptMessage(mcp.RoleAssistant, mcp.NewTextContent(strings.TrimSpace(responseText))),
			},
		), nil
	})

	switch transport {
	case "sse":
		ssePort := 8081 // Default SSE port
		if port != 0 {
			ssePort = port
		} else if p, err := strconv.Atoi(common.GetEnv("PORT", "")); err == nil {
			ssePort = p
		}
		log.Printf("Starting Imagen MCP Server (Version: %s, Transport: sse, Port: %d)", version, ssePort)
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
		log.Printf("Starting Imagen MCP Server (Version: %s, Transport: http, Port: %d)", version, httpPort)
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
		log.Printf("Starting Imagen MCP Server (Version: %s, Transport: stdio)", version)
		if err := server.ServeStdio(s); err != nil {
			log.Fatalf("STDIO Server error: %v", err)
		}
	default:
		log.Fatalf("Unsupported transport type: %s. Please use 'stdio', 'sse', or 'http'.", transport)
	}

	log.Println("Imagen Server has stopped.")
}

type ImagenOutput struct {
	GCSURIs   []string `json:"gcsUris"`
	HTTPSURLs []string `json:"httpsURLs"`
	Message   string   `json:"message"`
}

func contains(s []string, e string) bool {
	for _, a := range s {
		if a == e {
			return true
		}
	}
	return false
}

// imagenOutputNames returns the deterministic per-image output file names when a
// client output_filename is set (extension forced to the true image MIME, 1-based
// suffixing for count > 1 per design #842 §4b/§4c). It returns nil when
// output_filename is unset or cannot be applied, so the handler falls back to its
// existing default naming scheme (byte-for-byte legacy behavior).
func imagenOutputNames(outputFilename string, count int, mimeType string) []string {
	if strings.TrimSpace(outputFilename) == "" {
		return nil
	}
	names, err := common.BuildOutputFilenames(outputFilename, count, mimeType)
	if err != nil {
		log.Printf("output_filename %q could not be applied (%v); falling back to default naming", outputFilename, err)
		return nil
	}
	return names
}

// confineImagenOutputDir applies output-directory confinement (CWE-22) to the
// caller-supplied local output directory for the imagen local-save sink. It is a
// behavior-preserving extraction of the former inline block so the confinement
// wiring is independently testable (mirrors mcp-gemini-go's processGeminiImageResponse).
//
// Fail-closed: when attemptLocalSave is true and the directory is a traversal attempt
// (absolute path or containing ".."), it returns attempt=false and appends the
// rejection reason, so the caller's `if attemptLocalSave { … }` skips the local write
// entirely and nothing is written outside the root. On success it returns the confined
// directory. When attemptLocalSave is already false it is a no-op pass-through.
func confineImagenOutputDir(outputDir string, attemptLocalSave bool, reasons []string) (confinedDir string, attempt bool, updatedReasons []string) {
	if !attemptLocalSave {
		return outputDir, attemptLocalSave, reasons
	}
	confined, confErr := common.ResolveConfinedOutputDir(outputDir)
	if confErr != nil {
		log.Printf("Rejecting unsafe output_directory %q: %v", outputDir, confErr)
		reasons = append(reasons, confErr.Error())
		return outputDir, false, reasons
	}
	return confined, true, reasons
}

// buildImagenRenamePlan maps the API-written GCS objects (Path C: imagen lets
// Vertex name the objects sample_k under the output prefix) to the client-desired
// names. It returns the bucket, the ordered src→dst renames, and — aligned 1:1 with
// renames — the source gs:// URI each rename came from (planSrcURIs) and the
// resulting destination gs:// URI (dstURIs). names[i] belongs to the artifact
// srcURIs[i] by identity, so a skipped (unparseable) URI never drifts the mapping.
// The returned planSrcURIs lets the caller write each renamed URI back onto the
// exact artifact it came from by identity rather than by slice position. names are
// the output of imagenOutputNames; when names is empty it returns nil (default API
// names kept).
func buildImagenRenamePlan(gcsOutputURI string, srcURIs, names []string) (bucket string, renames []common.Rename, planSrcURIs, dstURIs []string) {
	if len(names) == 0 || len(srcURIs) == 0 {
		return "", nil, nil, nil
	}
	bucket, prefix := common.ParseGCSBucketAndPrefix(gcsOutputURI)
	n := len(srcURIs)
	if len(names) < n {
		n = len(names)
	}
	for i := 0; i < n; i++ {
		_, srcObject, err := common.ParseGCSPath(srcURIs[i])
		if err != nil {
			log.Printf("skipping GCS rename for unparseable URI %q: %v", srcURIs[i], err)
			continue
		}
		dstObject := prefix + names[i]
		renames = append(renames, common.Rename{Src: srcObject, Dst: dstObject})
		planSrcURIs = append(planSrcURIs, srcURIs[i])
		dstURIs = append(dstURIs, common.BuildGCSURI(bucket, dstObject))
	}
	return bucket, renames, planSrcURIs, dstURIs
}

// applyRenamedURIs writes each successfully-renamed destination URI back onto the
// artifact it came from, pairing by identity (the source gs:// URI in planSrcURIs)
// rather than by slice position. renames/planSrcURIs/dstURIs are aligned 1:1 by
// construction (buildImagenRenamePlan), and renamedCount is how many leading plan
// entries common.RenameGCSObjects reported as renamed (it returns a prefix of the
// plan, truncated at the first failure). Positional writeback into the
// (un-compacted) gcsSavedURIs would drift if any source URI was skipped or the
// batch partially failed; identity pairing never does.
func applyRenamedURIs(gcsSavedURIs, planSrcURIs, dstURIs []string, renamedCount int) {
	for k := 0; k < renamedCount && k < len(dstURIs) && k < len(planSrcURIs); k++ {
		for idx := range gcsSavedURIs {
			if gcsSavedURIs[idx] == planSrcURIs[k] {
				gcsSavedURIs[idx] = dstURIs[k]
				break
			}
		}
	}
}

func imagenGenerationHandler(client *genai.Client, ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "imagen_t2i")
	defer span.End()

	prompt, ok := request.GetArguments()["prompt"].(string)
	if !ok {
		return &mcp.CallToolResult{Content: []mcp.Content{mcp.TextContent{Type: "text", Text: "Error: prompt must be a string and is required"}}}, nil
	}

	modelInput := common.ResolveModel(request.GetArguments(), "model_id", "model_name")
	if modelInput == "" {
		log.Printf("Model not provided or empty, using default: imagen-4.0-fast-generate-001")
		modelInput = "imagen-4.0-fast-generate-001"
	}

	modelInfo, found := common.ResolveImagenModel(modelInput, appConfig.AllowUnsafeModels)
	if !found {
		return &mcp.CallToolResult{Content: []mcp.Content{mcp.TextContent{Type: "text", Text: fmt.Sprintf("Error: Model '%s' is not a valid or supported model name.", modelInput)}}}, nil
	}
	model := modelInfo.CanonicalName
	modelDetails := modelInfo

	var numberOfImages int32 = 1
	if numImagesArg, ok := request.GetArguments()["num_images"]; ok {
		if numImagesFloat, okFloat := numImagesArg.(float64); okFloat {
			numberOfImages = int32(numImagesFloat)
		} else {
			log.Printf("Warning: num_images was not a float64, received %T. Using default.", numImagesArg)
		}
	}

	if numberOfImages < 1 {
		numberOfImages = 1
	}
	if numberOfImages > modelDetails.MaxImages {
		log.Printf("Warning: Requested %d images, but model %s only supports up to %d. Adjusting to max.", numberOfImages, model, modelDetails.MaxImages)
		numberOfImages = modelDetails.MaxImages
	}

	aspectRatio, ok := request.GetArguments()["aspect_ratio"].(string)
	if !ok || aspectRatio == "" {
		log.Printf("Aspect ratio not provided or empty, using default: 1:1")
		aspectRatio = "1:1"
	}

	if !contains(modelDetails.SupportedAspectRatios, aspectRatio) {
		log.Printf("Warning: Requested aspect ratio '%s' is not supported by model %s. Supported ratios are: %v. Falling back to '1:1'.", aspectRatio, model, modelDetails.SupportedAspectRatios)
		aspectRatio = "1:1" // Fallback to a safe default
	}

	imageSize, _ := request.GetArguments()["image_size"].(string)
	var finalImageSize string
	if imageSize != "" {
		if len(modelDetails.SupportedImageSizes) == 0 {
			log.Printf("Warning: image_size parameter ('%s') provided, but model %s does not support it. The parameter will be ignored.", imageSize, model)
		} else if !contains(modelDetails.SupportedImageSizes, imageSize) {
			log.Printf("Warning: Requested image size '%s' is not supported by model %s. Supported sizes are: %v. The parameter will be ignored.", imageSize, model, modelDetails.SupportedImageSizes)
		} else {
			finalImageSize = imageSize
		}
	} // ... rest of handler ...
	gcsOutputURI := ""
	gcsBucketUriParam := common.ResolveGCSBucketURI(request.GetArguments(), "bucket", "output_gcs_bucket")

	if gcsBucketUriParam != "" {
		gcsOutputURI = gcsBucketUriParam
		if !strings.HasPrefix(gcsOutputURI, "gs://") {
			gcsOutputURI = "gs://" + gcsOutputURI
			log.Printf("gcs_bucket_uri did not start with 'gs://', prepended. New URI: %s", gcsOutputURI)
		}
	} else if appConfig.GenmediaBucket != "" {
		gcsOutputURI = fmt.Sprintf("gs://%s/imagen_outputs/", appConfig.GenmediaBucket)
		log.Printf("Handler imagen_t2i: 'gcs_bucket_uri' parameter not provided, using default constructed from GENMEDIA_BUCKET: %s", gcsOutputURI)
	} else {
		log.Printf("Handler imagen_t2i: 'gcs_bucket_uri' parameter and GENMEDIA_BUCKET env var are both empty. No GCS output will be saved.")
	}

	if gcsOutputURI != "" && !strings.HasSuffix(gcsOutputURI, "/") {
		gcsOutputURI += "/"
		log.Printf("Appended '/' to gcsOutputURI for directory structure. New URI: %s", gcsOutputURI)
	}

	outputDir := common.ResolveOutputDirectory(request.GetArguments(), "output_local_dir", "local_path")
	attemptLocalSave := outputDir != ""

	span.SetAttributes(
		attribute.String("prompt", prompt),
		attribute.String("model", model),
		attribute.Int("num_images", int(numberOfImages)),
		attribute.String("aspect_ratio", aspectRatio),
		attribute.String("image_size", finalImageSize),
		attribute.String("gcs_bucket_uri", gcsBucketUriParam),
		attribute.String("output_directory", outputDir),
	)

	select {
	case <-ctx.Done():
		errMsg := fmt.Sprintf("Request processing canceled early: %v", ctx.Err())
		log.Printf("Incoming context for prompt \"%s\" was already canceled: %v", prompt, ctx.Err())
		return &mcp.CallToolResult{Content: []mcp.Content{mcp.TextContent{Type: "text", Text: errMsg}}}, nil
	default:
		log.Printf("Handling imagen request: Prompt=\"%s\", Model=%s, NumImages=%d, AspectRatio=%s, ImageSize=%s, GCSOutputURI='%s', OutputDirectory='%s'",
			prompt, model, numberOfImages, aspectRatio, finalImageSize, gcsOutputURI, outputDir)
	}

	config := &genai.GenerateImagesConfig{
		NumberOfImages: numberOfImages,
		AspectRatio:    aspectRatio,
		ImageSize:      finalImageSize,
		OutputGCSURI:   gcsOutputURI,
	}

	apiCallCtx, apiCallCancel := context.WithTimeout(ctx, 3*time.Minute)
	defer apiCallCancel()

	log.Printf("Calling GenerateImages with Model: %s, Prompt: \"%s\". API call timeout: 3m", model, prompt)
	startTime := time.Now()

	response, err := client.Models.GenerateImages(
		apiCallCtx,
		model,
		prompt,
		config,
	)

	apiCallDuration := time.Since(startTime)
	log.Printf("GenerateImages call took: %v", apiCallDuration)
	span.SetAttributes(attribute.Float64("duration_ms", float64(apiCallDuration.Milliseconds())))

	var contentItems []mcp.Content

	// Check for optional Sherlog header
	if response != nil && response.SDKHTTPResponse != nil && response.SDKHTTPResponse.Headers != nil {
		if link := response.SDKHTTPResponse.Headers.Get("x-goog-sherlog-link"); link != "" {
			contentItems = append(contentItems, mcp.TextContent{Type: "text", Text: fmt.Sprintf("Optional header capture: %s\n", link)})
		}
	}

	if err != nil {
		errorMessage := fmt.Sprintf("error generating images: %v", err.Error())
		if errors.Is(err, context.DeadlineExceeded) && apiCallCtx.Err() == context.DeadlineExceeded {
			log.Printf("GenerateImages failed due to API call timeout (3 minutes): %v", err)
			errorMessage = "image generation timed out"
		} else if errors.Is(err, context.Canceled) {
			log.Printf("GenerateImages failed due to context cancellation: %v", err)
			errorMessage = "image generation was canceled"
		} else {
			log.Printf("Error generating images (API call failed): %v", err)
		}
		span.RecordError(err)
		contentItems = append(contentItems, mcp.TextContent{Type: "text", Text: errorMessage})
		return &mcp.CallToolResult{Content: contentItems}, nil
	}

	if response == nil || len(response.GeneratedImages) == 0 {
		noImageText := fmt.Sprintf("Sorry, I couldn't generate any images for the prompt \"%s\".", prompt)
		log.Print(noImageText)
		contentItems = append(contentItems, mcp.TextContent{Type: "text", Text: noImageText})
		return &mcp.CallToolResult{Content: contentItems}, nil
	}

	log.Printf("Successfully received %d image metadata/references from API.", len(response.GeneratedImages))

	var savedLocalFilenames []string
	var failedLocalSaveReasons []string

	// Confine the caller-supplied output directory to the configured output root
	// before any filesystem operation (CWE-22 directory traversal). Resolved once
	// here so the per-image loop writes only under the confined path. On a
	// traversal attempt (absolute path or ".."), local save is disabled and the
	// reason is surfaced in the response rather than writing outside the root.
	outputDir, attemptLocalSave, failedLocalSaveReasons = confineImagenOutputDir(outputDir, attemptLocalSave, failedLocalSaveReasons)

	var gcsSavedURIs []string
	// gcsSavedMimes stays 1:1 with gcsSavedURIs so a resource_link per GCS
	// artifact carries the right MIME type (design #483).
	var gcsSavedMimes []string
	var totalSizeBytesGenerated int64 = 0
	imagesWithDataOrURI := 0
	returnImageDataInResponse := gcsOutputURI == "" && !attemptLocalSave
	log.Printf("Will return image data in response: %t", returnImageDataInResponse)

	// Resolve an optional client-supplied output_filename (design #842). When set,
	// outputNames holds the deterministic per-image names (extension forced to the
	// true image MIME, 1-based suffix for >1 image); when unset it is nil and the
	// handler keeps its existing default naming scheme (byte-for-byte legacy
	// behavior). The MIME is taken from the first image (imagen returns a
	// homogeneous batch); default image/png.
	outputFilename := common.ResolveOutputFilename(request.GetArguments())
	firstMimeType := "image/png"
	for _, gi := range response.GeneratedImages {
		if gi.Image != nil && gi.Image.MIMEType != "" {
			firstMimeType = gi.Image.MIMEType
			break
		}
	}
	outputNames := imagenOutputNames(outputFilename, len(response.GeneratedImages), firstMimeType)

	for n, genImg := range response.GeneratedImages {
		var imageData []byte
		imageMimeType := "image/png"
		imageSourceIsGCS := false
		var currentImageGCSURI string

		if genImg.Image != nil && genImg.Image.GCSURI != "" {
			currentImageGCSURI = genImg.Image.GCSURI
			imagesWithDataOrURI++
			imageSourceIsGCS = true
			gcsSavedURIs = append(gcsSavedURIs, currentImageGCSURI)
			log.Printf("Image %d available at GCS URI (from API response): %s", n, currentImageGCSURI)
			if genImg.Image.MIMEType != "" {
				imageMimeType = genImg.Image.MIMEType
			}
			gcsSavedMimes = append(gcsSavedMimes, imageMimeType)
		} else if genImg.Image != nil && genImg.Image.ImageBytes != nil && len(genImg.Image.ImageBytes) > 0 {
			imagesWithDataOrURI++
			imageData = genImg.Image.ImageBytes
			totalSizeBytesGenerated += int64(len(imageData))
			if genImg.Image.MIMEType != "" {
				imageMimeType = genImg.Image.MIMEType
			}
			log.Printf("Image %d received as bytes from API (Size: %s, MIME: %s)", n, common.FormatBytes(int64(len(imageData))), imageMimeType)
		} else {
			log.Printf("Generated image %d (model: %s) from API had no GCS URI and no direct image data.", n, model)
			continue
		}

		if attemptLocalSave {
			var localFilename string
			if outputNames != nil {
				// Client output_filename: use the deterministic name (extension
				// already forced to the true media MIME).
				localFilename = outputNames[n]
			} else {
				localFilename = fmt.Sprintf("imagen-%s-%s-%d", model, time.Now().Format("20060102-150405"), n)
				switch imageMimeType {
				case "image/jpeg":
					localFilename += ".jpg"
				case "image/webp":
					localFilename += ".webp"
				default:
					localFilename += ".png"
				}
			}
			// outputDir is already confined to the output root above (CWE-22);
			// filepath.Clean alone does NOT confine and has been removed.
			actualSavePath := filepath.Join(outputDir, localFilename)

			if imageSourceIsGCS {
				log.Printf("Attempting to download image %d from GCS URI %s to %s", n, currentImageGCSURI, actualSavePath)
				downloadCtx, downloadCancel := context.WithTimeout(ctx, 2*time.Minute)
				err := common.DownloadFromGCS(downloadCtx, currentImageGCSURI, actualSavePath)
				downloadCancel()
				if err != nil {
					log.Print(err)
					failedLocalSaveReasons = append(failedLocalSaveReasons, err.Error())
				} else {
					log.Printf("Successfully downloaded and saved image %d to %s", n, actualSavePath)
					savedLocalFilenames = append(savedLocalFilenames, actualSavePath)
					fileInfo, statErr := os.Stat(actualSavePath)
					if statErr == nil {
						totalSizeBytesGenerated += fileInfo.Size()
					} else {
						log.Printf("Could not get file info for downloaded file %s: %v", actualSavePath, statErr)
					}
				}
			} else if len(imageData) > 0 {
				if err := os.MkdirAll(outputDir, 0755); err != nil {
					log.Print(err)
					failedLocalSaveReasons = append(failedLocalSaveReasons, err.Error())
				} else {
					if err := os.WriteFile(actualSavePath, imageData, 0644); err != nil {
						log.Print(err)
						failedLocalSaveReasons = append(failedLocalSaveReasons, err.Error())
					} else {
						log.Printf("Saved image %s (Size: %s)", actualSavePath, common.FormatBytes(int64(len(imageData))))
						savedLocalFilenames = append(savedLocalFilenames, actualSavePath)
					}
				}
			}
		}

		if returnImageDataInResponse && len(imageData) > 0 {
			base64Data := base64.StdEncoding.EncodeToString(imageData)
			imageItem := mcp.ImageContent{
				Type:     "image",
				Data:     base64Data,
				MIMEType: imageMimeType,
			}
			contentItems = append(contentItems, imageItem)
		}
	}

	// Path C copy-rename (design #842 §4d): imagen lets Vertex name the GCS objects
	// itself (sample_k) under the output prefix. When output_filename is set, copy-
	// rename those API-written objects to the client-desired names and delete the
	// originals. Already-renamed valid outputs are not rolled back on a partial
	// failure; the reported URIs reflect the successfully-renamed objects.
	var renameNote string
	if outputNames != nil && len(gcsSavedURIs) > 0 {
		renameBucket, renames, planSrcURIs, dstURIs := buildImagenRenamePlan(gcsOutputURI, gcsSavedURIs, outputNames)
		if len(renames) > 0 {
			renamed, rErr := common.RenameGCSObjects(ctx, renameBucket, renames)
			// Pair each renamed URI back to its source artifact by identity, not by
			// slice position, so a skipped/unparseable URI or a partial batch failure
			// never writes a renamed URI onto the wrong artifact.
			applyRenamedURIs(gcsSavedURIs, planSrcURIs, dstURIs, len(renamed))
			if rErr != nil {
				renameNote = fmt.Sprintf("Note: renaming generated GCS object(s) to match output_filename '%s' partially failed (some API-original sample_* objects may remain): %v", outputFilename, rErr)
				log.Print(renameNote)
			} else {
				log.Printf("Renamed %d generated GCS object(s) to match output_filename '%s'.", len(renamed), outputFilename)
			}
		}
	}

	var resultText string
	var saveMessageParts []string

	if gcsOutputURI != "" {
		if len(gcsSavedURIs) > 0 {
			httpURIs := make([]string, len(gcsSavedURIs))
			for i, gcsUri := range gcsSavedURIs {
				httpURIs[i] = strings.Replace(gcsUri, "gs://", "https://storage.mtls.cloud.google.com/", 1)
			}
			saveMessageParts = append(saveMessageParts, fmt.Sprintf("Images saved to GCS: %s. HTTPS URLs: %s.", strings.Join(gcsSavedURIs, ", "), strings.Join(httpURIs, ", ")))
		} else if imagesWithDataOrURI > 0 && len(gcsSavedURIs) == 0 {
			saveMessageParts = append(saveMessageParts, fmt.Sprintf("GCS output was requested to '%s', but API did not return GCS URIs for the generated images.", config.OutputGCSURI))
		} else {
			saveMessageParts = append(saveMessageParts, fmt.Sprintf("GCS output was requested to '%s', but no images with GCS URIs were returned by the API.", config.OutputGCSURI))
		}
		if renameNote != "" {
			saveMessageParts = append(saveMessageParts, renameNote)
		}
	}

	if attemptLocalSave {
		if gcsOutputURI != "" {
			saveMessageParts = append(saveMessageParts, fmt.Sprintf("Attempted to download images from GCS to local directory '%s'.", outputDir))
		} else {
			saveMessageParts = append(saveMessageParts, fmt.Sprintf("Attempted to save images from API response bytes to local directory '%s'.", outputDir))
		}
		if len(savedLocalFilenames) > 0 {
			saveMessageParts = append(saveMessageParts, fmt.Sprintf("Successfully saved locally: %s.", strings.Join(savedLocalFilenames, ", ")))
		}
		if len(failedLocalSaveReasons) > 0 {
			saveMessageParts = append(saveMessageParts, fmt.Sprintf("Local save/download issues: %s.", strings.Join(failedLocalSaveReasons, "; ")))
		}
	}

	if !returnImageDataInResponse {
		saveMessageParts = append(saveMessageParts, "Image data is not included in this MCP response because a GCS URI or local output directory was specified.")
	} else if returnImageDataInResponse && imagesWithDataOrURI > 0 {
		saveMessageParts = append(saveMessageParts, "Image(s) are included in this MCP response as base64 data.")
	}

	sizeReport := ""
	if totalSizeBytesGenerated > 0 {
		sizeReport = fmt.Sprintf("(total processed/downloaded byte size: %s) ", common.FormatBytes(totalSizeBytesGenerated))
	} else if len(gcsSavedURIs) > 0 && !attemptLocalSave {
		sizeReport = "(image sizes are on GCS) "
	}

	if imagesWithDataOrURI > 0 {
		resultText = fmt.Sprintf("Generated %d image(s) %susing model %s for prompt \"%s\". This took about %s. %s",
			imagesWithDataOrURI,
			sizeReport,
			model,
			prompt,
			apiCallDuration.Round(time.Second),
			strings.Join(saveMessageParts, " "),
		)
	} else {
		resultText = fmt.Sprintf("Processed request for model %s with prompt \"%s\" (took %s), but no images with data or GCS URIs were returned by the API.",
			model,
			prompt,
			apiCallDuration.Round(time.Second),
		)
	}

	textItem := mcp.TextContent{
		Type: "text",
		Text: strings.TrimSpace(resultText),
	}

	finalContentItems := []mcp.Content{textItem}
	if returnImageDataInResponse {
		finalContentItems = append(finalContentItems, contentItems...)
	}

	// Text output is unchanged; append one resource_link per GCS artifact
	// (design #483), in generation order, using the (possibly renamed) gs:// URIs.
	finalContentItems = appendImagenResourceLinks(finalContentItems, gcsSavedURIs, gcsSavedMimes)

	return &mcp.CallToolResult{Content: finalContentItems}, nil
}

// appendImagenResourceLinks appends one resource_link per GCS image artifact to
// items (design #483). gcsSavedURIs and gcsSavedMimes are aligned 1:1 by
// construction, so each link carries that artifact's own MIME type; the
// description is the 1-based "imagen output i of n". This only ADDS links (the
// caller's text/image content is unchanged) and returns items unchanged when
// there are no GCS artifacts (inline/local-only paths).
func appendImagenResourceLinks(items []mcp.Content, gcsSavedURIs, gcsSavedMimes []string) []mcp.Content {
	var mediaResults []common.MediaResult
	for i, uri := range gcsSavedURIs {
		mediaResults = append(mediaResults, common.MediaResult{
			GCSURI:      uri,
			MimeType:    gcsSavedMimes[i],
			Description: fmt.Sprintf("imagen output %d of %d", i+1, len(gcsSavedURIs)),
		})
	}
	return common.AppendMediaContent(items, mediaResults)
}

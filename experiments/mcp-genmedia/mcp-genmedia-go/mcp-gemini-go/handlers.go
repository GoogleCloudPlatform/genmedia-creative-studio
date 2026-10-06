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
	"encoding/base64"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"google.golang.org/genai"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
)

// validateGeminiImageParams checks the requested aspect_ratio and image_size
// against a resolved model's declared capabilities, mirroring the
// mcp-imagen-go fallback pattern: an unsupported aspect_ratio falls back to
// "1:1", and an image_size that the model does not support (or does not
// support at all) is dropped so the API applies its own default. It returns
// the (possibly adjusted) aspect_ratio and image_size.
func validateGeminiImageParams(info common.GeminiImageModelInfo, model, aspectRatio, imageSize string) (string, string) {
	if !slices.Contains(info.SupportedAspectRatios, aspectRatio) {
		log.Printf("Warning: Requested aspect ratio '%s' is not supported by model %s. Supported ratios are: %v. Falling back to '1:1'.", aspectRatio, model, info.SupportedAspectRatios)
		aspectRatio = "1:1"
	}
	if imageSize != "" {
		if len(info.SupportedImageSizes) == 0 {
			log.Printf("Warning: image_size parameter ('%s') provided, but model %s does not support it. The parameter will be ignored.", imageSize, model)
			imageSize = ""
		} else if !slices.Contains(info.SupportedImageSizes, imageSize) {
			log.Printf("Warning: Requested image size '%s' is not supported by model %s. Supported sizes are: %v. The parameter will be ignored.", imageSize, model, info.SupportedImageSizes)
			imageSize = ""
		}
	}
	return aspectRatio, imageSize
}

func geminiGenerateContentHandler(client *genai.Client, ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "gemini_generate_content")
	defer span.End()

	// --- Parameter Parsing ---
	prompt, ok := request.GetArguments()["prompt"].(string)
	if !ok || strings.TrimSpace(prompt) == "" {
		return mcp.NewToolResultError("prompt must be a non-empty string and is required"), nil
	}

	aspectRatio := "1:1"
	if ar, ok := request.GetArguments()["aspect_ratio"].(string); ok && strings.TrimSpace(ar) != "" {
		aspectRatio = strings.TrimSpace(ar)
	}

	imageSize := ""
	if is, ok := request.GetArguments()["image_size"].(string); ok && strings.TrimSpace(is) != "" {
		imageSize = strings.TrimSpace(is)
	}

	modelArg, _ := request.GetArguments()["model"].(string)
	model := "gemini-nano-banana-2.1"
	if modelArg != "" {
		model = modelArg
	}
	// Resolve the model (including the default) so aspect_ratio/image_size can be
	// validated against its declared capabilities. Unknown models that cannot be
	// resolved (AllowUnsafeModels disabled) are passed through untouched.
	if resolvedInfo, found := common.ResolveGeminiImageModel(model, appConfig.AllowUnsafeModels); found {
		model = resolvedInfo.CanonicalName
		aspectRatio, imageSize = validateGeminiImageParams(resolvedInfo, model, aspectRatio, imageSize)
	}

	outputDir := ""
	if dir, ok := request.GetArguments()["output_directory"].(string); ok && strings.TrimSpace(dir) != "" {
		outputDir = strings.TrimSpace(dir)
	}

	gcsOutputURI := ""
	gcsBucketName := ""
	gcsObjectPrefix := ""
	if gcsURI, ok := request.GetArguments()["gcs_bucket_uri"].(string); ok && strings.TrimSpace(gcsURI) != "" {
		gcsOutputURI = common.EnsureGCSPathPrefix(strings.TrimSpace(gcsURI))
		var err error
		gcsBucketName, gcsObjectPrefix, err = common.ParseGCSPrefix(gcsOutputURI)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("invalid gcs_bucket_uri: %v", err)), nil
		}
	}

	// --- Construct Gemini Request ---
	var parts []*genai.Part
	parts = append(parts, genai.NewPartFromText(prompt))

	if imageArgs, ok := request.GetArguments()["images"].([]interface{}); ok {
		for _, imgArg := range imageArgs {
			if imgPath, ok := imgArg.(string); ok {
				if strings.HasPrefix(imgPath, "gs://") {
					parts = append(parts, genai.NewPartFromURI(imgPath, ""))
				} else {
					imgData, err := os.ReadFile(imgPath)
					if err != nil {
						return mcp.NewToolResultError(fmt.Sprintf("failed to read image file %s: %v", imgPath, err)), nil
					}
					parts = append(parts, genai.NewPartFromBytes(imgData, inferMimeType(imgPath)))
				}
			}
		}
	}

	span.SetAttributes(
		attribute.String("prompt", prompt),
		attribute.String("model", model),
		attribute.String("output_directory", outputDir),
		attribute.String("gcs_bucket_uri", gcsOutputURI),
	)

	// --- API Call ---
	log.Printf("Calling GenerateContent with Model: %s, Prompt: \"%s\"", model, prompt)
	startTime := time.Now()

	config := &genai.GenerateContentConfig{
		ResponseModalities: []string{"IMAGE", "TEXT"},
		ImageConfig: &genai.ImageConfig{
			AspectRatio: aspectRatio,
			ImageSize:   imageSize,
		},
	}
	contents := &genai.Content{Parts: parts, Role: "USER"}

	resp, err := client.Models.GenerateContent(ctx, model, []*genai.Content{contents}, config)

	apiCallDuration := time.Since(startTime)
	log.Printf("GenerateContent call took: %v", apiCallDuration)
	span.SetAttributes(attribute.Float64("duration_ms", float64(apiCallDuration.Milliseconds())))

	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("error calling Gemini API: %v", err)), nil
	}

	// --- Process Response ---
	return processGeminiImageResponse(ctx, resp, request.GetArguments(), outputDir, gcsOutputURI, gcsBucketName, gcsObjectPrefix)
}

// writeFileFn / uploadToGCSFn are the local-write and GCS-upload seams. They are
// package-level variables so tests can inject fakes and exercise the
// response-processing wiring (naming, two-pass assignment, write/upload targets)
// without a live genai client or cloud access.
var (
	writeFileFn   = os.WriteFile
	uploadToGCSFn = common.UploadToGCS
)

// processGeminiImageResponse writes/uploads each generated image and builds the
// user-facing summary, honoring output_filename-derived names when provided and
// preserving the legacy gemini_<ts>_<n> per-part scheme otherwise. Extracted from
// the handler so the naming + write/upload wiring is unit-testable (design #842).
func processGeminiImageResponse(ctx context.Context, resp *genai.GenerateContentResponse, args map[string]any, outputDir, gcsOutputURI, gcsBucketName, gcsObjectPrefix string) (*mcp.CallToolResult, error) {
	var responseText strings.Builder
	var savedFiles []string
	var gcsSavedURIs []string
	// gcsSavedMimes stays 1:1 with gcsSavedURIs so a resource_link per GCS
	// artifact carries the right MIME type (design #483).
	var gcsSavedMimes []string
	var responseImages []mcp.Content
	generatedImages := 0
	returnImageDataInResponse := outputDir == "" && gcsOutputURI == ""

	// Confine the caller-supplied output directory to the configured output root
	// before any filesystem operation (CWE-22 directory traversal). Resolved once
	// here so the per-image loop below writes only under the confined path.
	if outputDir != "" {
		confinedDir, confErr := common.ResolveConfinedOutputDir(outputDir)
		if confErr != nil {
			return mcp.NewToolResultError(fmt.Sprintf("invalid output_directory: %v", confErr)), nil
		}
		outputDir = confinedDir
	}

	// Check for optional Sherlog header
	if resp.SDKHTTPResponse != nil && resp.SDKHTTPResponse.Headers != nil {
		if link := resp.SDKHTTPResponse.Headers.Get("x-goog-sherlog-link"); link != "" {
			fmt.Fprintf(&responseText, "Optional header capture: %s\n\n", link)
		}
	}
	gentime := time.Now().Format("20060102150405")

	// First pass: count image artifacts (and capture the first MIME type) so the
	// total is known before naming — required for deterministic _1..n suffixing
	// when output_filename is set.
	imageCount := 0
	firstImageMime := ""
	for _, candidate := range resp.Candidates {
		for _, part := range candidate.Content.Parts {
			if part.InlineData != nil {
				if imageCount == 0 {
					firstImageMime = common.NormalizeImageMIMEType(part.InlineData.MIMEType)
				}
				imageCount++
			}
		}
	}

	// When output_filename is set, precompute client-predictable names via the
	// shared helper (extension forced to the true MIME, deterministic suffixing).
	// When unset, names is nil and each image keeps the legacy per-part scheme —
	// byte-for-byte unchanged behavior. gemini image carries no legacy alias.
	var names []string
	if base := common.ResolveOutputFilename(args); base != "" && imageCount > 0 {
		var err error
		names, err = common.BuildOutputFilenames(base, imageCount, firstImageMime)
		if err != nil {
			return mcp.NewToolResultError(err.Error()), nil
		}
	}

	// Second pass: preserve the original text/image interleaving and persist each
	// image via the injectable write/upload seams.
	imgIdx := 0
	for _, candidate := range resp.Candidates {
		for n, part := range candidate.Content.Parts {
			if part.Text != "" {
				responseText.WriteString(part.Text)
			}
			if part.InlineData != nil {
				generatedImages++
				mimeType := common.NormalizeImageMIMEType(part.InlineData.MIMEType)
				var fileName string
				if names != nil {
					fileName = names[imgIdx]
				} else {
					fileName = fmt.Sprintf("gemini_%s_%d%s", gentime, n, common.ImageExtensionForMIMEType(mimeType))
				}
				imgIdx++
				log.Printf("part %d mime-type: %s", n, mimeType)

				if outputDir != "" {
					if err := os.MkdirAll(outputDir, 0755); err != nil {
						return mcp.NewToolResultError(fmt.Sprintf("failed to create output directory: %v", err)), nil
					}
					filePath := filepath.Join(outputDir, fileName)
					// Collision policy: overwrite with a warning (design §4e).
					if _, statErr := os.Stat(filePath); statErr == nil {
						log.Printf("Warning: output file %q already exists in %s; overwriting (collision policy).", fileName, outputDir)
					}
					if err := writeFileFn(filePath, part.InlineData.Data, 0644); err != nil {
						return mcp.NewToolResultError(fmt.Sprintf("failed to write image file: %v", err)), nil
					}
					savedFiles = append(savedFiles, filePath)
				}

				if gcsOutputURI != "" {
					objectName := common.JoinGCSObjectName(gcsObjectPrefix, fileName)
					if err := uploadToGCSFn(ctx, gcsBucketName, objectName, mimeType, part.InlineData.Data); err != nil {
						return mcp.NewToolResultError(fmt.Sprintf("failed to upload image to GCS: %v", err)), nil
					}
					gcsSavedURIs = append(gcsSavedURIs, common.BuildGCSURI(gcsBucketName, objectName))
					gcsSavedMimes = append(gcsSavedMimes, mimeType)
				}

				if returnImageDataInResponse {
					responseImages = append(responseImages, mcp.ImageContent{
						Type:     "image",
						Data:     base64.StdEncoding.EncodeToString(part.InlineData.Data),
						MIMEType: mimeType,
					})
				}
			}
		}
	}

	// --- Format Final Result ---
	finalMessage := strings.TrimSpace(responseText.String())
	if finalMessage == "" && generatedImages > 0 {
		finalMessage = fmt.Sprintf("Generated %d image(s).", generatedImages)
	}
	if len(savedFiles) > 0 {
		finalMessage += fmt.Sprintf("\n\nGenerated and saved %d image(s): %s", len(savedFiles), strings.Join(savedFiles, ", "))
	}
	if len(gcsSavedURIs) > 0 {
		finalMessage += fmt.Sprintf("\n\nGenerated and uploaded %d image(s) to GCS: %s", len(gcsSavedURIs), strings.Join(gcsSavedURIs, ", "))
	}
	if returnImageDataInResponse && len(responseImages) > 0 {
		finalMessage += "\n\nImage(s) are included in this MCP response as base64 data."
	}

	contentItems := []mcp.Content{mcp.TextContent{Type: "text", Text: strings.TrimSpace(finalMessage)}}
	if returnImageDataInResponse {
		contentItems = append(contentItems, responseImages...)
	}

	// Text output is unchanged; append one resource_link per GCS artifact
	// (design #483). content[1..n] = resource_link in generation order.
	var mediaResults []common.MediaResult
	for i, uri := range gcsSavedURIs {
		mediaResults = append(mediaResults, common.MediaResult{
			GCSURI:      uri,
			MimeType:    gcsSavedMimes[i],
			Description: fmt.Sprintf("gemini output %d of %d", i+1, len(gcsSavedURIs)),
		})
	}
	contentItems = common.AppendMediaContent(contentItems, mediaResults)

	return &mcp.CallToolResult{Content: contentItems}, nil
}

func inferMimeType(path string) string {
	ext := strings.ToLower(filepath.Ext(path))
	switch ext {
	case ".jpg", ".jpeg":
		return "image/jpeg"
	case ".png":
		return "image/png"
	case ".gif":
		return "image/gif"
	case ".webp":
		return "image/webp"
	case ".pdf":
		return "application/pdf"
	case ".mp4":
		return "video/mp4"
	case ".mov":
		return "video/quicktime"
	case ".webm":
		return "video/webm"
	case ".avi":
		return "video/x-msvideo"
	case ".mkv":
		return "video/x-matroska"
	default:
		// Defaulting to a common image type if extension is unknown, as the API might handle it.
		// A more robust solution might involve reading file headers.
		return "image/png"
	}
}

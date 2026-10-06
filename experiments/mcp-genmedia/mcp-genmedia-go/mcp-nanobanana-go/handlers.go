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

// modelsRejectingSeed lists the canonical Gemini image models that return an API
// error when a seed is supplied. Nano Banana 2.1 rejects seed, temperature, topP,
// topK, and logprobs; of these, seed is the only one this handler ever sends, so
// it is the only one that needs gating here.
var modelsRejectingSeed = map[string]bool{
	"gemini-nano-banana-2.1": true,
}

// seedForModel returns the seed to forward to the API for the given canonical
// model name. For models that reject seed it returns nil (dropping any
// caller-supplied value); for all others it returns seed unchanged.
func seedForModel(model string, seed *int32) *int32 {
	if seed != nil && modelsRejectingSeed[model] {
		log.Printf("Warning: seed is not supported by model %s and will be ignored.", model)
		return nil
	}
	return seed
}

func nanobananaGenerateContentHandler(client *genai.Client, ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "nanobanana_generate_content")
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

	seed, err := common.ParseOptionalNonNegativeInt32(request.GetArguments(), "seed")
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}
	// Drop the seed for models that reject it (gemini-nano-banana-2.1) before it is
	// forwarded to the API. `model` is already the resolved canonical name here.
	seed = seedForModel(model, seed)

	outputDir := ""
	if dir, ok := request.GetArguments()["output_directory"].(string); ok && strings.TrimSpace(dir) != "" {
		outputDir = strings.TrimSpace(dir)
	}

	// gcsBucketURI: explicit "gcs_bucket_uri" argument takes precedence. If not
	// provided, fall back to the server-wide GENMEDIA_BUCKET default (mirrors
	// the fallback behavior documented for the other genmedia MCP tools).
	gcsBucketURI := ""
	if u, ok := request.GetArguments()["gcs_bucket_uri"].(string); ok && strings.TrimSpace(u) != "" {
		gcsBucketURI = strings.TrimSpace(u)
	} else if appConfig != nil && appConfig.GenmediaBucket != "" {
		gcsBucketURI = appConfig.GenmediaBucket + "/nanobanana_outputs/"
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
		attribute.String("gcs_bucket_uri", gcsBucketURI),
	)
	if seed != nil {
		span.SetAttributes(attribute.Int("seed", int(*seed)))
	}

	// --- API Call ---
	log.Printf("Calling GenerateContent with Model: %s, Prompt: \"%s\"", model, prompt)
	startTime := time.Now()

	config := &genai.GenerateContentConfig{
		ResponseModalities: []string{"IMAGE", "TEXT"},
		ImageConfig: &genai.ImageConfig{
			AspectRatio: aspectRatio,
			ImageSize:   imageSize,
		},
		Seed: seed,
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
	return processImageResponse(ctx, resp, request.GetArguments(), outputDir, gcsBucketURI)
}

// persistMediaOutputs is the persistence seam. It is a package-level variable so
// tests can inject a fake and exercise the response-processing wiring (naming,
// two-pass assignment, MediaArtifact.FileName -> seam, collision branch) without
// a live genai client or cloud access.
var persistMediaOutputs = common.PersistMediaOutputs

// processImageResponse builds the human-readable summary and persists each image
// artifact from resp, honoring output_filename-derived names when provided and
// preserving the legacy per-part scheme otherwise. Extracted from the handler so
// the naming + seam wiring is unit-testable (design #842 Phase-1 review nit 4.1).
func processImageResponse(ctx context.Context, resp *genai.GenerateContentResponse, args map[string]any, outputDir, gcsBucketURI string) (*mcp.CallToolResult, error) {
	var responseText strings.Builder
	var savedFiles []string
	// mediaResults collects one entry per image persisted to GCS so the result
	// can carry a resource_link per artifact in addition to the text summary
	// (design #483 Phase 1). Purely additive: the text output below is unchanged.
	var mediaResults []common.MediaResult

	// Check for optional Sherlog header
	if resp.SDKHTTPResponse != nil && resp.SDKHTTPResponse.Headers != nil {
		if link := resp.SDKHTTPResponse.Headers.Get("x-goog-sherlog-link"); link != "" {
			fmt.Fprintf(&responseText, "Optional header capture: %s\n\n", link)
		}
	}
	gentime := time.Now().Format("20060102150405")
	expiry := common.SignedURLExpiryFromEnv("NANOBANANA_SIGNED_URL_EXPIRY_HOURS")

	// First pass: count the generated image artifacts (and capture the MIME type
	// of the first one) so the total count is known before naming — required for
	// deterministic _1..n suffixing when output_filename is set.
	imageCount := 0
	firstImageMime := ""
	for _, candidate := range resp.Candidates {
		for _, part := range candidate.Content.Parts {
			if part.InlineData != nil {
				if imageCount == 0 {
					firstImageMime = part.InlineData.MIMEType
				}
				imageCount++
			}
		}
	}

	// When output_filename is set, precompute client-predictable names via the
	// shared helper (extension forced to the true MIME, deterministic suffixing).
	// When unset, names is nil and each image keeps the default per-part scheme —
	// byte-for-byte unchanged legacy behavior. The precedence contract lives in
	// common.ResolveOutputFilename (nanobanana has no legacy alias of its own).
	base := common.ResolveOutputFilename(args)
	names, err := buildImageFilenames(base, imageCount, firstImageMime)
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}

	// Second pass: preserve the original text/image interleaving exactly and
	// persist each image through the shared seam.
	imgIdx := 0
	for _, candidate := range resp.Candidates {
		for n, part := range candidate.Content.Parts {
			if part.Text != "" {
				responseText.WriteString(part.Text)
			}
			if part.InlineData != nil {
				log.Printf("part %d mime-type: %s", n, part.InlineData.MIMEType)

				var fileName string
				if names != nil {
					fileName = names[imgIdx]
				} else {
					fileName = defaultImageFilename(gentime, n, part.InlineData.MIMEType)
				}
				imgIdx++

				// Collision policy: overwrite with a warning (design §4e). Surface
				// a local collision before the shared seam truncates the file.
				if outputDir != "" {
					if _, statErr := os.Stat(filepath.Join(outputDir, fileName)); statErr == nil {
						log.Printf("Warning: output file %q already exists in %s; overwriting (collision policy).", fileName, outputDir)
					}
				}

				persisted, err := persistMediaOutputs(ctx, common.MediaArtifact{
					Data:     part.InlineData.Data,
					MimeType: part.InlineData.MIMEType,
					FileName: fileName,
				}, outputDir, gcsBucketURI, expiry)
				if err != nil {
					return mcp.NewToolResultError(err.Error()), nil
				}

				if persisted.LocalPath != "" {
					savedFiles = append(savedFiles, persisted.LocalPath)
				}
				if persisted.GCSError != nil {
					log.Printf("failed to upload image to gs://%s/%s: %v", persisted.GCSBucket, persisted.GCSObject, persisted.GCSError)
					fmt.Fprintf(&responseText, "\n\n[Warning: failed to upload generated image to GCS: %v]", persisted.GCSError)
				}
				if persisted.GCSURI != "" {
					savedFiles = append(savedFiles, persisted.GCSURI)
					// Collect a resource_link per GCS artifact (1-based description).
					mediaResults = append(mediaResults, common.MediaResultFromPersisted(
						persisted, part.InlineData.MIMEType,
						fmt.Sprintf("nanobanana output %d of %d", imgIdx, imageCount),
					))
				}
				// Best-effort V4 signed HTTPS URL so clients (e.g. Claude) can
				// fetch/display the image without the bucket being public.
				if persisted.SignedURL != "" {
					fmt.Fprintf(&responseText, "\n\nSigned URL for %s (valid %s):\n%s", persisted.GCSObject, expiry, persisted.SignedURL)
				}

				if persisted.LocalPath == "" && persisted.GCSURI == "" {
					log.Println("Received image data but no output_directory or gcs_bucket_uri was specified/valid. Image not saved.")
				}
			}
		}
	}

	// --- Format Final Result ---
	finalMessage := responseText.String()
	if len(savedFiles) > 0 {
		finalMessage += fmt.Sprintf("\n\nGenerated and saved %d image(s): %s", len(savedFiles), strings.Join(savedFiles, ", "))
	}

	// Text output is unchanged; append one resource_link per GCS artifact.
	content := []mcp.Content{mcp.TextContent{Type: "text", Text: strings.TrimSpace(finalMessage)}}
	content = common.AppendMediaContent(content, mediaResults)
	return &mcp.CallToolResult{Content: content}, nil
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

// buildImageFilenames returns the persisted file names for `count` image
// artifacts of the given MIME type. When the client supplied output_filename
// (base != ""), names are client-predictable and deterministically suffixed via
// the shared common helper. Otherwise it returns nil so the caller falls back to
// its default per-part scheme (byte-for-byte unchanged legacy behavior).
func buildImageFilenames(base string, count int, mimeType string) ([]string, error) {
	if strings.TrimSpace(base) == "" || count < 1 {
		return nil, nil
	}
	return common.BuildOutputFilenames(base, count, mimeType)
}

// defaultImageFilename is nanobanana's legacy naming scheme, used when
// output_filename is unset. Preserved verbatim to guarantee zero regression.
func defaultImageFilename(gentime string, partIndex int, mimeType string) string {
	return fmt.Sprintf("gemini_%s_%d%s", gentime, partIndex, extForMimeType(mimeType))
}

// extForMimeType returns a reasonable file extension for a given image MIME type.
func extForMimeType(mimeType string) string {
	switch mimeType {
	case "image/jpeg":
		return ".jpg"
	case "image/webp":
		return ".webp"
	case "image/gif":
		return ".gif"
	case "image/png":
		return ".png"
	default:
		return ".png"
	}
}

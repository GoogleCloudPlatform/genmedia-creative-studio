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

// Package common provides shared utilities for the MCP Genmedia servers.
//
// This file hoists the omni_video_generation MCP tool plumbing — argument
// parsing/validation and response rendering — that was previously duplicated
// verbatim between mcp-omni-go and mcp-gemini-go. Both servers now call
// ParseOmniToolArgs + GenerateOmniVideo + RenderOmniResult, so their argument
// surface, validation errors, and output text share a single implementation and
// cannot drift (this duplication was the reason input-hardening fixes previously
// had to be applied twice).

package common

import (
	"context"
	"fmt"
	"log"
	"math"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
)

// maxOmniImages is the per-prompt image input limit.
const maxOmniImages = 10

// maxInlineMediaBytes caps the size of a local media file that will be read into
// memory and base64-inlined into the interaction request. Larger files must be
// referenced by a gs:// URI instead (base64 inflates payloads ~33%, and the
// Interactions request body is bounded). 20 MiB is a deliberately conservative cap.
const maxInlineMediaBytes = 20 * 1024 * 1024

// OmniToolArgs holds the parsed and validated arguments for the
// omni_video_generation MCP tool, ready to hand to GenerateOmniVideo (Params)
// and RenderOmniResult (OutputDir/GCSBucketURI). It is produced by
// ParseOmniToolArgs so both mcp-omni-go and mcp-gemini-go share one
// implementation of the tool's argument surface.
type OmniToolArgs struct {
	// Params are the model-call inputs for GenerateOmniVideo.
	Params OmniParams
	// OutputDir is the resolved local output directory ("" when unset).
	OutputDir string
	// GCSBucketURI is the resolved GCS destination prefix, honoring an explicit
	// gcs_bucket_uri argument and otherwise falling back to the server's
	// GENMEDIA_BUCKET + "/omni_outputs/".
	GCSBucketURI string
	// OutputFilename is the client-supplied base output name ("" when unset).
	// When set, RenderOmniResult derives client-predictable, deterministically
	// suffixed names (extension forced to the true media type). omni carries no
	// legacy naming alias.
	OutputFilename string
}

// ParseOmniToolArgs parses and validates the raw MCP tool argument map for the
// omni_video_generation tool. It performs all client-side validation — prompt
// presence, model resolution, the image-count guard BEFORE any file is read,
// the inline-size and directory guards, integer sample_count, and ranged
// temperature/top_p — and returns typed inputs. Validation failures are returned
// as plain errors whose message the caller surfaces verbatim via
// mcp.NewToolResultError, so both servers report byte-identical errors.
func ParseOmniToolArgs(args map[string]interface{}, cfg *Config) (OmniToolArgs, error) {
	var out OmniToolArgs

	// --- Parameter Parsing ---
	prompt, ok := args["prompt"].(string)
	if !ok || strings.TrimSpace(prompt) == "" {
		return out, fmt.Errorf("prompt must be a non-empty string and is required")
	}
	prompt = strings.TrimSpace(prompt)

	outputDir := ""
	if dir, ok := args["output_directory"].(string); ok && strings.TrimSpace(dir) != "" {
		outputDir = strings.TrimSpace(dir)
	}

	// gcsBucketURI: explicit "gcs_bucket_uri" takes precedence, otherwise fall
	// back to the server-wide GENMEDIA_BUCKET default (mirrors the other tools).
	gcsBucketURI := ""
	if u, ok := args["gcs_bucket_uri"].(string); ok && strings.TrimSpace(u) != "" {
		gcsBucketURI = strings.TrimSpace(u)
	} else if cfg != nil && cfg.GenmediaBucket != "" {
		gcsBucketURI = cfg.GenmediaBucket + "/omni_outputs/"
	}

	// Model resolution (honors an optional "model" arg / alias).
	modelArg, _ := args["model"].(string)
	model := DefaultOmniModel
	if resolved, found := ResolveOmniModel(modelArg, cfg.AllowUnsafeModels); found {
		model = resolved.CanonicalName
	} else if strings.TrimSpace(modelArg) != "" {
		return out, fmt.Errorf("unsupported model %q (set ALLOW_UNSAFE_MODELS=true to bypass)", modelArg)
	}

	// Image / video inputs (local paths -> inline bytes; gs:// -> URI).
	// Enforce the image-count limit BEFORE parseMediaRefs reads any file into memory.
	if imgs, ok := args["images"].([]interface{}); ok && len(imgs) > maxOmniImages {
		return out, fmt.Errorf("too many images: %d provided, the model accepts at most %d", len(imgs), maxOmniImages)
	}
	images, err := parseMediaRefs(args["images"], "image")
	if err != nil {
		return out, err
	}
	videos, err := parseMediaRefs(args["videos"], "video")
	if err != nil {
		return out, err
	}

	// sample_count (default 1, clamped to the model max by the shared helper).
	sampleCount := 1
	if raw, present := args["sample_count"]; present {
		n, convErr := toInt(raw)
		if convErr != nil {
			return out, fmt.Errorf("sample_count must be an integer: %v", convErr)
		}
		if n >= 1 {
			sampleCount = n
		}
	}

	// temperature / top_p (optional; validated client-side, then sent in generation_config).
	temperature, err := parseOptionalFloatInRange(args, "temperature", 0.0, 2.0)
	if err != nil {
		return out, err
	}
	topP, err := parseOptionalFloatInRange(args, "top_p", 0.0, 1.0)
	if err != nil {
		return out, err
	}

	out.Params = OmniParams{
		Prompt:      prompt,
		Model:       model,
		Images:      images,
		Videos:      videos,
		SampleCount: sampleCount,
		Temperature: temperature,
		TopP:        topP,
	}
	out.OutputDir = outputDir
	out.GCSBucketURI = gcsBucketURI
	out.OutputFilename = ResolveOutputFilename(args)
	return out, nil
}

// RenderOmniResult persists each returned video (locally and/or to GCS, with a
// best-effort V4 signed URL) via the shared PersistMediaOutputs helper and builds
// the tool's user-facing text response: the optional header-capture line, the
// model text, a thought-step NOTE, per-video GCS warnings / signed URLs, and a
// final saved-files summary. It returns the tool-result content both servers
// return verbatim, so the output can never drift between them: content[0] is the
// trimmed text message (unchanged byte-for-byte) followed by one resource_link
// per video persisted to GCS (design #483).
func RenderOmniResult(ctx context.Context, result *OmniResult, outputDir, gcsBucketURI, outputFilename string) ([]mcp.Content, error) {
	// --- Process / persist output ---
	var responseText strings.Builder
	// mediaResults collects one entry per video persisted to GCS so the result can
	// carry a resource_link per artifact in addition to the text summary
	// (design #483). Purely additive: the text built below is unchanged.
	var mediaResults []MediaResult
	if result.SherlogLink != "" {
		fmt.Fprintf(&responseText, "Optional header capture: %s\n\n", result.SherlogLink)
	}
	if strings.TrimSpace(result.Text) != "" {
		responseText.WriteString(result.Text)
	}
	// Surface any thought/summary reasoning as a NOTE (not as a media output).
	if result.ThoughtSteps > 0 {
		fmt.Fprintf(&responseText, "\n\n[Note: model returned %d reasoning (thought) step(s).]", result.ThoughtSteps)
	}

	gentime := time.Now().Format("20060102150405")
	expiry := SignedURLExpiryFromEnv("OMNI_SIGNED_URL_EXPIRY_HOURS")
	var savedFiles []string

	// When output_filename is set, precompute client-predictable names via the
	// shared helper (extension forced to the true MIME, deterministic _1..n
	// suffixing). When unset, names is nil and each video keeps the legacy
	// omni_<ts>_<n> scheme — byte-for-byte unchanged behavior.
	var names []string
	if strings.TrimSpace(outputFilename) != "" && len(result.Videos) > 0 {
		firstMime := "video/mp4"
		if len(result.VideoMimeTypes) > 0 && result.VideoMimeTypes[0] != "" {
			firstMime = result.VideoMimeTypes[0]
		}
		var err error
		names, err = BuildOutputFilenames(outputFilename, len(result.Videos), firstMime)
		if err != nil {
			return nil, err
		}
	}

	for n, videoBytes := range result.Videos {
		mimeType := "video/mp4"
		if n < len(result.VideoMimeTypes) && result.VideoMimeTypes[n] != "" {
			mimeType = result.VideoMimeTypes[n]
		}

		fileName := fmt.Sprintf("omni_%s_%d%s", gentime, n, videoExtForMimeType(mimeType))
		if names != nil {
			fileName = names[n]
		}

		// Collision policy: overwrite with a warning. Surface a local
		// collision before the shared seam truncates the file.
		if outputDir != "" {
			if _, statErr := os.Stat(filepath.Join(outputDir, fileName)); statErr == nil {
				log.Printf("Warning: output file %q already exists in %s; overwriting (collision policy).", fileName, outputDir)
			}
		}

		persisted, err := PersistMediaOutputs(ctx, MediaArtifact{
			Data:     videoBytes,
			MimeType: mimeType,
			FileName: fileName,
		}, outputDir, gcsBucketURI, expiry)
		if err != nil {
			return nil, err
		}

		if persisted.LocalPath != "" {
			savedFiles = append(savedFiles, persisted.LocalPath)
		}
		if persisted.GCSError != nil {
			log.Printf("failed to upload video to gs://%s/%s: %v", persisted.GCSBucket, persisted.GCSObject, persisted.GCSError)
			fmt.Fprintf(&responseText, "\n\n[Warning: failed to upload generated video to GCS: %v]", persisted.GCSError)
		}
		if persisted.GCSURI != "" {
			savedFiles = append(savedFiles, persisted.GCSURI)
			// Collect a resource_link per GCS-persisted artifact. The 1-based
			// "omni output i of n" description is filled in after the loop (below)
			// so the numerator/denominator reflect the count of videos actually
			// persisted to GCS (consistent with the other servers' len(gcsSavedURIs))
			// rather than the total video count — correct even if a subset of videos
			// lacks a GCS URI. Behavior is identical in the all-or-none common case.
			mediaResults = append(mediaResults, MediaResultFromPersisted(persisted, mimeType, ""))
		}
		if persisted.SignedURL != "" {
			fmt.Fprintf(&responseText, "\n\nSigned URL for %s (valid %s):\n%s", persisted.GCSObject, expiry, persisted.SignedURL)
		}
		if persisted.LocalPath == "" && persisted.GCSURI == "" {
			log.Println("Received video data but no output_directory or gcs_bucket_uri was specified/valid. Video not saved.")
		}
	}

	finalMessage := responseText.String()
	if len(savedFiles) > 0 {
		finalMessage += fmt.Sprintf("\n\nGenerated and saved %d video(s): %s", len(result.Videos), strings.Join(savedFiles, ", "))
	} else {
		finalMessage += fmt.Sprintf("\n\nGenerated %d video(s) but none were saved (set output_directory or gcs_bucket_uri).", len(result.Videos))
	}

	// Fill in the 1-based resource_link descriptions now that the count of videos
	// actually persisted to GCS is known (review NB-2): the denominator is the GCS
	// artifact count (len(mediaResults)), matching the other servers' len(gcsSavedURIs).
	for i := range mediaResults {
		mediaResults[i].Description = fmt.Sprintf("omni output %d of %d", i+1, len(mediaResults))
	}

	// Text output is unchanged; append one resource_link per GCS artifact.
	content := []mcp.Content{mcp.TextContent{Type: "text", Text: strings.TrimSpace(finalMessage)}}
	content = AppendMediaContent(content, mediaResults)
	return content, nil
}

// parseMediaRefs converts a tool argument (expected to be an array of strings,
// each a local file path or a gs:// URI) into OmniMediaRef values. Local paths
// are read into memory; gs:// URIs are passed through by reference. kind is
// "image" or "video" and is used only for error messages and MIME inference.
func parseMediaRefs(arg any, kind string) ([]OmniMediaRef, error) {
	if arg == nil {
		return nil, nil
	}
	list, ok := arg.([]interface{})
	if !ok {
		return nil, fmt.Errorf("%ss must be an array of strings", kind)
	}

	refs := make([]OmniMediaRef, 0, len(list))
	for _, item := range list {
		path, ok := item.(string)
		if !ok || strings.TrimSpace(path) == "" {
			return nil, fmt.Errorf("each %s entry must be a non-empty string (local path or gs:// URI)", kind)
		}
		path = strings.TrimSpace(path)
		mimeType := inferMediaMimeType(path)

		if strings.HasPrefix(path, "gs://") {
			refs = append(refs, OmniMediaRef{URI: path, MimeType: mimeType})
			continue
		}
		// Guard against inlining an oversized file: stat first, and reject files
		// above the inline cap with a hint to use a gs:// URI instead.
		info, statErr := os.Stat(path)
		if statErr != nil {
			return nil, fmt.Errorf("failed to read %s file %q: %w", kind, path, statErr)
		}
		if info.IsDir() {
			return nil, fmt.Errorf("%s path %q is a directory, not a file (expected a local media file or a gs:// URI)", kind, path)
		}
		if info.Size() > maxInlineMediaBytes {
			return nil, fmt.Errorf("%s file %q is %d bytes, exceeding the %d-byte inline limit; upload it to GCS and pass a gs:// URI instead", kind, path, info.Size(), maxInlineMediaBytes)
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("failed to read %s file %q: %w", kind, path, err)
		}
		refs = append(refs, OmniMediaRef{Data: data, MimeType: mimeType})
	}
	return refs, nil
}

// inferMediaMimeType infers an image/video MIME type from a file extension.
func inferMediaMimeType(path string) string {
	switch strings.ToLower(filepath.Ext(path)) {
	case ".jpg", ".jpeg":
		return "image/jpeg"
	case ".png":
		return "image/png"
	case ".webp":
		return "image/webp"
	case ".gif":
		return "image/gif"
	case ".heic":
		return "image/heic"
	case ".heif":
		return "image/heif"
	case ".mp4":
		return "video/mp4"
	case ".mov":
		return "video/quicktime"
	case ".webm":
		return "video/webm"
	case ".mpeg", ".mpg":
		return "video/mpeg"
	case ".flv":
		return "video/x-flv"
	case ".wmv":
		return "video/wmv"
	case ".3gp", ".3gpp":
		return "video/3gpp"
	default:
		return "application/octet-stream"
	}
}

// videoExtForMimeType returns a file extension for a generated video MIME type,
// defaulting to ".mp4" (the Omni model's output format) for unknown or empty
// types so the saved filename's extension matches the actual bytes.
func videoExtForMimeType(mimeType string) string {
	switch strings.ToLower(strings.TrimSpace(mimeType)) {
	case "video/mp4":
		return ".mp4"
	case "video/webm":
		return ".webm"
	case "video/quicktime":
		return ".mov"
	case "video/mpeg":
		return ".mpeg"
	case "video/3gpp":
		return ".3gp"
	case "video/x-flv":
		return ".flv"
	case "video/wmv", "video/x-ms-wmv":
		return ".wmv"
	default:
		return ".mp4"
	}
}

// toInt coerces a JSON-decoded numeric tool argument to an int. MCP arguments
// arrive as float64 for JSON numbers, but integer literals may surface as int /
// int64 depending on the decoder, so those are accepted too. Only these numeric
// types are accepted: a non-integral float64 is rejected, and any non-numeric
// value — including a string, even one of digits — is rejected with an error
// (this function does not parse strings).
func toInt(v any) (int, error) {
	switch n := v.(type) {
	case float64:
		if n != math.Trunc(n) {
			return 0, fmt.Errorf("expected an integer, got %v", n)
		}
		return int(n), nil
	case int:
		return n, nil
	case int64:
		return int(n), nil
	default:
		return 0, fmt.Errorf("expected a number, got %T", v)
	}
}

// toFloat64 coerces a JSON-decoded numeric tool argument to a float64. MCP
// arguments usually arrive as float64, but integer literals may surface as int /
// int64 depending on the decoder, so those are accepted too (mirrors toInt).
func toFloat64(v any) (float64, bool) {
	switch n := v.(type) {
	case float64:
		return n, true
	case float32:
		return float64(n), true
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	default:
		return 0, false
	}
}

// parseOptionalFloatInRange reads an optional float tool argument and validates
// it lies within [min, max]. Returns nil when the argument is absent.
func parseOptionalFloatInRange(args map[string]interface{}, key string, min, max float64) (*float32, error) {
	raw, present := args[key]
	if !present || raw == nil {
		return nil, nil
	}
	f, ok := toFloat64(raw)
	if !ok {
		return nil, fmt.Errorf("%s must be a number", key)
	}
	if f < min || f > max {
		return nil, fmt.Errorf("%s must be in the range [%.1f, %.1f], got %v", key, min, max, f)
	}
	v := float32(f)
	return &v, nil
}

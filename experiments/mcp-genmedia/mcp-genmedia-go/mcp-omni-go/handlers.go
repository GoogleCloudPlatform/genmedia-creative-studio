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

package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
)

// omniVideoGenerationHandler is a thin MCP wrapper around the shared mcp-common
// Omni plumbing: it parses/validates the tool arguments via
// common.ParseOmniToolArgs, calls the shared common.GenerateOmniVideo entry
// point, and renders the response via common.RenderOmniResult. All argument
// parsing, validation, and output formatting live once in mcp-common so this
// server and mcp-gemini-go can never drift.
func omniVideoGenerationHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	tr := otel.Tracer(serviceName)
	ctx, span := tr.Start(ctx, "omni_video_generation")
	defer span.End()

	parsed, err := common.ParseOmniToolArgs(request.GetArguments(), appConfig)
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}

	span.SetAttributes(
		attribute.String("prompt", parsed.Params.Prompt),
		attribute.String("model", parsed.Params.Model),
		attribute.String("resolution", parsed.Params.Resolution),
		attribute.String("aspect_ratio", parsed.Params.AspectRatio),
		attribute.Int("duration_seconds", parsed.Params.DurationSeconds),
		attribute.String("output_directory", parsed.OutputDir),
		attribute.String("gcs_bucket_uri", parsed.GCSBucketURI),
		attribute.Int("images", len(parsed.Params.Images)),
		attribute.Int("videos", len(parsed.Params.Videos)),
		attribute.Int("sample_count", parsed.Params.SampleCount),
	)

	// --- Shared Omni call ---
	log.Printf("Calling GenerateOmniVideo Model=%s resolution=%q aspect_ratio=%q duration=%ds sample_count=%d images=%d videos=%d", parsed.Params.Model, parsed.Params.Resolution, parsed.Params.AspectRatio, parsed.Params.DurationSeconds, parsed.Params.SampleCount, len(parsed.Params.Images), len(parsed.Params.Videos))
	startTime := time.Now()

	result, err := common.GenerateOmniVideo(ctx, appConfig, parsed.Params)

	apiCallDuration := time.Since(startTime)
	log.Printf("GenerateOmniVideo call took: %v", apiCallDuration)
	span.SetAttributes(attribute.Float64("duration_ms", float64(apiCallDuration.Milliseconds())))

	if err != nil {
		span.RecordError(err)
		return mcp.NewToolResultError(fmt.Sprintf("error generating Omni video: %v", err)), nil
	}
	span.SetAttributes(attribute.Int("video_count", len(result.Videos)))

	// --- Render / persist output (shared) ---
	content, err := common.RenderOmniResult(ctx, result, parsed.OutputDir, parsed.GCSBucketURI, parsed.OutputFilename)
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}

	return &mcp.CallToolResult{Content: content}, nil
}

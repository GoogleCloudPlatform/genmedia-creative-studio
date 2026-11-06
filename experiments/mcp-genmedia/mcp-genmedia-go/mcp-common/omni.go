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

package common

import (
	"context"
	"encoding/base64"
	"fmt"
	"strings"
)

// omniVideoMimePrefix is the MIME prefix identifying a video output part.
const omniVideoMimePrefix = "video/"

// MaxOmniSampleCount is the maximum number of videos the Omni model produces per
// prompt (findings §1). sample_count is clamped to this ceiling.
const MaxOmniSampleCount = 3

// Explicit Omni video tasks sent as generation_config.video_config.task. The
// remaining modes (text-to-video, image-to-video, first/last frame, edit) are
// inferred by the model from the prompt and inputs, so no task is sent for them.
//
// Inference from images (verified live on gemini-omni-1.2-flash and
// gemini-omni-1.1-flash-preview): with no task, ONE image is used as the literal
// first frame (image-to-video) and TWO images, in the order given, are the first
// and last frame. Sending task=image_to_video with the same images behaves
// identically, and the API has no dedicated first/last-frame task. Subject or
// style references therefore need the explicit OmniTaskReferenceToVideo task.
const (
	// OmniTaskExtend continues an input video (video + optional text prompt).
	OmniTaskExtend = "extend"
	// OmniTaskUpscale re-renders an input video at a higher resolution
	// (video only: the API rejects a text part for this task).
	OmniTaskUpscale = "upscale"
	// OmniTaskReferenceToVideo treats the input images as subject/style
	// references instead of frames (prompt + one or more images). Without it a
	// single image is read as the first frame and two as first/last frames.
	OmniTaskReferenceToVideo = "reference_to_video"
)

// OmniTasks lists every explicit task the tool accepts, in schema order. Which
// of them a given model supports is declared per model (SupportedTasks).
var OmniTasks = []string{OmniTaskExtend, OmniTaskUpscale, OmniTaskReferenceToVideo}

// OmniMediaRef is a single image or video input to an Omni generation. It is
// either inline bytes (Data, base64-encoded onto the wire) or a gs:// URI
// (URI) — exactly one should be set. MimeType is required for both.
type OmniMediaRef struct {
	// Data holds raw media bytes for an inline input part. Mutually exclusive with URI.
	Data []byte
	// URI is a gs:// URI for a media input part. Mutually exclusive with Data.
	URI string
	// MimeType is the media MIME type (e.g. "image/png", "video/mp4").
	MimeType string
}

// OmniParams are the inputs to a Gemini Omni video generation call (design §5.1).
type OmniParams struct {
	// Prompt is the text prompt (required, except for the upscale task which is
	// video-only and must not carry text).
	Prompt string
	// Task is the optional explicit video task (one of OmniTasks). Empty lets
	// the model infer the mode from the inputs.
	Task string
	// Model is the resolved canonical model ID. If empty, the default Omni model
	// is used (see ResolveOmniModel).
	Model string
	// Images are optional image inputs (image-conditioned generation).
	Images []OmniMediaRef
	// Videos are optional video inputs (reference / editing).
	Videos []OmniMediaRef
	// SampleCount is the number of videos to generate (1..MaxOmniSampleCount).
	// Values < 1 are treated as 1; values above the max are clamped. Because the
	// endpoint rejects generation_config.candidate_count, multiple samples are
	// produced by issuing that many sequential interactions.
	SampleCount int
	// Temperature is the optional sampling temperature (0.0-2.0). Sent in
	// generation_config only when non-nil (Q1: empirically accepted).
	Temperature *float32
	// TopP is the optional nucleus-sampling top_p (0.0-1.0). Sent in
	// generation_config only when non-nil (Q1: empirically accepted).
	TopP *float32
	// Resolution is the optional output video resolution (e.g. "360p", "720p",
	// "1080p", "4k"). Sent in response_format when non-empty.
	Resolution string
	// AspectRatio is the optional output video aspect ratio (e.g. "16:9", "9:16").
	// Sent in response_format when non-empty.
	AspectRatio string
	// DurationSeconds is the optional video duration in seconds (up to 10s).
	// Sent in response_format as "<N>s" when > 0.
	DurationSeconds int
}

// OmniResult is the mapped output of a Gemini Omni video generation call.
type OmniResult struct {
	// Videos holds the decoded MP4 bytes for each returned video part.
	Videos [][]byte
	// VideoMimeTypes holds the MIME type for each entry in Videos (index-aligned).
	VideoMimeTypes []string
	// Text is the concatenated model text output (excluding thought summaries).
	Text string
	// ThoughtSteps is the number of "thought" steps the model returned.
	ThoughtSteps int
	// SherlogLink is the optional captured x-goog-sherlog-link, if enabled.
	SherlogLink string
	// Status is the interaction status reported by the API (e.g. "completed").
	Status string
}

// GenerateOmniVideo is the single shared entry point both mcp-omni-go and
// mcp-gemini-go call, so the request/response contract can never drift. It builds
// the Omni envelope (lowercase response_modalities, image/video input parts,
// optional generation_config), calls the Interactions client sample_count times,
// and aggregates the decoded MP4 bytes + text (design §7.2).
func GenerateOmniVideo(ctx context.Context, cfg *Config, p OmniParams) (*OmniResult, error) {
	if strings.TrimSpace(p.Prompt) == "" && p.Task != OmniTaskUpscale {
		return nil, fmt.Errorf("omni: prompt must be a non-empty string")
	}

	client, err := NewInteractionsClient(ctx, cfg)
	if err != nil {
		return nil, err
	}
	return generateOmniVideoWithClient(ctx, client, p)
}

// generateOmniVideoWithClient runs the generation against a provided
// InteractionsClient. It is separated from GenerateOmniVideo so the multi-sample
// aggregation is unit-testable with a fake client (no ADC required).
func generateOmniVideoWithClient(ctx context.Context, client InteractionsClient, p OmniParams) (*OmniResult, error) {
	model := p.Model
	if strings.TrimSpace(model) == "" {
		model = DefaultOmniModel
	}

	samples := clampSampleCount(p.SampleCount)
	req, err := buildOmniRequest(model, p)
	if err != nil {
		return nil, err
	}

	agg := &OmniResult{}
	for i := 0; i < samples; i++ {
		resp, err := client.Create(ctx, req)
		if err != nil {
			return nil, fmt.Errorf("omni: sample %d/%d failed: %w", i+1, samples, err)
		}
		r, err := mapOmniResponse(resp)
		if err != nil {
			return nil, fmt.Errorf("omni: sample %d/%d: %w", i+1, samples, err)
		}
		agg.Videos = append(agg.Videos, r.Videos...)
		agg.VideoMimeTypes = append(agg.VideoMimeTypes, r.VideoMimeTypes...)
		agg.ThoughtSteps += r.ThoughtSteps
		if r.Text != "" {
			if agg.Text != "" {
				agg.Text += "\n"
			}
			agg.Text += r.Text
		}
		// Carry the last sample's status/sherlog link (representative of the batch).
		agg.Status = r.Status
		if r.SherlogLink != "" {
			agg.SherlogLink = r.SherlogLink
		}
	}

	if len(agg.Videos) == 0 {
		return agg, fmt.Errorf("omni: no video output found in interaction response(s) (status=%q)", agg.Status)
	}
	return agg, nil
}

// clampSampleCount normalizes a requested sample count into [1, MaxOmniSampleCount].
func clampSampleCount(n int) int {
	if n < 1 {
		return 1
	}
	if n > MaxOmniSampleCount {
		return MaxOmniSampleCount
	}
	return n
}

// buildOmniRequest constructs the Omni interaction envelope. response_modalities
// is lowercase ["text","video"] per the live wire (findings §3). Image/video
// inputs become additional content parts; sampling controls become a
// generation_config (only when set).
func buildOmniRequest(model string, p OmniParams) (*InteractionRequest, error) {
	if err := validateOmniTask(p); err != nil {
		return nil, err
	}

	var content []Part
	if strings.TrimSpace(p.Prompt) != "" {
		content = append(content, Part{Type: "text", Text: p.Prompt})
	}

	imageParts, err := mediaRefsToParts("image", p.Images)
	if err != nil {
		return nil, err
	}
	content = append(content, imageParts...)

	videoParts, err := mediaRefsToParts("video", p.Videos)
	if err != nil {
		return nil, err
	}
	content = append(content, videoParts...)

	req := &InteractionRequest{
		Model:              model,
		ResponseModalities: []string{"text", "video"},
		Input: []InputItem{
			{Type: "user_input", Content: content},
		},
		Store: false,
	}

	if p.Temperature != nil || p.TopP != nil || p.Task != "" {
		req.GenerationConfig = &GenerationConfig{Temperature: p.Temperature, TopP: p.TopP}
		if p.Task != "" {
			req.GenerationConfig.VideoConfig = &VideoConfig{Task: p.Task}
		}
	}

	if p.Resolution != "" || p.AspectRatio != "" || p.DurationSeconds > 0 {
		rf := OmniVideoResponseFormat{
			Type:        "video",
			Resolution:  p.Resolution,
			AspectRatio: p.AspectRatio,
		}
		if p.DurationSeconds > 0 {
			rf.Duration = fmt.Sprintf("%ds", p.DurationSeconds)
		}
		req.ResponseFormat = []OmniVideoResponseFormat{rf}
	}

	return req, nil
}

// validateOmniTask enforces the input contract of the explicit video tasks
// (verified live against gemini-omni-1.2-flash): extend and upscale take exactly
// one input video and no images, and neither takes an aspect ratio or duration
// (the output keeps the input's framing; extend adds a fixed span). Upscale is
// video-only: the API answers a text part with a 400. reference_to_video takes a
// prompt and one or more images (verified with 1-3) and, being a generative
// mode, accepts aspect_ratio and duration_seconds like a plain generation.
func validateOmniTask(p OmniParams) error {
	switch p.Task {
	case "":
		return nil
	case OmniTaskReferenceToVideo:
		return validateOmniReferenceToVideo(p)
	case OmniTaskExtend, OmniTaskUpscale:
	default:
		return fmt.Errorf("omni: unsupported task %q (supported: %s)", p.Task, strings.Join(OmniTasks, ", "))
	}
	if len(p.Videos) != 1 {
		return fmt.Errorf("omni: task %q requires exactly one input video, got %d", p.Task, len(p.Videos))
	}
	if len(p.Images) > 0 {
		return fmt.Errorf("omni: task %q does not accept input images", p.Task)
	}
	if p.AspectRatio != "" || p.DurationSeconds > 0 {
		return fmt.Errorf("omni: task %q does not accept aspect_ratio or duration_seconds", p.Task)
	}
	if p.Task == OmniTaskUpscale && strings.TrimSpace(p.Prompt) != "" {
		return fmt.Errorf("omni: task %q is video-only and does not accept a prompt", p.Task)
	}
	return nil
}

// validateOmniReferenceToVideo checks the reference_to_video input contract: a
// prompt and at least one reference image. Input videos are not part of the
// verified contract, so they are rejected rather than sent untested.
func validateOmniReferenceToVideo(p OmniParams) error {
	if strings.TrimSpace(p.Prompt) == "" {
		return fmt.Errorf("omni: task %q requires a prompt", p.Task)
	}
	if len(p.Images) < 1 {
		return fmt.Errorf("omni: task %q requires at least one reference image in images", p.Task)
	}
	if len(p.Videos) > 0 {
		return fmt.Errorf("omni: task %q does not accept input videos", p.Task)
	}
	return nil
}

// mediaRefsToParts converts input media refs into interaction Parts of the given
// type ("image" or "video"). Inline bytes are base64-encoded; gs:// refs are sent
// by URI. Exactly one of Data/URI must be set per ref.
func mediaRefsToParts(partType string, refs []OmniMediaRef) ([]Part, error) {
	parts := make([]Part, 0, len(refs))
	for i, ref := range refs {
		switch {
		case len(ref.Data) > 0 && ref.URI != "":
			return nil, fmt.Errorf("omni: %s input %d has both inline data and a URI (set exactly one)", partType, i)
		case len(ref.Data) > 0:
			parts = append(parts, Part{
				Type:     partType,
				MimeType: ref.MimeType,
				Data:     base64.StdEncoding.EncodeToString(ref.Data),
			})
		case ref.URI != "":
			parts = append(parts, Part{
				Type:     partType,
				MimeType: ref.MimeType,
				URI:      ref.URI,
			})
		default:
			return nil, fmt.Errorf("omni: %s input %d has neither inline data nor a URI", partType, i)
		}
	}
	return parts, nil
}

// mapOmniResponse walks the interaction's steps[] (falling back to outputs[]),
// decoding video parts to bytes and concatenating text. It counts thought steps
// and is tolerant of both nested (Omni) and flat (Lyria-style) media shapes.
func mapOmniResponse(resp *InteractionResponse) (*OmniResult, error) {
	if resp == nil {
		return nil, fmt.Errorf("omni: nil interaction response")
	}

	result := &OmniResult{
		SherlogLink: resp.SherlogLink,
		Status:      resp.Status,
	}

	steps := resp.Steps
	if len(steps) == 0 {
		// Some interaction shapes place results in outputs[] rather than steps[].
		steps = resp.Outputs
	}

	var textBuilder strings.Builder
	for _, step := range steps {
		if step.Type == "thought" {
			result.ThoughtSteps++
			continue
		}

		// Nested content parts (Omni's model_output shape).
		for _, part := range step.Content {
			switch {
			case part.Type == "text" || part.Text != "":
				textBuilder.WriteString(part.Text)
			case strings.HasPrefix(part.MimeType, omniVideoMimePrefix) || part.Type == "video":
				decoded, err := base64.StdEncoding.DecodeString(part.Data)
				if err != nil {
					return nil, fmt.Errorf("omni: failed to decode base64 video data: %w", err)
				}
				result.Videos = append(result.Videos, decoded)
				result.VideoMimeTypes = append(result.VideoMimeTypes, partMimeOrDefault(part.MimeType))
			}
		}

		// Flat media at the step level (Lyria-style outputs[] parts).
		if len(step.Content) == 0 {
			switch {
			case step.Type == "text" || step.Text != "":
				textBuilder.WriteString(step.Text)
			case strings.HasPrefix(step.MimeType, omniVideoMimePrefix) || step.Type == "video":
				decoded, err := base64.StdEncoding.DecodeString(step.Data)
				if err != nil {
					return nil, fmt.Errorf("omni: failed to decode base64 video data: %w", err)
				}
				result.Videos = append(result.Videos, decoded)
				result.VideoMimeTypes = append(result.VideoMimeTypes, partMimeOrDefault(step.MimeType))
			}
		}
	}

	result.Text = textBuilder.String()

	if len(result.Videos) == 0 {
		return result, fmt.Errorf("omni: no video output found in interaction response (status=%q)", resp.Status)
	}
	return result, nil
}

// partMimeOrDefault returns the given MIME type or a video/mp4 default.
func partMimeOrDefault(mime string) string {
	if mime == "" {
		return "video/mp4"
	}
	return mime
}

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

package common

import (
	"context"
	"encoding/base64"
	"errors"
	"testing"
)

// errFakeTransport is a sentinel error used by the fake Interactions client.
var errFakeTransport = errors.New("fake transport error")

// sampleMP4 is a tiny byte sequence with a valid MP4 "ftyp" box, used to verify
// the steps[] -> decoded bytes mapping without a live call.
var sampleMP4 = []byte{
	0x00, 0x00, 0x00, 0x18, 'f', 't', 'y', 'p', 'i', 's', 'o', 'm',
	0x00, 0x00, 0x02, 0x00, 'i', 's', 'o', 'm',
}

// omniResponseJSON reproduces the observed live Omni response drift:
// results in steps[] (not outputs[]), a leading thought step, created/updated
// timestamps, lowercase status, and extra usage fields — all of which the mapper
// must tolerate while still recovering the video bytes.
func omniResponseJSON(b64video string) string {
	// Mirrors the observed live wire (2026-05-20): RFC3339 created/updated, a
	// thought step whose "summary" is an ARRAY of parts (not a string) plus a
	// "signature" string, usage fields with *_by_modality arrays, and results in
	// steps[]. A tolerant decode must ignore all of these and still recover video.
	return `{
		"id": "abc123",
		"object": "interaction",
		"model": "gemini-omni-flash-preview",
		"status": "completed",
		"role": "model",
		"created": "2026-08-10T14:41:24Z",
		"updated": "2026-08-10T14:41:24Z",
		"steps": [
			{"type": "thought", "signature": "AY89a1RDWvi", "summary": [{"type": "text", "text": "thinking about balloons"}]},
			{"type": "model_output", "content": [
				{"type": "text", "text": "Here is your video."},
				{"type": "video", "mime_type": "video/mp4", "data": "` + b64video + `"}
			]}
		],
		"usage": {"total_tokens": 17560, "total_input_tokens": 15, "input_tokens_by_modality": [{"modality": "text", "tokens": 15}], "total_output_tokens": 17376, "output_tokens_by_modality": [{"modality": "video", "tokens": 17376}], "total_tool_use_tokens": 0, "total_thought_tokens": 169}
	}`
}

func TestDecodeAndMapOmniResponse(t *testing.T) {
	b64 := base64.StdEncoding.EncodeToString(sampleMP4)
	resp, err := decodeInteractionResponse([]byte(omniResponseJSON(b64)))
	if err != nil {
		t.Fatalf("decodeInteractionResponse returned error: %v", err)
	}

	if resp.Status != "completed" {
		t.Errorf("status = %q, want completed", resp.Status)
	}
	if len(resp.Steps) != 2 {
		t.Fatalf("len(Steps) = %d, want 2", len(resp.Steps))
	}

	result, err := mapOmniResponse(resp)
	if err != nil {
		t.Fatalf("mapOmniResponse returned error: %v", err)
	}
	if result.ThoughtSteps != 1 {
		t.Errorf("ThoughtSteps = %d, want 1", result.ThoughtSteps)
	}
	if result.Text != "Here is your video." {
		t.Errorf("Text = %q, want %q", result.Text, "Here is your video.")
	}
	if len(result.Videos) != 1 {
		t.Fatalf("len(Videos) = %d, want 1", len(result.Videos))
	}
	if string(result.Videos[0]) != string(sampleMP4) {
		t.Errorf("decoded video bytes do not match the source bytes")
	}
	if !hasFtypBox(result.Videos[0]) {
		t.Errorf("decoded video is missing an ftyp box")
	}
	if len(result.VideoMimeTypes) != 1 || result.VideoMimeTypes[0] != "video/mp4" {
		t.Errorf("VideoMimeTypes = %v, want [video/mp4]", result.VideoMimeTypes)
	}
}

func TestMapOmniResponseNoVideo(t *testing.T) {
	resp := &InteractionResponse{
		Status: "completed",
		Steps: []Step{
			{Type: "model_output", Content: []Part{{Type: "text", Text: "sorry, no video"}}},
		},
	}
	if _, err := mapOmniResponse(resp); err == nil {
		t.Errorf("expected an error when no video part is present, got nil")
	}
}

func TestBuildOmniRequest(t *testing.T) {
	req, err := buildOmniRequest("gemini-omni-flash-preview", OmniParams{Prompt: "a red balloon"})
	if err != nil {
		t.Fatalf("buildOmniRequest returned error: %v", err)
	}
	if req.Model != "gemini-omni-flash-preview" {
		t.Errorf("Model = %q", req.Model)
	}
	if len(req.ResponseModalities) != 2 || req.ResponseModalities[0] != "text" || req.ResponseModalities[1] != "video" {
		t.Errorf("ResponseModalities = %v, want lowercase [text video]", req.ResponseModalities)
	}
	if len(req.Input) != 1 || req.Input[0].Type != "user_input" {
		t.Fatalf("Input shape unexpected: %+v", req.Input)
	}
	if len(req.Input[0].Content) != 1 || req.Input[0].Content[0].Text != "a red balloon" {
		t.Errorf("Input content unexpected: %+v", req.Input[0].Content)
	}
	if req.GenerationConfig != nil {
		t.Errorf("GenerationConfig should be nil when no sampling params set, got %+v", req.GenerationConfig)
	}
}

func TestBuildOmniRequestWithInputsAndSampling(t *testing.T) {
	temp := float32(0.7)
	topP := float32(0.9)
	req, err := buildOmniRequest("gemini-omni-flash-preview", OmniParams{
		Prompt:      "animate this",
		Images:      []OmniMediaRef{{Data: []byte("PNGDATA"), MimeType: "image/png"}},
		Videos:      []OmniMediaRef{{URI: "gs://bucket/clip.mp4", MimeType: "video/mp4"}},
		Temperature: &temp,
		TopP:        &topP,
	})
	if err != nil {
		t.Fatalf("buildOmniRequest returned error: %v", err)
	}
	content := req.Input[0].Content
	// text + image + video = 3 parts, in that order.
	if len(content) != 3 {
		t.Fatalf("len(content) = %d, want 3: %+v", len(content), content)
	}
	if content[0].Type != "text" || content[0].Text != "animate this" {
		t.Errorf("part[0] = %+v, want text 'animate this'", content[0])
	}
	if content[1].Type != "image" || content[1].MimeType != "image/png" {
		t.Errorf("part[1] = %+v, want image/png", content[1])
	}
	if got := base64.StdEncoding.EncodeToString([]byte("PNGDATA")); content[1].Data != got {
		t.Errorf("image data = %q, want base64 %q", content[1].Data, got)
	}
	if content[1].URI != "" {
		t.Errorf("inline image should not set URI, got %q", content[1].URI)
	}
	if content[2].Type != "video" || content[2].URI != "gs://bucket/clip.mp4" || content[2].Data != "" {
		t.Errorf("part[2] = %+v, want video by URI", content[2])
	}
	if req.GenerationConfig == nil || req.GenerationConfig.Temperature == nil || *req.GenerationConfig.Temperature != 0.7 {
		t.Errorf("GenerationConfig.Temperature not set correctly: %+v", req.GenerationConfig)
	}
	if req.GenerationConfig.TopP == nil || *req.GenerationConfig.TopP != 0.9 {
		t.Errorf("GenerationConfig.TopP not set correctly: %+v", req.GenerationConfig)
	}
}

func TestMediaRefsToPartsErrors(t *testing.T) {
	if _, err := mediaRefsToParts("image", []OmniMediaRef{{MimeType: "image/png"}}); err == nil {
		t.Errorf("expected error for a ref with neither Data nor URI")
	}
	if _, err := mediaRefsToParts("image", []OmniMediaRef{{Data: []byte("x"), URI: "gs://b/o", MimeType: "image/png"}}); err == nil {
		t.Errorf("expected error for a ref with both Data and URI")
	}
}

func TestClampSampleCount(t *testing.T) {
	cases := []struct{ in, want int }{
		{-3, 1}, {0, 1}, {1, 1}, {2, 2}, {3, 3}, {4, 3}, {100, 3},
	}
	for _, c := range cases {
		if got := clampSampleCount(c.in); got != c.want {
			t.Errorf("clampSampleCount(%d) = %d, want %d", c.in, got, c.want)
		}
	}
}

// fakeInteractionsClient returns a fixed response (or error) for each Create,
// recording how many times it was called — enough to exercise the multi-sample
// aggregation in generateOmniVideoWithClient without ADC or a live call.
type fakeInteractionsClient struct {
	calls int
	resp  *InteractionResponse
	err   error
}

func (f *fakeInteractionsClient) Create(_ context.Context, _ *InteractionRequest) (*InteractionResponse, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	return f.resp, nil
}

func TestGenerateOmniVideoWithClientMultiSample(t *testing.T) {
	b64 := base64.StdEncoding.EncodeToString(sampleMP4)
	resp, err := decodeInteractionResponse([]byte(omniResponseJSON(b64)))
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	fake := &fakeInteractionsClient{resp: resp}

	result, err := generateOmniVideoWithClient(context.Background(), fake, OmniParams{Prompt: "x", SampleCount: 3})
	if err != nil {
		t.Fatalf("generateOmniVideoWithClient: %v", err)
	}
	if fake.calls != 3 {
		t.Errorf("Create called %d times, want 3", fake.calls)
	}
	if len(result.Videos) != 3 {
		t.Errorf("len(Videos) = %d, want 3 (one per sample)", len(result.Videos))
	}
	if result.ThoughtSteps != 3 {
		t.Errorf("ThoughtSteps = %d, want 3", result.ThoughtSteps)
	}
	for i, v := range result.Videos {
		if !hasFtypBox(v) {
			t.Errorf("video %d missing ftyp box", i)
		}
	}
}

func TestGenerateOmniVideoWithClientClampsAndErrors(t *testing.T) {
	// A sample count above the max is clamped to MaxOmniSampleCount calls.
	b64 := base64.StdEncoding.EncodeToString(sampleMP4)
	resp, _ := decodeInteractionResponse([]byte(omniResponseJSON(b64)))
	fake := &fakeInteractionsClient{resp: resp}
	if _, err := generateOmniVideoWithClient(context.Background(), fake, OmniParams{Prompt: "x", SampleCount: 99}); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if fake.calls != MaxOmniSampleCount {
		t.Errorf("Create called %d times, want %d (clamped)", fake.calls, MaxOmniSampleCount)
	}

	// A transport error is surfaced with sample context.
	failing := &fakeInteractionsClient{err: errFakeTransport}
	if _, err := generateOmniVideoWithClient(context.Background(), failing, OmniParams{Prompt: "x", SampleCount: 2}); err == nil {
		t.Errorf("expected error from failing client, got nil")
	}
}

func TestResolveOmniModel(t *testing.T) {
	cases := []struct {
		in    string
		want  string
		found bool
	}{
		{"", "gemini-omni-1.1-flash-preview", true},
		{"gemini-omni-1.1-flash-preview", "gemini-omni-1.1-flash-preview", true},
		{"Omni", "gemini-omni-1.1-flash-preview", true},
		// Legacy model kept selectable via explicit ID / alias (Q1).
		{"gemini-omni-flash-preview", "gemini-omni-flash-preview", true},
		{"Gemini Omni Flash", "gemini-omni-flash-preview", true},
		{"nonexistent-model", "", false},
	}
	for _, c := range cases {
		info, found := ResolveOmniModel(c.in, false)
		if found != c.found {
			t.Errorf("ResolveOmniModel(%q) found = %v, want %v", c.in, found, c.found)
			continue
		}
		if found && info.CanonicalName != c.want {
			t.Errorf("ResolveOmniModel(%q) = %q, want %q", c.in, info.CanonicalName, c.want)
		}
	}

	// allowUnsafe passes through an unknown model.
	info, found := ResolveOmniModel("some-future-omni", true)
	if !found || info.CanonicalName != "some-future-omni" {
		t.Errorf("allowUnsafe fallback failed: found=%v info=%+v", found, info)
	}
}

// hasFtypBox reports whether the bytes contain an MP4 "ftyp" box marker in the
// first 12 bytes (bytes 4-8), matching the acceptance-gate ftyp check.
func hasFtypBox(b []byte) bool {
	return len(b) >= 8 && string(b[4:8]) == "ftyp"
}

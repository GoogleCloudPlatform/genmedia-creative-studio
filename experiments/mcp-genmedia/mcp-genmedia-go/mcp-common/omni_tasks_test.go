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
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"slices"
	"strings"
	"testing"

	"github.com/mark3labs/mcp-go/mcp"
)

const (
	omni12 = "gemini-omni-1.2-flash"
	omni11 = "gemini-omni-1.1-flash-preview"
)

// TestParseOmniToolArgsTasks covers the extend/upscale input contract verified
// live against gemini-omni-1.2-flash.
func TestParseOmniToolArgsTasks(t *testing.T) {
	cfg := &Config{GenmediaBucket: "my-bucket"}
	vid := []interface{}{"gs://bucket/clip.mp4"}
	imgs2 := []interface{}{"gs://bucket/first.png", "gs://bucket/last.png"}

	cases := map[string]struct {
		args    map[string]interface{}
		wantErr string // substring; empty means success
		check   func(t *testing.T, p OmniParams)
	}{
		"upscale defaults to 1080p with no prompt": {
			args: map[string]interface{}{"task": "upscale", "model": omni12, "videos": vid},
			check: func(t *testing.T, p OmniParams) {
				if p.Task != OmniTaskUpscale || p.Prompt != "" || p.Resolution != "1080p" {
					t.Errorf("params = %+v, want upscale/no prompt/1080p", p)
				}
			},
		},
		"upscale 4k": {
			args: map[string]interface{}{"task": "upscale", "model": omni12, "videos": vid, "resolution": "4K"},
			check: func(t *testing.T, p OmniParams) {
				if p.Resolution != "4k" {
					t.Errorf("Resolution = %q, want 4k", p.Resolution)
				}
			},
		},
		"task is case-insensitive and uses the default model": {
			args: map[string]interface{}{"task": " Extend ", "prompt": "keep going", "videos": vid},
			check: func(t *testing.T, p OmniParams) {
				if p.Task != OmniTaskExtend || p.Model != omni12 {
					t.Errorf("params = %+v, want extend on %s", p, omni12)
				}
			},
		},
		"extend with prompt and one video": {
			args: map[string]interface{}{"task": "extend", "model": omni12, "prompt": "the camera pulls back", "videos": vid, "resolution": "720p"},
			check: func(t *testing.T, p OmniParams) {
				if p.Prompt != "the camera pulls back" || len(p.Videos) != 1 || p.Resolution != "720p" {
					t.Errorf("params = %+v", p)
				}
			},
		},
		"upscale rejects 720p": {
			args:    map[string]interface{}{"task": "upscale", "model": omni12, "videos": vid, "resolution": "720p"},
			wantErr: "1080p or 4k",
		},
		"upscale rejects a prompt": {
			args:    map[string]interface{}{"task": "upscale", "model": omni12, "videos": vid, "prompt": "sharper"},
			wantErr: "video-only",
		},
		"upscale rejects images": {
			args:    map[string]interface{}{"task": "upscale", "model": omni12, "videos": vid, "images": []interface{}{"gs://bucket/a.png"}},
			wantErr: "does not accept input images",
		},
		"upscale rejects aspect_ratio": {
			args:    map[string]interface{}{"task": "upscale", "model": omni12, "videos": vid, "aspect_ratio": "9:16"},
			wantErr: "aspect_ratio or duration_seconds",
		},
		"extend rejects duration_seconds": {
			args:    map[string]interface{}{"task": "extend", "model": omni12, "prompt": "more", "videos": vid, "duration_seconds": float64(5)},
			wantErr: "aspect_ratio or duration_seconds",
		},
		"extend requires a prompt": {
			args:    map[string]interface{}{"task": "extend", "model": omni12, "videos": vid},
			wantErr: "prompt must be a non-empty string",
		},
		"extend requires a video": {
			args:    map[string]interface{}{"task": "extend", "model": omni12, "prompt": "more"},
			wantErr: "exactly one input video, got 0",
		},
		"extend rejects two videos": {
			args:    map[string]interface{}{"task": "extend", "model": omni12, "prompt": "more", "videos": []interface{}{"gs://bucket/a.mp4", "gs://bucket/b.mp4"}},
			wantErr: "exactly one input video, got 2",
		},
		"1.1 does not support tasks": {
			args:    map[string]interface{}{"task": "extend", "model": omni11, "prompt": "more", "videos": vid},
			wantErr: "not supported by model",
		},
		"unknown task": {
			args:    map[string]interface{}{"task": "loop", "model": omni12, "prompt": "x", "videos": vid},
			wantErr: "unsupported task",
		},
		"no task still requires a prompt": {
			args:    map[string]interface{}{"model": omni12},
			wantErr: "prompt must be a non-empty string",
		},
		"no task keeps inferred modes untouched": {
			args: map[string]interface{}{"model": omni12, "prompt": "a cat", "videos": vid, "duration_seconds": float64(15), "aspect_ratio": "9:16"},
			check: func(t *testing.T, p OmniParams) {
				if p.Task != "" || p.DurationSeconds != 15 || p.AspectRatio != "9:16" {
					t.Errorf("params = %+v", p)
				}
			},
		},
		"no task with two images stays inferred (first/last frame)": {
			args: map[string]interface{}{"model": omni12, "prompt": "day to night", "images": imgs2},
			check: func(t *testing.T, p OmniParams) {
				if p.Task != "" || len(p.Images) != 2 {
					t.Errorf("params = %+v, want no task and two images", p)
				}
			},
		},
		"reference_to_video with images, aspect and duration": {
			args: map[string]interface{}{"task": "reference_to_video", "model": omni12, "prompt": "the ball rolls", "images": imgs2, "aspect_ratio": "9:16", "duration_seconds": float64(5)},
			check: func(t *testing.T, p OmniParams) {
				if p.Task != OmniTaskReferenceToVideo || len(p.Images) != 2 || p.AspectRatio != "9:16" || p.DurationSeconds != 5 {
					t.Errorf("params = %+v", p)
				}
			},
		},
		"reference_to_video is supported on 1.1": {
			args: map[string]interface{}{"task": "Reference_To_Video", "model": omni11, "prompt": "the ball rolls", "images": imgs2[:1]},
			check: func(t *testing.T, p OmniParams) {
				if p.Task != OmniTaskReferenceToVideo || p.Model != omni11 {
					t.Errorf("params = %+v, want reference_to_video on %s", p, omni11)
				}
			},
		},
		"reference_to_video requires an image": {
			args:    map[string]interface{}{"task": "reference_to_video", "model": omni12, "prompt": "the ball rolls"},
			wantErr: "at least one reference image",
		},
		"reference_to_video requires a prompt": {
			args:    map[string]interface{}{"task": "reference_to_video", "model": omni12, "images": imgs2},
			wantErr: "prompt must be a non-empty string",
		},
		"reference_to_video rejects videos": {
			args:    map[string]interface{}{"task": "reference_to_video", "model": omni12, "prompt": "x", "images": imgs2, "videos": vid},
			wantErr: "does not accept input videos",
		},
		"reference_to_video is not supported on the legacy model": {
			args:    map[string]interface{}{"task": "reference_to_video", "model": "gemini-omni-flash-preview", "prompt": "x", "images": imgs2},
			wantErr: "not supported by model",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			parsed, err := ParseOmniToolArgs(tc.args, cfg)
			if tc.wantErr != "" {
				if err == nil || !strings.Contains(err.Error(), tc.wantErr) {
					t.Fatalf("err = %v, want substring %q", err, tc.wantErr)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if tc.check != nil {
				tc.check(t, parsed.Params)
			}
		})
	}
}

func TestBuildOmniRequestTasks(t *testing.T) {
	video := []OmniMediaRef{{URI: "gs://bucket/clip.mp4", MimeType: "video/mp4"}}

	t.Run("upscale sends video only and the task", func(t *testing.T) {
		req, err := buildOmniRequest(omni12, OmniParams{Task: OmniTaskUpscale, Videos: video, Resolution: "4k"})
		if err != nil {
			t.Fatalf("buildOmniRequest: %v", err)
		}
		parts := req.Input[0].Content
		if len(parts) != 1 || parts[0].Type != "video" {
			t.Errorf("content = %+v, want a single video part (no text)", parts)
		}
		raw, _ := json.Marshal(req)
		if !strings.Contains(string(raw), `"generation_config":{"video_config":{"task":"upscale"}}`) {
			t.Errorf("body missing video_config task: %s", raw)
		}
		if !strings.Contains(string(raw), `"resolution":"4k"`) {
			t.Errorf("body missing resolution: %s", raw)
		}
	})

	t.Run("extend sends the prompt then the video", func(t *testing.T) {
		req, err := buildOmniRequest(omni12, OmniParams{Task: OmniTaskExtend, Prompt: "keep going", Videos: video})
		if err != nil {
			t.Fatalf("buildOmniRequest: %v", err)
		}
		parts := req.Input[0].Content
		if len(parts) != 2 || parts[0].Type != "text" || parts[1].Type != "video" {
			t.Errorf("content = %+v, want text then video", parts)
		}
		if req.GenerationConfig == nil || req.GenerationConfig.VideoConfig == nil || req.GenerationConfig.VideoConfig.Task != OmniTaskExtend {
			t.Errorf("GenerationConfig = %+v, want extend task", req.GenerationConfig)
		}
	})

	t.Run("inferred modes send no task", func(t *testing.T) {
		req, err := buildOmniRequest(omni12, OmniParams{Prompt: "a cat", Videos: video})
		if err != nil {
			t.Fatalf("buildOmniRequest: %v", err)
		}
		raw, _ := json.Marshal(req)
		if strings.Contains(string(raw), "video_config") || strings.Contains(string(raw), "generation_config") {
			t.Errorf("inferred mode should not send generation_config: %s", raw)
		}
	})

	t.Run("task keeps temperature alongside video_config", func(t *testing.T) {
		temp := float32(0.5)
		req, err := buildOmniRequest(omni12, OmniParams{Task: OmniTaskExtend, Prompt: "x", Videos: video, Temperature: &temp})
		if err != nil {
			t.Fatalf("buildOmniRequest: %v", err)
		}
		if req.GenerationConfig.Temperature == nil || req.GenerationConfig.VideoConfig == nil {
			t.Errorf("GenerationConfig = %+v, want temperature and video_config", req.GenerationConfig)
		}
	})

	t.Run("two images with no task keep their order and send no task", func(t *testing.T) {
		req, err := buildOmniRequest(omni12, OmniParams{
			Prompt: "day to night",
			Images: []OmniMediaRef{
				{URI: "gs://bucket/first.png", MimeType: "image/png"},
				{URI: "gs://bucket/last.png", MimeType: "image/png"},
			},
		})
		if err != nil {
			t.Fatalf("buildOmniRequest: %v", err)
		}
		parts := req.Input[0].Content
		if len(parts) != 3 || parts[0].Type != "text" || parts[1].Type != "image" || parts[2].Type != "image" {
			t.Fatalf("content = %+v, want text, image, image", parts)
		}
		if !strings.HasSuffix(parts[1].URI, "first.png") || !strings.HasSuffix(parts[2].URI, "last.png") {
			t.Errorf("image order = %q, %q, want first then last", parts[1].URI, parts[2].URI)
		}
		raw, _ := json.Marshal(req)
		if strings.Contains(string(raw), "video_config") {
			t.Errorf("first/last frame must not send a task: %s", raw)
		}
	})

	t.Run("reference_to_video sends the task with prompt then images", func(t *testing.T) {
		req, err := buildOmniRequest(omni12, OmniParams{
			Task:        OmniTaskReferenceToVideo,
			Prompt:      "the ball rolls",
			Images:      []OmniMediaRef{{URI: "gs://bucket/ball.png", MimeType: "image/png"}},
			AspectRatio: "16:9",
		})
		if err != nil {
			t.Fatalf("buildOmniRequest: %v", err)
		}
		parts := req.Input[0].Content
		if len(parts) != 2 || parts[0].Type != "text" || parts[1].Type != "image" {
			t.Errorf("content = %+v, want text then image", parts)
		}
		raw, _ := json.Marshal(req)
		if !strings.Contains(string(raw), `"video_config":{"task":"reference_to_video"}`) {
			t.Errorf("body missing reference_to_video task: %s", raw)
		}
		if !strings.Contains(string(raw), `"aspect_ratio":"16:9"`) {
			t.Errorf("body missing aspect_ratio: %s", raw)
		}
	})

	t.Run("invalid tasks are rejected", func(t *testing.T) {
		img := []OmniMediaRef{{URI: "gs://b/a.png", MimeType: "image/png"}}
		for name, p := range map[string]OmniParams{
			"no video":         {Task: OmniTaskUpscale},
			"two videos":       {Task: OmniTaskExtend, Prompt: "x", Videos: append(slices.Clone(video), video...)},
			"image with task":  {Task: OmniTaskExtend, Prompt: "x", Videos: video, Images: []OmniMediaRef{{URI: "gs://b/a.png", MimeType: "image/png"}}},
			"upscale prompt":   {Task: OmniTaskUpscale, Prompt: "x", Videos: video},
			"aspect with task": {Task: OmniTaskExtend, Prompt: "x", Videos: video, AspectRatio: "16:9"},
			"unknown task":     {Task: "loop", Prompt: "x", Videos: video},
			"ref2v no image":   {Task: OmniTaskReferenceToVideo, Prompt: "x"},
			"ref2v no prompt":  {Task: OmniTaskReferenceToVideo, Images: img},
			"ref2v with video": {Task: OmniTaskReferenceToVideo, Prompt: "x", Images: img, Videos: video},
		} {
			if _, err := buildOmniRequest(omni12, p); err == nil {
				t.Errorf("%s: expected error", name)
			}
		}
	})
}

// TestGenerateOmniVideoUpscaleAllowsEmptyPrompt confirms the shared entry point
// no longer insists on a prompt for the video-only upscale task.
func TestGenerateOmniVideoUpscaleAllowsEmptyPrompt(t *testing.T) {
	b64 := base64.StdEncoding.EncodeToString(sampleMP4)
	resp, err := decodeInteractionResponse([]byte(omniResponseJSON(b64)))
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	client := &fakeInteractionsClient{resp: resp}
	res, err := generateOmniVideoWithClient(context.Background(), client, OmniParams{
		Task:   OmniTaskUpscale,
		Videos: []OmniMediaRef{{URI: "gs://bucket/clip.mp4", MimeType: "video/mp4"}},
	})
	if err != nil {
		t.Fatalf("generateOmniVideoWithClient: %v", err)
	}
	if len(res.Videos) == 0 {
		t.Errorf("expected a video in the result")
	}
}

// TestInteractionsClientCreateVideoTask exercises the raw transport path used
// for requests that carry generation_config.video_config, which the adopted
// client library cannot serialize.
func TestInteractionsClientCreateVideoTask(t *testing.T) {
	b64 := base64.StdEncoding.EncodeToString(sampleMP4)

	var gotPath, gotUserProject, gotAPIRevision, gotContentType string
	var gotBody map[string]any

	ts := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotUserProject = r.Header.Get("x-goog-user-project")
		gotAPIRevision = r.Header.Get("Api-Revision")
		gotContentType = r.Header.Get("Content-Type")
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &gotBody)

		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Goog-Sherlog-Link", "https://sherlog.example/abc")
		_, _ = io.WriteString(w, omniResponseJSON(b64))
	}))
	defer ts.Close()

	baseURL := ts.URL + "/v1beta1/projects/test-project/locations/global/interactions"
	c := newTestClient(baseURL, ts.Client())

	req, err := buildOmniRequest(omni12, OmniParams{
		Task:       OmniTaskUpscale,
		Resolution: "1080p",
		Videos:     []OmniMediaRef{{Data: sampleMP4, MimeType: "video/mp4"}},
	})
	if err != nil {
		t.Fatalf("buildOmniRequest: %v", err)
	}
	resp, err := c.Create(context.Background(), req)
	if err != nil {
		t.Fatalf("Create: %v", err)
	}

	if gotPath != "/v1beta1/projects/test-project/locations/global/interactions" {
		t.Errorf("request path = %q", gotPath)
	}
	if gotUserProject != "test-project" {
		t.Errorf("x-goog-user-project = %q, want test-project", gotUserProject)
	}
	if gotAPIRevision != DefaultInteractionsAPIRevision {
		t.Errorf("Api-Revision = %q, want %q", gotAPIRevision, DefaultInteractionsAPIRevision)
	}
	if !strings.HasPrefix(gotContentType, "application/json") {
		t.Errorf("Content-Type = %q", gotContentType)
	}
	genCfg, _ := gotBody["generation_config"].(map[string]any)
	videoCfg, _ := genCfg["video_config"].(map[string]any)
	if videoCfg["task"] != "upscale" {
		t.Errorf("generation_config.video_config = %v, want task=upscale (body: %v)", genCfg, gotBody)
	}
	if gotBody["model"] != omni12 || gotBody["store"] != false {
		t.Errorf("model/store = %v/%v", gotBody["model"], gotBody["store"])
	}
	if resp.SherlogLink != "https://sherlog.example/abc" {
		t.Errorf("SherlogLink = %q", resp.SherlogLink)
	}
	if _, err := mapOmniResponse(resp); err != nil {
		t.Errorf("mapOmniResponse: %v", err)
	}
}

func TestInteractionsClientCreateVideoTaskAPIError(t *testing.T) {
	ts := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = io.WriteString(w, `{"error":{"message":"Text input is not supported for upscale task","code":"invalid_request"}}`)
	}))
	defer ts.Close()

	c := newTestClient(ts.URL+"/v1beta1/projects/test-project/locations/global/interactions", ts.Client())
	req := &InteractionRequest{
		Model:            omni12,
		Input:            []InputItem{{Type: "user_input", Content: []Part{{Type: "text", Text: "x"}}}},
		GenerationConfig: &GenerationConfig{VideoConfig: &VideoConfig{Task: OmniTaskUpscale}},
	}
	_, err := c.Create(context.Background(), req)
	if err == nil || !strings.Contains(err.Error(), "status 400") || !strings.Contains(err.Error(), "Text input is not supported") {
		t.Fatalf("err = %v, want the 400 body surfaced verbatim", err)
	}
}

func TestOmniModelDescriptionMentionsTasksAndDuration(t *testing.T) {
	desc := BuildOmniModelDescription()
	for _, want := range []string{"Supported tasks (task argument): extend, upscale, reference_to_video", "Supported tasks (task argument): reference_to_video.", "Duration: 3-15s"} {
		if !strings.Contains(desc, want) {
			t.Errorf("model description missing %q:\n%s", want, desc)
		}
	}
}

func TestOmniVideoToolOptionsSchema(t *testing.T) {
	tool := mcp.NewTool("omni_video_generation", OmniVideoToolOptions()...)
	taskProp, ok := tool.InputSchema.Properties["task"].(map[string]any)
	if !ok {
		t.Fatalf("task property missing from schema: %v", tool.InputSchema.Properties)
	}
	enum, _ := taskProp["enum"].([]string)
	if !slices.Equal(enum, []string{OmniTaskExtend, OmniTaskUpscale, OmniTaskReferenceToVideo}) {
		t.Errorf("task enum = %v", taskProp["enum"])
	}
	if slices.Contains(tool.InputSchema.Required, "prompt") {
		t.Errorf("prompt must not be schema-required (upscale is video-only); required = %v", tool.InputSchema.Required)
	}
	for _, name := range []string{"prompt", "model", "videos", "images", "resolution", "aspect_ratio", "duration_seconds"} {
		if _, ok := tool.InputSchema.Properties[name]; !ok {
			t.Errorf("schema missing %q", name)
		}
	}
}

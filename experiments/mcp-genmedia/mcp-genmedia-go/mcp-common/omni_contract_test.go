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

// Contract tests for the Omni path. Unlike omni_test.go (which unmarshals wire
// bodies through the suite's own decodeInteractionResponse), these tests drive
// canned, representative Interactions JSON THROUGH the real seam — the adopted
// github.com/ghchinoy/cloud-interactions-go transport behind the
// InteractionsClient interface — via an httptest server, and assert the full
// pipeline end to end: library HTTP + JSON decode -> fromLibResponse ->
// mapOmniResponse -> generateOmniVideoWithClient aggregation. This is the check that
// would catch a library bump silently changing the wire contract, and it proves
// the observed live drift survives the concrete transport, not just
// the suite's structs. No live API call is made.

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	interactions "github.com/ghchinoy/cloud-interactions-go"
)

// newSeamAgainst builds the production libInteractionsClient (the concrete
// transport behind the InteractionsClient seam) pointed at a test server. It
// mirrors NewInteractionsClient exactly except that it injects the httptest
// client instead of an ADC-backed oauth2 client, so no credentials are needed.
func newSeamAgainst(server *httptest.Server, userProject string) InteractionsClient {
	client := interactions.NewClient(server.URL)
	client.HTTPClient = server.Client()
	client.WithUserProject(userProject)
	client.WithAPIRevision(DefaultInteractionsAPIRevision)
	return &libInteractionsClient{inner: client}
}

// omniOutputsJSON is a variant of the Omni response that places results in
// outputs[] rather than steps[] (the Lyria-style shape), to prove the seam
// recovers video from either location.
func omniOutputsJSON(b64video string) string {
	return `{
		"id": "out-1",
		"object": "interaction",
		"status": "completed",
		"outputs": [
			{"type": "model_output", "content": [
				{"type": "text", "text": "from outputs"},
				{"type": "video", "mime_type": "video/mp4", "data": "` + b64video + `"}
			]}
		]
	}`
}

// omniHeavyDriftJSON is a deliberately drift-heavy body: lowercase status, a
// thought step whose "summary" is an ARRAY (not a string) plus a "signature",
// created/updated timestamps (the wire names, not the library's create_time/
// update_time), and unknown fields at the top level, the step level, and inside
// content parts. A tolerant decode must ignore every unknown field and still map
// the video bytes, the text, and the single thought step.
func omniHeavyDriftJSON(b64video string) string {
	return `{
		"id": "drift-1",
		"object": "interaction",
		"status": "completed",
		"role": "model",
		"created": "2026-08-10T14:41:24Z",
		"updated": "2026-08-10T14:41:25Z",
		"some_unknown_top_field": {"nested": [1, 2, 3]},
		"steps": [
			{"type": "thought", "signature": "AbC123==", "summary": [{"type": "text", "text": "planning the shot"}, {"type": "text", "text": "and the motion"}]},
			{"type": "model_output", "future_field": "ignore-me", "content": [
				{"type": "text", "text": "done", "extra_part_field": 7},
				{"type": "video", "mime_type": "video/mp4", "data": "` + b64video + `", "another_unknown": true}
			]}
		],
		"usage": {"total_tokens": 100, "brand_new_metric": 42}
	}`
}

// TestOmniContractThroughSeam_StepsHappyPath drives the drift-bearing steps[]
// body (from omni_test.go) through the real transport and asserts the mapped
// result plus the request the seam actually sent (lowercase response_modalities,
// pinned Api-Revision, x-goog-user-project, POST).
func TestOmniContractThroughSeam_StepsHappyPath(t *testing.T) {
	b64 := base64.StdEncoding.EncodeToString(sampleMP4)

	var gotMethod, gotAPIRev, gotUserProject string
	var gotModalities []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotAPIRev = r.Header.Get("Api-Revision")
		gotUserProject = r.Header.Get("x-goog-user-project")
		body, _ := io.ReadAll(r.Body)
		var req struct {
			ResponseModalities []string `json:"response_modalities"`
		}
		_ = json.Unmarshal(body, &req)
		gotModalities = req.ResponseModalities
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, omniResponseJSON(b64))
	}))
	defer srv.Close()

	seam := newSeamAgainst(srv, "test-project")
	result, err := generateOmniVideoWithClient(context.Background(), seam, OmniParams{Prompt: "a red balloon"})
	if err != nil {
		t.Fatalf("generateOmniVideoWithClient through seam: %v", err)
	}

	// Response mapping.
	if len(result.Videos) != 1 {
		t.Fatalf("len(Videos) = %d, want 1", len(result.Videos))
	}
	if string(result.Videos[0]) != string(sampleMP4) {
		t.Errorf("decoded video bytes do not match the source bytes")
	}
	if !hasFtypBox(result.Videos[0]) {
		t.Errorf("decoded video missing ftyp box")
	}
	if result.Text != "Here is your video." {
		t.Errorf("Text = %q", result.Text)
	}
	if result.ThoughtSteps != 1 {
		t.Errorf("ThoughtSteps = %d, want 1", result.ThoughtSteps)
	}
	if result.Status != "completed" {
		t.Errorf("Status = %q, want completed (lowercase preserved)", result.Status)
	}
	if len(result.VideoMimeTypes) != 1 || result.VideoMimeTypes[0] != "video/mp4" {
		t.Errorf("VideoMimeTypes = %v", result.VideoMimeTypes)
	}

	// Request the seam actually sent.
	if gotMethod != http.MethodPost {
		t.Errorf("method = %q, want POST", gotMethod)
	}
	if gotAPIRev != DefaultInteractionsAPIRevision {
		t.Errorf("Api-Revision = %q, want %q", gotAPIRev, DefaultInteractionsAPIRevision)
	}
	if gotUserProject != "test-project" {
		t.Errorf("x-goog-user-project = %q, want test-project", gotUserProject)
	}
	if len(gotModalities) != 2 || gotModalities[0] != "text" || gotModalities[1] != "video" {
		t.Errorf("response_modalities on the wire = %v, want lowercase [text video]", gotModalities)
	}
}

// TestOmniContractThroughSeam_HeavyDrift proves the concrete transport tolerates
// the aggressive drift body (unknown fields everywhere, array thought summary,
// created/updated) and still recovers the video + text + thought count.
func TestOmniContractThroughSeam_HeavyDrift(t *testing.T) {
	b64 := base64.StdEncoding.EncodeToString(sampleMP4)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, omniHeavyDriftJSON(b64))
	}))
	defer srv.Close()

	seam := newSeamAgainst(srv, "p")
	result, err := generateOmniVideoWithClient(context.Background(), seam, OmniParams{Prompt: "x"})
	if err != nil {
		t.Fatalf("heavy-drift body failed through seam: %v", err)
	}
	if len(result.Videos) != 1 || !hasFtypBox(result.Videos[0]) {
		t.Fatalf("video not recovered from heavy-drift body: %+v", result.Videos)
	}
	if result.Text != "done" {
		t.Errorf("Text = %q, want %q", result.Text, "done")
	}
	if result.ThoughtSteps != 1 {
		t.Errorf("ThoughtSteps = %d, want 1 (array-summary thought step still counted)", result.ThoughtSteps)
	}
	if result.Status != "completed" {
		t.Errorf("Status = %q, want completed", result.Status)
	}
}

// TestOmniContractThroughSeam_OutputsShape proves the seam recovers video when
// the API returns results in outputs[] instead of steps[].
func TestOmniContractThroughSeam_OutputsShape(t *testing.T) {
	b64 := base64.StdEncoding.EncodeToString(sampleMP4)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, omniOutputsJSON(b64))
	}))
	defer srv.Close()

	seam := newSeamAgainst(srv, "p")
	result, err := generateOmniVideoWithClient(context.Background(), seam, OmniParams{Prompt: "x"})
	if err != nil {
		t.Fatalf("outputs[] body failed through seam: %v", err)
	}
	if len(result.Videos) != 1 || !hasFtypBox(result.Videos[0]) {
		t.Fatalf("video not recovered from outputs[] body: %+v", result.Videos)
	}
	if result.Text != "from outputs" {
		t.Errorf("Text = %q", result.Text)
	}
}

// TestOmniContractThroughSeam_MultiSample proves the multi-sample loop issues one
// POST per sample through the real transport and aggregates the videos.
func TestOmniContractThroughSeam_MultiSample(t *testing.T) {
	b64 := base64.StdEncoding.EncodeToString(sampleMP4)
	var calls int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls++
		_, _ = io.WriteString(w, omniResponseJSON(b64))
	}))
	defer srv.Close()

	seam := newSeamAgainst(srv, "p")
	result, err := generateOmniVideoWithClient(context.Background(), seam, OmniParams{Prompt: "x", SampleCount: 2})
	if err != nil {
		t.Fatalf("multi-sample through seam: %v", err)
	}
	if calls != 2 {
		t.Errorf("server received %d POSTs, want 2 (one per sample)", calls)
	}
	if len(result.Videos) != 2 {
		t.Errorf("len(Videos) = %d, want 2", len(result.Videos))
	}
	if result.ThoughtSteps != 2 {
		t.Errorf("ThoughtSteps = %d, want 2", result.ThoughtSteps)
	}
}

// TestOmniContractThroughSeam_APIError proves a 4xx from the endpoint is surfaced
// as an error (with the verbatim body) rather than a decode of an empty result.
func TestOmniContractThroughSeam_APIError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = io.WriteString(w, `{"error":{"code":400,"status":"INVALID_ARGUMENT","message":"response_modalities must be lowercase"}}`)
	}))
	defer srv.Close()

	seam := newSeamAgainst(srv, "p")
	_, err := generateOmniVideoWithClient(context.Background(), seam, OmniParams{Prompt: "x"})
	if err == nil {
		t.Fatalf("expected an error for a 400 response, got nil")
	}
	if !strings.Contains(err.Error(), "response_modalities must be lowercase") {
		t.Errorf("error %q does not surface the verbatim API body", err.Error())
	}
}

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

// Tests for failed interactions: the API reports a failed (background or
// mid-generation) interaction with HTTP 200, status "failed", and a plural
// "errors" list, which the adopted library drops while decoding.

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// failedInteractionJSON mirrors a live failed interaction (duration over the
// 1.2 maximum): thought steps, no model_output, and a plural errors list whose
// code is a string.
const failedInteractionJSON = `{
	"id": "failed-1",
	"object": "interaction",
	"status": "failed",
	"usage": {},
	"model": "gemini-omni-1.2-flash",
	"steps": [
		{"type": "user_input", "content": [{"type": "text", "text": "a lighthouse at dusk"}]},
		{"type": "thought", "summary": [{"type": "text", "text": "planning"}]}
	],
	"errors": [
		{"message": "Generation duration 20 seconds exceeds maximum duration 15 seconds.", "code": "invalid_request"}
	]
}`

func failedServer(body string) *httptest.Server {
	return httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, body)
	}))
}

func TestInteractionErrorUnmarshalCode(t *testing.T) {
	tests := []struct {
		name     string
		in       string
		wantCode string
	}{
		{"string code", `{"code":"invalid_request","message":"m"}`, "invalid_request"},
		{"numeric code", `{"code":400,"status":"INVALID_ARGUMENT","message":"m"}`, "400"},
		{"null code", `{"code":null,"message":"m"}`, ""},
		{"no code", `{"message":"m"}`, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var e InteractionError
			if err := json.Unmarshal([]byte(tt.in), &e); err != nil {
				t.Fatalf("Unmarshal: %v", err)
			}
			if e.Code != tt.wantCode || e.Message != "m" {
				t.Errorf("got code=%q message=%q, want code=%q message=m", e.Code, e.Message, tt.wantCode)
			}
		})
	}
}

func TestFailureDetail(t *testing.T) {
	r := &InteractionResponse{
		Error:  &InteractionError{Message: "single", Code: "400"},
		Errors: []InteractionError{{Message: "first", Code: "invalid_request"}, {Message: "second"}, {Code: "no-message"}},
	}
	want := "single (code: 400); first (code: invalid_request); second"
	if got := r.failureDetail(); got != want {
		t.Errorf("failureDetail() = %q, want %q", got, want)
	}
	if got := (&InteractionResponse{}).failureDetail(); got != "" {
		t.Errorf("empty response failureDetail() = %q, want empty", got)
	}
}

// TestCreateSurfacesPluralErrors covers both transports: the library path (plain
// request) and the raw path (explicit video task).
func TestCreateSurfacesPluralErrors(t *testing.T) {
	ts := failedServer(failedInteractionJSON)
	defer ts.Close()
	c := newTestClient(ts.URL, ts.Client())

	plain, err := buildOmniRequest("gemini-omni-1.2-flash", OmniParams{Prompt: "a lighthouse at dusk"})
	if err != nil {
		t.Fatalf("buildOmniRequest: %v", err)
	}
	upscale, err := buildOmniRequest("gemini-omni-1.2-flash", OmniParams{
		Task:   OmniTaskUpscale,
		Videos: []OmniMediaRef{{Data: sampleMP4, MimeType: "video/mp4"}},
	})
	if err != nil {
		t.Fatalf("buildOmniRequest upscale: %v", err)
	}

	for name, req := range map[string]*InteractionRequest{"library path": plain, "raw path": upscale} {
		t.Run(name, func(t *testing.T) {
			resp, err := c.Create(context.Background(), req)
			if err == nil {
				t.Fatal("expected an error for a failed interaction, got nil")
			}
			for _, want := range []string{
				"Generation duration 20 seconds exceeds maximum duration 15 seconds.",
				"invalid_request",
				"interaction status: failed",
			} {
				if !strings.Contains(err.Error(), want) {
					t.Errorf("error %q missing %q", err.Error(), want)
				}
			}
			if resp == nil || len(resp.Errors) != 1 || resp.Errors[0].Code != "invalid_request" {
				t.Errorf("resp.Errors = %+v, want one invalid_request entry", resp)
			}
		})
	}
}

// TestGenerateOmniVideoReportsFailureNotMissingOutput is the user-visible
// regression: a failed interaction used to surface as "no video output found".
func TestGenerateOmniVideoReportsFailureNotMissingOutput(t *testing.T) {
	ts := failedServer(failedInteractionJSON)
	defer ts.Close()
	c := newTestClient(ts.URL, ts.Client())

	_, err := generateOmniVideoWithClient(context.Background(), c, OmniParams{Prompt: "a lighthouse at dusk"})
	if err == nil {
		t.Fatal("expected an error")
	}
	if strings.Contains(err.Error(), "no video output found") {
		t.Errorf("error should carry the API reason, not a generic missing-output message: %v", err)
	}
	if !strings.Contains(err.Error(), "exceeds maximum duration 15 seconds") {
		t.Errorf("error should include the API's errors[] message, got: %v", err)
	}
}

func TestCreateFailedStatusWithoutDetails(t *testing.T) {
	ts := failedServer(`{"id":"f","object":"interaction","status":"failed","steps":[]}`)
	defer ts.Close()
	c := newTestClient(ts.URL, ts.Client())

	_, err := c.Create(context.Background(), &InteractionRequest{
		Model: "m",
		Input: []InputItem{{Type: "text", Text: "x"}},
	})
	if err == nil || !strings.Contains(err.Error(), `status "failed"`) {
		t.Errorf("want an error naming the failed status, got: %v", err)
	}
}

// TestCreateCompletedWithDiagnosticErrorsStillSucceeds: errors[] on a completed
// interaction is diagnostic; the video must not be discarded.
func TestCreateCompletedWithDiagnosticErrorsStillSucceeds(t *testing.T) {
	b64 := base64.StdEncoding.EncodeToString(sampleMP4)
	body := strings.Replace(omniResponseJSON(b64), `"status"`, `"errors":[{"message":"minor diagnostic","code":"warn"}],"status"`, 1)
	ts := failedServer(body)
	defer ts.Close()
	c := newTestClient(ts.URL, ts.Client())

	result, err := generateOmniVideoWithClient(context.Background(), c, OmniParams{Prompt: "x"})
	if err != nil {
		t.Fatalf("completed interaction with diagnostic errors[] should succeed: %v", err)
	}
	if len(result.Videos) != 1 {
		t.Errorf("len(Videos) = %d, want 1", len(result.Videos))
	}
}

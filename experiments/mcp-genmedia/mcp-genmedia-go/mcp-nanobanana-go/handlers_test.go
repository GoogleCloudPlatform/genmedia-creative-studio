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

package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
	"google.golang.org/genai"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
)

func TestGenerateContentGCSImageInputs(t *testing.T) {
	original := appConfig
	appConfig = &common.Config{}
	t.Cleanup(func() { appConfig = original })

	requests := make(chan []genai.Content, 1)
	vertex := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var got struct{ Contents []genai.Content }
		if err := json.NewDecoder(r.Body).Decode(&got); err != nil {
			t.Errorf("decode generateContent request: %v", err)
		}
		requests <- got.Contents
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}`))
	}))
	defer vertex.Close()
	client, err := genai.NewClient(t.Context(), &genai.ClientConfig{
		Backend: genai.BackendVertexAI, Project: "test", Location: "global",
		HTTPClient: vertex.Client(), HTTPOptions: genai.HTTPOptions{BaseURL: vertex.URL},
	})
	if err != nil {
		t.Fatal(err)
	}
	images := []any{"gs://test-bucket/a.jpg", "gs://test-bucket/b.png", "gs://test-bucket/c.webp"}
	req := mcp.CallToolRequest{Params: mcp.CallToolParams{Arguments: map[string]any{"prompt": "edit", "images": images}}}
	res, err := nanobananaGenerateContentHandler(client, t.Context(), req)
	if err != nil || res == nil || res.IsError {
		t.Fatalf("generate content: result=%v err=%v", res, err)
	}
	contents := <-requests
	if len(contents) != 1 || len(contents[0].Parts) != 1+len(images) {
		t.Fatalf("unexpected request contents: %+v", contents)
	}
	for i, mime := range []string{"image/jpeg", "image/png", "image/webp"} {
		file := contents[0].Parts[i+1].FileData // first part is the prompt
		if file == nil || file.FileURI != images[i] || file.MIMEType != mime {
			t.Errorf("fileData for %s = %+v, want original URI and %s", images[i], file, mime)
		}
	}
}

func TestExtForMimeType(t *testing.T) {
	tests := []struct {
		mimeType string
		want     string
	}{
		{"image/jpeg", ".jpg"},
		{"image/webp", ".webp"},
		{"image/gif", ".gif"},
		{"image/png", ".png"},
		{"application/octet-stream", ".png"}, // unknown -> default png
		{"", ".png"},                         // empty -> default png
		{"image/JPEG", ".png"},               // case-sensitive: not matched -> default png
	}
	for _, tc := range tests {
		t.Run(tc.mimeType, func(t *testing.T) {
			if got := extForMimeType(tc.mimeType); got != tc.want {
				t.Errorf("extForMimeType(%q) = %q, want %q", tc.mimeType, got, tc.want)
			}
		})
	}
}

// TestBuildImageFilenames covers the nanobanana naming decision: unset -> nil
// (default scheme), n==1 -> foo.png, n>1 -> foo_1.png..foo_n.png, extension
// forced to the real MIME type.
func TestBuildImageFilenames(t *testing.T) {
	tests := []struct {
		name     string
		base     string
		count    int
		mimeType string
		want     []string
		wantErr  bool
	}{
		{
			name:     "unset base returns nil (default scheme / back-compat)",
			base:     "",
			count:    2,
			mimeType: "image/png",
			want:     nil,
		},
		{
			name:     "blank base returns nil",
			base:     "   ",
			count:    1,
			mimeType: "image/png",
			want:     nil,
		},
		{
			name:     "single image no suffix",
			base:     "foo.png",
			count:    1,
			mimeType: "image/png",
			want:     []string{"foo.png"},
		},
		{
			name:     "multiple images suffixed",
			base:     "foo.png",
			count:    3,
			mimeType: "image/png",
			want:     []string{"foo_1.png", "foo_2.png", "foo_3.png"},
		},
		{
			name:     "extension forced to real MIME (single)",
			base:     "foo.jpeg",
			count:    1,
			mimeType: "image/png",
			want:     []string{"foo.png"},
		},
		{
			name:     "extension forced to real MIME (multiple)",
			base:     "foo.jpeg",
			count:    2,
			mimeType: "image/png",
			want:     []string{"foo_1.png", "foo_2.png"},
		},
		{
			name:     "missing extension gets forced",
			base:     "foo",
			count:    1,
			mimeType: "image/jpeg",
			want:     []string{"foo.jpg"},
		},
		{
			name:     "traversal base sanitized",
			base:     "../../hero.png",
			count:    1,
			mimeType: "image/png",
			want:     []string{"hero.png"},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := buildImageFilenames(tc.base, tc.count, tc.mimeType)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("buildImageFilenames(%q, %d, %q) = %v, want error", tc.base, tc.count, tc.mimeType, got)
				}
				return
			}
			if err != nil {
				t.Fatalf("buildImageFilenames(%q, %d, %q) unexpected error: %v", tc.base, tc.count, tc.mimeType, err)
			}
			if !reflect.DeepEqual(got, tc.want) {
				t.Errorf("buildImageFilenames(%q, %d, %q) = %v, want %v", tc.base, tc.count, tc.mimeType, got, tc.want)
			}
		})
	}
}

// TestDefaultImageFilename locks the legacy default naming scheme byte-for-byte,
// so the unset-output_filename path is guaranteed to be a zero regression.
func TestDefaultImageFilename(t *testing.T) {
	tests := []struct {
		gentime   string
		partIndex int
		mimeType  string
		want      string
	}{
		{"20260811120000", 0, "image/png", "gemini_20260811120000_0.png"},
		{"20260811120000", 1, "image/jpeg", "gemini_20260811120000_1.jpg"},
		{"20260811120000", 2, "", "gemini_20260811120000_2.png"},
	}
	for _, tc := range tests {
		t.Run(tc.want, func(t *testing.T) {
			if got := defaultImageFilename(tc.gentime, tc.partIndex, tc.mimeType); got != tc.want {
				t.Errorf("defaultImageFilename(%q, %d, %q) = %q, want %q", tc.gentime, tc.partIndex, tc.mimeType, got, tc.want)
			}
		})
	}
}

// imageResponse builds a fake genai response with the given text/image parts so
// the handler-level wiring can be exercised without a live genai client.
func imageResponse(parts ...*genai.Part) *genai.GenerateContentResponse {
	return &genai.GenerateContentResponse{
		Candidates: []*genai.Candidate{{Content: &genai.Content{Parts: parts}}},
	}
}

func textPart(s string) *genai.Part { return &genai.Part{Text: s} }

func imagePart(mime string, data []byte) *genai.Part {
	return &genai.Part{InlineData: &genai.Blob{MIMEType: mime, Data: data}}
}

// TestProcessImageResponseWiring exercises the actual handler response path
// (two-pass count/assign, imgIdx, MediaArtifact.FileName -> seam, text
// interleaving) with an injected persistence seam — the Phase-1 review nit 4.1.
// Downstream Path-A servers inherit this wiring-test pattern.
func TestProcessImageResponseWiring(t *testing.T) {
	// Swap in a fake seam that records the FileName it was asked to persist.
	orig := persistMediaOutputs
	t.Cleanup(func() { persistMediaOutputs = orig })

	t.Run("output_filename sets deterministic suffixed names via seam", func(t *testing.T) {
		var gotNames []string
		persistMediaOutputs = func(_ context.Context, art common.MediaArtifact, _, _ string, _ time.Duration) (common.PersistedMedia, error) {
			gotNames = append(gotNames, art.FileName)
			return common.PersistedMedia{LocalPath: "/out/" + art.FileName}, nil
		}

		resp := imageResponse(
			textPart("here you go"),
			imagePart("image/png", []byte("a")),
			imagePart("image/png", []byte("b")),
		)
		res, err := processImageResponse(context.Background(), resp, map[string]any{"output_filename": "hero.jpeg"}, "/out", "")
		if err != nil {
			t.Fatalf("processImageResponse error: %v", err)
		}
		// Extension forced to real MIME (png), 1-based suffix because n>1.
		want := []string{"hero_1.png", "hero_2.png"}
		if !reflect.DeepEqual(gotNames, want) {
			t.Errorf("persisted FileNames = %v, want %v", gotNames, want)
		}
		text := res.Content[0].(mcp.TextContent).Text
		if !strings.Contains(text, "here you go") {
			t.Errorf("summary missing model text; got %q", text)
		}
		if !strings.Contains(text, "Generated and saved 2 image(s)") {
			t.Errorf("summary missing saved-count line; got %q", text)
		}
	})

	t.Run("single image no suffix", func(t *testing.T) {
		var gotNames []string
		persistMediaOutputs = func(_ context.Context, art common.MediaArtifact, _, _ string, _ time.Duration) (common.PersistedMedia, error) {
			gotNames = append(gotNames, art.FileName)
			return common.PersistedMedia{LocalPath: "/out/" + art.FileName}, nil
		}
		resp := imageResponse(imagePart("image/png", []byte("a")))
		if _, err := processImageResponse(context.Background(), resp, map[string]any{"output_filename": "hero"}, "/out", ""); err != nil {
			t.Fatalf("processImageResponse error: %v", err)
		}
		if want := []string{"hero.png"}; !reflect.DeepEqual(gotNames, want) {
			t.Errorf("persisted FileNames = %v, want %v", gotNames, want)
		}
	})

	t.Run("unset output_filename falls back to legacy default scheme", func(t *testing.T) {
		var gotNames []string
		persistMediaOutputs = func(_ context.Context, art common.MediaArtifact, _, _ string, _ time.Duration) (common.PersistedMedia, error) {
			gotNames = append(gotNames, art.FileName)
			return common.PersistedMedia{LocalPath: "/out/" + art.FileName}, nil
		}
		resp := imageResponse(imagePart("image/jpeg", []byte("a")))
		if _, err := processImageResponse(context.Background(), resp, map[string]any{}, "/out", ""); err != nil {
			t.Fatalf("processImageResponse error: %v", err)
		}
		if len(gotNames) != 1 || !strings.HasPrefix(gotNames[0], "gemini_") || !strings.HasSuffix(gotNames[0], ".jpg") {
			t.Errorf("expected legacy gemini_*.jpg default name, got %v", gotNames)
		}
	})
}

// TestSignedURLExpiryWiring guards the nanobanana-specific env var name that is
// read through the shared common.SignedURLExpiryFromEnv helper. The exhaustive
// clamp/default/disable behavior is covered by common's own tests; this only
// asserts the wiring (correct env var, values honored) after the extraction.
func TestSignedURLExpiryWiring(t *testing.T) {
	const envVar = "NANOBANANA_SIGNED_URL_EXPIRY_HOURS"

	t.Run("default when unset", func(t *testing.T) {
		t.Setenv(envVar, "")
		if got := common.SignedURLExpiryFromEnv(envVar); got != 24*time.Hour {
			t.Errorf("got %v, want 24h", got)
		}
	})
	t.Run("explicit value honored", func(t *testing.T) {
		t.Setenv(envVar, "6")
		if got := common.SignedURLExpiryFromEnv(envVar); got != 6*time.Hour {
			t.Errorf("got %v, want 6h", got)
		}
	})
	t.Run("zero disables", func(t *testing.T) {
		t.Setenv(envVar, "0")
		if got := common.SignedURLExpiryFromEnv(envVar); got != 0 {
			t.Errorf("got %v, want 0", got)
		}
	})
}

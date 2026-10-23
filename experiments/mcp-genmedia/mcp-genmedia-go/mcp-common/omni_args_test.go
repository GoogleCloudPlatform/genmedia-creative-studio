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
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
)

// omniResultText asserts content[0] is the text item and returns its text, so the
// existing string-oriented assertions carry over to the new []mcp.Content shape.
func omniResultText(t *testing.T, content []mcp.Content) string {
	t.Helper()
	if len(content) == 0 {
		t.Fatalf("RenderOmniResult returned empty content")
	}
	text, ok := content[0].(mcp.TextContent)
	if !ok {
		t.Fatalf("content[0] = %T, want mcp.TextContent", content[0])
	}
	return text.Text
}

// TestParseMediaRefsGCSURI verifies gs:// entries are passed through by URI (no
// file read) with a MIME type inferred from the extension.
func TestParseMediaRefsGCSURI(t *testing.T) {
	refs, err := parseMediaRefs([]interface{}{"gs://bucket/cat.png"}, "image")
	if err != nil {
		t.Fatalf("parseMediaRefs returned error: %v", err)
	}
	if len(refs) != 1 {
		t.Fatalf("len(refs) = %d, want 1", len(refs))
	}
	if refs[0].URI != "gs://bucket/cat.png" {
		t.Errorf("URI = %q, want gs://bucket/cat.png", refs[0].URI)
	}
	if len(refs[0].Data) != 0 {
		t.Errorf("gs:// ref should carry no inline data, got %d bytes", len(refs[0].Data))
	}
	if refs[0].MimeType != "image/png" {
		t.Errorf("MimeType = %q, want image/png", refs[0].MimeType)
	}
}

// TestParseMediaRefsLocalFile verifies a local path is read into inline bytes.
func TestParseMediaRefsLocalFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "clip.mp4")
	want := []byte("fake-mp4-bytes")
	if err := os.WriteFile(path, want, 0o600); err != nil {
		t.Fatalf("failed to write temp file: %v", err)
	}

	refs, err := parseMediaRefs([]interface{}{path}, "video")
	if err != nil {
		t.Fatalf("parseMediaRefs returned error: %v", err)
	}
	if len(refs) != 1 {
		t.Fatalf("len(refs) = %d, want 1", len(refs))
	}
	if string(refs[0].Data) != string(want) {
		t.Errorf("Data = %q, want %q", refs[0].Data, want)
	}
	if refs[0].URI != "" {
		t.Errorf("local ref should carry no URI, got %q", refs[0].URI)
	}
	if refs[0].MimeType != "video/mp4" {
		t.Errorf("MimeType = %q, want video/mp4", refs[0].MimeType)
	}
}

func TestParseMediaRefsErrors(t *testing.T) {
	if _, err := parseMediaRefs("not-an-array", "image"); err == nil {
		t.Error("expected error for a non-array argument")
	}
	if _, err := parseMediaRefs([]interface{}{""}, "image"); err == nil {
		t.Error("expected error for an empty-string entry")
	}
	if _, err := parseMediaRefs([]interface{}{123}, "image"); err == nil {
		t.Error("expected error for a non-string entry")
	}
	if _, err := parseMediaRefs([]interface{}{"/no/such/file.png"}, "image"); err == nil {
		t.Error("expected error for an unreadable local file")
	}
}

// TestParseMediaRefsDirectoryRejected guards BOT-2: a directory path is rejected
// before any size check / read (info.IsDir()).
func TestParseMediaRefsDirectoryRejected(t *testing.T) {
	dir := t.TempDir()
	_, err := parseMediaRefs([]interface{}{dir}, "image")
	if err == nil {
		t.Fatal("expected an error for a directory path")
	}
	if !strings.Contains(err.Error(), "is a directory") {
		t.Errorf("error should mention it is a directory, got: %v", err)
	}
}

// TestParseMediaRefsNilYieldsNil confirms an absent argument produces no refs.
func TestParseMediaRefsNilYieldsNil(t *testing.T) {
	refs, err := parseMediaRefs(nil, "image")
	if err != nil {
		t.Fatalf("parseMediaRefs(nil) returned error: %v", err)
	}
	if refs != nil {
		t.Errorf("parseMediaRefs(nil) = %v, want nil", refs)
	}
}

func TestInferMediaMimeType(t *testing.T) {
	cases := map[string]string{
		"a.png":       "image/png",
		"a.JPG":       "image/jpeg",
		"a.jpeg":      "image/jpeg",
		"a.webp":      "image/webp",
		"clip.mp4":    "video/mp4",
		"clip.mov":    "video/quicktime",
		"clip.webm":   "video/webm",
		"unknown.bin": "application/octet-stream",
	}
	for name, want := range cases {
		if got := inferMediaMimeType(name); got != want {
			t.Errorf("inferMediaMimeType(%q) = %q, want %q", name, got, want)
		}
	}
}

// TestVideoExtForMimeType guards BOT-1: the saved filename's extension is derived
// from the resolved MIME type (defaulting to .mp4), not hardcoded.
func TestVideoExtForMimeType(t *testing.T) {
	cases := map[string]string{
		"video/mp4":       ".mp4",
		"video/webm":      ".webm",
		"video/quicktime": ".mov",
		"video/mpeg":      ".mpeg",
		"video/3gpp":      ".3gp",
		"":                ".mp4",
		"application/pdf": ".mp4",
	}
	for mime, want := range cases {
		if got := videoExtForMimeType(mime); got != want {
			t.Errorf("videoExtForMimeType(%q) = %q, want %q", mime, got, want)
		}
	}
}

func TestToInt(t *testing.T) {
	if n, err := toInt(float64(3)); err != nil || n != 3 {
		t.Errorf("toInt(3.0) = %d, %v; want 3, nil", n, err)
	}
	if n, err := toInt(2); err != nil || n != 2 {
		t.Errorf("toInt(2) = %d, %v; want 2, nil", n, err)
	}
	if _, err := toInt(float64(2.5)); err == nil {
		t.Error("expected error for a non-integer float")
	}
	if _, err := toInt("nope"); err == nil {
		t.Error("expected error for a string argument")
	}
}

func TestParseOptionalFloatInRange(t *testing.T) {
	args := map[string]interface{}{
		"temperature": float64(1.5),
		"too_high":    float64(9),
		"not_number":  "x",
	}

	// Absent key -> nil, no error.
	v, err := parseOptionalFloatInRange(args, "missing", 0, 2)
	if err != nil || v != nil {
		t.Errorf("absent key: got %v, %v; want nil, nil", v, err)
	}

	// In-range value.
	v, err = parseOptionalFloatInRange(args, "temperature", 0, 2)
	if err != nil || v == nil || *v != 1.5 {
		t.Errorf("in-range: got %v, %v; want 1.5, nil", v, err)
	}

	// Out-of-range value.
	if _, err := parseOptionalFloatInRange(args, "too_high", 0, 2); err == nil {
		t.Error("expected error for an out-of-range value")
	}

	// Wrong type.
	if _, err := parseOptionalFloatInRange(args, "not_number", 0, 2); err == nil {
		t.Error("expected error for a non-numeric value")
	}
}

// TestParseOptionalFloatInRangeIntegers guards BOT-1: integer JSON numbers (which
// may surface as float64, int, or int64) must be accepted for temperature/top_p,
// not rejected as "must be a number".
func TestParseOptionalFloatInRangeIntegers(t *testing.T) {
	cases := map[string]interface{}{
		"float64_int": float64(1), // JSON "1" decoded to float64
		"int":         1,
		"int64":       int64(1),
	}
	for name, raw := range cases {
		t.Run(name, func(t *testing.T) {
			// temperature range [0,2]
			v, err := parseOptionalFloatInRange(map[string]interface{}{"temperature": raw}, "temperature", 0, 2)
			if err != nil {
				t.Fatalf("integer temperature %v (%T) rejected: %v", raw, raw, err)
			}
			if v == nil || *v != 1 {
				t.Fatalf("temperature = %v, want 1", v)
			}
			// top_p range [0,1]
			p, err := parseOptionalFloatInRange(map[string]interface{}{"top_p": raw}, "top_p", 0, 1)
			if err != nil {
				t.Fatalf("integer top_p %v (%T) rejected: %v", raw, raw, err)
			}
			if p == nil || *p != 1 {
				t.Fatalf("top_p = %v, want 1", p)
			}
		})
	}
}

// TestParseMediaRefsOversized guards BOT-3: a local file above the inline cap is
// rejected with a hint to use a gs:// URI, and is not read fully into memory.
func TestParseMediaRefsOversized(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "big.mp4")
	f, err := os.Create(path)
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	// Sparse file just over the cap (no large allocation).
	if err := f.Truncate(maxInlineMediaBytes + 1); err != nil {
		t.Fatalf("truncate: %v", err)
	}
	f.Close()

	_, err = parseMediaRefs([]interface{}{path}, "video")
	if err == nil {
		t.Fatal("expected an error for an oversized local file")
	}
	if !strings.Contains(err.Error(), "gs://") {
		t.Errorf("error should suggest a gs:// URI, got: %v", err)
	}
}

// TestParseOmniToolArgsHappyPath exercises the full argument surface both servers
// share: prompt trimming, model default, media refs, sample_count, and the
// GENMEDIA_BUCKET fallback for gcs_bucket_uri.
func TestParseOmniToolArgsHappyPath(t *testing.T) {
	cfg := &Config{GenmediaBucket: "my-bucket"}
	args := map[string]interface{}{
		"prompt":           "  a cat surfing  ",
		"images":           []interface{}{"gs://bucket/cat.png"},
		"resolution":       "4K",
		"aspect_ratio":     "9:16",
		"duration_seconds": float64(8),
		"sample_count":     float64(2),
		"temperature":      float64(1),
		"top_p":            float64(0.5),
		"output_directory": "/tmp/out",
	}

	parsed, err := ParseOmniToolArgs(args, cfg)
	if err != nil {
		t.Fatalf("ParseOmniToolArgs returned error: %v", err)
	}
	if parsed.Params.Prompt != "a cat surfing" {
		t.Errorf("Prompt = %q, want trimmed %q", parsed.Params.Prompt, "a cat surfing")
	}
	if parsed.Params.Model != DefaultOmniModel {
		t.Errorf("Model = %q, want default %q", parsed.Params.Model, DefaultOmniModel)
	}
	if parsed.Params.Resolution != "4k" {
		t.Errorf("Resolution = %q, want normalized canonical '4k'", parsed.Params.Resolution)
	}
	if parsed.Params.AspectRatio != "9:16" {
		t.Errorf("AspectRatio = %q, want '9:16'", parsed.Params.AspectRatio)
	}
	if parsed.Params.DurationSeconds != 8 {
		t.Errorf("DurationSeconds = %d, want 8", parsed.Params.DurationSeconds)
	}
	if len(parsed.Params.Images) != 1 || parsed.Params.Images[0].URI != "gs://bucket/cat.png" {
		t.Errorf("Images = %+v, want one gs:// image ref", parsed.Params.Images)
	}
	if parsed.Params.SampleCount != 2 {
		t.Errorf("SampleCount = %d, want 2", parsed.Params.SampleCount)
	}
	if parsed.Params.Temperature == nil || *parsed.Params.Temperature != 1 {
		t.Errorf("Temperature = %v, want 1", parsed.Params.Temperature)
	}
	if parsed.Params.TopP == nil || *parsed.Params.TopP != 0.5 {
		t.Errorf("TopP = %v, want 0.5", parsed.Params.TopP)
	}
	if parsed.OutputDir != "/tmp/out" {
		t.Errorf("OutputDir = %q, want /tmp/out", parsed.OutputDir)
	}
	if parsed.GCSBucketURI != "my-bucket/omni_outputs/" {
		t.Errorf("GCSBucketURI = %q, want GENMEDIA_BUCKET fallback", parsed.GCSBucketURI)
	}
}

// TestParseOmniToolArgsExplicitBucketWins confirms an explicit gcs_bucket_uri
// takes precedence over the GENMEDIA_BUCKET fallback.
func TestParseOmniToolArgsExplicitBucketWins(t *testing.T) {
	cfg := &Config{GenmediaBucket: "fallback-bucket"}
	parsed, err := ParseOmniToolArgs(map[string]interface{}{
		"prompt":         "hi",
		"gcs_bucket_uri": "explicit-bucket/dir/",
	}, cfg)
	if err != nil {
		t.Fatalf("ParseOmniToolArgs returned error: %v", err)
	}
	if parsed.GCSBucketURI != "explicit-bucket/dir/" {
		t.Errorf("GCSBucketURI = %q, want the explicit value", parsed.GCSBucketURI)
	}
}

// TestParseOmniToolArgsDefaults verifies sample_count defaults to 1 and an absent
// GENMEDIA_BUCKET leaves gcs_bucket_uri empty.
func TestParseOmniToolArgsDefaults(t *testing.T) {
	parsed, err := ParseOmniToolArgs(map[string]interface{}{"prompt": "hi"}, &Config{})
	if err != nil {
		t.Fatalf("ParseOmniToolArgs returned error: %v", err)
	}
	if parsed.Params.SampleCount != 1 {
		t.Errorf("SampleCount = %d, want default 1", parsed.Params.SampleCount)
	}
	if parsed.GCSBucketURI != "" {
		t.Errorf("GCSBucketURI = %q, want empty", parsed.GCSBucketURI)
	}
	if parsed.Params.Temperature != nil || parsed.Params.TopP != nil {
		t.Errorf("unset temperature/top_p should be nil, got %v/%v", parsed.Params.Temperature, parsed.Params.TopP)
	}
}

func TestParseOmniToolArgsValidationErrors(t *testing.T) {
	cfg := &Config{}
	cases := map[string]struct {
		args    map[string]interface{}
		wantSub string
	}{
		"missing prompt": {
			args:    map[string]interface{}{},
			wantSub: "prompt must be a non-empty string and is required",
		},
		"blank prompt": {
			args:    map[string]interface{}{"prompt": "   "},
			wantSub: "prompt must be a non-empty string and is required",
		},
		"unsupported model": {
			args:    map[string]interface{}{"prompt": "hi", "model": "not-a-real-model"},
			wantSub: "unsupported model",
		},
		"too many images": {
			args: map[string]interface{}{
				"prompt": "hi",
				"images": make([]interface{}, maxOmniImages+1),
			},
			wantSub: "too many images",
		},
		"too many videos": {
			args: map[string]interface{}{
				"prompt": "hi",
				"videos": make([]interface{}, maxOmniVideos+1),
			},
			wantSub: "too many videos",
		},
		"unsupported resolution": {
			args:    map[string]interface{}{"prompt": "hi", "resolution": "8k"},
			wantSub: "unsupported resolution",
		},
		"unsupported resolution on legacy model": {
			args:    map[string]interface{}{"prompt": "hi", "model": "gemini-omni-flash-preview", "resolution": "4k"},
			wantSub: "unsupported resolution",
		},
		"unsupported aspect_ratio": {
			args:    map[string]interface{}{"prompt": "hi", "aspect_ratio": "1:1"},
			wantSub: "unsupported aspect_ratio",
		},
		"duration_seconds out of range": {
			args:    map[string]interface{}{"prompt": "hi", "duration_seconds": float64(15)},
			wantSub: "duration_seconds must be in the range",
		},
		"non-integer sample_count": {
			args:    map[string]interface{}{"prompt": "hi", "sample_count": float64(2.5)},
			wantSub: "sample_count must be an integer",
		},
		"temperature out of range": {
			args:    map[string]interface{}{"prompt": "hi", "temperature": float64(3)},
			wantSub: "temperature must be in the range",
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			_, err := ParseOmniToolArgs(tc.args, cfg)
			if err == nil {
				t.Fatalf("expected an error containing %q, got nil", tc.wantSub)
			}
			if !strings.Contains(err.Error(), tc.wantSub) {
				t.Errorf("error = %q, want it to contain %q", err.Error(), tc.wantSub)
			}
		})
	}
}

// TestParseOmniToolArgsImageCountGuardBeforeRead confirms the image-count guard
// fires before any file is read (BOT-2 ordering): a too-long list of nonexistent
// paths still fails with the count error, not a file-read error.
func TestParseOmniToolArgsImageCountGuardBeforeRead(t *testing.T) {
	imgs := make([]interface{}, maxOmniImages+1)
	for i := range imgs {
		imgs[i] = "/no/such/file.png"
	}
	_, err := ParseOmniToolArgs(map[string]interface{}{"prompt": "hi", "images": imgs}, &Config{})
	if err == nil || !strings.Contains(err.Error(), "too many images") {
		t.Fatalf("want a too-many-images error before any read, got: %v", err)
	}
}

// TestRenderOmniResultLocal exercises the shared response renderer end to end for
// a local-only save (no GCS), asserting the filename extension, saved-path
// summary, model text, and thought-step NOTE all appear.
func TestRenderOmniResultLocal(t *testing.T) {
	// output_directory is now confined to MCP_OUTPUT_ROOT (CWE-22): make the temp
	// dir a child of the configured root and pass it as a relative dir.
	dir := t.TempDir()
	t.Setenv(OutputRootEnvVar, filepath.Dir(dir))
	relDir := filepath.Base(dir)
	result := &OmniResult{
		Videos:         [][]byte{[]byte("mp4-bytes")},
		VideoMimeTypes: []string{"video/mp4"},
		Text:           "Here is your video.",
		ThoughtSteps:   1,
	}

	content, err := RenderOmniResult(context.Background(), result, relDir, "", "")
	if err != nil {
		t.Fatalf("RenderOmniResult returned error: %v", err)
	}
	msg := omniResultText(t, content)
	// Local-only save produces no GCS artifact, so no resource_link is appended.
	if len(content) != 1 {
		t.Errorf("expected 1 content item (text only, no GCS link), got %d", len(content))
	}
	if !strings.Contains(msg, "Here is your video.") {
		t.Errorf("message missing model text: %q", msg)
	}
	if !strings.Contains(msg, "reasoning (thought) step(s).") {
		t.Errorf("message missing thought-step NOTE: %q", msg)
	}
	if !strings.Contains(msg, "Generated and saved 1 video(s):") {
		t.Errorf("message missing saved summary: %q", msg)
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("ReadDir: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 saved file, got %d", len(entries))
	}
	name := entries[0].Name()
	if !strings.HasPrefix(name, "omni_") || !strings.HasSuffix(name, ".mp4") {
		t.Errorf("saved filename = %q, want omni_*.mp4", name)
	}
}

// TestRenderOmniResultGCSResourceLinks confirms that on a GCS-sink call the
// renderer appends one resource_link per video after the (unchanged) text item,
// each carrying the gs:// URI, MIME type, and 1-based "omni output i of n"
// description (design #483). The GCS upload and V4 signing seams are stubbed so
// the test needs no live bucket.
func TestRenderOmniResultGCSResourceLinks(t *testing.T) {
	origUpload := uploadToGCSFn
	origSign := generateV4SignedURLFn
	t.Cleanup(func() { uploadToGCSFn = origUpload; generateV4SignedURLFn = origSign })
	uploadToGCSFn = func(_ context.Context, _, _, _ string, _ []byte) error { return nil }
	generateV4SignedURLFn = func(_ context.Context, _, object string, _ time.Duration) (string, error) {
		return "https://signed.example/" + object, nil
	}

	result := &OmniResult{
		Videos:         [][]byte{[]byte("a"), []byte("b")},
		VideoMimeTypes: []string{"video/mp4", "video/mp4"},
		Text:           "two videos",
	}
	content, err := RenderOmniResult(context.Background(), result, "", "my-bucket/prefix", "")
	if err != nil {
		t.Fatalf("RenderOmniResult returned error: %v", err)
	}
	if len(content) != 3 {
		t.Fatalf("expected 3 content items (text + 2 links), got %d", len(content))
	}
	if msg := omniResultText(t, content); !strings.Contains(msg, "two videos") {
		t.Errorf("content[0] missing model text: %q", msg)
	}
	for i := 1; i <= 2; i++ {
		link, ok := content[i].(mcp.ResourceLink)
		if !ok {
			t.Fatalf("content[%d] = %T, want mcp.ResourceLink", i, content[i])
		}
		if link.Type != "resource_link" {
			t.Errorf("content[%d].Type = %q, want resource_link", i, link.Type)
		}
		wantURI := "gs://my-bucket/prefix/omni_"
		if !strings.HasPrefix(link.URI, wantURI) {
			t.Errorf("content[%d].URI = %q, want prefix %q", i, link.URI, wantURI)
		}
		if link.MIMEType != "video/mp4" {
			t.Errorf("content[%d].MIMEType = %q, want video/mp4", i, link.MIMEType)
		}
		wantDesc := fmt.Sprintf("omni output %d of 2", i)
		if link.Description != wantDesc {
			t.Errorf("content[%d].Description = %q, want %q", i, link.Description, wantDesc)
		}
	}
}

// TestRenderOmniResultGCSResourceLinksSubset proves review NB-2: when a subset of
// videos fails to persist to GCS, the "omni output i of n" description denominator
// reflects the count of videos actually persisted to GCS (len(mediaResults)), not
// the total video count — consistent with the other servers' len(gcsSavedURIs).
// The first video's upload is made to fail (GCSURI stays empty, no link), so only
// the second video yields a link, described "omni output 1 of 1" (pre-fix this
// would have been "omni output 2 of 2"). Behavior is identical in the all-or-none
// common case covered by TestRenderOmniResultGCSResourceLinks.
func TestRenderOmniResultGCSResourceLinksSubset(t *testing.T) {
	origUpload := uploadToGCSFn
	origSign := generateV4SignedURLFn
	t.Cleanup(func() { uploadToGCSFn = origUpload; generateV4SignedURLFn = origSign })
	// Fail the first video's upload (object name ends "_0.mp4"); succeed otherwise.
	uploadToGCSFn = func(_ context.Context, _, object, _ string, _ []byte) error {
		if strings.HasSuffix(object, "_0.mp4") {
			return fmt.Errorf("simulated upload failure for %s", object)
		}
		return nil
	}
	generateV4SignedURLFn = func(_ context.Context, _, object string, _ time.Duration) (string, error) {
		return "https://signed.example/" + object, nil
	}

	result := &OmniResult{
		Videos:         [][]byte{[]byte("a"), []byte("b")},
		VideoMimeTypes: []string{"video/mp4", "video/mp4"},
		Text:           "two videos",
	}
	content, err := RenderOmniResult(context.Background(), result, "", "my-bucket/prefix", "")
	if err != nil {
		t.Fatalf("RenderOmniResult returned error: %v", err)
	}
	// text + exactly one link (only the second video persisted to GCS).
	if len(content) != 2 {
		t.Fatalf("expected 2 content items (text + 1 link), got %d", len(content))
	}
	link, ok := content[1].(mcp.ResourceLink)
	if !ok {
		t.Fatalf("content[1] = %T, want mcp.ResourceLink", content[1])
	}
	if want := "omni output 1 of 1"; link.Description != want {
		t.Errorf("content[1].Description = %q, want %q (denominator = GCS artifact count, NB-2)", link.Description, want)
	}
}

// TestRenderOmniResultNoDestination confirms the "none saved" summary is used
// when neither an output directory nor a GCS bucket is provided.
func TestRenderOmniResultNoDestination(t *testing.T) {
	result := &OmniResult{
		Videos:         [][]byte{[]byte("mp4-bytes")},
		VideoMimeTypes: []string{"video/mp4"},
	}
	content, err := RenderOmniResult(context.Background(), result, "", "", "")
	if err != nil {
		t.Fatalf("RenderOmniResult returned error: %v", err)
	}
	msg := omniResultText(t, content)
	if !strings.Contains(msg, "none were saved (set output_directory or gcs_bucket_uri).") {
		t.Errorf("message missing none-saved summary: %q", msg)
	}
}

// TestRenderOmniResultOutputFilename confirms output_filename yields
// client-predictable names: no suffix for a single video, 1-based _1..n
// suffixing for multiple, with the extension forced to the true media type.
func TestRenderOmniResultOutputFilename(t *testing.T) {
	t.Run("single video honored, extension forced", func(t *testing.T) {
		dir := t.TempDir()
		t.Setenv(OutputRootEnvVar, filepath.Dir(dir))
		relDir := filepath.Base(dir)
		result := &OmniResult{
			Videos:         [][]byte{[]byte("mp4-bytes")},
			VideoMimeTypes: []string{"video/mp4"},
		}
		// Wrong client extension must be forced to the true media type.
		if _, err := RenderOmniResult(context.Background(), result, relDir, "", "clip.mov"); err != nil {
			t.Fatalf("RenderOmniResult returned error: %v", err)
		}
		entries, _ := os.ReadDir(dir)
		if len(entries) != 1 || entries[0].Name() != "clip.mp4" {
			t.Errorf("expected single file clip.mp4, got %v", names(entries))
		}
	})

	t.Run("multiple videos suffixed 1-based", func(t *testing.T) {
		dir := t.TempDir()
		t.Setenv(OutputRootEnvVar, filepath.Dir(dir))
		relDir := filepath.Base(dir)
		result := &OmniResult{
			Videos:         [][]byte{[]byte("a"), []byte("b"), []byte("c")},
			VideoMimeTypes: []string{"video/mp4", "video/mp4", "video/mp4"},
		}
		if _, err := RenderOmniResult(context.Background(), result, relDir, "", "clip.mp4"); err != nil {
			t.Fatalf("RenderOmniResult returned error: %v", err)
		}
		got := names(mustReadDir(t, dir))
		want := map[string]bool{"clip_1.mp4": true, "clip_2.mp4": true, "clip_3.mp4": true}
		if len(got) != 3 {
			t.Fatalf("expected 3 files, got %v", got)
		}
		for _, n := range got {
			if !want[n] {
				t.Errorf("unexpected file %q (want clip_1..3.mp4)", n)
			}
		}
	})
}

func mustReadDir(t *testing.T, dir string) []os.DirEntry {
	t.Helper()
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatalf("ReadDir: %v", err)
	}
	return entries
}

func names(entries []os.DirEntry) []string {
	out := make([]string, len(entries))
	for i, e := range entries {
		out[i] = e.Name()
	}
	return out
}

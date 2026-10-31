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
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// withFakeGCS swaps the GCS upload + V4-signing seams for the duration of a test
// and restores them afterwards, so the GCS branch of PersistMediaOutputs can be
// exercised without a live bucket or credentials (NIT-3). It returns the real
// implementations for tests that only want to override one of the two.
func withFakeGCS(t *testing.T, upload func(ctx context.Context, bucket, object, contentType string, data []byte) error, sign func(ctx context.Context, bucket, object string, expiry time.Duration) (string, error)) {
	t.Helper()
	origUpload := uploadToGCSFn
	origSign := generateV4SignedURLFn
	if upload != nil {
		uploadToGCSFn = upload
	}
	if sign != nil {
		generateV4SignedURLFn = sign
	}
	t.Cleanup(func() {
		uploadToGCSFn = origUpload
		generateV4SignedURLFn = origSign
	})
}

// TestPersistMediaOutputsGCSSuccess verifies the GCS+signed-URL branch: the
// artifact is uploaded to the parsed bucket/object, a V4 signed URL is generated,
// and every GCS field on PersistedMedia is populated correctly. Uses fake seams
// so no live bucket is required.
func TestPersistMediaOutputsGCSSuccess(t *testing.T) {
	var gotBucket, gotObject, gotContentType string
	var gotData []byte
	var signBucket, signObject string
	var signExpiry time.Duration

	withFakeGCS(t,
		func(_ context.Context, bucket, object, contentType string, data []byte) error {
			gotBucket, gotObject, gotContentType, gotData = bucket, object, contentType, data
			return nil
		},
		func(_ context.Context, bucket, object string, expiry time.Duration) (string, error) {
			signBucket, signObject, signExpiry = bucket, object, expiry
			return "https://signed.example/" + object, nil
		},
	)

	art := MediaArtifact{
		Data:     []byte("mp4-bytes"),
		MimeType: "video/mp4",
		FileName: "omni_20260101_0.mp4",
	}
	const expiry = 24 * time.Hour

	got, err := PersistMediaOutputs(context.Background(), art, "", "gs://my-bucket/omni_outputs/", expiry)
	if err != nil {
		t.Fatalf("PersistMediaOutputs returned fatal error: %v", err)
	}

	// Upload received the bucket/object parsed from the URI + the filename.
	if gotBucket != "my-bucket" {
		t.Errorf("upload bucket = %q, want %q", gotBucket, "my-bucket")
	}
	if gotObject != "omni_outputs/omni_20260101_0.mp4" {
		t.Errorf("upload object = %q, want %q", gotObject, "omni_outputs/omni_20260101_0.mp4")
	}
	if gotContentType != "video/mp4" {
		t.Errorf("upload contentType = %q, want video/mp4", gotContentType)
	}
	if string(gotData) != "mp4-bytes" {
		t.Errorf("upload data = %q, want %q", gotData, "mp4-bytes")
	}

	// PersistedMedia carries the URI, bucket, object, and signed URL.
	if got.GCSURI != "gs://my-bucket/omni_outputs/omni_20260101_0.mp4" {
		t.Errorf("GCSURI = %q", got.GCSURI)
	}
	if got.GCSBucket != "my-bucket" || got.GCSObject != "omni_outputs/omni_20260101_0.mp4" {
		t.Errorf("GCSBucket/GCSObject = %q/%q", got.GCSBucket, got.GCSObject)
	}
	if got.GCSError != nil {
		t.Errorf("GCSError = %v, want nil", got.GCSError)
	}
	if got.SignedURL != "https://signed.example/omni_outputs/omni_20260101_0.mp4" {
		t.Errorf("SignedURL = %q", got.SignedURL)
	}

	// The signer was called with the same bucket/object and the requested expiry.
	if signBucket != "my-bucket" || signObject != "omni_outputs/omni_20260101_0.mp4" {
		t.Errorf("signer bucket/object = %q/%q", signBucket, signObject)
	}
	if signExpiry != expiry {
		t.Errorf("signer expiry = %v, want %v", signExpiry, expiry)
	}
}

// TestPersistMediaOutputsGCSAndLocal verifies that when both a local dir and a
// GCS URI are set, the artifact is written locally and uploaded, and both
// LocalPath and GCSURI are populated.
func TestPersistMediaOutputsGCSAndLocal(t *testing.T) {
	withFakeGCS(t,
		func(_ context.Context, _, _, _ string, _ []byte) error { return nil },
		func(_ context.Context, _, object string, _ time.Duration) (string, error) {
			return "https://signed.example/" + object, nil
		},
	)

	// outputDir is now confined to MCP_OUTPUT_ROOT (CWE-22): make the temp dir a
	// child of the configured root and pass it as a relative dir so it stays inside.
	dir := t.TempDir()
	if resolved, err := filepath.EvalSymlinks(dir); err == nil {
		dir = resolved
	}
	t.Setenv(OutputRootEnvVar, filepath.Dir(dir))
	relDir := filepath.Base(dir)
	art := MediaArtifact{Data: []byte("v"), MimeType: "video/mp4", FileName: "clip.mp4"}

	got, err := PersistMediaOutputs(context.Background(), art, relDir, "gs://b/prefix", time.Hour)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.LocalPath != filepath.Join(dir, "clip.mp4") {
		t.Errorf("LocalPath = %q", got.LocalPath)
	}
	if got.GCSURI != "gs://b/prefix/clip.mp4" {
		t.Errorf("GCSURI = %q", got.GCSURI)
	}
	if got.SignedURL == "" {
		t.Errorf("SignedURL should be set")
	}
	if _, statErr := os.Stat(got.LocalPath); statErr != nil {
		t.Errorf("local file not written: %v", statErr)
	}
}

// TestPersistMediaOutputsGCSNoSignedURLWhenExpiryZero verifies that a zero
// expiry uploads to GCS but does NOT generate a signed URL (the signer is not
// even invoked).
func TestPersistMediaOutputsGCSNoSignedURLWhenExpiryZero(t *testing.T) {
	signerCalled := false
	withFakeGCS(t,
		func(_ context.Context, _, _, _ string, _ []byte) error { return nil },
		func(_ context.Context, _, _ string, _ time.Duration) (string, error) {
			signerCalled = true
			return "should-not-be-used", nil
		},
	)

	got, err := PersistMediaOutputs(context.Background(),
		MediaArtifact{Data: []byte("v"), MimeType: "video/mp4", FileName: "c.mp4"}, "", "gs://b", 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.GCSURI != "gs://b/c.mp4" {
		t.Errorf("GCSURI = %q", got.GCSURI)
	}
	if signerCalled {
		t.Errorf("signer should not be called when expiry is 0")
	}
	if got.SignedURL != "" {
		t.Errorf("SignedURL = %q, want empty when expiry is 0", got.SignedURL)
	}
}

// TestPersistMediaOutputsGCSSignedURLFailureNonFatal verifies that a signing
// failure is non-fatal: the upload still succeeds (GCSURI set) and only the
// SignedURL is left empty.
func TestPersistMediaOutputsGCSSignedURLFailureNonFatal(t *testing.T) {
	withFakeGCS(t,
		func(_ context.Context, _, _, _ string, _ []byte) error { return nil },
		func(_ context.Context, _, _ string, _ time.Duration) (string, error) {
			return "", errors.New("iam signBlob denied")
		},
	)

	got, err := PersistMediaOutputs(context.Background(),
		MediaArtifact{Data: []byte("v"), MimeType: "video/mp4", FileName: "c.mp4"}, "", "gs://b", time.Hour)
	if err != nil {
		t.Fatalf("signing failure must be non-fatal, got error: %v", err)
	}
	if got.GCSURI != "gs://b/c.mp4" {
		t.Errorf("GCSURI = %q, want upload to have succeeded", got.GCSURI)
	}
	if got.SignedURL != "" {
		t.Errorf("SignedURL = %q, want empty after signing failure", got.SignedURL)
	}
}

// TestPersistMediaOutputsGCSUploadFailureNonFatal verifies that an upload
// failure is non-fatal (no fatal error returned), leaves GCSURI empty, reports
// the error via GCSError, and still populates the intended bucket/object so the
// caller can log them.
func TestPersistMediaOutputsGCSUploadFailureNonFatal(t *testing.T) {
	wantErr := errors.New("bucket not found")
	signerCalled := false
	withFakeGCS(t,
		func(_ context.Context, _, _, _ string, _ []byte) error { return wantErr },
		func(_ context.Context, _, _ string, _ time.Duration) (string, error) {
			signerCalled = true
			return "x", nil
		},
	)

	got, err := PersistMediaOutputs(context.Background(),
		MediaArtifact{Data: []byte("v"), MimeType: "video/mp4", FileName: "c.mp4"}, "", "gs://my-bucket/p", time.Hour)
	if err != nil {
		t.Fatalf("upload failure must be non-fatal, got error: %v", err)
	}
	if !errors.Is(got.GCSError, wantErr) {
		t.Errorf("GCSError = %v, want %v", got.GCSError, wantErr)
	}
	if got.GCSURI != "" {
		t.Errorf("GCSURI = %q, want empty after upload failure", got.GCSURI)
	}
	if got.GCSBucket != "my-bucket" || got.GCSObject != "p/c.mp4" {
		t.Errorf("bucket/object for logging = %q/%q, want my-bucket/p/c.mp4", got.GCSBucket, got.GCSObject)
	}
	if signerCalled {
		t.Errorf("signer should not run after an upload failure")
	}
	if got.SignedURL != "" {
		t.Errorf("SignedURL = %q, want empty after upload failure", got.SignedURL)
	}
}

func TestParseGCSBucketAndPrefix(t *testing.T) {
	tests := []struct {
		name       string
		uri        string
		wantBucket string
		wantPrefix string
	}{
		{"bucket only", "my-bucket", "my-bucket", ""},
		{"bucket only with gs scheme", "gs://my-bucket", "my-bucket", ""},
		{"bucket with trailing slash", "gs://my-bucket/", "my-bucket", ""},
		{"bucket and prefix", "gs://my-bucket/prefix", "my-bucket", "prefix/"},
		{"bucket and prefix trailing slash preserved", "gs://my-bucket/prefix/", "my-bucket", "prefix/"},
		{"bucket and nested prefix", "gs://my-bucket/a/b/c", "my-bucket", "a/b/c/"},
		{"bucket and nested prefix trailing slash", "gs://my-bucket/a/b/c/", "my-bucket", "a/b/c/"},
		{"no gs scheme with prefix", "my-bucket/spike_a", "my-bucket", "spike_a/"},
		{"leading slash stripped", "/my-bucket/prefix", "my-bucket", "prefix/"},
		{"gs scheme leading slash", "gs:///my-bucket/prefix", "my-bucket", "prefix/"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			gotBucket, gotPrefix := ParseGCSBucketAndPrefix(tc.uri)
			if gotBucket != tc.wantBucket {
				t.Errorf("ParseGCSBucketAndPrefix(%q) bucket = %q, want %q", tc.uri, gotBucket, tc.wantBucket)
			}
			if gotPrefix != tc.wantPrefix {
				t.Errorf("ParseGCSBucketAndPrefix(%q) prefix = %q, want %q", tc.uri, gotPrefix, tc.wantPrefix)
			}
		})
	}
}

func TestSignedURLExpiryFromEnv(t *testing.T) {
	const def = 24 * time.Hour  // default validity
	const max = 168 * time.Hour // V4 ceiling
	const envVar = "TEST_SIGNED_URL_EXPIRY_HOURS"
	tests := []struct {
		name   string
		env    string // value to set; "" means unset/empty
		setEnv bool
		want   time.Duration
	}{
		{"unset defaults to 24h", "", false, def},
		{"empty defaults to 24h", "", true, def},
		{"explicit 24h", "24", true, 24 * time.Hour},
		{"1h", "1", true, 1 * time.Hour},
		{"exactly 168 stays 168", "168", true, max},
		{"over 168 clamps to 168", "200", true, max},
		{"way over clamps to 168", "100000", true, max},
		{"zero disables", "0", true, 0},
		{"negative -> default", "-5", true, def},
		{"non-numeric -> default", "notanumber", true, def},
		{"float -> default (Atoi fails)", "24.5", true, def},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			// t.Setenv cannot truly unset; empty string is treated as unset.
			t.Setenv(envVar, tc.env)
			if got := SignedURLExpiryFromEnv(envVar); got != tc.want {
				t.Errorf("SignedURLExpiryFromEnv(%q) with env=%q = %v, want %v", envVar, tc.env, got, tc.want)
			}
		})
	}
}

// TestPersistMediaOutputsLocalOnly verifies the local-write path of
// PersistMediaOutputs without touching GCS (gcsBucketURI empty).
func TestPersistMediaOutputsLocalOnly(t *testing.T) {
	// outputDir is now confined to MCP_OUTPUT_ROOT (CWE-22): make the temp dir a
	// child of the configured root and pass it as a relative dir so it stays inside.
	dir := t.TempDir()
	if resolved, err := filepath.EvalSymlinks(dir); err == nil {
		dir = resolved
	}
	t.Setenv(OutputRootEnvVar, filepath.Dir(dir))
	relDir := filepath.Base(dir)
	art := MediaArtifact{
		Data:     []byte("hello-mp4-bytes"),
		MimeType: "video/mp4",
		FileName: "omni_20260101_0.mp4",
	}

	got, err := PersistMediaOutputs(context.Background(), art, relDir, "", 0)
	if err != nil {
		t.Fatalf("PersistMediaOutputs returned fatal error: %v", err)
	}
	wantPath := filepath.Join(dir, art.FileName)
	if got.LocalPath != wantPath {
		t.Errorf("LocalPath = %q, want %q", got.LocalPath, wantPath)
	}
	if got.GCSURI != "" || got.SignedURL != "" || got.GCSError != nil {
		t.Errorf("expected no GCS fields, got %+v", got)
	}
	data, err := os.ReadFile(wantPath)
	if err != nil {
		t.Fatalf("reading persisted file: %v", err)
	}
	if string(data) != string(art.Data) {
		t.Errorf("persisted bytes = %q, want %q", data, art.Data)
	}
}

// TestPersistMediaOutputsNoDestinations verifies that with neither a local dir
// nor a GCS URI the call is a no-op (no error, empty result).
func TestPersistMediaOutputsNoDestinations(t *testing.T) {
	got, err := PersistMediaOutputs(context.Background(), MediaArtifact{Data: []byte("x"), FileName: "f.mp4"}, "", "", 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.LocalPath != "" || got.GCSURI != "" || got.SignedURL != "" || got.GCSError != nil {
		t.Errorf("expected empty result, got %+v", got)
	}
}

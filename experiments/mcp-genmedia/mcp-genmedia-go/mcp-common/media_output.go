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
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"cloud.google.com/go/storage"
)

// signedURLV4MaxHours is the maximum validity for a V4 signed URL (7 days).
const signedURLV4MaxHours = 168

// uploadToGCSFn and generateV4SignedURLFn are indirections over the real GCS
// upload and V4-signing helpers so the GCS branch of PersistMediaOutputs can be
// unit-tested without a live bucket or credentials. They default to the real
// implementations (UploadToGCS / GenerateV4SignedURL) — production behavior is
// unchanged — and are only reassigned by tests, which restore them afterwards.
var (
	uploadToGCSFn         = UploadToGCS
	generateV4SignedURLFn = GenerateV4SignedURL
)

// MediaArtifact is a single generated media blob to persist (an image, a video,
// an audio clip, ...). FileName is the base name including extension; it is used
// verbatim for the local file and, prefixed by any GCS object prefix, for the
// GCS object name.
type MediaArtifact struct {
	Data     []byte
	MimeType string
	FileName string
}

// PersistedMedia is the result of persisting one MediaArtifact. Fields are set
// only for the destinations that were requested and succeeded. GCSError is
// non-fatal (the local write, if any, still succeeded) and is left for the
// caller to surface — matching the suite's established "warn but continue on
// GCS failure" behavior.
type PersistedMedia struct {
	// LocalPath is the local file path written, if output_directory was set.
	LocalPath string
	// GCSURI is the gs:// URI uploaded, if gcs_bucket_uri was set and upload succeeded.
	GCSURI string
	// GCSBucket is the destination bucket name. It is populated whenever a GCS
	// destination was requested (even if the upload later failed) so callers can
	// log the intended bucket alongside GCSError.
	GCSBucket string
	// GCSObject is the object name (prefix + filename) used for the GCS upload. It
	// is populated whenever a GCS destination was requested (even on failure).
	GCSObject string
	// SignedURL is a best-effort V4 signed URL for the uploaded object.
	SignedURL string
	// GCSError holds a non-fatal GCS upload error, if one occurred.
	GCSError error
}

// PersistMediaOutputs writes a generated media artifact to a local directory
// (when outputDir != "") and/or to GCS (when gcsBucketURI != ""), generating a
// best-effort V4 signed URL when signedURLExpiry > 0.
//
// A local directory-creation or write failure is returned as a fatal error. A
// GCS upload failure is non-fatal and reported via PersistedMedia.GCSError so
// the local artifact is still usable. This centralizes the GCS upload +
// V4-signed-URL + prefix-parsing logic that previously lived, duplicated, inside
// individual servers.
func PersistMediaOutputs(ctx context.Context, art MediaArtifact, outputDir, gcsBucketURI string, signedURLExpiry time.Duration) (PersistedMedia, error) {
	var out PersistedMedia

	if outputDir != "" {
		// Confine the caller-supplied output directory to the configured output
		// root before any filesystem operation (CWE-22 directory traversal). This
		// rejects absolute paths and ".." escapes; see ResolveConfinedOutputDir.
		confinedDir, confErr := ResolveConfinedOutputDir(outputDir)
		if confErr != nil {
			return out, fmt.Errorf("invalid output directory: %w", confErr)
		}
		outputDir = confinedDir
		if err := os.MkdirAll(outputDir, 0755); err != nil {
			return out, fmt.Errorf("failed to create output directory: %w", err)
		}
		filePath := filepath.Join(outputDir, art.FileName)
		if err := os.WriteFile(filePath, art.Data, 0644); err != nil {
			return out, fmt.Errorf("failed to write output file: %w", err)
		}
		out.LocalPath = filePath
	}

	if gcsBucketURI != "" {
		bucketName, objectPrefix := ParseGCSBucketAndPrefix(gcsBucketURI)
		objectName := objectPrefix + art.FileName
		// Populate the destination up front so a failed upload can still be logged
		// with its intended bucket/object (GCSURI stays empty until success).
		out.GCSBucket = bucketName
		out.GCSObject = objectName
		if err := uploadToGCSFn(ctx, bucketName, objectName, art.MimeType, art.Data); err != nil {
			out.GCSError = err
			return out, nil
		}
		out.GCSURI = fmt.Sprintf("gs://%s/%s", bucketName, objectName)

		// Best-effort V4 signed HTTPS URL so clients can fetch the media without
		// the bucket being public. Non-fatal on failure.
		if signedURLExpiry > 0 {
			if signedURL, sErr := generateV4SignedURLFn(ctx, bucketName, objectName, signedURLExpiry); sErr != nil {
				log.Printf("failed to generate signed URL for %s: %v", out.GCSURI, sErr)
			} else {
				out.SignedURL = signedURL
			}
		}
	}

	return out, nil
}

// GenerateV4SignedURL creates a V4 GET signed URL for a GCS object. The signing
// key is detected automatically from the ambient credentials (e.g. the
// service-account JSON key referenced by GOOGLE_APPLICATION_CREDENTIALS).
func GenerateV4SignedURL(ctx context.Context, bucketName, objectName string, expiry time.Duration) (string, error) {
	client, err := storage.NewClient(ctx)
	if err != nil {
		return "", fmt.Errorf("storage.NewClient: %w", err)
	}
	defer func() { _ = client.Close() }()

	return client.Bucket(bucketName).SignedURL(objectName, &storage.SignedURLOptions{
		Scheme:  storage.SigningSchemeV4,
		Method:  "GET",
		Expires: time.Now().Add(expiry),
	})
}

// ParseGCSBucketAndPrefix splits a "bucket/optional/prefix/" string (with or
// without a leading gs:// scheme) into a bucket name and an object name prefix
// that is guaranteed to be empty or end with a "/".
func ParseGCSBucketAndPrefix(uri string) (bucket, prefix string) {
	uri = strings.TrimPrefix(uri, "gs://")
	uri = strings.TrimPrefix(uri, "/")
	parts := strings.SplitN(uri, "/", 2)
	bucket = parts[0]
	if len(parts) > 1 && parts[1] != "" {
		prefix = parts[1]
		if !strings.HasSuffix(prefix, "/") {
			prefix += "/"
		}
	}
	return bucket, prefix
}

// SignedURLExpiryFromEnv returns the validity duration for generated V4 signed
// URLs, read from the given environment variable (in hours). It defaults to 24
// hours, clamps values to 168 hours (the V4 maximum), treats "0" as "disable
// signed URLs", and falls back to the default for negative or non-numeric input.
func SignedURLExpiryFromEnv(envVar string) time.Duration {
	const def = 24 * time.Hour
	v := strings.TrimSpace(os.Getenv(envVar))
	if v == "" {
		return def
	}
	h, err := strconv.Atoi(v)
	if err != nil || h < 0 {
		log.Printf("invalid %s=%q, using default of 24", envVar, v)
		return def
	}
	if h == 0 {
		return 0
	}
	if h > signedURLV4MaxHours {
		log.Printf("%s=%d exceeds the V4 maximum of %d (7 days); clamping to %d", envVar, h, signedURLV4MaxHours, signedURLV4MaxHours)
		h = signedURLV4MaxHours
	}
	return time.Duration(h) * time.Hour
}

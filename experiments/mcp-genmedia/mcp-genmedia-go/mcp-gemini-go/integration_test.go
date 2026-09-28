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
	"os"
	"path/filepath"
	"sort"
	"testing"
)

// TestIntegrationGeminiImageNamingEndToEnd is an end-to-end (Path-B: manual
// write + upload) integration test. It drives the real handler response path,
// processGeminiImageResponse, with the REAL local-write seam (writeFileFn =
// os.WriteFile) so files actually land on disk, while routing the GCS leg through
// the network-free uploadToGCSFn seam to capture the object names that would be
// uploaded. It asserts that a single output_filename produces the same
// deterministic, extension-forced, 1-based-suffixed names on BOTH sinks at once —
// the local file tree and the GCS object names — proving the naming is computed
// once and applied consistently across destinations.
//
// TestProcessGeminiImageResponseNaming already covers the name computation via an
// injected writeFileFn; this test additionally proves the real os.WriteFile lands
// the bytes and that the local and GCS names agree. The live GCS upload leg is
// covered, gated behind GENMEDIA_BUCKET, in mcp-common's integration test.
func TestIntegrationGeminiImageNamingEndToEnd(t *testing.T) {
	origUpload := uploadToGCSFn
	t.Cleanup(func() { uploadToGCSFn = origUpload })

	readNames := func(t *testing.T, dir string) []string {
		t.Helper()
		entries, err := os.ReadDir(dir)
		if err != nil {
			t.Fatalf("ReadDir(%s): %v", dir, err)
		}
		var names []string
		for _, e := range entries {
			names = append(names, e.Name())
		}
		sort.Strings(names)
		return names
	}

	t.Run("output_filename applied identically to local files and GCS objects", func(t *testing.T) {
		// output_directory is confined to MCP_OUTPUT_ROOT (CWE-22): configure the
		// root to the temp dir's parent and pass the temp dir as a relative path.
		dir := t.TempDir()
		t.Setenv("MCP_OUTPUT_ROOT", filepath.Dir(dir))
		relDir := filepath.Base(dir)
		var gcsObjects []string
		uploadToGCSFn = func(_ context.Context, _ /*bucket*/, object, _ /*mime*/ string, _ []byte) error {
			gcsObjects = append(gcsObjects, object)
			return nil
		}

		resp := imageResponse(
			imagePart("image/png", []byte("a")),
			imagePart("image/png", []byte("b")),
			imagePart("image/png", []byte("c")),
		)
		// Wrong extension (.jpeg) forced to real MIME (.png); n>1 => _1..n.
		if _, err := processGeminiImageResponse(
			context.Background(), resp, map[string]any{"output_filename": "hero.jpeg"},
			relDir, "gs://bkt/pre/", "bkt", "pre/",
		); err != nil {
			t.Fatalf("processGeminiImageResponse error: %v", err)
		}

		wantLocal := []string{"hero_1.png", "hero_2.png", "hero_3.png"}
		if got := readNames(t, dir); !equalStrings(got, wantLocal) {
			t.Errorf("local files = %v, want %v", got, wantLocal)
		}
		wantGCS := []string{"pre/hero_1.png", "pre/hero_2.png", "pre/hero_3.png"}
		sort.Strings(gcsObjects)
		if !equalStrings(gcsObjects, wantGCS) {
			t.Errorf("uploaded GCS objects = %v, want %v", gcsObjects, wantGCS)
		}
		// Bytes actually written by the real os.WriteFile seam.
		for name, want := range map[string]string{"hero_1.png": "a", "hero_2.png": "b", "hero_3.png": "c"} {
			b, err := os.ReadFile(filepath.Join(dir, name))
			if err != nil {
				t.Fatalf("ReadFile(%s): %v", name, err)
			}
			if string(b) != want {
				t.Errorf("%s = %q, want %q", name, b, want)
			}
		}
	})

	t.Run("single image -> no suffix on both sinks", func(t *testing.T) {
		dir := t.TempDir()
		t.Setenv("MCP_OUTPUT_ROOT", filepath.Dir(dir))
		relDir := filepath.Base(dir)
		var gcsObjects []string
		uploadToGCSFn = func(_ context.Context, _, object, _ string, _ []byte) error {
			gcsObjects = append(gcsObjects, object)
			return nil
		}
		resp := imageResponse(imagePart("image/png", []byte("solo")))
		if _, err := processGeminiImageResponse(
			context.Background(), resp, map[string]any{"output_filename": "hero"},
			relDir, "gs://bkt/pre/", "bkt", "pre/",
		); err != nil {
			t.Fatalf("processGeminiImageResponse error: %v", err)
		}
		if got := readNames(t, dir); !equalStrings(got, []string{"hero.png"}) {
			t.Errorf("local files = %v, want [hero.png]", got)
		}
		if !equalStrings(gcsObjects, []string{"pre/hero.png"}) {
			t.Errorf("uploaded GCS objects = %v, want [pre/hero.png]", gcsObjects)
		}
	})
}

func equalStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

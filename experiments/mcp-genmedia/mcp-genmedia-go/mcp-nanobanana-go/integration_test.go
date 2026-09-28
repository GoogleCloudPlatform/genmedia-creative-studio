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

// TestIntegrationNanobananaNamingToDisk is an end-to-end (Path-A) integration
// test: it drives the real handler response path, processImageResponse, through
// the REAL persistence seam (common.PersistMediaOutputs — not a fake) and asserts
// the resolved output_filename actually lands on disk with the right names AND the
// right bytes. This goes beyond TestProcessImageResponseWiring, which injects a
// fake seam and only observes the requested FileName: here the whole chain
// (ResolveOutputFilename → buildImageFilenames → PersistMediaOutputs → os.WriteFile)
// runs and the observable artifact is the file tree.
//
// It is network-free: gcsBucketURI is empty, so the GCS branch of
// PersistMediaOutputs is never taken (no credentials, no bucket). The live GCS
// leg of Path A/C is covered, gated behind GENMEDIA_BUCKET, in mcp-common's
// integration_gcs_rename_test.go.
func TestIntegrationNanobananaNamingToDisk(t *testing.T) {
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
	readBytes := func(t *testing.T, dir, name string) string {
		t.Helper()
		b, err := os.ReadFile(filepath.Join(dir, name))
		if err != nil {
			t.Fatalf("ReadFile(%s): %v", name, err)
		}
		return string(b)
	}

	t.Run("multiple images -> 1-based suffixed files with forced extension", func(t *testing.T) {
		dir := t.TempDir()
		t.Setenv("MCP_OUTPUT_ROOT", filepath.Dir(dir))
		relDir := filepath.Base(dir)
		resp := imageResponse(
			textPart("here you go"),
			imagePart("image/png", []byte("alpha")),
			imagePart("image/png", []byte("bravo")),
			imagePart("image/png", []byte("charlie")),
		)
		// Client asks for hero.jpeg but the bytes are PNG: the extension must be
		// forced to .png and, because n>1, suffixed _1..n.
		if _, err := processImageResponse(context.Background(), resp, map[string]any{"output_filename": "hero.jpeg"}, relDir, ""); err != nil {
			t.Fatalf("processImageResponse error: %v", err)
		}
		want := []string{"hero_1.png", "hero_2.png", "hero_3.png"}
		if got := readNames(t, dir); !equalStrings(got, want) {
			t.Fatalf("files on disk = %v, want %v", got, want)
		}
		// Bytes must be paired to the right name in generation order.
		for name, wantData := range map[string]string{"hero_1.png": "alpha", "hero_2.png": "bravo", "hero_3.png": "charlie"} {
			if got := readBytes(t, dir, name); got != wantData {
				t.Errorf("%s bytes = %q, want %q", name, got, wantData)
			}
		}
	})

	t.Run("single image -> no suffix", func(t *testing.T) {
		dir := t.TempDir()
		t.Setenv("MCP_OUTPUT_ROOT", filepath.Dir(dir))
		relDir := filepath.Base(dir)
		resp := imageResponse(imagePart("image/png", []byte("solo")))
		if _, err := processImageResponse(context.Background(), resp, map[string]any{"output_filename": "hero"}, relDir, ""); err != nil {
			t.Fatalf("processImageResponse error: %v", err)
		}
		if got := readNames(t, dir); !equalStrings(got, []string{"hero.png"}) {
			t.Fatalf("files on disk = %v, want [hero.png]", got)
		}
		if got := readBytes(t, dir, "hero.png"); got != "solo" {
			t.Errorf("hero.png bytes = %q, want %q", got, "solo")
		}
	})

	t.Run("unset output_filename keeps the legacy default scheme on disk", func(t *testing.T) {
		dir := t.TempDir()
		t.Setenv("MCP_OUTPUT_ROOT", filepath.Dir(dir))
		relDir := filepath.Base(dir)
		resp := imageResponse(imagePart("image/jpeg", []byte("x")))
		if _, err := processImageResponse(context.Background(), resp, map[string]any{}, relDir, ""); err != nil {
			t.Fatalf("processImageResponse error: %v", err)
		}
		got := readNames(t, dir)
		if len(got) != 1 || filepath.Ext(got[0]) != ".jpg" || got[0][:7] != "gemini_" {
			t.Fatalf("expected a single legacy gemini_*.jpg file, got %v", got)
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

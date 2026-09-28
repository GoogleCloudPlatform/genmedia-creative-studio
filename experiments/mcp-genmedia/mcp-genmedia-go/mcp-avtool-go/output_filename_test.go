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
	"path/filepath"
	"strings"
	"testing"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
)

// TestAVToolOutputFilenameWiring is a handler-level wiring test: it drives the exact
// chain each avtool handler runs — resolveAVToolOutputFilename → common.HandleOutputPreparation
// — and asserts the resolved output_filename reaches the final output filename with
// avtool's distinguishing behavior: the extension is NOT forced (avtool is
// exempt — for ffmpeg the extension selects the output container), precedence is
// honored (output_filename wins over the legacy output_file_name), a missing
// extension gets the tool's default appended, traversal is sanitized, and an unset
// value falls through to a unique <default> name. avtool is single-artifact, so no
// _1..n suffix is applied.
func TestAVToolOutputFilenameWiring(t *testing.T) {
	const defaultExt = "mp4"

	t.Run("output_filename honored, client extension NOT forced", func(t *testing.T) {
		// Client asks for .mkv but the tool default is mp4 — avtool keeps .mkv.
		args := map[string]interface{}{"output_filename": "clip.mkv"}
		_, final, cleanup, err := common.HandleOutputPreparation(resolveAVToolOutputFilename(args), defaultExt)
		defer cleanup()
		if err != nil {
			t.Fatalf("HandleOutputPreparation error: %v", err)
		}
		if final != "clip.mkv" {
			t.Errorf("final filename = %q, want clip.mkv (extension must NOT be forced)", final)
		}
	})

	t.Run("output_filename wins over legacy output_file_name", func(t *testing.T) {
		args := map[string]interface{}{"output_filename": "new.mov", "output_file_name": "legacy.mp4"}
		_, final, cleanup, err := common.HandleOutputPreparation(resolveAVToolOutputFilename(args), defaultExt)
		defer cleanup()
		if err != nil {
			t.Fatalf("HandleOutputPreparation error: %v", err)
		}
		if final != "new.mov" {
			t.Errorf("final filename = %q, want new.mov (output_filename wins, ext not forced)", final)
		}
	})

	t.Run("missing extension gets the tool default appended", func(t *testing.T) {
		args := map[string]interface{}{"output_filename": "clip"}
		_, final, cleanup, err := common.HandleOutputPreparation(resolveAVToolOutputFilename(args), defaultExt)
		defer cleanup()
		if err != nil {
			t.Fatalf("HandleOutputPreparation error: %v", err)
		}
		if final != "clip."+defaultExt {
			t.Errorf("final filename = %q, want clip.%s", final, defaultExt)
		}
	})

	t.Run("traversal sanitized, extension preserved", func(t *testing.T) {
		args := map[string]interface{}{"output_filename": "../../etc/out.gif"}
		_, final, cleanup, err := common.HandleOutputPreparation(resolveAVToolOutputFilename(args), defaultExt)
		defer cleanup()
		if err != nil {
			t.Fatalf("HandleOutputPreparation error: %v", err)
		}
		if final != "out.gif" {
			t.Errorf("final filename = %q, want out.gif", final)
		}
		if strings.Contains(final, "/") || strings.Contains(final, "..") {
			t.Errorf("final filename %q still contains path separators/traversal", final)
		}
	})

	t.Run("unset -> unique default name with tool extension", func(t *testing.T) {
		args := map[string]interface{}{}
		_, final, cleanup, err := common.HandleOutputPreparation(resolveAVToolOutputFilename(args), defaultExt)
		defer cleanup()
		if err != nil {
			t.Fatalf("HandleOutputPreparation error: %v", err)
		}
		if !strings.HasPrefix(final, "ffmpeg_output_") || filepath.Ext(final) != "."+defaultExt {
			t.Errorf("final filename = %q, want ffmpeg_output_*.%s default", final, defaultExt)
		}
	})
}

// TestResolveAVToolOutputFilename covers the avtool naming decision: output_filename
// wins over the deprecated output_file_name alias; the client-provided extension is
// PRESERVED (avtool is exempt from extension-forcing); traversal is
// sanitized; and an empty/unusable value falls through to the unique-name default.
func TestResolveAVToolOutputFilename(t *testing.T) {
	tests := []struct {
		name    string
		argsMap map[string]interface{}
		want    string
	}{
		{
			name:    "output_filename honored, extension preserved",
			argsMap: map[string]interface{}{"output_filename": "converted.mp3"},
			want:    "converted.mp3",
		},
		{
			name:    "arbitrary client extension preserved (no forcing)",
			argsMap: map[string]interface{}{"output_filename": "clip.mkv"},
			want:    "clip.mkv",
		},
		{
			name:    "legacy output_file_name used when output_filename unset",
			argsMap: map[string]interface{}{"output_file_name": "legacy.mp4"},
			want:    "legacy.mp4",
		},
		{
			name: "output_filename wins over legacy output_file_name",
			argsMap: map[string]interface{}{
				"output_filename":  "new.mp4",
				"output_file_name": "legacy.mp4",
			},
			want: "new.mp4",
		},
		{
			name:    "traversal sanitized, extension kept",
			argsMap: map[string]interface{}{"output_filename": "../../etc/out.gif"},
			want:    "out.gif",
		},
		{
			name:    "unset -> empty (unique-name default)",
			argsMap: map[string]interface{}{},
			want:    "",
		},
		{
			name:    "dot-only sanitizes to empty (unique-name default)",
			argsMap: map[string]interface{}{"output_filename": "..."},
			want:    "",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := resolveAVToolOutputFilename(tc.argsMap); got != tc.want {
				t.Errorf("resolveAVToolOutputFilename(%v) = %q, want %q", tc.argsMap, got, tc.want)
			}
		})
	}
}

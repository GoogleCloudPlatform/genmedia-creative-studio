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
	"fmt"
	"os"
	"path/filepath"
	"testing"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
)

// mp3ID3Bytes is a minimal MP3 payload leading with an ID3v2 tag — the shape the
// Lyria 3 models return, carrying Google's C2PA provenance manifest (issue #1777).
var mp3ID3Bytes = append([]byte("ID3"), 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00)

// mp3SyncBytes is a payload leading with a bare MPEG-1 Layer 3 frame sync (no ID3).
var mp3SyncBytes = []byte{0xFF, 0xFB, 0x90, 0x00}

// wavBytes is a minimal RIFF/WAVE header.
var wavBytes = []byte("RIFF\x00\x00\x00\x00WAVEfmt ")

// unknownBytes are not recognizable as any known audio container.
var unknownBytes = []byte("not-real-audio-bytes")

// TestSaveLyriaLocalFileWiring is a handler-level wiring test: it drives the
// name→write path the handler uses (resolveLyriaOutputBase -> finalizeLyriaFilename
// -> saveLyriaLocalFile) with the os.WriteFile seam (writeFileFn) replaced by a
// recorder, and asserts the finalized name actually reaches the write. It covers
// issue #1777: the requested extension is respected, missing extensions default to
// .mp3, and an MP3 bitstream forces .mp3 regardless of the requested extension so
// the container matches the bytes and the C2PA/ID3 manifest is preserved.
func TestSaveLyriaLocalFileWiring(t *testing.T) {
	// saveLyriaLocalFile now confines the output directory to MCP_OUTPUT_ROOT
	// (CWE-22). Use a relative dir under a configured temp root.
	root := t.TempDir()
	t.Setenv("MCP_OUTPUT_ROOT", root)
	const dir = "out"
	resolvedRoot, evalErr := filepath.EvalSymlinks(root)
	if evalErr != nil {
		resolvedRoot = root
	}
	confinedDir := filepath.Join(resolvedRoot, dir)

	origWrite := writeFileFn
	t.Cleanup(func() { writeFileFn = origWrite })

	var gotPath string
	var gotBytes []byte
	writeFileFn = func(name string, data []byte, _ os.FileMode) error {
		gotPath, gotBytes = name, data
		return nil
	}

	cases := []struct {
		name   string
		params map[string]any
		audio  []byte
		want   string
	}{
		{"requested .mp3 respected (non-audio bytes)", map[string]any{"output_filename": "song.mp3"}, unknownBytes, "song.mp3"},
		{"requested .wav respected when bytes are WAV", map[string]any{"output_filename": "song.wav"}, wavBytes, "song.wav"},
		{"missing extension defaults to .mp3", map[string]any{"output_filename": "song"}, unknownBytes, "song.mp3"},
		{"MP3 (ID3) bytes force .mp3 over requested .wav", map[string]any{"output_filename": "song.wav"}, mp3ID3Bytes, "song.mp3"},
		{"MP3 (frame sync) bytes force .mp3 over requested .wav", map[string]any{"output_filename": "song.wav"}, mp3SyncBytes, "song.mp3"},
		{"requested .mp3 with MP3 bytes not over-corrected", map[string]any{"output_filename": "song.mp3"}, mp3ID3Bytes, "song.mp3"},
		{"legacy file_name alias used when output_filename unset", map[string]any{"file_name": "legacy.mp3"}, mp3ID3Bytes, "legacy.mp3"},
		{"output_filename wins over legacy file_name", map[string]any{"output_filename": "new.mp3", "file_name": "legacy.mp3"}, mp3ID3Bytes, "new.mp3"},
		{"traversal sanitized before write", map[string]any{"output_filename": "../../etc/song.wav"}, mp3ID3Bytes, "song.mp3"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			gotPath, gotBytes = "", nil
			base, err := resolveLyriaOutputBase(tc.params)
			if err != nil {
				t.Fatalf("resolveLyriaOutputBase error: %v", err)
			}
			finalName := finalizeLyriaFilename(base, tc.audio)
			fullPath, werr := saveLyriaLocalFile(dir, finalName, tc.audio)
			if werr != nil {
				t.Fatalf("saveLyriaLocalFile error: %v", werr)
			}
			want := filepath.Join(confinedDir, tc.want)
			if fullPath != want || gotPath != want {
				t.Errorf("fullPath=%q writeTarget=%q, want %q", fullPath, gotPath, want)
			}
			if string(gotBytes) != string(tc.audio) {
				t.Errorf("bytes written = %q, want %q", gotBytes, tc.audio)
			}
		})
	}

	t.Run("write error surfaced with the intended path", func(t *testing.T) {
		writeFileFn = func(string, []byte, os.FileMode) error { return fmt.Errorf("disk full") }
		t.Cleanup(func() {
			writeFileFn = func(name string, data []byte, _ os.FileMode) error { gotPath, gotBytes = name, data; return nil }
		})
		base, err := resolveLyriaOutputBase(map[string]any{"output_filename": "song.wav"})
		if err != nil {
			t.Fatalf("resolve error: %v", err)
		}
		finalName := finalizeLyriaFilename(base, mp3ID3Bytes)
		fullPath, werr := saveLyriaLocalFile(dir, finalName, mp3ID3Bytes)
		if werr == nil {
			t.Fatalf("expected write error")
		}
		if fullPath != filepath.Join(confinedDir, "song.mp3") {
			t.Errorf("path should still be reported on write error, got %q", fullPath)
		}
	})
}

// TestResolveLyriaOutputBase covers the base-name decision: output_filename wins
// over the legacy file_name alias, the client's requested extension is preserved
// (no longer forced — issue #1777, finalizeLyriaFilename decides the extension),
// traversal is sanitized, unset -> "" (caller uses the shortid default), and a
// dot-only name errors.
func TestResolveLyriaOutputBase(t *testing.T) {
	tests := []struct {
		name    string
		params  map[string]any
		want    string
		wantErr bool
	}{
		{
			name:   "output_filename honored, .mp3 extension kept",
			params: map[string]any{"output_filename": "song.mp3"},
			want:   "song.mp3",
		},
		{
			name:   "requested .wav extension preserved (not forced)",
			params: map[string]any{"output_filename": "song.wav"},
			want:   "song.wav",
		},
		{
			name:   "missing extension left as-is (finalized later)",
			params: map[string]any{"output_filename": "song"},
			want:   "song",
		},
		{
			name:   "legacy file_name alias used when output_filename unset",
			params: map[string]any{"file_name": "legacy.wav"},
			want:   "legacy.wav",
		},
		{
			name:   "output_filename wins over legacy file_name",
			params: map[string]any{"output_filename": "new.mp3", "file_name": "legacy.wav"},
			want:   "new.mp3",
		},
		{
			name:   "traversal sanitized",
			params: map[string]any{"output_filename": "../../etc/song.wav"},
			want:   "song.wav",
		},
		{
			name:   "unset -> empty (shortid default)",
			params: map[string]any{},
			want:   "",
		},
		{
			name:    "dot-only base errors",
			params:  map[string]any{"output_filename": "..."},
			wantErr: true,
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := resolveLyriaOutputBase(tc.params)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("resolveLyriaOutputBase(%v) = %q, want error", tc.params, got)
				}
				return
			}
			if err != nil {
				t.Fatalf("resolveLyriaOutputBase(%v) unexpected error: %v", tc.params, err)
			}
			if got != tc.want {
				t.Errorf("resolveLyriaOutputBase(%v) = %q, want %q", tc.params, got, tc.want)
			}
		})
	}
}

// TestDetectAudioMIMEType pins the magic-byte sniffing that keeps the saved
// container matched to the bitstream (issue #1777).
func TestDetectAudioMIMEType(t *testing.T) {
	tests := []struct {
		name string
		data []byte
		want string
	}{
		{"ID3v2 tag -> mp3", mp3ID3Bytes, "audio/mpeg"},
		{"MPEG frame sync -> mp3", mp3SyncBytes, "audio/mpeg"},
		{"RIFF/WAVE -> wav", wavBytes, "audio/wav"},
		{"Ogg -> ogg", []byte("OggS\x00\x02"), "audio/ogg"},
		{"unknown -> empty", unknownBytes, ""},
		{"empty -> empty", []byte{}, ""},
		{"single 0xFF (no valid sync) -> empty", []byte{0xFF}, ""},
		{"0xFF with non-sync second byte -> empty", []byte{0xFF, 0x01}, ""},
		{"RIFF without WAVE (e.g. AVI) -> empty", []byte("RIFF\x00\x00\x00\x00AVI LIST"), ""},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := detectAudioMIMEType(tc.data); got != tc.want {
				t.Errorf("detectAudioMIMEType(%q) = %q, want %q", tc.data, got, tc.want)
			}
		})
	}
}

// TestFinalizeLyriaFilename covers the extension-resolution contract for issue
// #1777: detected MP3 bytes force .mp3 regardless of the requested extension;
// otherwise the requested extension is respected; otherwise the default is .mp3.
func TestFinalizeLyriaFilename(t *testing.T) {
	tests := []struct {
		name  string
		base  string
		audio []byte
		want  string
	}{
		{"MP3 (ID3) forces .mp3 over requested .wav", "song.wav", mp3ID3Bytes, "song.mp3"},
		{"MP3 (frame sync) forces .mp3 over requested .wav", "song.wav", mp3SyncBytes, "song.mp3"},
		{"requested .mp3 preserved with MP3 bytes (no over-correction)", "song.mp3", mp3ID3Bytes, "song.mp3"},
		{"WAV bytes keep requested .wav", "song.wav", wavBytes, "song.wav"},
		{"unknown bytes respect requested extension", "song.aiff", unknownBytes, "song.aiff"},
		{"unknown bytes, no extension -> default .mp3", "song", unknownBytes, "song.mp3"},
		{"shortid default stem, MP3 bytes -> .mp3", "lyria_output_abc", mp3ID3Bytes, "lyria_output_abc.mp3"},
		{"shortid default stem, unknown bytes -> .mp3", "lyria_output_abc", unknownBytes, "lyria_output_abc.mp3"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := finalizeLyriaFilename(tc.base, tc.audio); got != tc.want {
				t.Errorf("finalizeLyriaFilename(%q, <%d bytes>) = %q, want %q", tc.base, len(tc.audio), got, tc.want)
			}
		})
	}
}

// TestResolveLyriaDestinationAndModel covers issue #1789 parameter standardization
// in mcp-lyria-go: canonical gcs_bucket_uri, output_directory, and model take
// precedence over legacy output_gcs_bucket, local_path, and model_id aliases.
func TestResolveLyriaDestinationAndModel(t *testing.T) {
	cfg := &common.Config{GenmediaBucket: "default-bucket"}

	t.Run("canonical params win over legacy aliases", func(t *testing.T) {
		params := map[string]any{
			"gcs_bucket_uri":    "gs://canonical-bucket/",
			"output_gcs_bucket": "legacy-bucket",
			"output_directory":  "./canonical_dir",
			"local_path":        "./legacy_dir",
			"model":             "lyria-3-pro-preview",
			"model_id":          "lyria-002",
		}
		bucket, dir, model := resolveLyriaDestinationAndModel(params, cfg)
		if bucket != "canonical-bucket" {
			t.Errorf("bucket = %q, want canonical-bucket", bucket)
		}
		if dir != "./canonical_dir" {
			t.Errorf("dir = %q, want ./canonical_dir", dir)
		}
		if model != "lyria-3-pro-preview" {
			t.Errorf("model = %q, want lyria-3-pro-preview", model)
		}
	})

	t.Run("legacy aliases still work when canonical unset", func(t *testing.T) {
		params := map[string]any{
			"output_gcs_bucket": "gs://legacy-bucket",
			"local_path":        "./legacy_dir",
			"model_id":          "lyria-002",
		}
		bucket, dir, model := resolveLyriaDestinationAndModel(params, cfg)
		if bucket != "legacy-bucket" {
			t.Errorf("bucket = %q, want legacy-bucket", bucket)
		}
		if dir != "./legacy_dir" {
			t.Errorf("dir = %q, want ./legacy_dir", dir)
		}
		if model != "lyria-002" {
			t.Errorf("model = %q, want lyria-002", model)
		}
	})

	t.Run("defaults used when neither canonical nor legacy set", func(t *testing.T) {
		bucket, dir, model := resolveLyriaDestinationAndModel(map[string]any{}, cfg)
		if bucket != "default-bucket" {
			t.Errorf("bucket = %q, want default-bucket", bucket)
		}
		if dir != "" {
			t.Errorf("dir = %q, want empty", dir)
		}
		if model != defaultLyriaModelID {
			t.Errorf("model = %q, want %q", model, defaultLyriaModelID)
		}
	})
}

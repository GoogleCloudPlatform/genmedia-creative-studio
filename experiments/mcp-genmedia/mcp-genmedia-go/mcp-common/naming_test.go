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
	"reflect"
	"strings"
	"testing"
)

func TestBuildOutputFilenames(t *testing.T) {
	tests := []struct {
		name     string
		base     string
		count    int
		mimeType string
		want     []string
		wantErr  bool
	}{
		{
			name:     "single no suffix",
			base:     "foo.png",
			count:    1,
			mimeType: "image/png",
			want:     []string{"foo.png"},
		},
		{
			name:     "multiple gets 1-based contiguous suffix",
			base:     "foo.png",
			count:    3,
			mimeType: "image/png",
			want:     []string{"foo_1.png", "foo_2.png", "foo_3.png"},
		},
		{
			name:     "no extension input gets forced extension",
			base:     "foo",
			count:    1,
			mimeType: "image/jpeg",
			want:     []string{"foo.jpg"},
		},
		{
			name:     "wrong extension is forced to true MIME",
			base:     "foo.jpeg",
			count:    1,
			mimeType: "image/png",
			want:     []string{"foo.png"},
		},
		{
			name:     "wrong extension forced across multiple",
			base:     "hero.gif",
			count:    2,
			mimeType: "image/png",
			want:     []string{"hero_1.png", "hero_2.png"},
		},
		{
			name:     "audio wav multiple",
			base:     "track",
			count:    2,
			mimeType: "audio/wav",
			want:     []string{"track_1.wav", "track_2.wav"},
		},
		{
			name:     "video mp4 single",
			base:     "clip",
			count:    1,
			mimeType: "video/mp4",
			want:     []string{"clip.mp4"},
		},
		{
			name:     "no zero padding across order of magnitude",
			base:     "img",
			count:    10,
			mimeType: "image/png",
			want: []string{
				"img_1.png", "img_2.png", "img_3.png", "img_4.png", "img_5.png",
				"img_6.png", "img_7.png", "img_8.png", "img_9.png", "img_10.png",
			},
		},
		{
			name:     "traversal base is sanitized before naming",
			base:     "../../etc/passwd",
			count:    1,
			mimeType: "image/png",
			want:     []string{"passwd.png"},
		},
		{
			name:     "count zero is an error",
			base:     "foo.png",
			count:    0,
			mimeType: "image/png",
			wantErr:  true,
		},
		{
			name:     "negative count is an error",
			base:     "foo.png",
			count:    -1,
			mimeType: "image/png",
			wantErr:  true,
		},
		{
			name:     "empty base is an error",
			base:     "",
			count:    1,
			mimeType: "image/png",
			wantErr:  true,
		},
		{
			name:     "dot-only base sanitizes to empty and errors",
			base:     "..",
			count:    2,
			mimeType: "image/png",
			wantErr:  true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := BuildOutputFilenames(tc.base, tc.count, tc.mimeType)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("BuildOutputFilenames(%q, %d, %q) = %v, want error", tc.base, tc.count, tc.mimeType, got)
				}
				return
			}
			if err != nil {
				t.Fatalf("BuildOutputFilenames(%q, %d, %q) unexpected error: %v", tc.base, tc.count, tc.mimeType, err)
			}
			if !reflect.DeepEqual(got, tc.want) {
				t.Errorf("BuildOutputFilenames(%q, %d, %q) = %v, want %v", tc.base, tc.count, tc.mimeType, got, tc.want)
			}
		})
	}
}

// TestBuildOutputFilenamesOrdering asserts contiguity and generation order
// independent of the table above.
func TestBuildOutputFilenamesOrdering(t *testing.T) {
	got, err := BuildOutputFilenames("scene.png", 4, "image/png")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := []string{"scene_1.png", "scene_2.png", "scene_3.png", "scene_4.png"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("ordering/contiguity mismatch: got %v want %v", got, want)
	}
}

func TestSanitizeBaseFilename(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want string
	}{
		{"plain name", "hero.png", "hero.png"},
		{"parent traversal", "../../etc/passwd", "passwd"},
		{"leading slash absolute", "/etc/passwd", "passwd"},
		{"embedded separators reduced to last component", "a/b/c.png", "c.png"},
		{"windows separators", "..\\..\\secret.txt", "secret.txt"},
		{"single dot", ".", ""},
		{"double dot", "..", ""},
		{"dot-only run", "...", ""},
		{"empty", "", ""},
		{"whitespace only", "   ", ""},
		{"control chars stripped", "he\x00ro\x1f.png", "hero.png"},
		{"trims surrounding whitespace", "  hero.png  ", "hero.png"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := SanitizeBaseFilename(tc.in); got != tc.want {
				t.Errorf("SanitizeBaseFilename(%q) = %q, want %q", tc.in, got, tc.want)
			}
		})
	}
}

// TestSanitizeBaseFilenameHasNoSeparators is a security invariant: the output
// must never contain a path separator, so it can never escape a target directory
// or GCS prefix.
func TestSanitizeBaseFilenameHasNoSeparators(t *testing.T) {
	inputs := []string{
		"../../etc/passwd",
		"/absolute/path/file.png",
		"..\\..\\windows\\file.png",
		"a/b/c/d.png",
		"nested/dir/",
	}
	for _, in := range inputs {
		got := SanitizeBaseFilename(in)
		if strings.ContainsAny(got, `/\`) {
			t.Errorf("SanitizeBaseFilename(%q) = %q, contains a path separator", in, got)
		}
	}
}

func TestExtensionForMIMEType(t *testing.T) {
	tests := []struct {
		mimeType string
		want     string
	}{
		// images delegate to ImageExtensionForMIMEType
		{"image/png", ".png"},
		{"image/jpeg", ".jpg"},
		{"image/webp", ".webp"},
		{"image/gif", ".gif"},
		{"image/unknown", ".png"}, // image/* default via ImageExtensionForMIMEType
		{"IMAGE/JPEG", ".jpg"},    // case-insensitive
		// audio
		{"audio/mpeg", ".mp3"},
		{"audio/mp3", ".mp3"},
		{"audio/wav", ".wav"},
		{"audio/x-wav", ".wav"},
		{"audio/L16", ".wav"},
		{"audio/ogg", ".ogg"},
		{"audio/mp4", ".m4a"},
		{"audio/x-m4a", ".m4a"},
		{"audio/mulaw", ".mulaw"},
		{"audio/alaw", ".alaw"},
		{"audio/pcm", ".pcm"},
		{"AUDIO/PCM", ".pcm"}, // case-insensitive
		// video
		{"video/mp4", ".mp4"},
		{"video/webm", ".webm"},
	}
	for _, tc := range tests {
		t.Run(tc.mimeType, func(t *testing.T) {
			if got := ExtensionForMIMEType(tc.mimeType); got != tc.want {
				t.Errorf("ExtensionForMIMEType(%q) = %q, want %q", tc.mimeType, got, tc.want)
			}
		})
	}
}

// TestExtensionForMIMETypeFallback covers the mime.ExtensionsByType fallback path
// and the empty/unknown -> "" behavior.
func TestExtensionForMIMETypeFallback(t *testing.T) {
	// A registered non-image/audio/video type should resolve via the stdlib.
	if got := ExtensionForMIMEType("application/json"); got == "" {
		t.Errorf("ExtensionForMIMEType(application/json) = \"\", want a stdlib-provided extension")
	}
	// A clearly bogus type has no extension.
	if got := ExtensionForMIMEType("not-a-real/mime-type-xyz"); got != "" {
		t.Errorf("ExtensionForMIMEType(bogus) = %q, want empty", got)
	}
	if got := ExtensionForMIMEType(""); got != "" {
		t.Errorf("ExtensionForMIMEType(empty) = %q, want empty", got)
	}
}

// TestResolveOutputFilename covers the shared accept-and-alias precedence
// contract: output_filename wins, then the first non-empty legacy alias
// (in order), then "" (caller falls back to its default scheme).
func TestResolveOutputFilename(t *testing.T) {
	tests := []struct {
		name       string
		args       map[string]any
		legacyKeys []string
		want       string
	}{
		{
			name: "output_filename honored",
			args: map[string]any{"output_filename": "hero.png"},
			want: "hero.png",
		},
		{
			name: "output_filename trimmed",
			args: map[string]any{"output_filename": "  hero.png  "},
			want: "hero.png",
		},
		{
			name:       "legacy alias used when output_filename unset (back-compat)",
			args:       map[string]any{"file_name": "legacy.wav"},
			legacyKeys: []string{"file_name"},
			want:       "legacy.wav",
		},
		{
			name:       "output_filename wins on conflict with legacy alias",
			args:       map[string]any{"output_filename": "new.wav", "file_name": "legacy.wav"},
			legacyKeys: []string{"file_name"},
			want:       "new.wav",
		},
		{
			name:       "first non-empty legacy alias wins when multiple given",
			args:       map[string]any{"output_file_name": "second.mp4"},
			legacyKeys: []string{"missing_key", "output_file_name"},
			want:       "second.mp4",
		},
		{
			name:       "blank legacy alias skipped",
			args:       map[string]any{"file_name": "   "},
			legacyKeys: []string{"file_name"},
			want:       "",
		},
		{
			name: "none set returns empty (default scheme)",
			args: map[string]any{},
			want: "",
		},
		{
			name: "blank output_filename ignored",
			args: map[string]any{"output_filename": "   "},
			want: "",
		},
		{
			name:       "non-string values ignored",
			args:       map[string]any{"output_filename": 42, "file_name": true},
			legacyKeys: []string{"file_name"},
			want:       "",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := ResolveOutputFilename(tc.args, tc.legacyKeys...); got != tc.want {
				t.Errorf("ResolveOutputFilename(%v, %v) = %q, want %q", tc.args, tc.legacyKeys, got, tc.want)
			}
		})
	}
}

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
	"testing"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
)

func TestValidateGeminiImageParams(t *testing.T) {
	withSizes := common.GeminiImageModelInfo{
		CanonicalName:         "gemini-3.1-flash-image",
		SupportedAspectRatios: []string{"1:1", "16:9", "9:21"},
		SupportedImageSizes:   []string{"1K", "2K", "4K"},
	}
	noSizes := common.GeminiImageModelInfo{
		CanonicalName:         "gemini-3.1-flash-image",
		SupportedAspectRatios: []string{"1:1", "16:9"},
		SupportedImageSizes:   []string{},
	}

	tests := []struct {
		name          string
		info          common.GeminiImageModelInfo
		aspectRatio   string
		imageSize     string
		wantAspect    string
		wantImageSize string
	}{
		{
			name:          "valid aspect and size pass through",
			info:          withSizes,
			aspectRatio:   "16:9",
			imageSize:     "2K",
			wantAspect:    "16:9",
			wantImageSize: "2K",
		},
		{
			name:          "unsupported aspect falls back to 1:1",
			info:          withSizes,
			aspectRatio:   "3:1",
			imageSize:     "1K",
			wantAspect:    "1:1",
			wantImageSize: "1K",
		},
		{
			name:          "unsupported size is dropped",
			info:          withSizes,
			aspectRatio:   "1:1",
			imageSize:     "8K",
			wantAspect:    "1:1",
			wantImageSize: "",
		},
		{
			name:          "size dropped when model supports none",
			info:          noSizes,
			aspectRatio:   "16:9",
			imageSize:     "2K",
			wantAspect:    "16:9",
			wantImageSize: "",
		},
		{
			name:          "empty size stays empty",
			info:          noSizes,
			aspectRatio:   "1:1",
			imageSize:     "",
			wantAspect:    "1:1",
			wantImageSize: "",
		},
		{
			name:          "newly-supported aspect ratio is not downgraded",
			info:          withSizes,
			aspectRatio:   "9:21",
			imageSize:     "",
			wantAspect:    "9:21",
			wantImageSize: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotAspect, gotSize := validateGeminiImageParams(tt.info, tt.info.CanonicalName, tt.aspectRatio, tt.imageSize)
			if gotAspect != tt.wantAspect {
				t.Errorf("aspectRatio = %q, want %q", gotAspect, tt.wantAspect)
			}
			if gotSize != tt.wantImageSize {
				t.Errorf("imageSize = %q, want %q", gotSize, tt.wantImageSize)
			}
		})
	}
}

// TestSeedForModel pins the Q3 behavior: gemini-nano-banana-2.1 rejects the seed
// parameter, so any caller-supplied seed must be dropped before it reaches the
// API; every other model forwards the seed unchanged.
func TestSeedForModel(t *testing.T) {
	s := int32(42)

	tests := []struct {
		name  string
		model string
		seed  *int32
		want  *int32
	}{
		{name: "seed dropped for nano-banana-2.1", model: "gemini-nano-banana-2.1", seed: &s, want: nil},
		{name: "nil seed stays nil for nano-banana-2.1", model: "gemini-nano-banana-2.1", seed: nil, want: nil},
		{name: "seed forwarded for gemini-3.1-flash-image", model: "gemini-3.1-flash-image", seed: &s, want: &s},
		{name: "seed forwarded for gemini-3-pro-image", model: "gemini-3-pro-image", seed: &s, want: &s},
		{name: "nil seed stays nil for other model", model: "gemini-3.1-flash-image", seed: nil, want: nil},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := seedForModel(tt.model, tt.seed)
			switch {
			case tt.want == nil && got != nil:
				t.Errorf("seedForModel(%q, %v) = %d, want nil", tt.model, tt.seed, *got)
			case tt.want != nil && got == nil:
				t.Errorf("seedForModel(%q, %v) = nil, want %d", tt.model, tt.seed, *tt.want)
			case tt.want != nil && got != nil && *got != *tt.want:
				t.Errorf("seedForModel(%q, %v) = %d, want %d", tt.model, tt.seed, *got, *tt.want)
			}
		})
	}
}

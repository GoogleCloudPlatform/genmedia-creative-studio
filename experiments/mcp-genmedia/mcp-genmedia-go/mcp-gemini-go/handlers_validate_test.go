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

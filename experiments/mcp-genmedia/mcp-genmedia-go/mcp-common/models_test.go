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
	"testing"
)

// TestGeminiImageModelAspectRatios pins the corrected, doc-verified aspect-ratio
// lists for every supported Gemini image model. These lists gate the handler
// validation added for issue #1746: a stale list would wrongly downgrade a
// user's valid aspect ratio to 1:1.
func TestGeminiImageModelAspectRatios(t *testing.T) {
	want := map[string][]string{
		"gemini-3.1-flash-image":      {"1:1", "3:2", "2:3", "3:4", "1:4", "4:1", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9", "9:21"},
		"gemini-3.1-flash-lite-image": {"1:1", "1:4", "4:1", "1:8", "8:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"},
		"gemini-3-pro-image":          {"1:1", "3:2", "2:3", "3:4", "1:4", "4:1", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9", "9:21"},
		"gemini-nano-banana-2.1":      {"1:1", "3:2", "2:3", "3:4", "1:4", "4:1", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9", "9:21"},
	}
	for model, ratios := range want {
		info, ok := SupportedGeminiImageModels[model]
		if !ok {
			t.Errorf("model %q missing from SupportedGeminiImageModels", model)
			continue
		}
		if !reflect.DeepEqual(info.SupportedAspectRatios, ratios) {
			t.Errorf("model %q aspect ratios = %v, want %v", model, info.SupportedAspectRatios, ratios)
		}
	}
}

// TestGeminiImageModelSizes pins the SupportedImageSizes field added for #1746.
func TestGeminiImageModelSizes(t *testing.T) {
	want := map[string][]string{
		"gemini-3.1-flash-image":      {"512", "1K", "2K", "4K"},
		"gemini-3.1-flash-lite-image": {"1K"},
		"gemini-3-pro-image":          {"1K", "2K", "4K"},
		"gemini-nano-banana-2.1":      {"1K", "2K", "4K"},
	}
	for model, sizes := range want {
		info, ok := SupportedGeminiImageModels[model]
		if !ok {
			t.Errorf("model %q missing from SupportedGeminiImageModels", model)
			continue
		}
		if len(info.SupportedImageSizes) != len(sizes) {
			t.Errorf("model %q image sizes = %v, want %v", model, info.SupportedImageSizes, sizes)
			continue
		}
		if len(sizes) > 0 && !reflect.DeepEqual(info.SupportedImageSizes, sizes) {
			t.Errorf("model %q image sizes = %v, want %v", model, info.SupportedImageSizes, sizes)
		}
	}
}

// TestResolveGeminiImageModelAlias confirms alias resolution still returns the
// canonical entry (with its populated SupportedImageSizes).
func TestResolveGeminiImageModelAlias(t *testing.T) {
	info, found := ResolveGeminiImageModel("nano-banana-2.1", false)
	if !found {
		t.Fatal("expected alias 'nano-banana-2.1' to resolve")
	}
	if info.CanonicalName != "gemini-nano-banana-2.1" {
		t.Errorf("CanonicalName = %q, want gemini-nano-banana-2.1", info.CanonicalName)
	}
	if len(info.SupportedImageSizes) == 0 {
		t.Errorf("gemini-nano-banana-2.1 SupportedImageSizes = %v, want non-empty", info.SupportedImageSizes)
	}
}

// TestResolveGeminiImageModelUnsafeFallback confirms the permissive fallback for
// experimental models carries a populated SupportedImageSizes superset so a
// caller-supplied image_size is not stripped by the handler validation.
func TestResolveGeminiImageModelUnsafeFallback(t *testing.T) {
	info, found := ResolveGeminiImageModel("some-future-image-model", true)
	if !found {
		t.Fatal("expected unsafe fallback to resolve when allowUnsafe=true")
	}
	if info.CanonicalName != "some-future-image-model" {
		t.Errorf("CanonicalName = %q, want some-future-image-model", info.CanonicalName)
	}
	if len(info.SupportedImageSizes) == 0 {
		t.Error("expected unsafe fallback to carry a permissive SupportedImageSizes list")
	}

	if _, found := ResolveGeminiImageModel("some-future-image-model", false); found {
		t.Error("expected unknown model to NOT resolve when allowUnsafe=false")
	}
}

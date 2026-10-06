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
	"fmt"
	"sort"
	"strings"
)

// --- Imagen Model Configuration ---

// ImagenModelInfo holds the details for a specific Imagen model.
type ImagenModelInfo struct {
	CanonicalName         string
	MaxImages             int32
	Aliases               []string
	SupportedAspectRatios []string
	SupportedImageSizes   []string
}

// SupportedImagenModels is the single source of truth for all supported Imagen models.
var SupportedImagenModels = map[string]ImagenModelInfo{
	"imagen-3.0-generate-001": {
		CanonicalName:         "imagen-3.0-generate-001",
		MaxImages:             4,
		Aliases:               []string{},
		SupportedAspectRatios: []string{"1:1", "3:4", "4:3", "9:16", "16:9"},
		SupportedImageSizes:   []string{},
	},
	"imagen-3.0-fast-generate-001": {
		CanonicalName:         "imagen-3.0-fast-generate-001",
		MaxImages:             4,
		Aliases:               []string{"Imagen 3 Fast"},
		SupportedAspectRatios: []string{"1:1", "3:4", "4:3", "9:16", "16:9"},
		SupportedImageSizes:   []string{},
	},
	"imagen-3.0-generate-002": {
		CanonicalName:         "imagen-3.0-generate-002",
		MaxImages:             4,
		Aliases:               []string{"Imagen 3"},
		SupportedAspectRatios: []string{"1:1", "3:4", "4:3", "9:16", "16:9"},
		SupportedImageSizes:   []string{},
	},
	"imagen-4.0-generate-001": {
		CanonicalName:         "imagen-4.0-generate-001",
		MaxImages:             4,
		Aliases:               []string{"Imagen 4", "Imagen4"},
		SupportedAspectRatios: []string{"1:1", "3:4", "4:3", "9:16", "16:9"},
		SupportedImageSizes:   []string{"1K", "2K"},
	},
	"imagen-4.0-fast-generate-001": {
		CanonicalName:         "imagen-4.0-fast-generate-001",
		MaxImages:             4,
		Aliases:               []string{"Imagen 4 Fast", "Imagen4 Fast"},
		SupportedAspectRatios: []string{"1:1", "3:4", "4:3", "9:16", "16:9"},
		SupportedImageSizes:   []string{"1K", "2K"},
	},
	"imagen-4.0-ultra-generate-001": {
		CanonicalName:         "imagen-4.0-ultra-generate-001",
		MaxImages:             1,
		Aliases:               []string{"Imagen 4 Ultra", "Imagen4 Ultra"},
		SupportedAspectRatios: []string{"1:1", "3:4", "4:3", "9:16", "16:9"},
		SupportedImageSizes:   []string{"1K", "2K"},
	},
}

var imagenAliasMap = make(map[string]string)

func init() {
	for canonicalName, info := range SupportedImagenModels {
		imagenAliasMap[strings.ToLower(canonicalName)] = canonicalName
		for _, alias := range info.Aliases {
			imagenAliasMap[strings.ToLower(alias)] = canonicalName
		}
	}
}

// ResolveImagenModel finds the canonical model info from a user-provided name or alias.
func ResolveImagenModel(modelInput string, allowUnsafe bool) (ImagenModelInfo, bool) {
	canonicalName, found := imagenAliasMap[strings.ToLower(modelInput)]
	if found {
		return SupportedImagenModels[canonicalName], true
	}

	if allowUnsafe && modelInput != "" {
		// Return a permissive fallback struct for experimental models
		return ImagenModelInfo{
			CanonicalName:         modelInput,
			MaxImages:             99, // Delegate max limits to the API
			SupportedAspectRatios: []string{"1:1", "3:4", "4:3", "9:16", "16:9", "21:9"},
			SupportedImageSizes:   []string{"1K", "2K"},
		}, true
	}

	return ImagenModelInfo{}, false
}

// BuildImagenModelDescription generates a formatted string for the tool description.
func BuildImagenModelDescription() string {
	var sb strings.Builder
	sb.WriteString("Model for image generation. Can be a full model ID or a common name. Supported models:\n")
	var sortedNames []string
	for name := range SupportedImagenModels {
		sortedNames = append(sortedNames, name)
	}
	sort.Strings(sortedNames)

	for _, name := range sortedNames {
		info := SupportedImagenModels[name]
		baseInfo := fmt.Sprintf("- *%s* (Max Images: %d, Ratios: %s)", info.CanonicalName, info.MaxImages, strings.Join(info.SupportedAspectRatios, ", "))
		sb.WriteString(baseInfo)
		if len(info.SupportedImageSizes) > 0 {
			fmt.Fprintf(&sb, " (Sizes: %s)", strings.Join(info.SupportedImageSizes, ", "))
		}
		if len(info.Aliases) > 0 {
			fmt.Fprintf(&sb, " Aliases: *%s*", strings.Join(info.Aliases, "*, *"))
		}
		sb.WriteString("\n")
	}
	return sb.String()
}

// --- Gemini Image Model Configuration ---

// GeminiImageModelInfo holds the details for a specific Gemini Image model.
type GeminiImageModelInfo struct {
	CanonicalName         string
	Aliases               []string
	SupportedAspectRatios []string
	SupportedImageSizes   []string // mirrors ImagenModelInfo; empty means image_size is unsupported/ignored
	Description           string
}

// SupportedGeminiImageModels is the single source of truth for all supported Gemini Image models.
var SupportedGeminiImageModels = map[string]GeminiImageModelInfo{
	"gemini-3.1-flash-image": {
		CanonicalName:         "gemini-3.1-flash-image",
		Aliases:               []string{"Nano Banana 2"},
		SupportedAspectRatios: []string{"1:1", "3:2", "2:3", "3:4", "1:4", "4:1", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9", "9:21"},
		SupportedImageSizes:   []string{"512", "1K", "2K", "4K"}, // 4K is Preview
		Description:           "Gemini 3.1 Flash Image, or Nano Banana 2.",
	},
	"gemini-3.1-flash-lite-image": {
		CanonicalName:         "gemini-3.1-flash-lite-image",
		Aliases:               []string{"Nano Banana 2 Lite"},
		SupportedAspectRatios: []string{"1:1", "1:4", "4:1", "1:8", "8:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"},
		SupportedImageSizes:   []string{"1K"},
		Description:           "Gemini 3.1 Flash Lite Image, or Nano Banana 2 Lite, is optimized for high-speed, cost-effective image generation at 1K resolution.",
	},

	"gemini-3-pro-image": {
		CanonicalName:         "gemini-3-pro-image",
		Aliases:               []string{"Nano Banana Pro", "Gemini 3 Pro Image"},
		SupportedAspectRatios: []string{"1:1", "3:2", "2:3", "3:4", "1:4", "4:1", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9", "9:21"},
		SupportedImageSizes:   []string{"1K", "2K", "4K"}, // 4K is Preview
		Description:           "Gemini 3 Pro Image, or Gemini 3 Pro (with Nano Banana), is designed to tackle the most challenging image generation by incorporating state-of-the-art reasoning capabilities. It's the best model for complex and multi-turn image generation and editing, having improved accuracy and enhanced image quality.",
	},
	"gemini-2.5-flash-image": {
		CanonicalName:         "gemini-2.5-flash-image",
		Aliases:               []string{"Nano Banana", "nano-banana"},
		SupportedAspectRatios: []string{"1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"},
		SupportedImageSizes:   []string{}, // no resolution control: image_size is silently ignored by the API (verified empirically)
		Description:           "Gemini 2.5 Flash Image, or Nano Banana, is optimized for image understanding and generation and offers a balance of price and performance.",
	},
	"gemini-nano-banana-2.1": {
		CanonicalName:         "gemini-nano-banana-2.1",
		Aliases:               []string{"Nano Banana 2.1", "nano-banana-2.1"},
		SupportedAspectRatios: []string{"1:1", "3:2", "2:3", "3:4", "1:4", "4:1", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9", "9:21"},
		SupportedImageSizes:   []string{"1K", "2K", "4K"},
		// NOTE: Nano Banana 2.1 rejects the seed, temperature, topP, topK, and
		// logprobs parameters (the API returns an error if any are set). The
		// gemini_image_generation handler never sends these, and the
		// nanobanana_image_generation handler gates its seed param on this
		// canonical name (see mcp-nanobanana-go/handlers.go).
		Description: "Gemini Nano Banana 2.1 is optimized for multimodal image generation and editing and offers a balance of price and performance.",
	},
}

var geminiImageAliasMap = make(map[string]string)

func init() {
	for canonicalName, info := range SupportedGeminiImageModels {
		geminiImageAliasMap[strings.ToLower(canonicalName)] = canonicalName
		for _, alias := range info.Aliases {
			geminiImageAliasMap[strings.ToLower(alias)] = canonicalName
		}
	}
}

// ResolveGeminiImageModel finds the canonical model info from a user-provided name or alias.
func ResolveGeminiImageModel(modelInput string, allowUnsafe bool) (GeminiImageModelInfo, bool) {
	canonicalName, found := geminiImageAliasMap[strings.ToLower(modelInput)]
	if found {
		return SupportedGeminiImageModels[canonicalName], true
	}

	if allowUnsafe && modelInput != "" {
		// Return a permissive fallback struct for experimental models
		return GeminiImageModelInfo{
			CanonicalName:         modelInput,
			SupportedAspectRatios: []string{"1:1", "3:2", "2:3", "3:4", "1:4", "4:1", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9", "9:21"},
			SupportedImageSizes:   []string{"512", "1K", "2K", "4K"},
		}, true
	}

	return GeminiImageModelInfo{}, false
}

// BuildGeminiImageModelDescription generates a formatted string for the tool description.
func BuildGeminiImageModelDescription() string {
	var sb strings.Builder
	sb.WriteString("Model for image generation. Can be a full model ID or a common name. Supported models:\n")
	var sortedNames []string
	for name := range SupportedGeminiImageModels {
		sortedNames = append(sortedNames, name)
	}
	sort.Strings(sortedNames)

	for _, name := range sortedNames {
		info := SupportedGeminiImageModels[name]
		fmt.Fprintf(&sb, "- *%s* (Ratios: %s)", info.CanonicalName, strings.Join(info.SupportedAspectRatios, ", "))
		if len(info.SupportedImageSizes) > 0 {
			fmt.Fprintf(&sb, " (Sizes: %s)", strings.Join(info.SupportedImageSizes, ", "))
		}
		if len(info.Aliases) > 0 {
			fmt.Fprintf(&sb, " Aliases: *%s*", strings.Join(info.Aliases, "*, *"))
		}
		if info.Description != "" {
			fmt.Fprintf(&sb, " - %s", info.Description)
		}
		sb.WriteString("\n")
	}
	return sb.String()
}

// --- Veo Model Configuration ---

// VeoModelInfo holds the details for a specific Veo model.
type VeoModelInfo struct {
	CanonicalName          string
	Aliases                []string
	DefaultDuration        int32
	SupportedDurations     []int32
	MaxVideos              int32
	SupportedAspectRatios  []string
	SupportsGenerateAudio  bool
	SupportsFirstLast      bool
	SupportsReferenceImage bool
	SupportsExtend         bool
}

// SupportedVeoModels is the single source of truth for all supported Veo models.
var SupportedVeoModels = map[string]VeoModelInfo{
	"veo-2.0-generate-001": {
		CanonicalName:          "veo-2.0-generate-001",
		Aliases:                []string{"Veo 2"},
		DefaultDuration:        8,
		SupportedDurations:     []int32{5, 6, 7, 8},
		MaxVideos:              4,
		SupportedAspectRatios:  []string{"16:9", "9:16"},
		SupportsGenerateAudio:  false,
		SupportsFirstLast:      false,
		SupportsReferenceImage: false,
	},
	"veo-2.0-generate-exp": { // TODO: Deprecated, remove
		CanonicalName:          "veo-2.0-generate-exp",
		Aliases:                []string{"Veo 2 Exp"},
		DefaultDuration:        8,
		SupportedDurations:     []int32{5, 6, 7, 8},
		MaxVideos:              4,
		SupportedAspectRatios:  []string{"16:9", "9:16"},
		SupportsGenerateAudio:  false,
		SupportsFirstLast:      true,
		SupportsReferenceImage: true,
	},
	"veo-2.0-generate-preview": {
		CanonicalName:          "veo-2.0-generate-preview",
		Aliases:                []string{"Veo 2 Preview"},
		DefaultDuration:        8,
		SupportedDurations:     []int32{5, 6, 7, 8},
		MaxVideos:              4,
		SupportedAspectRatios:  []string{"16:9", "9:16"},
		SupportsGenerateAudio:  false,
		SupportsFirstLast:      true,
		SupportsReferenceImage: false,
	},
	"veo-3.0-generate-001": {
		CanonicalName:          "veo-3.0-generate-001",
		Aliases:                []string{"Veo 3.0"},
		DefaultDuration:        8,
		SupportedDurations:     []int32{4, 6, 8},
		MaxVideos:              2,
		SupportedAspectRatios:  []string{"16:9"},
		SupportsGenerateAudio:  true,
		SupportsFirstLast:      false,
		SupportsReferenceImage: false,
	},
	"veo-3.0-fast-generate-001": {
		CanonicalName:          "veo-3.0-fast-generate-001",
		Aliases:                []string{"Veo 3.0 Fast"},
		DefaultDuration:        8,
		SupportedDurations:     []int32{4, 6, 8},
		MaxVideos:              2,
		SupportedAspectRatios:  []string{"16:9"},
		SupportsGenerateAudio:  true,
		SupportsFirstLast:      false,
		SupportsReferenceImage: false,
	},
	"veo-3.1-generate-001": {
		CanonicalName:          "veo-3.1-generate-001",
		Aliases:                []string{"Veo 3.1"},
		DefaultDuration:        8,
		SupportedDurations:     []int32{4, 6, 8},
		MaxVideos:              4,
		SupportedAspectRatios:  []string{"16:9", "9:16"},
		SupportsGenerateAudio:  true,
		SupportsFirstLast:      true,
		SupportsReferenceImage: false,
	},
	"veo-3.1-fast-generate-001": {
		CanonicalName:          "veo-3.1-fast-generate-001",
		Aliases:                []string{"Veo 3.1 Fast"},
		DefaultDuration:        8,
		SupportedDurations:     []int32{4, 6, 8},
		MaxVideos:              4,
		SupportedAspectRatios:  []string{"16:9", "9:16"},
		SupportsGenerateAudio:  true,
		SupportsFirstLast:      true,
		SupportsReferenceImage: false,
	},
	"veo-3.1-generate-preview": {
		CanonicalName:          "veo-3.1-generate-preview",
		Aliases:                []string{"Veo 3.1 Preview"},
		DefaultDuration:        8,
		SupportedDurations:     []int32{4, 6, 8},
		MaxVideos:              4,
		SupportedAspectRatios:  []string{"16:9", "9:16"},
		SupportsGenerateAudio:  true,
		SupportsFirstLast:      true,
		SupportsReferenceImage: true,
	},
	"veo-3.1-fast-generate-preview": {
		CanonicalName:          "veo-3.1-fast-generate-preview",
		Aliases:                []string{"Veo 3.1 Fast Preview"},
		DefaultDuration:        8,
		SupportedDurations:     []int32{4, 6, 8},
		MaxVideos:              4,
		SupportedAspectRatios:  []string{"16:9", "9:16"},
		SupportsGenerateAudio:  true,
		SupportsFirstLast:      true,
		SupportsReferenceImage: true,
	},
	"veo-3.1-lite-generate-001": {
		CanonicalName:          "veo-3.1-lite-generate-001",
		Aliases:                []string{"Veo 3.1 Lite"},
		DefaultDuration:        8,
		SupportedDurations:     []int32{4, 6, 8},
		MaxVideos:              4,
		SupportedAspectRatios:  []string{"16:9", "9:16"},
		SupportsGenerateAudio:  true,
		SupportsFirstLast:      true,
		SupportsReferenceImage: false,
		SupportsExtend:         true,
	},
}

var veoAliasMap = make(map[string]string)

func init() {
	for canonicalName, info := range SupportedVeoModels {
		veoAliasMap[strings.ToLower(canonicalName)] = canonicalName
		for _, alias := range info.Aliases {
			veoAliasMap[strings.ToLower(alias)] = canonicalName
		}
	}
}

// ResolveVeoModel finds the canonical model info from a user-provided name or alias.
func ResolveVeoModel(modelInput string, allowUnsafe bool) (VeoModelInfo, bool) {
	canonicalName, found := veoAliasMap[strings.ToLower(modelInput)]
	if found {
		return SupportedVeoModels[canonicalName], true
	}

	if allowUnsafe && modelInput != "" {
		// Return a permissive fallback struct for experimental models
		return VeoModelInfo{
			CanonicalName:          modelInput,
			DefaultDuration:        5,
			SupportedDurations:     []int32{4, 5, 6, 7, 8},
			MaxVideos:              99, // Delegate max limits to the API
			SupportedAspectRatios:  []string{"16:9", "9:16", "1:1", "3:4", "4:3"},
			SupportsGenerateAudio:  true,
			SupportsFirstLast:      true,
			SupportsReferenceImage: true,
			SupportsExtend:         true,
		}, true
	}

	return VeoModelInfo{}, false
}

// BuildVeoModelDescription generates a formatted string for the tool description.
func BuildVeoModelDescription() string {
	var sb strings.Builder
	sb.WriteString("Model for video generation. Can be a full model ID or a common name. Supported models:\n")
	var sortedNames []string
	for name := range SupportedVeoModels {
		sortedNames = append(sortedNames, name)
	}
	sort.Strings(sortedNames)

	for _, name := range sortedNames {
		info := SupportedVeoModels[name]
		durationsStr := make([]string, len(info.SupportedDurations))
		for i, d := range info.SupportedDurations {
			durationsStr[i] = fmt.Sprintf("%d", d)
		}
		fmt.Fprintf(&sb, "- *%s* (Durations: [%s]s, Max Videos: %d, Ratios: %s)",
			info.CanonicalName, strings.Join(durationsStr, ", "), info.MaxVideos, strings.Join(info.SupportedAspectRatios, ", "))
		if len(info.Aliases) > 0 {
			fmt.Fprintf(&sb, " Aliases: *%s*", strings.Join(info.Aliases, "*, *"))
		}
		sb.WriteString("\n")
	}
	return sb.String()
}

// --- Lyria Model Configuration ---

// LyriaModelInfo holds the details for a specific Lyria model.
type LyriaModelInfo struct {
	CanonicalName string
	Aliases       []string
	Description   string
	EndpointType  string // "prediction" or "interactions"
}

// SupportedLyriaModels is the single source of truth for all supported Lyria models.
var SupportedLyriaModels = map[string]LyriaModelInfo{
	"lyria-002": {
		CanonicalName: "lyria-002",
		Aliases:       []string{"Lyria 2"},
		Description:   "The original Lyria 2 model (using standard Vertex AI Prediction API).",
		EndpointType:  "prediction",
	},
	"lyria-3-clip-preview": {
		CanonicalName: "lyria-3-clip-preview",
		Aliases:       []string{"Lyria 3 Clip"},
		Description:   "Lyria 3 Clip model for 30-second audio generation (using Interactions API).",
		EndpointType:  "interactions",
	},
	"lyria-3-pro-preview": {
		CanonicalName: "lyria-3-pro-preview",
		Aliases:       []string{"Lyria 3 Pro"},
		Description:   "Lyria 3 Pro model for 2:30 audio generation (using Interactions API).",
		EndpointType:  "interactions",
	},
}

// ResolveLyriaModel finds the canonical model info from a user-provided name or alias.
func ResolveLyriaModel(modelInput string, allowUnsafe bool) (LyriaModelInfo, bool) {
	// Note: Lyria doesn't use a precomputed alias map in the original code, but we can iterate.
	modelInputLower := strings.ToLower(modelInput)
	for canonicalName, info := range SupportedLyriaModels {
		if strings.ToLower(canonicalName) == modelInputLower {
			return info, true
		}
		for _, alias := range info.Aliases {
			if strings.ToLower(alias) == modelInputLower {
				return info, true
			}
		}
	}

	if allowUnsafe && modelInput != "" {
		// Return a permissive fallback struct for experimental models
		// Default to Interactions API as it's the newer path for upcoming models.
		return LyriaModelInfo{
			CanonicalName: modelInput,
			EndpointType:  "interactions",
		}, true
	}

	return LyriaModelInfo{}, false
}

// --- Omni Model Configuration ---

// DefaultOmniModel is the canonical default Gemini Omni model ID.
const DefaultOmniModel = "gemini-omni-1.1-flash-preview"

// OmniModelInfo holds the details for a specific Gemini Omni model. Omni models
// (text/image/video in, text+video out) are reachable only via the Vertex
// Interactions API and are global-only.
type OmniModelInfo struct {
	CanonicalName string
	Aliases       []string
	// SupportedResolutions lists the video output resolutions the model can emit
	// (mirrors GeminiImageModelInfo.SupportedImageSizes). This is capability
	// metadata surfaced in the tool description; the resolution request parameter
	// itself is not yet wired into the tool (see follow-up).
	SupportedResolutions []string
	Description          string
}

// SupportedOmniModels is the single source of truth for all supported Omni models.
var SupportedOmniModels = map[string]OmniModelInfo{
	"gemini-omni-1.1-flash-preview": {
		CanonicalName:        "gemini-omni-1.1-flash-preview",
		Aliases:              []string{"Gemini Omni 1.1 Flash", "Omni 1.1", "Omni"},
		SupportedResolutions: []string{"360p", "720p", "1080p", "4k"},
		Description:          "Gemini Omni 1.1 Flash (Preview): text/image/video in, text+video out, via the Vertex Interactions API (global only). Supports 360p/720p/1080p/4k video output.",
	},
	"gemini-omni-flash-preview": {
		CanonicalName:        "gemini-omni-flash-preview",
		Aliases:              []string{"Gemini Omni Flash"},
		SupportedResolutions: []string{"720p"},
		Description:          "Gemini Omni Flash (Preview): text/image/video in, text+video out, via the Vertex Interactions API (global only).",
	},
}

// ResolveOmniModel finds the canonical model info from a user-provided name or
// alias. An empty input resolves to the default Omni model.
func ResolveOmniModel(modelInput string, allowUnsafe bool) (OmniModelInfo, bool) {
	if strings.TrimSpace(modelInput) == "" {
		return SupportedOmniModels[DefaultOmniModel], true
	}

	modelInputLower := strings.ToLower(modelInput)
	for canonicalName, info := range SupportedOmniModels {
		if strings.ToLower(canonicalName) == modelInputLower {
			return info, true
		}
		for _, alias := range info.Aliases {
			if strings.ToLower(alias) == modelInputLower {
				return info, true
			}
		}
	}

	if allowUnsafe && modelInput != "" {
		// Return a permissive fallback struct for experimental models.
		return OmniModelInfo{CanonicalName: modelInput}, true
	}

	return OmniModelInfo{}, false
}

// BuildOmniModelDescription generates a formatted string listing supported Omni
// models and their aliases, suitable for use in an MCP tool description.
func BuildOmniModelDescription() string {
	var sb strings.Builder
	sb.WriteString("The Gemini Omni model ID to use for video generation. Supported models:\n")

	keys := make([]string, 0, len(SupportedOmniModels))
	for k := range SupportedOmniModels {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	for _, k := range keys {
		info := SupportedOmniModels[k]
		fmt.Fprintf(&sb, "- *%s*", info.CanonicalName)
		if len(info.Aliases) > 0 {
			fmt.Fprintf(&sb, " Aliases: *%s*", strings.Join(info.Aliases, "*, *"))
		}
		if info.Description != "" {
			fmt.Fprintf(&sb, " - %s", info.Description)
		}
		if len(info.SupportedResolutions) > 0 {
			fmt.Fprintf(&sb, " Supported resolutions: %s.", strings.Join(info.SupportedResolutions, ", "))
		}
		sb.WriteString("\n")
	}
	return sb.String()
}

// and their aliases, suitable for use in an MCP tool description.
func BuildLyriaModelDescription() string {
	var sb strings.Builder
	sb.WriteString("The specific Lyria model ID to use. Supported models:\n")

	keys := make([]string, 0, len(SupportedLyriaModels))
	for k := range SupportedLyriaModels {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	for _, k := range keys {
		info := SupportedLyriaModels[k]
		fmt.Fprintf(&sb, "- *%s*", info.CanonicalName)
		if len(info.Aliases) > 0 {
			fmt.Fprintf(&sb, " Aliases: *%s*", strings.Join(info.Aliases, "*, *"))
		}
		sb.WriteString("\n")
	}
	return sb.String()
}

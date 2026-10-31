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
	"mime"
	"path"
	"strings"
)

// ResolveStringParam returns the client-supplied string argument for canonicalKey,
// applying the shared accept-and-alias precedence contract (design #842 §4a /
// issue #1789): the canonical parameter always wins when non-empty; otherwise
// the first non-empty legacy alias (in the order given) is used; otherwise ""
// is returned so the caller falls back to its default. Surrounding whitespace
// is trimmed.
func ResolveStringParam(args map[string]any, canonicalKey string, legacyKeys ...string) string {
	if v, ok := args[canonicalKey].(string); ok && strings.TrimSpace(v) != "" {
		return strings.TrimSpace(v)
	}
	for _, k := range legacyKeys {
		if v, ok := args[k].(string); ok && strings.TrimSpace(v) != "" {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

// ResolveOutputFilename returns the client-supplied base output name, applying
// the shared accept-and-alias precedence contract (design #842 §4a): the
// canonical output_filename parameter always wins; otherwise the first non-empty
// legacy alias (in the order given) is used; otherwise "" so the caller falls
// back to its existing default naming scheme. Surrounding whitespace is trimmed.
//
// This is the single place the precedence rule lives; every genmedia server
// reuses it (passing its own legacy key(s) as legacyKeys) so the rule this issue
// exists to unify is never re-implemented per-server.
func ResolveOutputFilename(args map[string]any, legacyKeys ...string) string {
	return ResolveStringParam(args, "output_filename", legacyKeys...)
}

// ResolveModel returns the client-supplied model identifier, preferring the
// canonical "model" parameter over legacy aliases such as "model_id" or
// "model_name" (issue #1789).
func ResolveModel(args map[string]any, legacyKeys ...string) string {
	return ResolveStringParam(args, "model", legacyKeys...)
}

// ResolveGCSBucketURI returns the client-supplied GCS bucket or URI prefix,
// preferring the canonical "gcs_bucket_uri" parameter over legacy aliases such
// as "bucket" or "output_gcs_bucket" (issue #1789).
func ResolveGCSBucketURI(args map[string]any, legacyKeys ...string) string {
	return ResolveStringParam(args, "gcs_bucket_uri", legacyKeys...)
}

// ResolveOutputDirectory returns the client-supplied local output directory,
// preferring the canonical "output_directory" parameter over legacy aliases
// such as "local_path" or "output_local_dir" (issue #1789).
func ResolveOutputDirectory(args map[string]any, legacyKeys ...string) string {
	return ResolveStringParam(args, "output_directory", legacyKeys...)
}

// BuildOutputFilenames returns deterministic output file names for a generation
// that produced `count` artifacts, honoring the client base name and forcing the
// extension to the true media type (design #842 §4b, §4c).
//
//	base     the client-supplied output_filename (stem + optional ext). REQUIRED non-empty.
//	count    number of artifacts (>= 1).
//	mimeType the model's output MIME (e.g. "image/png", "audio/wav", "video/mp4").
//
// Rules: stem = SanitizeBaseFilename(base) with any client extension stripped;
// ext = ExtensionForMIMEType(mimeType).
//
//	count == 1 -> ["<stem><ext>"]
//	count  > 1 -> ["<stem>_1<ext>", ..., "<stem>_N<ext>"] (1-based, no zero-pad,
//	              contiguous, in generation order, suffix inserted before the extension)
//
// Returns an error if count < 1 or the base sanitizes to empty. It is never
// invoked when output_filename is unset — callers keep their existing default
// naming scheme in that case (preserving byte-for-byte current behavior).
func BuildOutputFilenames(base string, count int, mimeType string) ([]string, error) {
	if count < 1 {
		return nil, fmt.Errorf("count must be >= 1, got %d", count)
	}

	stem := SanitizeBaseFilename(base)
	// Strip any client-supplied extension; the extension is forced to the true
	// media type below (§4b).
	stem = strings.TrimSuffix(stem, path.Ext(stem))
	stem = strings.TrimSpace(stem)
	if stem == "" {
		return nil, fmt.Errorf("output filename %q sanitizes to an empty base name", base)
	}

	ext := ExtensionForMIMEType(mimeType)

	names := make([]string, count)
	if count == 1 {
		names[0] = stem + ext
		return names, nil
	}
	for i := 0; i < count; i++ {
		names[i] = fmt.Sprintf("%s_%d%s", stem, i+1, ext)
	}
	return names, nil
}

// SanitizeBaseFilename reduces a client-supplied name to a safe single path
// component: it strips control characters, normalizes Windows separators, reduces
// the value to its final path component (dropping directory parts and traversal
// such as "../../etc/passwd" -> "passwd"), and trims. It returns "" when nothing
// safe remains (e.g. "", ".", "..") so the caller can treat that as an error and
// fall back to its default scheme. This is a security-relevant control against
// path traversal / separator injection in both local paths and GCS object names,
// not a cosmetic one.
func SanitizeBaseFilename(name string) string {
	name = strings.TrimSpace(name)

	// Strip control characters (including DEL).
	name = strings.Map(func(r rune) rune {
		if r < 0x20 || r == 0x7f {
			return -1
		}
		return r
	}, name)

	// Normalize Windows separators so path.Base reliably drops directory parts
	// even on non-Windows hosts (where '\\' is not a path separator).
	name = strings.ReplaceAll(name, "\\", "/")

	// Reduce to the final path component (defense against traversal).
	name = path.Base(name)
	name = strings.TrimSpace(name)

	// path.Base yields "." for empty/dot-only inputs and ".." for parent refs; a
	// name that is only dots is not a usable file name.
	if strings.Trim(name, ".") == "" {
		return ""
	}
	return name
}

// ExtensionForMIMEType generalizes ImageExtensionForMIMEType to audio and video.
// image/* MIME types delegate to the existing ImageExtensionForMIMEType (no
// behavior change / no duplication for existing image callers). Unknown types
// fall back to mime.ExtensionsByType, else "".
func ExtensionForMIMEType(mimeType string) string {
	m := strings.ToLower(strings.TrimSpace(mimeType))
	if strings.HasPrefix(m, "image/") {
		return ImageExtensionForMIMEType(mimeType)
	}
	switch m {
	case "audio/mpeg", "audio/mp3":
		return ".mp3"
	case "audio/wav", "audio/x-wav", "audio/l16":
		return ".wav"
	case "audio/ogg":
		return ".ogg"
	case "audio/mp4", "audio/aac", "audio/x-m4a":
		return ".m4a"
	case "audio/mulaw":
		return ".mulaw"
	case "audio/alaw":
		return ".alaw"
	case "audio/pcm", "audio/l8", "audio/l24":
		return ".pcm"
	case "video/mp4":
		return ".mp4"
	case "video/webm":
		return ".webm"
	}
	if exts, err := mime.ExtensionsByType(m); err == nil && len(exts) > 0 {
		return exts[0]
	}
	return ""
}

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
	"reflect"
	"testing"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
)

// TestVeoOutputNames locks the output_filename → per-video name mapping, including
// the n==1 (no suffix) and n>1 (1-based suffix) cases, extension forcing to the
// true video MIME, path-traversal sanitization, and the unset back-compat path
// (nil → handler keeps its default naming scheme).
func TestVeoOutputNames(t *testing.T) {
	tests := []struct {
		name       string
		outputName string
		count      int
		mimeType   string
		want       []string
	}{
		{"unset returns nil (back-compat default naming)", "", 2, "video/mp4", nil},
		{"whitespace-only returns nil", "   ", 2, "video/mp4", nil},
		{"zero count returns nil", "clip.mp4", 0, "video/mp4", nil},
		{"single video, no suffix", "clip.mp4", 1, "video/mp4", []string{"clip.mp4"}},
		{"three videos, 1-based suffix", "clip.mp4", 3, "video/mp4", []string{"clip_1.mp4", "clip_2.mp4", "clip_3.mp4"}},
		{"extension forced to true MIME", "clip.mov", 1, "video/mp4", []string{"clip.mp4"}},
		{"no extension supplied gets forced", "clip", 2, "video/mp4", []string{"clip_1.mp4", "clip_2.mp4"}},
		{"path traversal sanitized", "../../etc/passwd", 1, "video/mp4", []string{"passwd.mp4"}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := veoOutputNames(tc.outputName, tc.count, tc.mimeType)
			if !reflect.DeepEqual(got, tc.want) {
				t.Errorf("veoOutputNames(%q, %d, %q) = %v, want %v", tc.outputName, tc.count, tc.mimeType, got, tc.want)
			}
		})
	}
}

// TestBuildVeoRenamePlan verifies the Path-C plan that maps the API-written video
// objects to the client-desired names: num_videos>1 + gcs + output_filename="clip.mp4"
// ⇒ the API sample objects → clip_1..N.mp4 under the output prefix, same bucket,
// with correct gs:// URIs. src→dst are paired by identity (srcURIs[i] ↔ names[i]).
// Feeding the returned renames to common.RenameGCSObjects (whose copy-fatal /
// delete-nonfatal / collision-overwrite / originals-removed contract is unit-tested
// network-free in mcp-common) removes the originals.
func TestBuildVeoRenamePlan(t *testing.T) {
	gcsOutputURI := "gs://mybucket/veo_outputs/"
	srcURIs := []string{
		"gs://mybucket/veo_outputs/1234/sample_0.mp4",
		"gs://mybucket/veo_outputs/1234/sample_1.mp4",
		"gs://mybucket/veo_outputs/1234/sample_2.mp4",
	}
	names := veoOutputNames("clip.mp4", 3, "video/mp4")

	bucket, renames, planSrcURIs, dstURIs := buildVeoRenamePlan(gcsOutputURI, srcURIs, names)

	if bucket != "mybucket" {
		t.Errorf("bucket = %q, want mybucket", bucket)
	}
	// planSrcURIs is aligned 1:1 with renames/dstURIs and echoes the source URIs so
	// the caller can pair renamed URIs back by identity, not slice position.
	if !reflect.DeepEqual(planSrcURIs, srcURIs) {
		t.Errorf("planSrcURIs = %v, want %v", planSrcURIs, srcURIs)
	}
	wantRenames := []common.Rename{
		{Src: "veo_outputs/1234/sample_0.mp4", Dst: "veo_outputs/clip_1.mp4"},
		{Src: "veo_outputs/1234/sample_1.mp4", Dst: "veo_outputs/clip_2.mp4"},
		{Src: "veo_outputs/1234/sample_2.mp4", Dst: "veo_outputs/clip_3.mp4"},
	}
	if !reflect.DeepEqual(renames, wantRenames) {
		t.Errorf("renames = %v, want %v", renames, wantRenames)
	}
	wantURIs := []string{
		"gs://mybucket/veo_outputs/clip_1.mp4",
		"gs://mybucket/veo_outputs/clip_2.mp4",
		"gs://mybucket/veo_outputs/clip_3.mp4",
	}
	if !reflect.DeepEqual(dstURIs, wantURIs) {
		t.Errorf("dstURIs = %v, want %v", dstURIs, wantURIs)
	}
}

// TestBuildVeoRenamePlanSingle: n==1 ⇒ no suffix (clip.mp4), extension forced.
func TestBuildVeoRenamePlanSingle(t *testing.T) {
	names := veoOutputNames("clip.mov", 1, "video/mp4")
	bucket, renames, _, dstURIs := buildVeoRenamePlan("gs://mybucket/veo_outputs/", []string{"gs://mybucket/veo_outputs/sample_0.mp4"}, names)
	if bucket != "mybucket" {
		t.Errorf("bucket = %q, want mybucket", bucket)
	}
	want := common.Rename{Src: "veo_outputs/sample_0.mp4", Dst: "veo_outputs/clip.mp4"}
	if len(renames) != 1 || renames[0] != want {
		t.Errorf("renames = %v, want [%v]", renames, want)
	}
	if len(dstURIs) != 1 || dstURIs[0] != "gs://mybucket/veo_outputs/clip.mp4" {
		t.Errorf("dstURIs = %v, want [gs://mybucket/veo_outputs/clip.mp4]", dstURIs)
	}
}

// TestBuildVeoRenamePlanBackCompat: no output_filename ⇒ nil plan, so the handler
// leaves the API-written object names untouched (byte-for-byte legacy behavior).
func TestBuildVeoRenamePlanBackCompat(t *testing.T) {
	names := veoOutputNames("", 3, "video/mp4") // nil
	bucket, renames, planSrcURIs, dstURIs := buildVeoRenamePlan("gs://mybucket/veo_outputs/", []string{"gs://mybucket/veo_outputs/sample_0.mp4"}, names)
	if bucket != "" || renames != nil || planSrcURIs != nil || dstURIs != nil {
		t.Errorf("expected empty plan for unset output_filename, got bucket=%q renames=%v planSrcURIs=%v dstURIs=%v", bucket, renames, planSrcURIs, dstURIs)
	}
}

// TestVeoRenamePlanIsNonNoop asserts that buildVeoRenamePlan yields a valid,
// non-no-op set of renames: each destination is the deterministic client name,
// distinct from the API sample_* source, so common.RenameGCSObjects would copy+
// delete each source. This test does NOT call RenameGCSObjects — the actual
// copy-fatal / delete-nonfatal / collision-overwrite / originals-removed contract
// is asserted network-free in mcp-common, the module that owns the copy/delete/
// exists seam. Here we only verify the plan is a well-formed input to that helper.
func TestVeoRenamePlanIsNonNoop(t *testing.T) {
	names := veoOutputNames("clip.mp4", 2, "video/mp4")
	_, renames, _, _ := buildVeoRenamePlan(
		"gs://mybucket/veo_outputs/",
		[]string{
			"gs://mybucket/veo_outputs/sample_0.mp4",
			"gs://mybucket/veo_outputs/sample_1.mp4",
		},
		names,
	)
	if len(renames) != 2 {
		t.Fatalf("expected 2 renames, got %d", len(renames))
	}
	// The destinations are the deterministic client names, distinct from the API
	// sample_* sources (so RenameGCSObjects will copy+delete each source).
	for i, r := range renames {
		if r.Src == r.Dst {
			t.Errorf("rename %d is a no-op (src==dst=%q); expected sample_* → clip name", i, r.Src)
		}
	}
}

// TestApplyRenamedURIsIdentityPairing proves the URI writeback pairs each rename
// result to its artifact by identity (source URI), not by slice position (nit
// p3b-1). It uses a src list with a middle unparseable URI (skipped by the plan)
// and asserts renamed URIs land on the correct artifacts — a positional writeback
// would drift them.
func TestApplyRenamedURIsIdentityPairing(t *testing.T) {
	gcsVideoURIs := []string{
		"gs://mybucket/veo_outputs/sample_0.mp4",
		"not-a-gcs-uri", // unparseable → skipped by the plan
		"gs://mybucket/veo_outputs/sample_2.mp4",
	}
	names := veoOutputNames("clip.mp4", 3, "video/mp4") // clip_1.mp4, clip_2.mp4, clip_3.mp4

	_, renames, planSrcURIs, dstURIs := buildVeoRenamePlan("gs://mybucket/veo_outputs/", gcsVideoURIs, names)
	if len(renames) != 2 {
		t.Fatalf("expected 2 renames (middle skipped), got %d", len(renames))
	}

	t.Run("full success renames both parseable artifacts to the right names", func(t *testing.T) {
		saved := append([]string(nil), gcsVideoURIs...)
		applyRenamedURIs(saved, planSrcURIs, dstURIs, len(renames))
		want := []string{
			"gs://mybucket/veo_outputs/clip_1.mp4",
			"not-a-gcs-uri",
			"gs://mybucket/veo_outputs/clip_3.mp4",
		}
		if !reflect.DeepEqual(saved, want) {
			t.Errorf("identity writeback = %v, want %v", saved, want)
		}
	})

	t.Run("partial failure only writes back the renamed prefix, still by identity", func(t *testing.T) {
		saved := append([]string(nil), gcsVideoURIs...)
		applyRenamedURIs(saved, planSrcURIs, dstURIs, 1)
		want := []string{
			"gs://mybucket/veo_outputs/clip_1.mp4",
			"not-a-gcs-uri",
			"gs://mybucket/veo_outputs/sample_2.mp4", // NOT drifted onto by clip_3
		}
		if !reflect.DeepEqual(saved, want) {
			t.Errorf("partial identity writeback = %v, want %v", saved, want)
		}
	})
}

// TestParseCommonVideoParamsStandardizedAliases verifies issue #1789 parameter
// standardization in mcp-veo-go: canonical gcs_bucket_uri wins over legacy
// bucket, while legacy bucket and output_gcs_bucket still work seamlessly.
func TestParseCommonVideoParamsStandardizedAliases(t *testing.T) {
	cfg := &common.Config{GenmediaBucket: "fallback-bucket"}

	t.Run("canonical gcs_bucket_uri wins over legacy bucket", func(t *testing.T) {
		args := map[string]interface{}{
			"gcs_bucket_uri":   "canonical-bucket/videos",
			"bucket":           "legacy-bucket/videos",
			"output_directory": "./canonical_dir",
			"local_path":       "./legacy_dir",
		}
		gcsBucket, outputDir, model, _, _, _, _, _, err := parseCommonVideoParams(args, cfg, false)
		if err != nil {
			t.Fatalf("parseCommonVideoParams error: %v", err)
		}
		if gcsBucket != "gs://canonical-bucket/videos" {
			t.Errorf("gcsBucket = %q, want gs://canonical-bucket/videos", gcsBucket)
		}
		if outputDir != "./canonical_dir" {
			t.Errorf("outputDir = %q, want ./canonical_dir", outputDir)
		}
		if model != "veo-3.1-fast-generate-001" {
			t.Errorf("model = %q, want veo-3.1-fast-generate-001", model)
		}
	})

	t.Run("legacy bucket alias still honored when gcs_bucket_uri unset", func(t *testing.T) {
		args := map[string]interface{}{
			"bucket":   "legacy-bucket/videos",
			"model_id": "Veo 3.1",
		}
		gcsBucket, _, model, _, _, _, _, _, err := parseCommonVideoParams(args, cfg, false)
		if err != nil {
			t.Fatalf("parseCommonVideoParams error: %v", err)
		}
		if gcsBucket != "gs://legacy-bucket/videos" {
			t.Errorf("gcsBucket = %q, want gs://legacy-bucket/videos", gcsBucket)
		}
		if model != "veo-3.1-generate-001" {
			t.Errorf("model = %q, want veo-3.1-generate-001", model)
		}
	})
}

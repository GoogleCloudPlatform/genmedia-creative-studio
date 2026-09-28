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
	"context"
	"fmt"
	"os"
	"testing"
	"time"
)

// TestIntegrationBuildNamesThenRename ties the two halves of the Path-C
// (API-controls-GCS) naming pipeline together end-to-end and network-free: the
// name computation (BuildOutputFilenames) feeds the copy-rename mechanism
// (RenameGCSObjects) exactly as imagen/veo wire them. The GCS I/O is routed
// through the in-memory fakeGCS seam, so no bucket or credentials are needed. It
// asserts the deterministic 1-based suffix / no-suffix rules survive the rename
// and that every source object ends up removed.
func TestIntegrationBuildNamesThenRename(t *testing.T) {
	const (
		bucket = "bkt"
		prefix = "imagen_outputs/"
	)

	buildRenames := func(count int, base string) (renames []Rename, wantDst []string) {
		names, err := BuildOutputFilenames(base, count, "image/png")
		if err != nil {
			t.Fatalf("BuildOutputFilenames(%q, %d): %v", base, count, err)
		}
		for i := 0; i < count; i++ {
			src := fmt.Sprintf("%ssample_%d.png", prefix, i)
			dst := prefix + names[i]
			renames = append(renames, Rename{Src: src, Dst: dst})
			wantDst = append(wantDst, dst)
		}
		return renames, wantDst
	}

	t.Run("multiple images -> suffixed dst objects, sources removed", func(t *testing.T) {
		renames, wantDst := buildRenames(3, "hero.jpg") // wrong ext forced to .png
		f := newFakeGCS(renames[0].Src, renames[1].Src, renames[2].Src)
		f.install(t)

		renamed, err := RenameGCSObjects(context.Background(), bucket, renames)
		if err != nil {
			t.Fatalf("RenameGCSObjects error: %v", err)
		}
		if !equalStr(renamed, wantDst) {
			t.Errorf("renamed = %v, want %v", renamed, wantDst)
		}
		for _, dst := range wantDst {
			if !f.objects[dst] {
				t.Errorf("destination %q missing after rename; objects=%v", dst, f.list())
			}
		}
		for _, r := range renames {
			if f.objects[r.Src] {
				t.Errorf("source %q should have been deleted; objects=%v", r.Src, f.list())
			}
		}
		// The forced-extension suffixing must be present in the destinations.
		if wantDst[0] != prefix+"hero_1.png" || wantDst[2] != prefix+"hero_3.png" {
			t.Errorf("unexpected suffixed names: %v", wantDst)
		}
	})

	t.Run("single image -> no suffix", func(t *testing.T) {
		renames, wantDst := buildRenames(1, "hero")
		f := newFakeGCS(renames[0].Src)
		f.install(t)

		renamed, err := RenameGCSObjects(context.Background(), bucket, renames)
		if err != nil {
			t.Fatalf("RenameGCSObjects error: %v", err)
		}
		if len(wantDst) != 1 || wantDst[0] != prefix+"hero.png" {
			t.Fatalf("want single dst %shero.png, got %v", prefix, wantDst)
		}
		if !equalStr(renamed, wantDst) {
			t.Errorf("renamed = %v, want %v", renamed, wantDst)
		}
		if !f.objects[wantDst[0]] || f.objects[renames[0].Src] {
			t.Errorf("expected dst present and src gone; objects=%v", f.list())
		}
	})
}

// TestIntegrationGCSRenameLiveRoundTrip exercises the real copy-rename against a
// live bucket end-to-end: it uploads two objects, renames them via
// RenameGCSObjects (the exact copy-fatal/delete-nonfatal helper imagen/veo
// use), verifies the destinations exist and the sources are gone, then cleans up.
//
// It requires real GCS access and is therefore gated behind GENMEDIA_BUCKET: when
// the env var is unset (as in CI, which drops go.work and runs without cloud
// credentials) the test skips cleanly. Objects live under a unique, clearly-named
// prefix so a run cannot collide with concurrent runs and cleanup is unambiguous.
func TestIntegrationGCSRenameLiveRoundTrip(t *testing.T) {
	bucket := os.Getenv("GENMEDIA_BUCKET")
	if bucket == "" {
		t.Skip("GENMEDIA_BUCKET not set; skipping live GCS rename round-trip")
	}
	ctx := context.Background()

	prefix := fmt.Sprintf("integ_842_rename_%d/", time.Now().UnixNano())
	src1, src2 := prefix+"sample_0.png", prefix+"sample_1.png"
	dst1, dst2 := prefix+"hero_1.png", prefix+"hero_2.png"

	// Best-effort cleanup of anything this test might leave behind.
	t.Cleanup(func() {
		for _, o := range []string{src1, src2, dst1, dst2} {
			_ = deleteGCSObject(ctx, bucket, o)
		}
	})

	for _, o := range []string{src1, src2} {
		if err := UploadToGCS(ctx, bucket, o, "image/png", []byte("integration-test")); err != nil {
			t.Fatalf("UploadToGCS(%s): %v", o, err)
		}
	}

	renamed, err := RenameGCSObjects(ctx, bucket, []Rename{{Src: src1, Dst: dst1}, {Src: src2, Dst: dst2}})
	if err != nil {
		t.Fatalf("RenameGCSObjects error: %v", err)
	}
	if !equalStr(renamed, []string{dst1, dst2}) {
		t.Fatalf("renamed = %v, want %v", renamed, []string{dst1, dst2})
	}

	for _, o := range []string{dst1, dst2} {
		exists, err := gcsObjectExists(ctx, bucket, o)
		if err != nil {
			t.Fatalf("gcsObjectExists(%s): %v", o, err)
		}
		if !exists {
			t.Errorf("destination %q should exist after rename", o)
		}
	}
	for _, o := range []string{src1, src2} {
		exists, err := gcsObjectExists(ctx, bucket, o)
		if err != nil {
			t.Fatalf("gcsObjectExists(%s): %v", o, err)
		}
		if exists {
			t.Errorf("source %q should have been deleted after rename", o)
		}
	}
}

func equalStr(a, b []string) bool {
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

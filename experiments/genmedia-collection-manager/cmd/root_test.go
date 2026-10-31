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

package cmd

import (
	"bytes"
	"testing"
	"time"

	"github.com/charmbracelet/bubbles/table"
	"github.com/google/go-cmp/cmp"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
)

func TestRootSubcommands_Registered(t *testing.T) {
	subcommands := []struct {
		name    string
		groupID string
	}{
		{name: "add", groupID: GroupMutate},
		{name: "check-operation", groupID: GroupOps},
		{name: "delete", groupID: GroupMutate},
		{name: "get", groupID: GroupBrowse},
		{name: "ingest", groupID: GroupMutate},
		{name: "list", groupID: GroupBrowse},
		{name: "list-errors", groupID: GroupBrowse},
		{name: "search", groupID: GroupBrowse},
		{name: "top-models", groupID: GroupAnalytics},
		{name: "top-users", groupID: GroupAnalytics},
		{name: "update", groupID: GroupMutate},
	}

	for _, tc := range subcommands {
		t.Run(tc.name, func(t *testing.T) {
			found, _, err := rootCmd.Find([]string{tc.name})
			if err != nil {
				t.Fatalf("rootCmd.Find(%q) returned unexpected error: %v", tc.name, err)
			}
			if found == nil || found.Name() != tc.name {
				var gotName string
				if found != nil {
					gotName = found.Name()
				}
				t.Errorf("rootCmd.Find(%q) = %q, want %q", tc.name, gotName, tc.name)
			}
			if found.GroupID != tc.groupID {
				t.Errorf("subcommand %q GroupID = %q, want %q", tc.name, found.GroupID, tc.groupID)
			}
			if found.Short == "" || found.Long == "" || found.Example == "" {
				t.Errorf("subcommand %q must populate Short, Long, and Example documentation", tc.name)
			}
		})
	}
}

func TestRequiredFlags(t *testing.T) {
	tests := []struct {
		name    string
		cmdName string
		args    []string
		wantErr bool
	}{
		{
			name:    "add_missing_data",
			cmdName: "add",
			args:    []string{},
			wantErr: true,
		},
		{
			name:    "add_with_data",
			cmdName: "add",
			args:    []string{"--data={\"model\":\"veo\"}"},
			wantErr: false,
		},
		{
			name:    "delete_missing_id",
			cmdName: "delete",
			args:    []string{},
			wantErr: true,
		},
		{
			name:    "delete_with_id",
			cmdName: "delete",
			args:    []string{"--id=doc-123"},
			wantErr: false,
		},
		{
			name:    "search_missing_both",
			cmdName: "search",
			args:    []string{},
			wantErr: true,
		},
		{
			name:    "search_missing_value",
			cmdName: "search",
			args:    []string{"--key=model"},
			wantErr: true,
		},
		{
			name:    "search_with_key_and_value",
			cmdName: "search",
			args:    []string{"--key=model", "--value=imagen"},
			wantErr: false,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			subCmd, _, err := rootCmd.Find([]string{tc.cmdName})
			if err != nil {
				t.Fatalf("rootCmd.Find(%q) returned unexpected error: %v", tc.cmdName, err)
			}
			resetFlagChanged(subCmd)

			if err := subCmd.ParseFlags(tc.args); err != nil {
				t.Fatalf("ParseFlags(%v) returned unexpected error: %v", tc.args, err)
			}
			err = subCmd.ValidateRequiredFlags()
			if gotErr := err != nil; gotErr != tc.wantErr {
				t.Errorf("ValidateRequiredFlags(%q, %v) error = %v, wantErr %v", tc.cmdName, tc.args, err, tc.wantErr)
			}
		})
	}
}

func TestValidateUpdateFlags(t *testing.T) {
	tests := []struct {
		name     string
		payload  string
		dataFile string
		wantErr  bool
	}{
		{
			name:     "neither_set",
			payload:  "",
			dataFile: "",
			wantErr:  true,
		},
		{
			name:     "both_set_mutually_exclusive",
			payload:  `{"a":1}`,
			dataFile: "payload.json",
			wantErr:  true,
		},
		{
			name:     "data_only",
			payload:  `{"a":1}`,
			dataFile: "",
			wantErr:  false,
		},
		{
			name:     "data_file_only",
			payload:  "",
			dataFile: "payload.json",
			wantErr:  false,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			err := validateUpdateFlags(tc.payload, tc.dataFile)
			if gotErr := err != nil; gotErr != tc.wantErr {
				t.Errorf("validateUpdateFlags(%q, %q) error = %v, wantErr %v", tc.payload, tc.dataFile, err, tc.wantErr)
			}
		})
	}
}

func TestValidateDocID_And_Identifier(t *testing.T) {
	docTests := []struct {
		name    string
		docID   string
		wantErr bool
	}{
		{name: "valid_id", docID: "gcs_a1b2c3d4e5f60011", wantErr: false},
		{name: "empty_id", docID: "  ", wantErr: true},
		{name: "slash_traversal", docID: "../secret", wantErr: true},
		{name: "dot_segment", docID: "..", wantErr: true},
	}
	for _, tc := range docTests {
		t.Run("docID_"+tc.name, func(t *testing.T) {
			err := validateDocID(tc.docID)
			if gotErr := err != nil; gotErr != tc.wantErr {
				t.Errorf("validateDocID(%q) error = %v, wantErr %v", tc.docID, err, tc.wantErr)
			}
		})
	}

	idTests := []struct {
		name    string
		value   string
		wantErr bool
	}{
		{name: "valid_operation", value: "1234567890-op_1", wantErr: false},
		{name: "flag_injection", value: "--quiet", wantErr: true},
		{name: "shell_metachar", value: "op;rm -rf /", wantErr: true},
	}
	for _, tc := range idTests {
		t.Run("identifier_"+tc.name, func(t *testing.T) {
			err := validateIdentifier("operation ID", tc.value)
			if gotErr := err != nil; gotErr != tc.wantErr {
				t.Errorf("validateIdentifier(%q) error = %v, wantErr %v", tc.value, err, tc.wantErr)
			}
		})
	}
}

func TestParseGCSURI(t *testing.T) {
	tests := []struct {
		name       string
		rawURI     string
		wantBucket string
		wantPrefix string
		wantErr    bool
	}{
		{
			name:       "bucket_and_prefix_with_scheme",
			rawURI:     "gs://my-campaign-bucket/summer/2026/",
			wantBucket: "my-campaign-bucket",
			wantPrefix: "summer/2026/",
		},
		{
			name:       "bucket_only_with_scheme",
			rawURI:     "gs://my-campaign-bucket",
			wantBucket: "my-campaign-bucket",
			wantPrefix: "",
		},
		{
			name:       "bucket_and_prefix_without_scheme",
			rawURI:     "my-campaign-bucket/vto/models",
			wantBucket: "my-campaign-bucket",
			wantPrefix: "vto/models",
		},
		{
			name:    "empty_uri",
			rawURI:  "   ",
			wantErr: true,
		},
		{
			name:    "traversal_rejected",
			rawURI:  "gs://my-campaign-bucket/../secret",
			wantErr: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			gotBucket, gotPrefix, err := parseGCSURI(tc.rawURI)
			if gotErr := err != nil; gotErr != tc.wantErr {
				t.Fatalf("parseGCSURI(%q) error = %v, wantErr %v", tc.rawURI, err, tc.wantErr)
			}
			if tc.wantErr {
				return
			}
			if gotBucket != tc.wantBucket || gotPrefix != tc.wantPrefix {
				t.Errorf("parseGCSURI(%q) = (%q, %q), want (%q, %q)",
					tc.rawURI, gotBucket, gotPrefix, tc.wantBucket, tc.wantPrefix)
			}
		})
	}
}

func TestInferMediaMimeType(t *testing.T) {
	tests := []struct {
		name        string
		objectName  string
		contentType string
		wantMime    string
		wantCat     string
		wantOK      bool
	}{
		{
			name:       "png_extension",
			objectName: "campaign/hero_shot.PNG",
			wantMime:   "image/png",
			wantCat:    "image",
			wantOK:     true,
		},
		{
			name:       "mp4_extension",
			objectName: "renders/clip_01.mp4",
			wantMime:   "video/mp4",
			wantCat:    "video",
			wantOK:     true,
		},
		{
			name:       "wav_extension",
			objectName: "voiceover/take_1.wav",
			wantMime:   "audio/wav",
			wantCat:    "audio",
			wantOK:     true,
		},
		{
			name:        "fallback_to_content_type",
			objectName:  "blobs/asset_without_ext",
			contentType: "image/jpeg; charset=binary",
			wantMime:    "image/jpeg",
			wantCat:     "image",
			wantOK:      true,
		},
		{
			name:        "non_media_file_skipped",
			objectName:  "campaign/notes.txt",
			contentType: "text/plain",
			wantOK:      false,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			gotMime, gotCat, gotOK := inferMediaMimeType(tc.objectName, tc.contentType)
			if gotOK != tc.wantOK || gotMime != tc.wantMime || gotCat != tc.wantCat {
				t.Errorf("inferMediaMimeType(%q, %q) = (%q, %q, %v), want (%q, %q, %v)",
					tc.objectName, tc.contentType, gotMime, gotCat, gotOK, tc.wantMime, tc.wantCat, tc.wantOK)
			}
		})
	}
}

func TestBuildIngestedMediaItem_And_CSVPresets(t *testing.T) {
	ts := time.Date(2026, time.October, 31, 12, 0, 0, 0, time.UTC)
	uri := "gs://campaign-bkt/looks/linen_blazer-front.png"
	item := gcsMediaObject{
		ID:            deterministicMediaDocID(uri),
		Bucket:        "campaign-bkt",
		ObjectName:    "looks/linen_blazer-front.png",
		GCSURI:        uri,
		MimeType:      "image/png",
		MediaCategory: "image",
		SizeBytes:     204800,
		Updated:       ts,
		Prompt:        humanizeObjectPrompt("looks/linen_blazer-front.png", ""),
		Model:         "external-ingest",
	}

	opts := ingestOptions{
		UserEmail:  "alice@example.com",
		Model:      "external-ingest",
		Mode:       "ingested",
		ModelGroup: "formal",
	}

	doc := buildIngestedMediaItem(item, opts)
	if doc["id"] != item.ID || doc["gcsuri"] != uri || doc["prompt"] != "linen blazer front" {
		t.Errorf("buildIngestedMediaItem(%+v, %+v) = %+v, unexpected id/gcsuri/prompt", item, opts, doc)
	}

	for _, preset := range []string{CSVPresetGeneric, CSVPresetBatchPrompt, CSVPresetVTOModels, CSVPresetVTOCatalog} {
		t.Run("preset_"+preset, func(t *testing.T) {
			headers, rows, err := buildIngestCSV([]gcsMediaObject{item}, preset, opts)
			if err != nil {
				t.Fatalf("buildIngestCSV(%q) returned unexpected error: %v", preset, err)
			}
			if len(headers) == 0 || len(rows) != 1 || len(rows[0]) != len(headers) {
				t.Errorf("buildIngestCSV(%q) headers=%v rows=%v, want 1 row matching header length", preset, headers, rows)
			}
		})
	}

	if _, _, err := buildIngestCSV([]gcsMediaObject{item}, "invalid-preset", opts); err == nil {
		t.Errorf("buildIngestCSV(\"invalid-preset\") succeeded, want error")
	}
}

func TestResolveFieldsToShow(t *testing.T) {
	tests := []struct {
		name      string
		fields    string
		mediaType string
		want      []string
	}{
		{
			name:      "custom_fields_trimmed",
			fields:    " prompt , model , timestamp ",
			mediaType: "image",
			want:      []string{"prompt", "model", "timestamp"},
		},
		{
			name:      "default_image",
			fields:    "",
			mediaType: "image",
			want:      []string{"id", "mime_type", "user_email", "timestamp", "model", "original_prompt", "rewritten_prompt"},
		},
		{
			name:      "default_video",
			fields:    "",
			mediaType: "video",
			want:      []string{"id", "mime_type", "user_email", "timestamp", "model", "prompt", "duration"},
		},
		{
			name:      "default_audio",
			fields:    "",
			mediaType: "audio",
			want:      []string{"id", "mime_type", "user_email", "timestamp", "model", "original_prompt", "prompt"},
		},
		{
			name:      "default_all",
			fields:    "",
			mediaType: "",
			want:      []string{"id", "mime_type", "user_email", "timestamp", "model", "prompt"},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := resolveFieldsToShow(tc.fields, tc.mediaType)
			if diff := cmp.Diff(tc.want, got); diff != "" {
				t.Errorf("resolveFieldsToShow(%q, %q) returned unexpected diff (-want +got):\n%s", tc.fields, tc.mediaType, diff)
			}
		})
	}
}

func TestExtractErrorDoc(t *testing.T) {
	ts := time.Date(2026, time.October, 24, 15, 4, 0, 0, time.UTC)

	tests := []struct {
		name    string
		id      string
		docData map[string]any
		want    errorDoc
		wantOK  bool
	}{
		{
			name: "missing_error_message",
			id:   "doc-1",
			docData: map[string]any{
				"mime_type": "image/png",
			},
			want:   errorDoc{},
			wantOK: false,
		},
		{
			name: "error_with_missing_mime_type_does_not_panic",
			id:   "doc-2",
			docData: map[string]any{
				"error_message": "quota exceeded",
				"user_email":    "alice@example.com",
				"timestamp":     ts,
			},
			want: errorDoc{
				ID:           "doc-2",
				MimeType:     "",
				Timestamp:    ts,
				ErrorMessage: "quota exceeded",
				UserEmail:    "alice@example.com",
				Model:        "",
			},
			wantOK: true,
		},
		{
			name: "complete_error_doc",
			id:   "doc-3",
			docData: map[string]any{
				"error_message": "generation failed",
				"mime_type":     "video/mp4",
				"user_email":    "bob@example.com",
				"model":         "veo-2",
				"timestamp":     ts,
			},
			want: errorDoc{
				ID:           "doc-3",
				MimeType:     "video/mp4",
				Timestamp:    ts,
				ErrorMessage: "generation failed",
				UserEmail:    "bob@example.com",
				Model:        "veo-2",
			},
			wantOK: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, gotOK := extractErrorDoc(tc.id, tc.docData)
			if gotOK != tc.wantOK {
				t.Errorf("extractErrorDoc(%q, %+v) ok = %v, want %v", tc.id, tc.docData, gotOK, tc.wantOK)
			}
			if diff := cmp.Diff(tc.want, got); diff != "" {
				t.Errorf("extractErrorDoc(%q, %+v) returned unexpected diff (-want +got):\n%s", tc.id, tc.docData, diff)
			}
		})
	}
}

func TestFormatFieldValue(t *testing.T) {
	ts := time.Date(2026, time.October, 24, 15, 4, 0, 0, time.UTC)

	tests := []struct {
		name   string
		val    any
		maxLen int
		want   string
	}{
		{
			name:   "nil_value",
			val:    nil,
			maxLen: 50,
			want:   "<nil>",
		},
		{
			name:   "timestamp_value",
			val:    ts,
			maxLen: 50,
			want:   "2026-10-24 15:04",
		},
		{
			name:   "short_string",
			val:    "hello world",
			maxLen: 50,
			want:   "hello world",
		},
		{
			name:   "truncated_string",
			val:    "abcdefghijklmnopqrstuvwxyz",
			maxLen: 10,
			want:   "abcdefg...",
		},
		{
			name:   "string_slice_joined",
			val:    []string{"gs://bkt/a.png", "gs://bkt/b.png"},
			maxLen: 0,
			want:   "gs://bkt/a.png;gs://bkt/b.png",
		},
		{
			name:   "numeric_value",
			val:    42,
			maxLen: 0,
			want:   "42",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := formatFieldValue(tc.val, tc.maxLen); got != tc.want {
				t.Errorf("formatFieldValue(%v, %d) = %q, want %q", tc.val, tc.maxLen, got, tc.want)
			}
		})
	}
}

func TestFormatRowHeader(t *testing.T) {
	tests := []struct {
		name string
		row  table.Row
		want string
	}{
		{
			name: "empty_row",
			row:  nil,
			want: "",
		},
		{
			name: "short_row_fewer_than_5_cols",
			row:  table.Row{"doc-1", "prompt text"},
			want: "Document ID: doc-1",
		},
		{
			name: "standard_row_5_or_more_cols",
			row:  table.Row{"doc-1", "image/png", "user@example.com", "2026-10-24 15:04", "imagen-3"},
			want: "Document ID: doc-1 | Mime Type: image/png | Model: imagen-3",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := formatRowHeader(tc.row); got != tc.want {
				t.Errorf("formatRowHeader(%v) = %q, want %q", tc.row, got, tc.want)
			}
		})
	}
}

func TestSortedModelUsers(t *testing.T) {
	t1 := time.Date(2026, time.October, 20, 10, 0, 0, 0, time.UTC)
	t2 := time.Date(2026, time.October, 24, 12, 0, 0, 0, time.UTC)

	stats := make(map[string]*modelStat)
	docs := []map[string]any{
		{"model": "imagen-3", "user_email": "bob@example.com", "timestamp": t1},
		{"model": "imagen-3", "user_email": "alice@example.com", "timestamp": t1},
		{"model": "imagen-3", "user_email": "alice@example.com", "timestamp": t2},
	}
	for _, doc := range docs {
		accumulateModelStat(stats, doc)
	}

	got := sortedModelUsers(stats["imagen-3"].UserDocs)
	want := []*modelUserStat{
		{Email: "alice@example.com", DocCount: 2, LastActivity: t2},
		{Email: "bob@example.com", DocCount: 1, LastActivity: t1},
	}

	if diff := cmp.Diff(want, got); diff != "" {
		t.Errorf("sortedModelUsers(%+v) returned unexpected diff (-want +got):\n%s", docs, diff)
	}
}

func TestWriteCSV(t *testing.T) {
	headers := []string{"ID", "MODEL"}
	rows := [][]string{
		{"doc-1", "imagen-3"},
		{"doc-2", "veo-2"},
	}
	var buf bytes.Buffer
	if err := writeCSV(&buf, headers, rows); err != nil {
		t.Fatalf("writeCSV(%v, %v) returned unexpected error: %v", headers, rows, err)
	}

	want := "ID,MODEL\ndoc-1,imagen-3\ndoc-2,veo-2\n"
	if got := buf.String(); got != want {
		t.Errorf("writeCSV(%v, %v) = %q, want %q", headers, rows, got, want)
	}
}

func TestApplyLimit_And_EffectiveView(t *testing.T) {
	items := []int{1, 2, 3, 4, 5}
	if got := applyLimit(items, 3); len(got) != 3 {
		t.Errorf("applyLimit(%v, 3) len = %d, want 3", items, len(got))
	}
	if got := applyLimit(items, 0); len(got) != 5 {
		t.Errorf("applyLimit(%v, 0) len = %d, want 5", items, len(got))
	}

	t.Setenv("GENMEDIA_NO_TUI", "1")
	if got := resolveEffectiveView(nil, "table"); got != "text" {
		t.Errorf("resolveEffectiveView(nil, \"table\") with GENMEDIA_NO_TUI=1 = %q, want \"text\"", got)
	}
}

func resetFlagChanged(cmd *cobra.Command) {
	cmd.Flags().VisitAll(func(f *pflag.Flag) {
		f.Changed = false
		_ = f.Value.Set(f.DefValue)
	})
}

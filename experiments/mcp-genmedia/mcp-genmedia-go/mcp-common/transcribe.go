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
//
// This file holds the shared Gemini 3.5 Transcribe (speech-to-text) plumbing so
// both the all-in-one mcp-gemini-go server and the standalone
// mcp-gemini-transcribe-go server call the exact same request/response contract
// and can never drift — the same pattern the Omni helpers in this package use.
//
// It targets the *synchronous* transcription API (the standard generate_content
// method with an AudioTranscriptionConfig on gemini-3.5-transcribe-preview), NOT
// the live/streaming BidiGenerateContent API. See
// https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-transcribe.md.txt

package common

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path"
	"strings"
	"time"

	"github.com/mark3labs/mcp-go/mcp"
	"google.golang.org/genai"
)

// DefaultTranscribeModel is the synchronous ("audio file processing") Gemini 3.5
// Transcribe model. The live/streaming variant (gemini-3.5-transcribe-live-preview)
// is deliberately NOT used here.
const DefaultTranscribeModel = "gemini-3.5-transcribe-preview"

// maxTranscribeCustomVocabulary is the documented ceiling on custom-vocabulary
// bias terms accepted by the model.
const maxTranscribeCustomVocabulary = 1000

// TranscribeParams are the inputs to a single synchronous transcription call.
// Exactly one audio source must be provided: LocalPath (a local file that is read
// and sent inline) or GCSURI (a gs:// URI sent by reference).
type TranscribeParams struct {
	// LocalPath is a local audio file path. Mutually exclusive with GCSURI.
	LocalPath string
	// GCSURI is a gs:// URI to an audio file. Mutually exclusive with LocalPath.
	GCSURI string
	// MimeType is the audio MIME type (e.g. "audio/wav"). Required; callers may
	// infer it from the file extension via InferAudioMIMEType.
	MimeType string
	// Model is the resolved model ID. If empty, DefaultTranscribeModel is used.
	Model string
	// LanguageCodes are optional BCP-47 hints. Omit for auto-detection.
	LanguageCodes []string
	// CustomVocabulary biases recognition toward specific terms (up to 1000).
	CustomVocabulary []string
	// Diarization asks the model to label individual speakers (up to 8).
	Diarization bool
	// WordTimestamps requests word-level start/end offsets.
	WordTimestamps bool
	// SmartFormatting selects SMART transcription mode (disfluency removal, light
	// grammatical cleanup, automatic formatting). Incompatible with Diarization
	// and WordTimestamps.
	SmartFormatting bool
}

// TranscribeWord is one recognized word with its timing, mirroring genai.WordInfo
// so the JSON output is stable and independent of the SDK's wire tags.
type TranscribeWord struct {
	Word        string `json:"word"`
	StartOffset string `json:"start_offset,omitempty"`
	EndOffset   string `json:"end_offset,omitempty"`
}

// TranscribeSegment is one transcription part (a speaker turn when diarization is
// enabled, otherwise a contiguous chunk of transcript).
type TranscribeSegment struct {
	Text         string           `json:"text"`
	SpeakerLabel string           `json:"speaker_label,omitempty"`
	LanguageCode string           `json:"language_code,omitempty"`
	Words        []TranscribeWord `json:"words,omitempty"`
}

// TranscribeResult is the mapped output of a synchronous transcription call.
type TranscribeResult struct {
	Model      string              `json:"model"`
	Transcript string              `json:"transcript"`
	Segments   []TranscribeSegment `json:"segments,omitempty"`
}

// HasStructuredDetail reports whether any segment carries speaker labels or
// word-level timing worth surfacing beyond the plain transcript.
func (r *TranscribeResult) HasStructuredDetail() bool {
	for _, s := range r.Segments {
		if s.SpeakerLabel != "" || len(s.Words) > 0 {
			return true
		}
	}
	return false
}

// ParsedTranscribeArgs is the validated result of parsing an MCP tool call's
// arguments for a transcription request.
type ParsedTranscribeArgs struct {
	Params         TranscribeParams
	OutputDir      string
	GCSBucketURI   string
	OutputFilename string
}

// ParseTranscribeToolArgs validates and normalizes the raw MCP tool arguments
// shared by both transcribe servers. It resolves the audio source (local path vs
// gs:// URI), infers the MIME type from the extension when not supplied, and
// enforces the model's documented feature constraints (SMART mode is incompatible
// with diarization / word timestamps; custom vocabulary is capped at 1000 terms).
func ParseTranscribeToolArgs(args map[string]any) (*ParsedTranscribeArgs, error) {
	source, _ := args["input_audio"].(string)
	source = strings.TrimSpace(source)
	if source == "" {
		return nil, fmt.Errorf("input_audio must be a non-empty string (a local file path or a gs:// URI) and is required")
	}

	var p TranscribeParams
	if strings.HasPrefix(source, "gs://") {
		p.GCSURI = source
	} else {
		p.LocalPath = source
	}

	mimeType, _ := args["mime_type"].(string)
	mimeType = strings.TrimSpace(mimeType)
	if mimeType == "" {
		mimeType = InferAudioMIMEType(source)
	}
	if mimeType == "" {
		return nil, fmt.Errorf("could not infer the audio MIME type from %q; set mime_type explicitly (e.g. audio/wav)", source)
	}
	p.MimeType = mimeType

	if model := ResolveModel(args, "model_id", "model_name"); model != "" {
		p.Model = model
	} else {
		p.Model = DefaultTranscribeModel
	}

	p.LanguageCodes = stringSliceArg(args["language_codes"])
	p.CustomVocabulary = stringSliceArg(args["custom_vocabulary"])
	if len(p.CustomVocabulary) > maxTranscribeCustomVocabulary {
		return nil, fmt.Errorf("custom_vocabulary has %d terms; the maximum is %d", len(p.CustomVocabulary), maxTranscribeCustomVocabulary)
	}

	p.Diarization = boolArg(args["enable_diarization"])
	p.WordTimestamps = boolArg(args["enable_word_timestamps"])
	p.SmartFormatting = boolArg(args["smart_formatting"])
	if p.SmartFormatting && (p.Diarization || p.WordTimestamps) {
		return nil, fmt.Errorf("smart_formatting (SMART mode) is incompatible with enable_diarization and enable_word_timestamps; enable at most one")
	}

	parsed := &ParsedTranscribeArgs{Params: p}
	parsed.OutputDir = ResolveOutputDirectory(args, "output_local_dir", "local_path")
	if uri := ResolveGCSBucketURI(args, "bucket", "output_gcs_bucket"); uri != "" {
		parsed.GCSBucketURI = EnsureGCSPathPrefix(uri)
	}
	parsed.OutputFilename = ResolveOutputFilename(args)

	return parsed, nil
}

// Transcribe runs a single synchronous transcription against the provided genai
// client. It reads a local audio file (when LocalPath is set) or references a
// gs:// URI, builds the AudioTranscriptionConfig, calls generate_content, and maps
// the response. The client must be a Vertex AI genai client configured for the
// "global" location (the only region the transcribe models are served in).
func Transcribe(ctx context.Context, client *genai.Client, p TranscribeParams) (*TranscribeResult, error) {
	if client == nil {
		return nil, fmt.Errorf("transcribe: genai client is not initialized")
	}
	contents, err := buildTranscribeContents(p)
	if err != nil {
		return nil, err
	}
	model := p.Model
	if strings.TrimSpace(model) == "" {
		model = DefaultTranscribeModel
	}
	resp, err := client.Models.GenerateContent(ctx, model, contents, buildTranscribeConfig(p))
	if err != nil {
		return nil, fmt.Errorf("transcribe: generate_content failed: %w", err)
	}
	return mapTranscribeResponse(model, resp), nil
}

// buildTranscribeContents constructs the single-part audio content for the
// request, reading the local file when needed.
func buildTranscribeContents(p TranscribeParams) ([]*genai.Content, error) {
	if strings.TrimSpace(p.MimeType) == "" {
		return nil, fmt.Errorf("transcribe: mime_type is required")
	}
	var part *genai.Part
	switch {
	case p.LocalPath != "" && p.GCSURI != "":
		return nil, fmt.Errorf("transcribe: provide either a local path or a gs:// URI, not both")
	case p.GCSURI != "":
		part = genai.NewPartFromURI(p.GCSURI, p.MimeType)
	case p.LocalPath != "":
		data, err := os.ReadFile(p.LocalPath)
		if err != nil {
			return nil, fmt.Errorf("transcribe: failed to read audio file %q: %w", p.LocalPath, err)
		}
		if len(data) == 0 {
			return nil, fmt.Errorf("transcribe: audio file %q is empty", p.LocalPath)
		}
		part = genai.NewPartFromBytes(data, p.MimeType)
	default:
		return nil, fmt.Errorf("transcribe: no audio source provided")
	}
	return []*genai.Content{{Parts: []*genai.Part{part}, Role: "user"}}, nil
}

// buildTranscribeConfig maps TranscribeParams onto the genai request config,
// setting only the AudioTranscriptionConfig fields the caller requested.
func buildTranscribeConfig(p TranscribeParams) *genai.GenerateContentConfig {
	atc := &genai.AudioTranscriptionConfig{}
	if len(p.LanguageCodes) > 0 {
		atc.LanguageCodes = p.LanguageCodes
	}
	if len(p.CustomVocabulary) > 0 {
		atc.CustomVocabulary = p.CustomVocabulary
	}
	if p.Diarization {
		v := true
		atc.Diarization = &v
	}
	if p.WordTimestamps {
		v := true
		atc.WordTimestamp = &v
	}
	if p.SmartFormatting {
		atc.Mode = genai.AudioTranscriptionConfigModeSmart
	}
	return &genai.GenerateContentConfig{AudioTranscriptionConfig: atc}
}

// mapTranscribeResponse walks the response candidates/parts, collecting the plain
// transcript and any structured (speaker/word) detail. Text may live on the part
// directly or inside the part's audio_transcription (the diarization shape).
func mapTranscribeResponse(model string, resp *genai.GenerateContentResponse) *TranscribeResult {
	result := &TranscribeResult{Model: model}
	if resp == nil {
		return result
	}

	var lines []string
	diarized := false
	for _, cand := range resp.Candidates {
		if cand == nil || cand.Content == nil {
			continue
		}
		for _, part := range cand.Content.Parts {
			if part == nil {
				continue
			}
			seg := TranscribeSegment{Text: part.Text}
			if at := part.AudioTranscription; at != nil {
				if seg.Text == "" {
					seg.Text = at.Text
				}
				seg.SpeakerLabel = at.SpeakerLabel
				seg.LanguageCode = at.LanguageCode
				for _, w := range at.Words {
					if w == nil {
						continue
					}
					seg.Words = append(seg.Words, TranscribeWord{
						Word:        w.Word,
						StartOffset: w.StartOffset,
						EndOffset:   w.EndOffset,
					})
				}
			}
			if seg.Text == "" && seg.SpeakerLabel == "" && len(seg.Words) == 0 {
				continue
			}
			if seg.SpeakerLabel != "" {
				diarized = true
			}
			result.Segments = append(result.Segments, seg)
			if seg.Text != "" {
				if seg.SpeakerLabel != "" {
					lines = append(lines, fmt.Sprintf("%s: %s", seg.SpeakerLabel, seg.Text))
				} else {
					lines = append(lines, seg.Text)
				}
			}
		}
	}

	sep := " "
	if diarized {
		sep = "\n"
	}
	result.Transcript = strings.TrimSpace(strings.Join(lines, sep))
	return result
}

// RenderTranscribeResult builds the MCP content for a transcription result and,
// when an output destination is requested, persists the full structured result
// as a JSON file locally and/or to GCS. The plain transcript is always returned
// as the first text item; structured (speaker/word) detail is returned as a
// second JSON text item when present.
func RenderTranscribeResult(ctx context.Context, result *TranscribeResult, outputDir, gcsBucketURI, outputFilename string) ([]mcp.Content, error) {
	summary := result.Transcript
	if summary == "" {
		summary = "(no speech detected in the audio)"
	}

	var saveMsg string
	if outputDir != "" || gcsBucketURI != "" {
		jsonBytes, err := json.MarshalIndent(result, "", "  ")
		if err != nil {
			return nil, fmt.Errorf("failed to marshal transcription result: %w", err)
		}
		art := MediaArtifact{
			Data:     jsonBytes,
			MimeType: "application/json",
			FileName: transcribeOutputFilename(outputFilename),
		}
		persisted, err := PersistMediaOutputs(ctx, art, outputDir, gcsBucketURI, 0)
		if err != nil {
			return nil, err
		}
		var dests []string
		if persisted.LocalPath != "" {
			dests = append(dests, fmt.Sprintf("saved to %s", persisted.LocalPath))
		}
		if persisted.GCSURI != "" {
			dests = append(dests, fmt.Sprintf("uploaded to %s", persisted.GCSURI))
		} else if persisted.GCSError != nil {
			dests = append(dests, fmt.Sprintf("GCS upload to gs://%s/%s failed: %v", persisted.GCSBucket, persisted.GCSObject, persisted.GCSError))
		}
		if len(dests) > 0 {
			saveMsg = "\n\nTranscript (JSON) " + strings.Join(dests, "; ") + "."
		}
	}

	content := []mcp.Content{
		mcp.TextContent{Type: "text", Text: summary + saveMsg},
	}
	if result.HasStructuredDetail() {
		jsonBytes, err := json.MarshalIndent(result, "", "  ")
		if err != nil {
			return nil, fmt.Errorf("failed to marshal transcription detail: %w", err)
		}
		content = append(content, mcp.TextContent{Type: "text", Text: string(jsonBytes)})
	}
	return content, nil
}

// transcribeOutputFilename resolves the JSON output filename, honoring a
// client-supplied base name (extension forced to .json) and falling back to a
// timestamped default.
func transcribeOutputFilename(base string) string {
	if base != "" {
		stem := SanitizeBaseFilename(base)
		stem = strings.TrimSuffix(stem, path.Ext(stem))
		stem = strings.TrimSpace(stem)
		if stem != "" {
			return stem + ".json"
		}
	}
	return fmt.Sprintf("transcript-%s.json", time.Now().Format("20060102-150405"))
}

// InferAudioMIMEType guesses an audio MIME type from a file path/URI extension.
// It returns "" when the extension is unknown so callers can require an explicit
// mime_type.
func InferAudioMIMEType(name string) string {
	ext := strings.ToLower(path.Ext(strings.TrimSpace(name)))
	switch ext {
	case ".wav":
		return "audio/wav"
	case ".mp3":
		return "audio/mpeg"
	case ".ogg", ".oga", ".opus":
		return "audio/ogg"
	case ".flac":
		return "audio/flac"
	case ".m4a", ".mp4", ".aac":
		return "audio/mp4"
	case ".aiff", ".aif":
		return "audio/aiff"
	case ".amr":
		return "audio/amr"
	case ".webm":
		return "audio/webm"
	case ".pcm", ".l16":
		return "audio/pcm"
	default:
		return ""
	}
}

// stringSliceArg coerces an MCP argument into a []string, accepting either a
// JSON array of strings or a single comma-separated string. Empty entries are
// dropped and surrounding whitespace trimmed.
func stringSliceArg(v any) []string {
	var out []string
	switch t := v.(type) {
	case []string:
		for _, s := range t {
			if s = strings.TrimSpace(s); s != "" {
				out = append(out, s)
			}
		}
	case []any:
		for _, item := range t {
			if s, ok := item.(string); ok {
				if s = strings.TrimSpace(s); s != "" {
					out = append(out, s)
				}
			}
		}
	case string:
		for _, s := range strings.Split(t, ",") {
			if s = strings.TrimSpace(s); s != "" {
				out = append(out, s)
			}
		}
	}
	return out
}

// boolArg coerces an MCP argument into a bool, accepting native bools and the
// strings "true"/"false".
func boolArg(v any) bool {
	switch t := v.(type) {
	case bool:
		return t
	case string:
		return strings.EqualFold(strings.TrimSpace(t), "true")
	default:
		return false
	}
}

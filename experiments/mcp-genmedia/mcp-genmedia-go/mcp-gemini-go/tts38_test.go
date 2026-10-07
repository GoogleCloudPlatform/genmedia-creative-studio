// Copyright 2026 Google LLC
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
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
	"github.com/mark3labs/mcp-go/mcp"
	"google.golang.org/genai"
)

func TestIsTTS38Model(t *testing.T) {
	for model, want := range map[string]bool{
		"gemini-3.8-flash-tts":         true,
		"gemini-3.8-flash-lite-tts":    true,
		" Gemini-3.8-Flash-TTS ":       true,
		"gemini-3.1-flash-tts-preview": false,
		"gemini-2.5-pro-tts":           false,
		"gemini-3.8-live-preview":      false,
	} {
		if got := isTTS38Model(model); got != want {
			t.Errorf("isTTS38Model(%q) = %v, want %v", model, got, want)
		}
	}
}

func TestBuildTTS38RequestSingleSpeaker(t *testing.T) {
	contents, cfg, err := buildTTS38Request("Hello <sigh> there.", "  warm  ", "en-au-podcaster-4", "", "LINEAR16", nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	p := contents[0].Parts[0]
	if contents[0].Role != "user" || p.Text != "Hello <sigh> there." {
		t.Fatalf("unexpected part: %+v", p)
	}
	if p.SpeechMetadata == nil || p.SpeechMetadata.Style != "warm" {
		t.Fatalf("style not set/trimmed: %+v", p.SpeechMetadata)
	}
	if cfg.SpeechConfig.VoiceConfig.Voice != "en-au-podcaster-4" || cfg.SpeechConfig.VoiceConfig.PrebuiltVoiceConfig != nil {
		t.Fatalf("voice must use voiceConfig.voice: %+v", cfg.SpeechConfig.VoiceConfig)
	}
	if cfg.SpeechConfig.LanguageCode != "" || cfg.HTTPOptions != nil {
		t.Fatalf("no language/responseFormat expected: %+v", cfg)
	}
	if cfg.ResponseModalities[0] != "AUDIO" || cfg.SystemInstruction != nil || cfg.Temperature != nil {
		t.Fatalf("unexpected config: %+v", cfg)
	}

	// Empty style -> no speechMetadata at all.
	contents, _, _ = buildTTS38Request("Hi.", "", "Kore", "", "", nil, nil)
	if contents[0].Parts[0].SpeechMetadata != nil {
		t.Fatal("empty style must not send speechMetadata")
	}
}

func TestBuildTTS38RequestEncodings(t *testing.T) {
	for enc, want := range map[string]string{"PCM": "AUDIO_L16", "MULAW": "AUDIO_MULAW", "ALAW": "AUDIO_ALAW"} {
		_, cfg, err := buildTTS38Request("Hi.", "", "Kore", "", enc, nil, nil)
		if err != nil {
			t.Fatalf("%s: %v", enc, err)
		}
		b, _ := json.Marshal(cfg.HTTPOptions.ExtraBody)
		if !strings.Contains(string(b), `"responseFormat":[{"audio":{"mimeType":"`+want+`"}}]`) {
			t.Errorf("%s: extra body %s", enc, b)
		}
	}
	for _, enc := range []string{"MP3", "OGG_OPUS", "M4A"} {
		if _, _, err := buildTTS38Request("Hi.", "", "Kore", "", enc, nil, nil); err == nil {
			t.Errorf("%s should be rejected for 3.8", enc)
		}
	}
}

func TestBuildTTS38RequestMultiSpeaker(t *testing.T) {
	speakers := []ttsSpeaker{{"Joe", "Puck"}, {"Jane", "voice_abc"}}
	turns := []ttsTurn{{"Joe", "Ready? |oh hmm|", "brisk"}, {"Jane", "Ready enough.", ""}}
	contents, cfg, err := buildTTS38Request("ignored", "ignored", "Kore", "", "", turns, speakers)
	if err != nil {
		t.Fatal(err)
	}
	parts := contents[0].Parts
	if len(parts) != 2 || parts[0].SpeechMetadata.Speaker != "Joe" || parts[0].SpeechMetadata.Style != "brisk" || parts[1].SpeechMetadata.Speaker != "Jane" {
		t.Fatalf("bad parts: %+v %+v", parts[0].SpeechMetadata, parts[1].SpeechMetadata)
	}
	if cfg.SpeechConfig.VoiceConfig != nil {
		t.Fatal("single voiceConfig must be unset for multi-speaker")
	}
	svc := cfg.SpeechConfig.MultiSpeakerVoiceConfig.SpeakerVoiceConfigs
	if len(svc) != 2 || svc[1].VoiceConfig.Voice != "voice_abc" {
		t.Fatalf("bad speaker configs: %+v", svc)
	}

	if _, _, err := buildTTS38Request("", "", "", "", "", turns, speakers[:1]); err == nil {
		t.Error("1 speaker must error")
	}
	three := append(append([]ttsSpeaker{}, speakers...), ttsSpeaker{"Max", "Charon"})
	if _, _, err := buildTTS38Request("", "", "", "", "", turns, three); err == nil {
		t.Error("3 speakers must error (API requires exactly 2)")
	}
	if _, _, err := buildTTS38Request("", "", "", "", "", []ttsTurn{{"Zed", "Hi", ""}}, speakers); err == nil {
		t.Error("unknown turn speaker must error")
	}
}

func TestLintTTSInput(t *testing.T) {
	has := func(ws []string, sub string) bool {
		for _, w := range ws {
			if strings.Contains(w, sub) {
				return true
			}
		}
		return false
	}
	m38, m31 := "gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview"

	cases := []struct {
		name, model, text, style string
		want                     string // substring expected; "" = expect no warnings
	}{
		{"clean 3.8", m38, "Wait... <short pause> did you hear that? <gasp>", "whispered, nervous", ""},
		{"say the following", m38, "Say the following cheerfully: The eagle flies at midnight.", "", "Say the following"},
		{"markdown profile", m38, "# AUDIO PROFILE: Jaz\n#### TRANSCRIPT\nHello", "", "Audio Profile"},
		{"take markers", m38, "Take 1. Direct.\nBuy now.\nTake 2. Urgent.\nBuy now!", "", "Take N"},
		{"speaker prefixes", m38, "Joe: Hi Jane.\nJane: Hi Joe.", "", "turns + speakers"},
		{"square tags", m38, "[sigh] I can't believe it.", "", "[square] tags"},
		{"inline style tag", m38, "[whispering] Don't move.", "", `[whispering] -> style "whispering"`},
		{"undocumented angle", m38, "<sarcastic> Great.", "", "<sarcastic>"},
		{"long style", m38, "Hi.", strings.Repeat("very ", 50), "short styles"},
		{"angle on 3.1", m31, "<sigh> Hi.", "", "[square] tags"},
		{"square on 3.1", m31, "[sigh] Hi.", "", ""},
	}
	for _, c := range cases {
		ws := lintTTSInput(c.model, c.text, c.style, nil)
		if c.want == "" && len(ws) != 0 {
			t.Errorf("%s: expected no warnings, got %v", c.name, ws)
		}
		if c.want != "" && !has(ws, c.want) {
			t.Errorf("%s: expected warning containing %q, got %v", c.name, c.want, ws)
		}
	}
	// Turns are linted too.
	if ws := lintTTSInput(m38, "", "", []ttsTurn{{"A", "[shouting] Go!", ""}}); !has(ws, "shouting") {
		t.Errorf("turn text not linted: %v", ws)
	}
}

func TestExtractTTS38Audio(t *testing.T) {
	pcmA, pcmB := []byte{1, 2, 3, 4}, []byte{5, 6}
	resp := &genai.GenerateContentResponse{Candidates: []*genai.Candidate{{Content: &genai.Content{Parts: []*genai.Part{
		{InlineData: &genai.Blob{MIMEType: "audio/wav", Data: pcmToWAV(pcmA, 24000, 1)}},
		{Text: "ignored text part"},
		{InlineData: &genai.Blob{MIMEType: "audio/wav", Data: pcmToWAV(pcmB, 24000, 1)}},
	}}}}}
	b, mime, err := extractTTS38Audio(resp)
	if err != nil || mime != "audio/wav" {
		t.Fatalf("err=%v mime=%s", err, mime)
	}
	if got := stripWAVHeader(b); string(got) != string(append(pcmA, pcmB...)) {
		t.Fatalf("merged PCM = %v", got)
	}
	if len(b) != 44+6 {
		t.Fatalf("expected a single header, len=%d", len(b))
	}

	if _, _, err := extractTTS38Audio(&genai.GenerateContentResponse{PromptFeedback: &genai.GenerateContentResponsePromptFeedback{BlockReason: "PROHIBITED_CONTENT"}}); err == nil || !strings.Contains(err.Error(), "PROHIBITED_CONTENT") {
		t.Fatalf("expected block reason in error, got %v", err)
	}
}

func callTTS(t *testing.T, args map[string]any) *mcp.CallToolResult {
	t.Helper()
	req := mcp.CallToolRequest{}
	req.Params.Arguments = args
	res, err := geminiAudioTTSHandler(context.Background(), req)
	if err != nil {
		t.Fatal(err)
	}
	return res
}

func resultText(r *mcp.CallToolResult) string {
	var sb strings.Builder
	for _, c := range r.Content {
		if tc, ok := c.(mcp.TextContent); ok {
			sb.WriteString(tc.Text)
		}
	}
	return sb.String()
}

func TestGeminiAudioTTSHandlerRouting(t *testing.T) {
	orig := generateTTS38Fn
	t.Cleanup(func() { generateTTS38Fn = orig })
	var gotModel string
	var gotContents []*genai.Content
	var gotCfg *genai.GenerateContentConfig
	generateTTS38Fn = func(_ context.Context, model string, contents []*genai.Content, cfg *genai.GenerateContentConfig) (*genai.GenerateContentResponse, error) {
		gotModel, gotContents, gotCfg = model, contents, cfg
		return &genai.GenerateContentResponse{Candidates: []*genai.Candidate{{Content: &genai.Content{Parts: []*genai.Part{
			{InlineData: &genai.Blob{MIMEType: "audio/wav", Data: pcmToWAV([]byte{0, 0}, 24000, 1)}},
		}}}}}, nil
	}

	// Default model is 3.8 and accepts a library voice ID; style goes to speechMetadata.
	res := callTTS(t, map[string]any{"text": "[whispering] Hello.", "prompt": "warm", "voice_name": "en-au-podcaster-4"})
	if res.IsError {
		t.Fatalf("unexpected error: %s", resultText(res))
	}
	if gotModel != defaultGeminiTTSModel || gotContents[0].Parts[0].SpeechMetadata.Style != "warm" || gotCfg.SpeechConfig.VoiceConfig.Voice != "en-au-podcaster-4" {
		t.Fatalf("bad routing: model=%s cfg=%+v", gotModel, gotCfg.SpeechConfig)
	}
	if gotCfg.SpeechConfig.LanguageCode != "" {
		t.Fatalf("3.8 should auto-detect language, got %q", gotCfg.SpeechConfig.LanguageCode)
	}
	if !strings.Contains(resultText(res), "Prompt advisories") {
		t.Fatalf("expected advisories in result: %s", resultText(res))
	}
	if len(res.Content) != 2 {
		t.Fatalf("expected text + inline audio, got %d items", len(res.Content))
	}

	// Multi-speaker on 3.8.
	res = callTTS(t, map[string]any{
		"model_name": "gemini-3.8-flash-tts",
		"speakers":   []any{map[string]any{"name": "Joe", "voice": "Puck"}, map[string]any{"name": "Jane", "voice": "Kore"}},
		"turns":      []any{map[string]any{"speaker": "Joe", "text": "Hi."}, map[string]any{"speaker": "Jane", "text": "Hey.", "style": "dry"}},
	})
	if res.IsError || len(gotContents[0].Parts) != 2 {
		t.Fatalf("multi-speaker failed: %s", resultText(res))
	}

	// Errors that must not reach any API.
	gotModel = ""
	for name, args := range map[string]map[string]any{
		"library voice on 3.1": {"text": "Hi", "model_name": "gemini-3.1-flash-tts-preview", "voice_name": "en-au-podcaster-4"},
		"turns on 3.1":         {"model_name": "gemini-3.1-flash-tts-preview", "turns": []any{map[string]any{"speaker": "A", "text": "x"}}},
		"no text":              {"text": "  "},
		"3.1 over 800":         {"text": strings.Repeat("a", 801), "model_name": "gemini-2.5-flash-tts"},
		"3.8 over 4000":        {"text": strings.Repeat("a", 4001)},
		"mp3 on 3.8":           {"text": "Hi", "audio_encoding": "MP3"},
	} {
		if r := callTTS(t, args); !r.IsError {
			t.Errorf("%s: expected error, got %s", name, resultText(r))
		}
	}
	if gotModel != "" {
		t.Fatalf("validation errors must not call the API (called %s)", gotModel)
	}
}

func TestListVoicesAPI(t *testing.T) {
	var queries []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		queries = append(queries, r.URL.RawQuery)
		if r.Header.Get("X-Goog-User-Project") != "proj" {
			t.Errorf("missing quota project header")
		}
		if !strings.HasSuffix(r.URL.Path, "/v1beta1/projects/proj/locations/global/voices") {
			t.Errorf("bad path %s", r.URL.Path)
		}
		if r.URL.Query().Get("pageToken") == "" {
			_, _ = w.Write([]byte(`{"voices":[{"id":"en-au-a","language_code":"en-AU","accent":"Sydney English"},{"id":"fr-x","language_code":"fr-FR","accent":"Paris French"}],"next_page_token":"p2"}`))
			return
		}
		_, _ = w.Write([]byte(`{"voices":[{"id":"en-au-b","language_code":"en-AU","accent":"Sydney English","display_name":"B"}]}`))
	}))
	defer srv.Close()
	origURL, origClient := voicesAPIBaseURL, voicesHTTPClientFn
	t.Cleanup(func() { voicesAPIBaseURL, voicesHTTPClientFn = origURL, origClient })
	voicesAPIBaseURL = srv.URL
	voicesHTTPClientFn = func(context.Context) (*http.Client, error) { return srv.Client(), nil }

	got, err := listVoicesAPI(context.Background(), "proj", "host", []string{"prebuilt"}, "en", "sydney", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[0].ID != "en-au-a" || got[1].DisplayName != "B" {
		t.Fatalf("got %+v", got)
	}
	if !strings.Contains(queries[0], "search=host") || !strings.Contains(queries[0], "type=prebuilt") || !strings.Contains(queries[1], "pageToken=p2") {
		t.Fatalf("queries %v", queries)
	}

	// Handler path uses the API only when filters are present.
	appConfig = &common.Config{ProjectID: "proj"}
	t.Cleanup(func() { appConfig = nil })
	req := mcp.CallToolRequest{}
	req.Params.Arguments = map[string]any{"accent": "Sydney", "limit": float64(1)}
	res, _ := listGeminiVoicesHandler(context.Background(), req)
	if res.IsError || !strings.Contains(resultText(res), "en-au-a") || strings.Contains(resultText(res), "en-au-b") {
		t.Fatalf("handler result: %s", resultText(res))
	}
	req.Params.Arguments = map[string]any{}
	res, _ = listGeminiVoicesHandler(context.Background(), req)
	if !strings.Contains(resultText(res), "Callirrhoe") {
		t.Fatalf("no-arg call should list prebuilt voices: %s", resultText(res))
	}
}

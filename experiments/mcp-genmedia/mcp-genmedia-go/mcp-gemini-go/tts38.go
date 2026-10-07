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

// Gemini 3.8 TTS support (gemini-3.8-flash-tts, gemini-3.8-flash-lite-tts).
//
// The 3.8 models are NOT served by the Cloud Text-to-Speech API; they are only
// available through Vertex AI generateContent in the "global" location. They
// also use a different control model than <=3.1:
//   - parts[].text is a verbatim transcript (directions written into it may be
//     spoken aloud);
//   - sustained delivery goes in parts[].speechMetadata.style (short);
//   - point-in-time vocal events are inline <angle> tags (<sigh>, <short pause>);
//   - multi-speaker = one part per turn with speechMetadata.speaker, exactly 2
//     speakers;
//   - voiceConfig.voice accepts prebuilt names, Extended Voice Library IDs and
//     designed/replicated voice IDs (voice_..., voicekey_...);
//   - unary responses are a complete WAV file by default.

import (
	"bytes"
	"context"
	"encoding/binary"
	"fmt"
	"log"
	"regexp"
	"strings"
	"sync"
	"time"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
	"google.golang.org/genai"
)

const (
	tts38Location = "global"
	// maxTextCharsLegacy is the historical Cloud TTS guard for <=3.1 models.
	maxTextCharsLegacy = 800
	// maxTextChars38 bounds a single 3.8 request. The model accepts 8,192 input
	// tokens but emits at most 16,384 audio tokens (~5.5 minutes), and the tool
	// uses a 120 s unary timeout; ~4,000 characters keeps well inside both.
	maxTextChars38 = 4000
	// longStyleChars is the soft threshold above which a 3.8 style string is
	// flagged: the prompting guide recommends short styles and names long
	// Audio Profile / Director's Notes blocks as the main cause of voice drift.
	longStyleChars = 200
)

// geminiTTSModels lists every model accepted by gemini_audio_tts.
var geminiTTSModels = []string{
	"gemini-3.8-flash-lite-tts",
	"gemini-3.8-flash-tts",
	"gemini-3.1-flash-tts-preview",
	"gemini-2.5-flash-tts",
	"gemini-2.5-pro-tts",
	"gemini-2.5-flash-lite-preview-tts",
}

// isTTS38Model reports whether model uses the Gemini 3.8 TTS request format
// (Vertex generateContent, speechMetadata, global only).
func isTTS38Model(model string) bool {
	m := strings.ToLower(strings.TrimSpace(model))
	return strings.HasPrefix(m, "gemini-3.8") && strings.Contains(m, "tts")
}

// ttsTurn is one dialogue turn for multi-speaker synthesis.
type ttsTurn struct {
	Speaker string
	Text    string
	Style   string
}

// ttsSpeaker maps a speaker name used in turns to a voice.
type ttsSpeaker struct {
	Name  string
	Voice string
}

// parseTTSTurns reads the optional "turns" argument: [{speaker, text, style?}].
func parseTTSTurns(args map[string]any) ([]ttsTurn, error) {
	raw, ok := args["turns"]
	if !ok || raw == nil {
		return nil, nil
	}
	items, ok := raw.([]any)
	if !ok {
		return nil, fmt.Errorf("turns must be an array of {speaker, text, style} objects")
	}
	turns := make([]ttsTurn, 0, len(items))
	for i, it := range items {
		m, ok := it.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("turns[%d] must be an object with speaker and text", i)
		}
		t := ttsTurn{}
		t.Speaker, _ = m["speaker"].(string)
		t.Text, _ = m["text"].(string)
		t.Style, _ = m["style"].(string)
		if strings.TrimSpace(t.Speaker) == "" || strings.TrimSpace(t.Text) == "" {
			return nil, fmt.Errorf("turns[%d] requires non-empty speaker and text", i)
		}
		turns = append(turns, t)
	}
	return turns, nil
}

// parseTTSSpeakers reads the optional "speakers" argument: [{name, voice}].
func parseTTSSpeakers(args map[string]any) ([]ttsSpeaker, error) {
	raw, ok := args["speakers"]
	if !ok || raw == nil {
		return nil, nil
	}
	items, ok := raw.([]any)
	if !ok {
		return nil, fmt.Errorf("speakers must be an array of {name, voice} objects")
	}
	out := make([]ttsSpeaker, 0, len(items))
	for i, it := range items {
		m, ok := it.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("speakers[%d] must be an object with name and voice", i)
		}
		s := ttsSpeaker{}
		s.Name, _ = m["name"].(string)
		s.Voice, _ = m["voice"].(string)
		if strings.TrimSpace(s.Name) == "" || strings.TrimSpace(s.Voice) == "" {
			return nil, fmt.Errorf("speakers[%d] requires non-empty name and voice", i)
		}
		out = append(out, s)
	}
	return out, nil
}

// tts38ResponseFormat maps the tool's audio_encoding to a 3.8 responseFormat
// mimeType. LINEAR16 (WAV) is the unary default, so it returns "".
func tts38ResponseFormat(encoding string) (string, error) {
	switch strings.ToUpper(encoding) {
	case "", "LINEAR16":
		return "", nil
	case "PCM":
		return "AUDIO_L16", nil
	case "MULAW":
		return "AUDIO_MULAW", nil
	case "ALAW":
		return "AUDIO_ALAW", nil
	default:
		return "", fmt.Errorf("audio_encoding %s is not supported by Gemini 3.8 TTS (supported: LINEAR16, PCM, MULAW, ALAW); request LINEAR16 and convert with the avtool server (e.g. ffmpeg_convert_audio_wav_to_mp3)", encoding)
	}
}

// buildTTS38Request builds the generateContent contents and config for a 3.8
// TTS model. Either text (single speaker, optional style) or turns+speakers
// (exactly two speakers) must be provided.
func buildTTS38Request(text, style, voice, languageCode, encoding string, turns []ttsTurn, speakers []ttsSpeaker) ([]*genai.Content, *genai.GenerateContentConfig, error) {
	speech := &genai.SpeechConfig{LanguageCode: languageCode}
	var parts []*genai.Part

	if len(turns) > 0 {
		if len(speakers) != 2 {
			return nil, nil, fmt.Errorf("multi-speaker synthesis requires exactly 2 entries in speakers (got %d); for more speakers synthesize each turn separately and concatenate", len(speakers))
		}
		known := map[string]bool{}
		svc := make([]*genai.SpeakerVoiceConfig, 0, 2)
		for _, s := range speakers {
			if known[s.Name] {
				return nil, nil, fmt.Errorf("duplicate speaker name %q", s.Name)
			}
			known[s.Name] = true
			svc = append(svc, &genai.SpeakerVoiceConfig{Speaker: s.Name, VoiceConfig: &genai.VoiceConfig{Voice: s.Voice}})
		}
		for i, t := range turns {
			if !known[t.Speaker] {
				return nil, nil, fmt.Errorf("turns[%d].speaker %q is not one of the configured speakers", i, t.Speaker)
			}
			parts = append(parts, &genai.Part{Text: t.Text, SpeechMetadata: &genai.SpeechMetadata{Speaker: t.Speaker, Style: strings.TrimSpace(t.Style)}})
		}
		speech.MultiSpeakerVoiceConfig = &genai.MultiSpeakerVoiceConfig{SpeakerVoiceConfigs: svc}
	} else {
		if strings.TrimSpace(text) == "" {
			return nil, nil, fmt.Errorf("text is required when turns are not provided")
		}
		p := &genai.Part{Text: text}
		if s := strings.TrimSpace(style); s != "" {
			p.SpeechMetadata = &genai.SpeechMetadata{Style: s}
		}
		parts = []*genai.Part{p}
		speech.VoiceConfig = &genai.VoiceConfig{Voice: voice}
	}

	cfg := &genai.GenerateContentConfig{
		ResponseModalities: []string{"AUDIO"},
		SpeechConfig:       speech,
	}
	mime, err := tts38ResponseFormat(encoding)
	if err != nil {
		return nil, nil, err
	}
	if mime != "" {
		// GenerateContentConfig has no ResponseFormat field (only GenerationConfig
		// does), so send it through ExtraBody, which the SDK deep-merges into the
		// request body. This mirrors the documented Python http_options.extra_body.
		cfg.HTTPOptions = &genai.HTTPOptions{ExtraBody: map[string]any{
			"generationConfig": map[string]any{
				"responseFormat": []any{map[string]any{"audio": map[string]any{"mimeType": mime}}},
			},
		}}
	}
	return []*genai.Content{{Role: "user", Parts: parts}}, cfg, nil
}

// --- Prompt lint -----------------------------------------------------------

var (
	reSayTheFollowing = regexp.MustCompile(`(?i)\bsay (the following|this)\b[^:\n]{0,60}:`)
	reInstructions    = regexp.MustCompile(`(?i)^\s*(instructions:|#{1,4}\s*(audio profile|the scene|director'?s notes|transcript))`)
	reTakeMarker      = regexp.MustCompile(`(?im)^\s*take\s+(\d+|one|two|three)\b`)
	reSpeakerPrefix   = regexp.MustCompile(`(?m)^\s*[A-Z][\w .'-]{0,24}:\s+\S`)
	reSquareTag       = regexp.MustCompile(`\[([a-zA-Z][a-zA-Z \-]{1,30})\]`)
	reAngleTag        = regexp.MustCompile(`<([a-zA-Z][a-zA-Z \-]{1,30})>`)
	reAngleWhisper    = regexp.MustCompile(`(?i)<\s*whisper(s|ing)\s*>`)
)

// lintTTSSpeakers flags custom voices in two-speaker requests. The API accepts
// them, but the docs recommend synthesizing designed/replicated voices one
// turn at a time and concatenating.
func lintTTSSpeakers(speakers []ttsSpeaker) []string {
	for _, s := range speakers {
		v := strings.ToLower(s.Voice)
		if strings.HasPrefix(v, "voice_") || strings.HasPrefix(v, "voicekey_") {
			return []string{"speakers use a designed/replicated voice; the request works, but the docs recommend synthesizing each custom-voice turn separately and concatenating the audio for best identity stability."}
		}
	}
	return nil
}

// tts38VocalTags is the documented Gemini 3.8 inline vocal-tag vocabulary.
var tts38VocalTags = map[string]bool{
	"argh": true, "breath": true, "heavy breath": true, "exhales": true, "cackle": true, "cheer": true,
	"chuckle": true, "chuckles": true, "cough": true, "cry": true, "gasp": true, "giggle": true,
	"groan": true, "growl": true, "grunt": true, "grr": true, "hiss": true, "laugh": true, "laughter": true,
	"moan": true, "pant": true, "pff": true, "phew": true, "scream": true, "shout": true, "shriek": true,
	"sigh": true, "sighs": true, "sneeze": true, "snicker": true, "snort": true, "sob": true,
	"throat-clearing": true, "tsk": true, "whimper": true, "whispers": true, "whispering": true,
	"yawn": true, "short pause": true, "long pause": true,
}

// legacyStyleTags are <=3.1 square-bracket tags that describe sustained
// delivery. On 3.8 they belong in style; written inline they can be spoken
// aloud (e.g. "[whispering]" was read as a word in testing).
var legacyStyleTags = map[string]string{
	"whispering": "whispering", "whispers": "whispering", "shouting": "shouting", "robotic": "robotic, monotone",
	"extremely fast": "speaking rapidly", "fast": "speaking rapidly", "slow": "speaking slowly",
	"sarcasm": "sarcastic", "sarcastic": "sarcastic",
}

// lintTTSInput returns advisory warnings for prompt patterns that behave
// differently on the selected model family. It never mutates the input.
func lintTTSInput(model, text, style string, turns []ttsTurn) []string {
	var w []string
	texts := []string{text}
	for _, t := range turns {
		texts = append(texts, t.Text)
	}
	all := strings.Join(texts, "\n")

	if isTTS38Model(model) {
		if reSayTheFollowing.MatchString(all) {
			w = append(w, `text contains a "Say the following ...:" preamble; 3.8 reads text verbatim and may speak it. Move the direction to prompt (style).`)
		}
		if reInstructions.MatchString(all) {
			w = append(w, "text starts with INSTRUCTIONS / Audio Profile / Director's Notes headings; on 3.8 put only the transcript in text and a short delivery direction in prompt.")
		}
		if reTakeMarker.MatchString(all) {
			w = append(w, `text contains "Take N" markers; 3.8 speaks them. For multiple takes make separate calls, each with its own prompt (style).`)
		}
		if len(turns) == 0 && reSpeakerPrefix.MatchString(text) && strings.Count(text, "\n") > 0 {
			w = append(w, `text looks like "Name: line" dialogue; 3.8 may speak the names. Use turns + speakers instead.`)
		}
		var styleish, unknownAngle []string
		square := false
		for _, m := range reSquareTag.FindAllStringSubmatch(all, -1) {
			tag := strings.ToLower(strings.TrimSpace(m[1]))
			square = true
			if s, ok := legacyStyleTags[tag]; ok {
				styleish = append(styleish, fmt.Sprintf("[%s] -> style %q", tag, s))
			}
		}
		if square {
			w = append(w, "text uses [square] tags; 3.8 prefers <angle> vocal tags such as <sigh>, <laugh>, <short pause>.")
		}
		if len(styleish) > 0 {
			w = append(w, "inline delivery tags may be spoken aloud on 3.8; move them to prompt: "+strings.Join(styleish, ", "))
		}
		for _, m := range reAngleTag.FindAllStringSubmatch(all, -1) {
			tag := strings.ToLower(strings.TrimSpace(m[1]))
			if !tts38VocalTags[tag] {
				unknownAngle = append(unknownAngle, "<"+tag+">")
			}
		}
		// <whispers>/<whispering> are in the documented list, but a live probe
		// heard the word "whispering" spoken in 2 of 3 runs. Prefer style.
		if reAngleWhisper.MatchString(all) {
			w = append(w, `<whispering>/<whispers> inline was sometimes spoken as a word in testing; for a whispered delivery set prompt (style) to "whispering" and split the turn where it starts.`)
		}
		if len(unknownAngle) > 0 {
			w = append(w, "undocumented 3.8 tags "+strings.Join(unknownAngle, ", ")+"; use human vocal sounds and <short pause>/<long pause> inline, and put emotions in prompt (style).")
		}
		styles := []string{style}
		for _, t := range turns {
			styles = append(styles, t.Style)
		}
		for _, s := range styles {
			if len(s) > longStyleChars {
				w = append(w, fmt.Sprintf("style is %d characters; 3.8 works best with short styles (e.g. \"warm, unhurried\"). Put permanent traits (age, accent, timbre) in the voice (library voice or Voice design) instead.", len(s)))
				break
			}
		}
	} else {
		if reAngleTag.MatchString(all) && !reSquareTag.MatchString(all) {
			w = append(w, "text uses <angle> tags; <=3.1 models document [square] tags (e.g. [sigh], [short pause]).")
		}
	}
	return w
}

// --- Client + call -----------------------------------------------------------

var (
	tts38ClientOnce sync.Once
	tts38Client     *genai.Client
	tts38ClientErr  error
)

// getTTS38Client returns a GenAI client pinned to the global location. 3.8 TTS
// is global-only, so it must not inherit a regional LOCATION configured for
// other tools on this server.
func getTTS38Client(ctx context.Context) (*genai.Client, error) {
	tts38ClientOnce.Do(func() {
		cfg := &genai.ClientConfig{Backend: genai.BackendVertexAI, Project: appConfig.ProjectID, Location: tts38Location}
		if appConfig.ApiEndpoint != "" {
			cfg.HTTPOptions.BaseURL = appConfig.ApiEndpoint
		}
		if err := common.InjectCaptureHeaders(ctx, appConfig, cfg); err != nil {
			log.Printf("Warning: Failed to inject capture headers for TTS client: %v", err)
		}
		tts38Client, tts38ClientErr = genai.NewClient(ctx, cfg)
	})
	return tts38Client, tts38ClientErr
}

// generateTTS38Fn is the generateContent seam (replaced in tests).
var generateTTS38Fn = func(ctx context.Context, model string, contents []*genai.Content, cfg *genai.GenerateContentConfig) (*genai.GenerateContentResponse, error) {
	client, err := getTTS38Client(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to create global GenAI client: %w", err)
	}
	return client.Models.GenerateContent(ctx, model, contents, cfg)
}

// callGeminiTTS38 synthesizes speech with a 3.8 model and returns audio bytes
// and their MIME type.
func callGeminiTTS38(model string, contents []*genai.Content, cfg *genai.GenerateContentConfig) ([]byte, string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()
	resp, err := generateTTS38Fn(ctx, model, contents, cfg)
	if err != nil {
		return nil, "", fmt.Errorf("generateContent failed: %w", err)
	}
	return extractTTS38Audio(resp)
}

// extractTTS38Audio pulls the audio from a generateContent response. Multiple
// WAV parts are merged into a single WAV.
func extractTTS38Audio(resp *genai.GenerateContentResponse) ([]byte, string, error) {
	if resp == nil || len(resp.Candidates) == 0 || resp.Candidates[0].Content == nil {
		reason := ""
		if resp != nil && resp.PromptFeedback != nil {
			reason = fmt.Sprintf(" (block reason: %s)", resp.PromptFeedback.BlockReason)
		}
		return nil, "", fmt.Errorf("model returned no audio%s", reason)
	}
	var chunks [][]byte
	mime := ""
	for _, p := range resp.Candidates[0].Content.Parts {
		if p.InlineData != nil && len(p.InlineData.Data) > 0 {
			chunks = append(chunks, p.InlineData.Data)
			if mime == "" {
				mime = p.InlineData.MIMEType
			}
		}
	}
	if len(chunks) == 0 {
		return nil, "", fmt.Errorf("model returned no audio (finish reason: %s)", resp.Candidates[0].FinishReason)
	}
	if len(chunks) == 1 {
		return chunks[0], mime, nil
	}
	if isWAV(chunks[0]) {
		var pcm []byte
		for _, c := range chunks {
			pcm = append(pcm, stripWAVHeader(c)...)
		}
		return pcmToWAV(pcm, 24000, 1), "audio/wav", nil
	}
	return bytes.Join(chunks, nil), mime, nil
}

func isWAV(b []byte) bool {
	return len(b) >= 44 && string(b[0:4]) == "RIFF" && string(b[8:12]) == "WAVE"
}

// stripWAVHeader returns the PCM payload of a RIFF/WAVE file by locating the
// "data" chunk (falls back to a 44-byte header).
func stripWAVHeader(b []byte) []byte {
	if !isWAV(b) {
		return b
	}
	for i := 12; i+8 <= len(b); {
		id := string(b[i : i+4])
		size := int(binary.LittleEndian.Uint32(b[i+4 : i+8]))
		if id == "data" {
			end := i + 8 + size
			if end > len(b) || size == 0 {
				end = len(b)
			}
			return b[i+8 : end]
		}
		i += 8 + size + size%2
	}
	return b[44:]
}

// pcmToWAV wraps 16-bit little-endian PCM in a RIFF/WAVE header.
func pcmToWAV(pcm []byte, rate, channels int) []byte {
	var buf bytes.Buffer
	byteRate := rate * channels * 2
	buf.WriteString("RIFF")
	_ = binary.Write(&buf, binary.LittleEndian, uint32(36+len(pcm)))
	buf.WriteString("WAVEfmt ")
	_ = binary.Write(&buf, binary.LittleEndian, uint32(16))
	_ = binary.Write(&buf, binary.LittleEndian, uint16(1))
	_ = binary.Write(&buf, binary.LittleEndian, uint16(channels))
	_ = binary.Write(&buf, binary.LittleEndian, uint32(rate))
	_ = binary.Write(&buf, binary.LittleEndian, uint32(byteRate))
	_ = binary.Write(&buf, binary.LittleEndian, uint16(channels*2))
	_ = binary.Write(&buf, binary.LittleEndian, uint16(16))
	buf.WriteString("data")
	_ = binary.Write(&buf, binary.LittleEndian, uint32(len(pcm)))
	buf.Write(pcm)
	return buf.Bytes()
}

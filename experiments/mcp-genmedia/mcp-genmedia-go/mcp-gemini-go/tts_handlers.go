// Package main implements an MCP server for Google's Gemini models.

package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	texttospeech "cloud.google.com/go/texttospeech/apiv1"
	"cloud.google.com/go/texttospeech/apiv1/texttospeechpb"
	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
	"github.com/mark3labs/mcp-go/mcp"
)

// resolveGeminiTTSFilename decides the saved audio filename. The canonical
// output_filename wins over the deprecated output_filename_prefix (design §4a):
// when set, it yields a client-predictable base name with the extension forced to
// the true audio MIME for the selected encoding (design §4b) — a single artifact
// is used as-is (<stem>.<ext>), multiple would be suffixed _1..n by the shared
// helper. When only the legacy prefix (or neither) is provided, the historical
// <prefix>-<voice>-<timestamp><ext> scheme is preserved byte-for-byte.
func resolveGeminiTTSFilename(args map[string]any, voiceName, legacyExt, mimeType string) (string, error) {
	if base := common.ResolveOutputFilename(args); base != "" {
		names, err := common.BuildOutputFilenames(base, 1, mimeType)
		if err != nil {
			return "", err
		}
		return names[0], nil
	}
	prefix, _ := args["output_filename_prefix"].(string)
	if prefix == "" {
		prefix = "gemini_tts_audio"
	}
	return fmt.Sprintf("%s-%s-%s%s", prefix, voiceName, time.Now().Format(timeFormatForTTSFilename), legacyExt), nil
}

// saveGeminiTTSAudio wires the resolved output_filename through to the local file
// write: it resolves the client-predictable name (output_filename wins over the
// legacy output_filename_prefix; extension forced to the true audio MIME — §4a/§4b),
// joins it under outputDir, applies the collision-overwrite warning (§4e), and
// writes the bytes through the injectable writeFileFn seam. It returns the full
// saved path. A name-resolution failure is returned as nameErr (fatal to the
// caller); a write failure as writeErr (the caller falls back to returning the
// audio inline). Splitting the two errors mirrors the handler's original behavior.
func saveGeminiTTSAudio(args map[string]any, audioBytes []byte, outputDir, voiceName, legacyExt, mimeType string) (savedFilename string, nameErr, writeErr error) {
	filename, err := resolveGeminiTTSFilename(args, voiceName, legacyExt, mimeType)
	if err != nil {
		return "", err, nil
	}
	// Confine the caller-supplied output directory to the configured output root
	// before creating it or writing into it (CWE-22 directory traversal). A
	// traversal attempt (absolute path or "..") is fatal (nameErr); a directory
	// creation failure is non-fatal (writeErr) so the caller falls back to inline.
	confinedDir, confErr := common.ResolveConfinedOutputDir(outputDir)
	if confErr != nil {
		return "", confErr, nil
	}
	if mkErr := os.MkdirAll(confinedDir, 0755); mkErr != nil {
		return "", nil, mkErr
	}
	savedFilename = filepath.Join(confinedDir, filename)
	// Collision policy: overwrite with a warning (design §4e).
	if _, statErr := os.Stat(savedFilename); statErr == nil {
		log.Printf("Warning: output file %q already exists in %s; overwriting (collision policy).", filename, outputDir)
	}
	if werr := writeFileFn(savedFilename, audioBytes, 0644); werr != nil {
		return savedFilename, nil, werr
	}
	return savedFilename, nil, nil
}

const (
	// defaultGeminiTTSModel is the documented replacement for
	// gemini-3.1-flash-tts-preview. <=3.1 models remain selectable and still use
	// the Cloud Text-to-Speech API.
	defaultGeminiTTSModel    = "gemini-3.8-flash-lite-tts"
	defaultGeminiTTSVoice    = "Callirrhoe"
	timeFormatForTTSFilename = "20060102-150405"
)

// availableGeminiVoices are the 30 prebuilt voices shared by every Gemini TTS
// model. Gemini 3.8 models additionally accept Extended Voice Library IDs and
// designed/replicated voice IDs (voice_..., voicekey_...).
var availableGeminiVoices = []string{
	"Achernar",
	"Achird",
	"Algenib",
	"Algieba",
	"Alnilam",
	"Aoede",
	"Autonoe",
	"Callirrhoe",
	"Charon",
	"Despina",
	"Enceladus",
	"Erinome",
	"Fenrir",
	"Gacrux",
	"Iapetus",
	"Kore",
	"Laomedeia",
	"Leda",
	"Orus",
	"Pulcherrima",
	"Puck",
	"Rasalgethi",
	"Sadachbia",
	"Sadaltager",
	"Schedar",
	"Sulafat",
	"Umbriel",
	"Vindemiatrix",
	"Zephyr",
	"Zubenelgenubi",
}

// geminiLanguageCodeMap holds the supported languages.
var geminiLanguageCodeMap = map[string]string{
	"arabic (egypt)":               "ar-EG",
	"dutch (netherlands)":          "nl-NL",
	"english (india)":              "en-IN",
	"english (united states)":      "en-US",
	"french (france)":              "fr-FR",
	"german (germany)":             "de-DE",
	"hindi (india)":                "hi-IN",
	"indonesian (indonesia)":       "id-ID",
	"italian (italy)":              "it-IT",
	"japanese (japan)":             "ja-JP",
	"korean (south korea)":         "ko-KR",
	"marathi (india)":              "mr-IN",
	"polish (poland)":              "pl-PL",
	"portuguese (brazil)":          "pt-BR",
	"romanian (romania)":           "ro-RO",
	"russian (russia)":             "ru-RU",
	"spanish (spain)":              "es-ES",
	"tamil (india)":                "ta-IN",
	"telugu (india)":               "te-IN",
	"thai (thailand)":              "th-TH",
	"turkish (turkey)":             "tr-TR",
	"ukrainian (ukraine)":          "uk-UA",
	"vietnamese (vietnam)":         "vi-VN",
	"afrikaans (south africa)":     "af-ZA",
	"albanian (albania)":           "sq-AL",
	"amharic (ethiopia)":           "am-ET",
	"arabic (world)":               "ar-001",
	"armenian (armenia)":           "hy-AM",
	"azerbaijani (azerbaijan)":     "az-AZ",
	"bangla (bangladesh)":          "bn-BD",
	"basque (spain)":               "eu-ES",
	"belarusian (belarus)":         "be-BY",
	"bulgarian (bulgaria)":         "bg-BG",
	"burmese (myanmar)":            "my-MM",
	"catalan (spain)":              "ca-ES",
	"cebuano (philippines)":        "ceb-PH",
	"chinese, mandarin (china)":    "cmn-CN",
	"chinese, mandarin (taiwan)":   "cmn-TW",
	"croatian (croatia)":           "hr-HR",
	"czech (czech republic)":       "cs-CZ",
	"danish (denmark)":             "da-DK",
	"english (australia)":          "en-AU",
	"english (united kingdom)":     "en-GB",
	"estonian (estonia)":           "et-EE",
	"filipino (philippines)":       "fil-PH",
	"finnish (finland)":            "fi-FI",
	"french (canada)":              "fr-CA",
	"galician (spain)":             "gl-ES",
	"georgian (georgia)":           "ka-GE",
	"greek (greece)":               "el-GR",
	"gujarati (india)":             "gu-IN",
	"haitian creole (haiti)":       "ht-HT",
	"hebrew (israel)":              "he-IL",
	"hungarian (hungary)":          "hu-HU",
	"icelandic (iceland)":          "is-IS",
	"javanese (java)":              "jv-JV",
	"kannada (india)":              "kn-IN",
	"konkani (india)":              "kok-IN",
	"lao (laos)":                   "lo-LA",
	"latin (vatican city)":         "la-VA",
	"latvian (latvia)":             "lv-LV",
	"lithuanian (lithuania)":       "lt-IT",
	"luxembourgish (luxembourg)":   "lb-LU",
	"macedonian (north macedonia)": "mk-MK",
	"maithili (india)":             "mai-IN",
	"malagasy (madagascar)":        "mg-MG",
	"malay (malaysia)":             "ms-MY",
	"malayalam (india)":            "ml-IN",
	"mongolian (mongolia)":         "mn-MN",
	"nepali (nepal)":               "ne-NP",
	"norwegian, bokmål (norway)":   "nb-NO",
	"norwegian, nynorsk (norway)":  "nn-NO",
	"odia (india)":                 "or-IN",
	"pashto (afghanistan)":         "ps-AF",
	"persian (iran)":               "fa-IR",
	"portuguese (portugal)":        "pt-PT",
	"punjabi (india)":              "pa-IN",
	"serbian (serbia)":             "sr-RS",
	"sindhi (india)":               "sd-IN",
	"sinhala (sri lanka)":          "si-LK",
	"slovak (slovakia)":            "sk-SK",
	"slovenian (slovenia)":         "sl-SI",
	"spanish (latin america)":      "es-419",
	"spanish (mexico)":             "es-MX",
	"swahili (kenya)":              "sw-KE",
	"swedish (sweden)":             "sv-SE",
	"urdu (pakistan)":              "ur-PK",
}

// --- Resource Handler ---

func geminiLanguageCodesHandler(ctx context.Context, request mcp.ReadResourceRequest) ([]mcp.ResourceContents, error) {
	jsonData, err := json.MarshalIndent(geminiLanguageCodeMap, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("failed to marshal language codes: %w", err)
	}
	return []mcp.ResourceContents{
		mcp.TextResourceContents{
			URI:      "gemini://language_codes",
			MIMEType: "application/json",
			Text:     string(jsonData),
		},
	}, nil
}

// --- Tool Handlers ---

// listGeminiVoicesHandler handles the 'list_gemini_voices' tool request.
// With no arguments it returns the 30 prebuilt voices (valid for every model).
// With search / language_code / accent / voice_types it queries the Voices API
// (Gemini 3.8: Extended Voice Library + project voices).
func listGeminiVoicesHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	log.Println("Handling list_gemini_voices request.")
	args := request.GetArguments()
	search, _ := args["search"].(string)
	language, _ := args["language_code"].(string)
	accent, _ := args["accent"].(string)
	var types []string
	if raw, ok := args["voice_types"].([]any); ok {
		for _, t := range raw {
			if s, ok := t.(string); ok && s != "" {
				types = append(types, s)
			}
		}
	}
	limit := 25
	if l, ok := args["limit"].(float64); ok && l > 0 {
		limit = int(l)
	}
	if search != "" || language != "" || accent != "" || len(types) > 0 {
		project := ""
		if appConfig != nil {
			project = appConfig.ProjectID
		}
		voices, err := listVoicesAPI(ctx, project, search, types, language, accent, limit)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("failed to query the Voices API: %v", err)), nil
		}
		b, err := json.MarshalIndent(voices, "", "  ")
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("failed to marshal voice list: %v", err)), nil
		}
		summary := fmt.Sprintf("Found %d voices from the Voices API. Pass a voice 'id' as voice_name with a Gemini 3.8 TTS model (gemini-3.8-flash-tts or gemini-3.8-flash-lite-tts). Library and project voices are not available on <=3.1 models.", len(voices))
		return &mcp.CallToolResult{Content: []mcp.Content{
			mcp.TextContent{Type: "text", Text: summary},
			mcp.TextContent{Type: "text", Text: string(b)},
		}}, nil
	}

	voiceListJSON, err := json.MarshalIndent(availableGeminiVoices, "", "  ")
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("failed to marshal voice list: %v", err)), nil
	}

	summary := fmt.Sprintf("Found %d prebuilt Gemini TTS voices (valid for all models). For Gemini 3.8 models, search the Extended Voice Library with the search, language_code or accent arguments.", len(availableGeminiVoices))

	return &mcp.CallToolResult{
		Content: []mcp.Content{
			mcp.TextContent{Type: "text", Text: summary},
			mcp.TextContent{Type: "text", Text: string(voiceListJSON)},
		},
	}, nil
}

var audioEncodingToFileExtension = map[string]string{
	"LINEAR16": ".wav",
	"MP3":      ".mp3",
	"OGG_OPUS": ".ogg",
	"MULAW":    ".mulaw",
	"ALAW":     ".alaw",
	"PCM":      ".pcm",
	"M4A":      ".m4a",
}

var audioEncodingToMIMEType = map[string]string{
	"LINEAR16": "audio/wav",
	"MP3":      "audio/mpeg",
	"OGG_OPUS": "audio/ogg",
	"MULAW":    "audio/mulaw",
	"ALAW":     "audio/alaw",
	"PCM":      "audio/pcm",
	"M4A":      "audio/mp4",
}

// geminiAudioTTSHandler handles the 'gemini_audio_tts' tool request.
func geminiAudioTTSHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	log.Printf("Handling gemini_audio_tts request with arguments: %v", request.GetArguments())

	// --- 1. Parse and Validate Arguments ---
	args := request.GetArguments()
	text, _ := args["text"].(string)
	prompt, _ := args["prompt"].(string)

	modelName, _ := args["model_name"].(string)
	if modelName == "" {
		modelName = defaultGeminiTTSModel
	}
	is38 := isTTS38Model(modelName)

	turns, err := parseTTSTurns(args)
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}
	speakers, err := parseTTSSpeakers(args)
	if err != nil {
		return mcp.NewToolResultError(err.Error()), nil
	}
	if len(turns) > 0 && !is38 {
		return mcp.NewToolResultError(fmt.Sprintf("turns/speakers (multi-speaker) are supported only with Gemini 3.8 TTS models; %s is not one", modelName)), nil
	}
	if len(turns) == 0 && strings.TrimSpace(text) == "" {
		return mcp.NewToolResultError("text parameter must be a non-empty string and is required (or provide turns + speakers with a Gemini 3.8 model)"), nil
	}
	totalChars := len(text)
	for _, t := range turns {
		totalChars += len(t.Text)
	}
	maxChars := maxTextCharsLegacy
	if is38 {
		maxChars = maxTextChars38
	}
	if totalChars > maxChars {
		return mcp.NewToolResultError(fmt.Sprintf("text cannot exceed %d characters for %s (got %d); split it into segments and concatenate the audio", maxChars, modelName, totalChars)), nil
	}

	voiceName, _ := args["voice_name"].(string)
	if voiceName == "" {
		voiceName = defaultGeminiTTSVoice
	}
	// <=3.1 models accept only the 30 prebuilt voices; 3.8 also accepts
	// Extended Voice Library IDs and designed/replicated voice IDs.
	validVoice := is38
	for _, v := range availableGeminiVoices {
		if v == voiceName {
			validVoice = true
			break
		}
	}
	if !validVoice {
		return mcp.NewToolResultError(fmt.Sprintf("invalid voice_name '%s' for %s. Use 'list_gemini_voices' to see available voices (library and custom voice IDs require a Gemini 3.8 model)", voiceName, modelName)), nil
	}

	// 3.8 detects the language automatically; only send a code when asked.
	languageCode, _ := args["language_code"].(string)
	if languageCode == "" && !is38 {
		languageCode = "en-US"
	}

	audioEncoding, _ := args["audio_encoding"].(string)
	if audioEncoding == "" {
		audioEncoding = "LINEAR16"
	}

	outputDir, _ := args["output_directory"].(string)

	warnings := lintTTSInput(modelName, text, prompt, turns)
	if len(turns) > 0 {
		warnings = append(warnings, lintTTSSpeakers(speakers)...)
	}

	// --- 2. Call the TTS API ---
	var audioBytes []byte
	if is38 {
		contents, cfg, berr := buildTTS38Request(text, prompt, voiceName, languageCode, audioEncoding, turns, speakers)
		if berr != nil {
			return mcp.NewToolResultError(berr.Error()), nil
		}
		var gotMIME string
		audioBytes, gotMIME, err = callGeminiTTS38(modelName, contents, cfg)
		if err == nil && audioEncoding == "LINEAR16" && strings.HasPrefix(strings.ToLower(gotMIME), "audio/l16") {
			audioBytes = pcmToWAV(audioBytes, 24000, 1)
		}
		if len(speakers) > 0 && len(turns) > 0 {
			voiceName = speakers[0].Voice + "+" + speakers[1].Voice
		}
	} else {
		audioBytes, err = callGeminiTTSAPI(ctx, text, prompt, voiceName, modelName, audioEncoding, languageCode)
	}
	if err != nil {
		return mcp.NewToolResultError(fmt.Sprintf("error calling Gemini TTS API: %v", err)), nil
	}

	// --- 3. Process the Audio Response ---
	var contentItems []mcp.Content
	var fileSaveMessage string

	fileExtension, ok := audioEncodingToFileExtension[audioEncoding]
	if !ok {
		fileExtension = ".wav"
	}
	mimeType, ok := audioEncodingToMIMEType[audioEncoding]
	if !ok {
		mimeType = "audio/wav"
	}

	if outputDir != "" {
		// Directory confinement + creation now happen inside saveGeminiTTSAudio so
		// the caller-supplied directory is validated before any filesystem write.
		savedFilename, nameErr, writeErr := saveGeminiTTSAudio(args, audioBytes, outputDir, safeFilenamePart(voiceName), fileExtension, mimeType)
		if nameErr != nil {
			return mcp.NewToolResultError(nameErr.Error()), nil
		}
		if writeErr != nil {
			fileSaveMessage = fmt.Sprintf("Error writing audio file %s: %v. Audio data will be returned in response instead.", savedFilename, writeErr)
			log.Print(fileSaveMessage)
			base64AudioData := base64.StdEncoding.EncodeToString(audioBytes)
			contentItems = append(contentItems, mcp.AudioContent{Type: "audio", Data: base64AudioData, MIMEType: mimeType})
		} else {
			fileSaveMessage = fmt.Sprintf("Audio saved to: %s (%d bytes).", savedFilename, len(audioBytes))
			log.Print(fileSaveMessage)
		}
	} else {
		base64AudioData := base64.StdEncoding.EncodeToString(audioBytes)
		contentItems = append(contentItems, mcp.AudioContent{Type: "audio", Data: base64AudioData, MIMEType: mimeType})
		fileSaveMessage = "Audio data is included in the response."
	}

	resultText := fmt.Sprintf("Speech synthesized successfully with voice %s (model %s). %s", voiceName, modelName, fileSaveMessage)
	if len(warnings) > 0 {
		resultText += "\nPrompt advisories:\n- " + strings.Join(warnings, "\n- ")
	}
	contentItems = append([]mcp.Content{mcp.TextContent{Type: "text", Text: resultText}}, contentItems...)

	return &mcp.CallToolResult{Content: contentItems}, nil
}

// safeFilenamePart keeps voice IDs (which may contain '/', ':' or be very long
// for replication keys) safe for the legacy <prefix>-<voice>-<ts> filename.
func safeFilenamePart(s string) string {
	var b strings.Builder
	for _, r := range s {
		switch {
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9', r == '-', r == '_', r == '+':
			b.WriteRune(r)
		default:
			b.WriteRune('_')
		}
		if b.Len() >= 48 {
			break
		}
	}
	if b.Len() == 0 {
		return "voice"
	}
	return b.String()
}

// --- API Helper Function ---

func callGeminiTTSAPI(ctx context.Context, text, stylePrompt, voiceName, modelName, audioEncoding, languageCode string) ([]byte, error) {
	// Detach from parent context to avoid inherited short timeouts from the server/client
	ttsCtx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()

	client, err := texttospeech.NewClient(ttsCtx)
	if err != nil {
		return nil, fmt.Errorf("failed to create texttospeech client: %w", err)
	}
	defer func() { _ = client.Close() }()

	req := &texttospeechpb.SynthesizeSpeechRequest{
		Input: &texttospeechpb.SynthesisInput{
			InputSource: &texttospeechpb.SynthesisInput_Text{Text: text},
		},
		Voice: &texttospeechpb.VoiceSelectionParams{
			LanguageCode: languageCode,
			Name:         voiceName,
			ModelName:    modelName,
		},
		AudioConfig: &texttospeechpb.AudioConfig{
			AudioEncoding: texttospeechpb.AudioEncoding(texttospeechpb.AudioEncoding_value[audioEncoding]),
		},
	}

	if stylePrompt != "" {
		req.Input.Prompt = &stylePrompt
	}

	resp, err := client.SynthesizeSpeech(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("failed to synthesize speech: %w", err)
	}

	return resp.AudioContent, nil
}

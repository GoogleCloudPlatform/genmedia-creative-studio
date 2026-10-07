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

// Voices API (v1beta1, global) listing for Gemini 3.8 TTS: the 30 prebuilt
// voices, the Extended Voice Library (~2,000 voices with accent/persona
// metadata) and voices designed or replicated in the project. The Go GenAI SDK
// has no Voices surface, so this is a small REST client.

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"golang.org/x/oauth2/google"
)

// voicesAPIBaseURL is overridable in tests.
var voicesAPIBaseURL = "https://aiplatform.googleapis.com"

// voicesHTTPClientFn returns an authenticated HTTP client (seam for tests).
var voicesHTTPClientFn = func(ctx context.Context) (*http.Client, error) {
	return google.DefaultClient(ctx, "https://www.googleapis.com/auth/cloud-platform")
}

// libraryVoice is one entry from voices.list. The API responds in snake_case.
type libraryVoice struct {
	ID           string `json:"id"`
	Type         string `json:"type,omitempty"`
	DisplayName  string `json:"display_name,omitempty"`
	LanguageCode string `json:"language_code,omitempty"`
	Accent       string `json:"accent,omitempty"`
	Gender       string `json:"gender,omitempty"`
	Pitch        string `json:"pitch,omitempty"`
	Persona      string `json:"persona,omitempty"`
	Description  string `json:"description,omitempty"`
}

type voicesListResponse struct {
	Voices        []libraryVoice `json:"voices"`
	NextPageToken string         `json:"next_page_token"`
	NextPageCamel string         `json:"nextPageToken"`
}

// listVoicesAPI pages through voices.list. search is sent to the API (it
// matches display name and description, not accent); language and accent are
// filtered client-side because the API rejects those filters. At most limit
// voices are returned.
func listVoicesAPI(ctx context.Context, project, search string, types []string, language, accent string, limit int) ([]libraryVoice, error) {
	if limit <= 0 {
		limit = 50
	}
	ctx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	client, err := voicesHTTPClientFn(ctx)
	if err != nil {
		return nil, fmt.Errorf("auth: %w", err)
	}
	language = strings.ToLower(strings.TrimSpace(language))
	accent = strings.ToLower(strings.TrimSpace(accent))
	endpoint := fmt.Sprintf("%s/v1beta1/projects/%s/locations/global/voices", voicesAPIBaseURL, url.PathEscape(project))

	var out []libraryVoice
	token := ""
	for page := 0; page < 60; page++ {
		q := url.Values{}
		q.Set("pageSize", "50")
		if search != "" {
			q.Set("search", search)
		}
		for _, t := range types {
			q.Add("type", t)
		}
		if token != "" {
			q.Set("pageToken", token)
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint+"?"+q.Encode(), nil)
		if err != nil {
			return nil, err
		}
		// User ADC credentials need a quota project for the Voices API.
		req.Header.Set("X-Goog-User-Project", project)
		resp, err := client.Do(req)
		if err != nil {
			return nil, err
		}
		body, _ := io.ReadAll(resp.Body)
		_ = resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return nil, fmt.Errorf("voices.list HTTP %d: %s", resp.StatusCode, truncate(string(body), 300))
		}
		var lr voicesListResponse
		if err := json.Unmarshal(body, &lr); err != nil {
			return nil, fmt.Errorf("decode voices.list: %w", err)
		}
		for _, v := range lr.Voices {
			if language != "" && !strings.HasPrefix(strings.ToLower(v.LanguageCode), language) {
				continue
			}
			if accent != "" && !strings.Contains(strings.ToLower(v.Accent), accent) {
				continue
			}
			out = append(out, v)
			if len(out) >= limit {
				return out, nil
			}
		}
		token = lr.NextPageToken
		if token == "" {
			token = lr.NextPageCamel
		}
		if token == "" {
			break
		}
	}
	return out, nil
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}

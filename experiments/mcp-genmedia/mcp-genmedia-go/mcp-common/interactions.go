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
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	interactions "github.com/ghchinoy/cloud-interactions-go"
	"golang.org/x/oauth2"
	"golang.org/x/oauth2/google"
)

// DefaultInteractionsAPIRevision is the Vertex Interactions API revision pinned by
// the suite. It localizes Pre-GA wire drift to a single constant and is sent
// via the "Api-Revision" header. It intentionally
// matches interactions.DefaultAPIRevision in the adopted client library; we set it
// explicitly so a future library default change cannot silently move our wire.
const DefaultInteractionsAPIRevision = "2026-05-20"

// interactionsScope is the OAuth scope required for Vertex AI calls.
const interactionsScope = "https://www.googleapis.com/auth/cloud-platform"

// interactionsRequestTimeout bounds a single synchronous interaction call. Omni
// video generation is observed at ~20-30s; the ceiling mirrors the library's own
// default and guards against a hung Pre-GA backend.
const interactionsRequestTimeout = 10 * time.Minute

// InteractionsClient is the small seam behind which the concrete Interactions API
// transport lives. Servers and GenerateOmniVideo depend on this interface and on
// the suite's own request/response types (below), never on the transport package,
// so the concrete implementation can be swapped later — from the currently adopted
// github.com/ghchinoy/cloud-interactions-go to the future official Go GenAI SDK
// Interactions surface — without touching callers.
type InteractionsClient interface {
	// Create performs a synchronous interaction POST to
	// .../locations/global/interactions and returns the decoded response.
	Create(ctx context.Context, req *InteractionRequest) (*InteractionResponse, error)
}

// InteractionRequest models the Vertex Interactions request envelope. It is
// deliberately minimal for the current phase (no generation_config / streaming /
// background); those fields are added when the wire is confirmed to accept them.
type InteractionRequest struct {
	Model string `json:"model"`
	// ResponseModalities MUST be lowercase on the live wire, e.g.
	// ["text","video"]. Callers are responsible for lowercasing.
	ResponseModalities []string    `json:"response_modalities,omitempty"`
	Input              []InputItem `json:"input"`
	Store              bool        `json:"store"`
	// GenerationConfig carries sampling controls (temperature/top_p). It is only
	// sent when non-nil; the Omni Interactions endpoint parses and validates these
	// (empirically confirmed: temperature is range-checked to [0.0, 2.0]).
	GenerationConfig *GenerationConfig `json:"generation_config,omitempty"`
}

// GenerationConfig models the subset of generation_config the suite sends. Fields
// are pointers so an unset value is omitted from the wire entirely (the endpoint
// rejects unknown fields, so we only send what it accepts — e.g. candidate_count
// is deliberately NOT modeled because the endpoint rejects it, findings/p2a).
type GenerationConfig struct {
	Temperature *float32 `json:"temperature,omitempty"`
	TopP        *float32 `json:"top_p,omitempty"`
}

// InputItem is one entry in an interaction's input array. For Omni the shape is
// {type:"user_input", content:[Part...]}. Flat text inputs (type/text) are also
// supported for the Lyria-style input shape.
type InputItem struct {
	Type    string `json:"type"`
	Content []Part `json:"content,omitempty"`
	Text    string `json:"text,omitempty"`
}

// Part is a single content part in an input or output. It carries either text or
// media (base64 data or a gs:// URI).
type Part struct {
	Type     string `json:"type"`
	Text     string `json:"text,omitempty"`
	MimeType string `json:"mime_type,omitempty"`
	Data     string `json:"data,omitempty"`
	URI      string `json:"uri,omitempty"`
}

// InteractionResponse models the Vertex Interactions response in the suite's own
// vocabulary. It is populated by translating the adopted library's response type
// (fromLibResponse) and is tolerant of the observed live drift:
// results may arrive in steps[] (Omni) or outputs[] (Lyria).
type InteractionResponse struct {
	ID      string            `json:"id"`
	Object  string            `json:"object"`
	Status  string            `json:"status"`
	Role    string            `json:"role"`
	Steps   []Step            `json:"steps"`
	Outputs []Step            `json:"outputs"`
	Usage   *InteractionUsage `json:"usage,omitempty"`
	Error   *InteractionError `json:"error,omitempty"`

	// SherlogLink is populated from the x-goog-sherlog-link response header. It is
	// not part of the JSON body. Since cloud-interactions-go v0.2.0 the adopted
	// library surfaces this header on the non-streaming Create path
	// (interactions.InteractionResponse.SherlogLink), and fromLibResponse copies it
	// through, so it is populated on Create.
	SherlogLink string `json:"-"`
}

// Step is one entry in steps[]/outputs[]. For Omni it wraps nested content parts
// (type:"model_output", content:[Part...]) or a thought (type:"thought"). It also
// carries flat media fields so a Lyria-style flat outputs[] part
// ({type:"audio", mime_type, data}) is not silently dropped.
type Step struct {
	Type    string `json:"type"`
	Content []Part `json:"content,omitempty"`
	Text    string `json:"text,omitempty"`

	// Flat media fields (Lyria-style outputs[]).
	MimeType string `json:"mime_type,omitempty"`
	Data     string `json:"data,omitempty"`
}

// InteractionUsage models token usage; extra fields on the wire are ignored.
type InteractionUsage struct {
	TotalTokens        int `json:"total_tokens,omitempty"`
	InputTokens        int `json:"input_tokens,omitempty"`
	OutputTokens       int `json:"output_tokens,omitempty"`
	TotalThoughtTokens int `json:"total_thought_tokens,omitempty"`
}

// InteractionError models a structured error object if the API returns one.
type InteractionError struct {
	Code    int    `json:"code,omitempty"`
	Status  string `json:"status,omitempty"`
	Message string `json:"message,omitempty"`
}

// libInteractionsClient is the concrete transport, backed by the adopted
// github.com/ghchinoy/cloud-interactions-go client. It lives entirely behind the
// InteractionsClient seam: it translates the suite's request/response types to and
// from the library's types so callers never import the library directly.
type libInteractionsClient struct {
	inner *interactions.Client
}

// NewInteractionsClient builds an Interactions client from the suite Config,
// backed by the adopted client library. Auth is ADC (google.FindDefaultCredentials)
// wrapped in an auto-refreshing oauth2 *http.Client that is injected as the
// library's HTTPClient — the library then sets x-goog-user-project and the pinned
// Api-Revision header on every request. The location is hard-pinned to "global"
// because the Interactions models are global-only.
func NewInteractionsClient(ctx context.Context, cfg *Config) (InteractionsClient, error) {
	if cfg == nil {
		return nil, fmt.Errorf("interactions: nil config")
	}
	if cfg.ProjectID == "" {
		return nil, fmt.Errorf("interactions: ProjectID is required")
	}

	creds, err := google.FindDefaultCredentials(ctx, interactionsScope)
	if err != nil {
		return nil, fmt.Errorf("interactions: failed to get default credentials (is ADC configured?): %w", err)
	}

	endpoint := "aiplatform.googleapis.com"
	if cfg.ApiEndpoint != "" {
		endpoint = cfg.ApiEndpoint
	}
	baseURL := fmt.Sprintf("https://%s/v1beta1/projects/%s/locations/global/interactions", endpoint, cfg.ProjectID)

	// ADC -> oauth2 auto-refreshing http.Client, injected as the library transport.
	httpClient := oauth2.NewClient(ctx, creds.TokenSource)
	httpClient.Timeout = interactionsRequestTimeout

	client := interactions.NewClient(baseURL)
	client.HTTPClient = httpClient
	client.WithUserProject(cfg.ProjectID)
	// The library already defaults Api-Revision to 2026-05-20; pin it explicitly so
	// the load-bearing header is guaranteed regardless of a future library default.
	client.WithAPIRevision(DefaultInteractionsAPIRevision)

	return &libInteractionsClient{inner: client}, nil
}

// Create translates the request into the library's type, performs a synchronous
// interaction POST via the library, and translates the response back. Any 4xx/5xx
// body is surfaced verbatim by the library so preview-access / quota errors remain
// legible.
func (c *libInteractionsClient) Create(ctx context.Context, req *InteractionRequest) (*InteractionResponse, error) {
	libResp, err := c.inner.Create(ctx, toLibRequest(req))
	if err != nil {
		return nil, fmt.Errorf("interactions: create failed: %w", err)
	}

	resp := fromLibResponse(libResp)
	if resp.Error != nil && resp.Error.Message != "" {
		return resp, fmt.Errorf("interactions API returned error: %s", resp.Error.Message)
	}
	log.Printf("Interactions API call completed: status=%q steps=%d outputs=%d", resp.Status, len(resp.Steps), len(resp.Outputs))
	return resp, nil
}

// toLibRequest translates the suite's InteractionRequest into the library's type.
// The Input is rendered as []interactions.Content (the shape the API expects for
// structured multi-part input), and Store is sent explicitly (including false).
func toLibRequest(req *InteractionRequest) *interactions.InteractionRequest {
	contents := make([]interactions.Content, 0, len(req.Input))
	for _, in := range req.Input {
		c := interactions.Content{Type: in.Type, Text: in.Text}
		for _, p := range in.Content {
			c.Content = append(c.Content, interactions.Part{
				Type:     p.Type,
				Text:     p.Text,
				MimeType: p.MimeType,
				Data:     p.Data,
				URI:      p.URI,
			})
		}
		contents = append(contents, c)
	}

	store := req.Store
	libReq := &interactions.InteractionRequest{
		Model:              req.Model,
		ResponseModalities: req.ResponseModalities,
		Input:              contents,
		Store:              &store,
	}
	if req.GenerationConfig != nil {
		libReq.GenerationConfig = &interactions.GenerationConfig{
			Temperature: req.GenerationConfig.Temperature,
			TopP:        req.GenerationConfig.TopP,
		}
	}
	return libReq
}

// fromLibResponse translates the library's response type into the suite's own
// InteractionResponse. It tolerates the observed live drift: results may arrive in
// steps[] or outputs[]. The library drops the wire's created/updated timestamps
// (it expects create_time/update_time) — a v0.2.0 lib gap we do not depend on.
func fromLibResponse(resp *interactions.InteractionResponse) *InteractionResponse {
	if resp == nil {
		return &InteractionResponse{}
	}

	out := &InteractionResponse{
		ID:          resp.ID,
		Object:      resp.Object,
		Status:      resp.Status,
		Steps:       fromLibContents(resp.Steps),
		Outputs:     fromLibContents(resp.Outputs),
		SherlogLink: resp.SherlogLink,
	}
	if resp.Usage != nil {
		out.Usage = &InteractionUsage{
			TotalTokens:        resp.Usage.TotalTokens,
			InputTokens:        resp.Usage.TotalInputTokens,
			OutputTokens:       resp.Usage.TotalOutputTokens,
			TotalThoughtTokens: resp.Usage.TotalThoughtTokens,
		}
	}
	if resp.Error != nil {
		out.Error = &InteractionError{
			Code:    resp.Error.Code,
			Status:  resp.Error.Status,
			Message: resp.Error.Message,
		}
	}
	return out
}

// fromLibContents maps a slice of library Content (a step/output entry) into the
// suite's Step slice, copying nested content parts as well as the flat media
// fields (MimeType/Data) the library exposes since v0.2.0 for Lyria-style flat
// outputs[]/steps[]. Thought steps carry no parts; they are preserved by Type so
// GenerateOmniVideo can count them.
func fromLibContents(in []interactions.Content) []Step {
	if in == nil {
		return nil
	}
	steps := make([]Step, 0, len(in))
	for _, c := range in {
		s := Step{Type: c.Type, Text: c.Text, MimeType: c.MimeType, Data: c.Data}
		for _, p := range c.Content {
			s.Content = append(s.Content, Part{
				Type:     p.Type,
				Text:     p.Text,
				MimeType: p.MimeType,
				Data:     p.Data,
				URI:      p.URI,
			})
		}
		steps = append(steps, s)
	}
	return steps
}

// decodeInteractionResponse unmarshals a raw Interactions response body into the
// suite's InteractionResponse, ignoring unknown fields (the default encoding/json
// behavior) so Pre-GA wire drift is non-fatal. The production Create path decodes
// via the adopted library and translates with fromLibResponse; this helper exists
// for tests that exercise the suite's own mapping directly against captured wire.
func decodeInteractionResponse(body []byte) (*InteractionResponse, error) {
	var interaction InteractionResponse
	if err := json.Unmarshal(body, &interaction); err != nil {
		return nil, fmt.Errorf("interactions: failed to parse JSON response: %w", err)
	}
	return &interaction, nil
}

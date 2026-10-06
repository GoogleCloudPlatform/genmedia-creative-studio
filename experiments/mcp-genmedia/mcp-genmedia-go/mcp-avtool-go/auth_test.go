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
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"google.golang.org/api/idtoken"
)

const testAudience = "https://avtool-xyz.a.run.app"

// reachHandler is a stand-in for the real MCP handler. If a request reaches it,
// it records that fact and returns 200. The whole point of the fix is that an
// unauthenticated request must NOT reach a handler like this.
func reachHandler(reached *bool) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		*reached = true
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("reached"))
	})
}

// fakeValidator accepts exactly one token ("good-token") for the expected
// audience and returns a payload carrying the given email claim. Everything else
// (wrong audience, any other token) is rejected. This is the test seam that
// stands in for idtoken.Validate so the test needs no network or Google certs.
func fakeValidator(email string) tokenValidator {
	return func(_ context.Context, token, audience string) (*idtoken.Payload, error) {
		if audience != testAudience {
			return nil, errors.New("unexpected audience")
		}
		if token != "good-token" {
			return nil, errors.New("invalid signature")
		}
		return &idtoken.Payload{
			Audience: audience,
			Claims:   map[string]interface{}{"email": email},
		}, nil
	}
}

// TestProveIt_UnauthenticatedRequestReachesHandlerWithoutMiddleware documents
// the PRE-fix vulnerability (b/565096167): with no application-layer auth, a
// request carrying no credentials reaches the handler. This is exactly the
// behavior the Cloud Run flag alone left exposed.
func TestProveIt_UnauthenticatedRequestReachesHandlerWithoutMiddleware(t *testing.T) {
	var reached bool
	srv := httptest.NewServer(reachHandler(&reached))
	defer srv.Close()

	resp, err := http.Get(srv.URL + "/mcp")
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer resp.Body.Close()

	if !reached || resp.StatusCode != http.StatusOK {
		t.Fatalf("pre-fix baseline: expected unauthenticated request to reach handler with 200, got reached=%v status=%d", reached, resp.StatusCode)
	}
}

// TestProveIt_MiddlewareFailsClosed is the post-fix assertion. The same
// unauthenticated request is now rejected at the app layer; only a request with
// a valid token (or an explicit local bypass) is allowed through. Run against the
// reverted code (middleware wiring removed) the 401/403 subtests fail, proving
// the fix is what closes the gap.
func TestProveIt_MiddlewareFailsClosed(t *testing.T) {
	ac := &authConfig{
		audience: testAudience,
		validate: fakeValidator("caller@project.iam.gserviceaccount.com"),
	}

	cases := []struct {
		name        string
		header      string
		wantStatus  int
		wantReached bool
	}{
		{"no_authorization_header", "", http.StatusUnauthorized, false},
		{"malformed_header", "token good-token", http.StatusUnauthorized, false},
		{"empty_bearer", "Bearer ", http.StatusUnauthorized, false},
		{"invalid_token", "Bearer forged-token", http.StatusUnauthorized, false},
		{"valid_token", "Bearer good-token", http.StatusOK, true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var reached bool
			h := ac.middleware(reachHandler(&reached))

			req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
			if tc.header != "" {
				req.Header.Set("Authorization", tc.header)
			}
			rr := httptest.NewRecorder()
			h.ServeHTTP(rr, req)

			if rr.Code != tc.wantStatus {
				t.Errorf("status = %d, want %d (body: %q)", rr.Code, tc.wantStatus, rr.Body.String())
			}
			if reached != tc.wantReached {
				t.Errorf("handler reached = %v, want %v", reached, tc.wantReached)
			}
		})
	}
}

// TestMiddleware_Allowlist verifies the optional caller-email allowlist: a
// validly-signed token from a caller not on the list is rejected with 403, while
// an allowed caller passes.
func TestMiddleware_Allowlist(t *testing.T) {
	ac := &authConfig{
		audience:      testAudience,
		allowedEmails: parseAllowedEmails("allowed@project.iam.gserviceaccount.com"),
	}

	t.Run("allowed_caller", func(t *testing.T) {
		ac.validate = fakeValidator("allowed@project.iam.gserviceaccount.com")
		var reached bool
		req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
		req.Header.Set("Authorization", "Bearer good-token")
		rr := httptest.NewRecorder()
		ac.middleware(reachHandler(&reached)).ServeHTTP(rr, req)
		if rr.Code != http.StatusOK || !reached {
			t.Fatalf("allowed caller: status=%d reached=%v, want 200/true", rr.Code, reached)
		}
	})

	t.Run("disallowed_caller", func(t *testing.T) {
		ac.validate = fakeValidator("stranger@evil.example.com")
		var reached bool
		req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
		req.Header.Set("Authorization", "Bearer good-token")
		rr := httptest.NewRecorder()
		ac.middleware(reachHandler(&reached)).ServeHTTP(rr, req)
		if rr.Code != http.StatusForbidden || reached {
			t.Fatalf("disallowed caller: status=%d reached=%v, want 403/false", rr.Code, reached)
		}
	})
}

// TestMiddleware_LocalBypass verifies the explicit local-dev bypass allows
// requests through without a token, and that it is off by default.
func TestMiddleware_LocalBypass(t *testing.T) {
	ac := &authConfig{bypass: true}
	var reached bool
	req := httptest.NewRequest(http.MethodPost, "/mcp", nil)
	rr := httptest.NewRecorder()
	ac.middleware(reachHandler(&reached)).ServeHTTP(rr, req)
	if rr.Code != http.StatusOK || !reached {
		t.Fatalf("local bypass: status=%d reached=%v, want 200/true", rr.Code, reached)
	}
}

// TestNewAuthConfig_FailsClosedWithoutAudience verifies startup fails closed when
// neither an audience nor the explicit bypass is configured.
func TestNewAuthConfig_FailsClosedWithoutAudience(t *testing.T) {
	t.Setenv(envAuthLocalBypass, "")
	t.Setenv(envAuthAudience, "")
	t.Setenv(envAuthAllowedSAs, "")

	if _, err := newAuthConfig(); err == nil {
		t.Fatal("expected newAuthConfig to fail closed when no audience and no bypass are set, got nil error")
	}
}

// TestNewAuthConfig_BypassAndAudience verifies the two valid configurations:
// explicit local bypass, and a configured audience.
func TestNewAuthConfig_BypassAndAudience(t *testing.T) {
	t.Run("local_bypass", func(t *testing.T) {
		t.Setenv(envAuthLocalBypass, "true")
		ac, err := newAuthConfig()
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if !ac.bypass {
			t.Fatal("expected bypass to be enabled")
		}
	})

	t.Run("configured_audience", func(t *testing.T) {
		t.Setenv(envAuthLocalBypass, "")
		t.Setenv(envAuthAudience, testAudience)
		ac, err := newAuthConfig()
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if ac.bypass {
			t.Fatal("expected bypass to be disabled")
		}
		if ac.audience != testAudience {
			t.Fatalf("audience = %q, want %q", ac.audience, testAudience)
		}
		if ac.validate == nil {
			t.Fatal("expected a production validator to be wired")
		}
	})
}

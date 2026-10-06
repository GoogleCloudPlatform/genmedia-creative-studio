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

// Application-layer authentication for the HTTP/SSE transports.
//
// The avtool MCP service is a Cloud Run service-to-service backend. It is
// invoked by other Google-authenticated callers (not through IAP, which fronts
// the user-facing Mesop app). The idiomatic defense for that invocation model is
// to verify a Google-signed OIDC ID token presented in the standard
// `Authorization: Bearer <token>` header: the signature, expiry and expected
// audience are validated against Google's public certificates before any handler
// runs. This provides defense independent of the Cloud Run
// `--no-allow-unauthenticated` deployment flag (b/565096167): if that flag is
// ever removed, misconfigured, or bypassed via a VPC/ingress path, the app still
// rejects unauthenticated callers.
//
// The behavior mirrors the Python app's verified-identity pattern
// (common/verified_identity.py): fail closed by default, make the audience and
// optional caller allowlist configurable per-env, and permit a local-development
// bypass only behind an explicit env flag.

package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"strings"

	common "github.com/GoogleCloudPlatform/genmedia-creative-studio/experiments/mcp-genmedia/mcp-genmedia-go/mcp-common"
	"google.golang.org/api/idtoken"
)

const (
	// envAuthAudience is the expected OIDC `aud` claim. For a Cloud Run
	// service this is typically the service's own URL. Required unless the
	// local bypass is enabled.
	envAuthAudience = "MCP_AUTH_AUDIENCE"

	// envAuthAllowedSAs is an optional comma-separated allowlist of caller
	// service-account emails. When set, a verified token whose `email` claim
	// is not in the list is rejected with 403. When empty, any caller holding
	// a validly-signed token for the expected audience is accepted.
	envAuthAllowedSAs = "MCP_AUTH_ALLOWED_SERVICE_ACCOUNTS"

	// envAuthLocalBypass, when set to "true", disables application-layer auth
	// entirely. This is strictly for local development and must never be set
	// in a deployed environment. Defaults to auth-required.
	envAuthLocalBypass = "MCP_AUTH_LOCAL_BYPASS"
)

// tokenValidator verifies a Google-signed OIDC ID token for the given audience
// and returns its payload. It is a seam so tests can inject a deterministic
// validator without network access; production wires it to idtoken.Validate.
type tokenValidator func(ctx context.Context, token, audience string) (*idtoken.Payload, error)

// authConfig holds the resolved application-layer auth policy.
type authConfig struct {
	// bypass disables auth entirely (local development only).
	bypass bool
	// audience is the expected OIDC `aud` claim.
	audience string
	// allowedEmails, when non-empty, restricts callers to these verified
	// service-account emails (lower-cased keys).
	allowedEmails map[string]struct{}
	// validate verifies the presented bearer token.
	validate tokenValidator
}

// newAuthConfig resolves the auth policy from the environment, failing closed.
//
// If MCP_AUTH_LOCAL_BYPASS=true the service runs without auth (local dev only).
// Otherwise MCP_AUTH_AUDIENCE must be set; an unset audience is a fatal
// misconfiguration (we refuse to serve rather than silently accept any token or
// 401 every request), mirroring the Python app's startup validation.
func newAuthConfig() (*authConfig, error) {
	if strings.EqualFold(common.GetEnv(envAuthLocalBypass, ""), "true") {
		log.Printf("WARNING: %s=true — application-layer authentication is DISABLED. "+
			"This is for local development only and must never be used in a deployed environment.",
			envAuthLocalBypass)
		return &authConfig{bypass: true}, nil
	}

	audience := common.GetEnv(envAuthAudience, "")
	if audience == "" {
		return nil, fmt.Errorf(
			"%s must be set to the expected OIDC audience (or set %s=true for local dev); refusing to serve without application-layer auth",
			envAuthAudience, envAuthLocalBypass)
	}

	return &authConfig{
		audience:      audience,
		allowedEmails: parseAllowedEmails(common.GetEnv(envAuthAllowedSAs, "")),
		validate: func(ctx context.Context, token, audience string) (*idtoken.Payload, error) {
			return idtoken.Validate(ctx, token, audience)
		},
	}, nil
}

// parseAllowedEmails parses a comma-separated allowlist into a lower-cased set.
func parseAllowedEmails(raw string) map[string]struct{} {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	set := make(map[string]struct{})
	for _, e := range strings.Split(raw, ",") {
		if e = strings.TrimSpace(strings.ToLower(e)); e != "" {
			set[e] = struct{}{}
		}
	}
	if len(set) == 0 {
		return nil
	}
	return set
}

// middleware wraps next so that every request is authenticated before reaching
// it. Missing or invalid credentials fail closed with 401; a verified caller not
// present in a configured allowlist fails with 403.
func (ac *authConfig) middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if ac.bypass {
			next.ServeHTTP(w, r)
			return
		}

		const prefix = "Bearer "
		authz := r.Header.Get("Authorization")
		if len(authz) <= len(prefix) || !strings.EqualFold(authz[:len(prefix)], prefix) {
			unauthorized(w, "missing or malformed Authorization bearer token")
			return
		}
		token := strings.TrimSpace(authz[len(prefix):])
		if token == "" {
			unauthorized(w, "empty bearer token")
			return
		}

		payload, err := ac.validate(r.Context(), token, ac.audience)
		if err != nil {
			// Present-but-invalid token is a tamper/misconfiguration signal:
			// fail closed and log, but do not leak details to the caller.
			log.Printf("auth: rejecting request to %s: token verification failed: %v", r.URL.Path, err)
			unauthorized(w, "invalid token")
			return
		}

		if len(ac.allowedEmails) > 0 {
			email, _ := payload.Claims["email"].(string)
			if _, ok := ac.allowedEmails[strings.ToLower(strings.TrimSpace(email))]; !ok {
				log.Printf("auth: rejecting request to %s: caller %q not in allowlist", r.URL.Path, email)
				http.Error(w, "forbidden: caller not permitted", http.StatusForbidden)
				return
			}
		}

		next.ServeHTTP(w, r)
	})
}

func unauthorized(w http.ResponseWriter, msg string) {
	http.Error(w, "unauthorized: "+msg, http.StatusUnauthorized)
}

package external_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	external "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/external"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
func TestGatheringSafetyAuthorityFailsClosedAcrossDecisionStates(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name       string
		statusCode int
		mutate     func(map[string]any)
		want       error
	}{
		{name: "allow", statusCode: http.StatusOK},
		{
			name: "denied", statusCode: http.StatusOK,
			mutate: func(payload map[string]any) { payload["allowed"] = false },
			want:   gatheringerrors.ErrGatheringSafetyTerminationDenied,
		},
		{
			name: "expired", statusCode: http.StatusOK,
			mutate: func(payload map[string]any) {
				payload["expiresAt"] = time.Now().UTC().Add(-time.Minute)
			},
			want: gatheringerrors.ErrGatheringSafetyTerminationDenied,
		},
		{
			name: "revoked", statusCode: http.StatusOK,
			mutate: func(payload map[string]any) {
				payload["revokedAt"] = time.Now().UTC()
			},
			want: gatheringerrors.ErrGatheringSafetyTerminationDenied,
		},
		{
			name: "identity_mismatch", statusCode: http.StatusOK,
			mutate: func(payload map[string]any) {
				payload["actorPersonaId"] = "persona-attacker"
			},
			want: gatheringerrors.ErrGatheringSafetyTerminationDenied,
		},
		{
			name:       "dependency_unavailable",
			statusCode: http.StatusServiceUnavailable,
			want:       gatheringerrors.ErrGatheringSafetyAuthorityUnavailable,
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			config := gatheringSafetyTokenConfig()
			verifier, err := rtauth.NewHS256Verifier(config)
			if err != nil {
				t.Fatal(err)
			}
			server := httptest.NewServer(http.HandlerFunc(
				func(writer http.ResponseWriter, request *http.Request) {
					if request.Method != http.MethodPost ||
						request.URL.Path != "/internal/content/gathering-safety-termination:authorize" {
						t.Errorf("unexpected authority route: %s %s", request.Method, request.URL.Path)
						writer.WriteHeader(http.StatusNotFound)
						return
					}
					token := strings.TrimPrefix(
						request.Header.Get("Authorization"),
						"Bearer ",
					)
					claims, verifyErr := verifier.Verify(token)
					if verifyErr != nil ||
						claims.Subject != "service:circle-service" ||
						!strings.Contains(
							claims.Scope,
							"content.gathering.safety.authorize",
						) {
						t.Errorf("invalid HS256 service authorization: claims=%+v err=%v", claims, verifyErr)
						writer.WriteHeader(http.StatusUnauthorized)
						return
					}
					var body map[string]any
					if decodeErr := json.NewDecoder(request.Body).Decode(&body); decodeErr != nil {
						t.Errorf("decode authority request: %v", decodeErr)
						writer.WriteHeader(http.StatusBadRequest)
						return
					}
					if body["actorPersonaId"] != "persona-safety" ||
						body["gatheringId"] != "gathering-1" ||
						body["action"] != gatheringapp.GatheringSafetyTerminationAction ||
						body["evidenceRef"] != "content.report/report-1" ||
						body["decisionRef"] != "content.report/report-1@3#terminate_gathering" {
						t.Errorf("authority request identity mismatch: %#v", body)
						writer.WriteHeader(http.StatusBadRequest)
						return
					}
					writer.Header().Set("Content-Type", "application/json")
					writer.WriteHeader(test.statusCode)
					if test.statusCode != http.StatusOK {
						_, _ = writer.Write([]byte(`{"code":"CONTENT.SYSTEM.gathering_safety_authority_unavailable"}`))
						return
					}
					payload := map[string]any{
						"allowed":         true,
						"actorPersonaId":  "persona-safety",
						"gatheringId":     "gathering-1",
						"action":          gatheringapp.GatheringSafetyTerminationAction,
						"evidenceRef":     "content.report/report-1",
						"decisionRef":     "content.report/report-1@3#terminate_gathering",
						"decisionVersion": 3,
						"decisionDigest":  strings.Repeat("ab", 32),
						"expiresAt":       time.Now().UTC().Add(time.Minute),
					}
					if test.mutate != nil {
						test.mutate(payload)
					}
					if encodeErr := json.NewEncoder(writer).Encode(payload); encodeErr != nil {
						t.Errorf("encode authority response: %v", encodeErr)
					}
				},
			))
			t.Cleanup(server.Close)
			credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
				config,
				"circle-service",
				[]string{"content.gathering.safety.authorize"},
			)
			if err != nil {
				t.Fatal(err)
			}
			authorizer, err := external.NewHTTPSafetyTerminationAuthorizer(
				server.URL,
				credentials,
				server.Client(),
			)
			if err != nil {
				t.Fatal(err)
			}
			err = authorizer.AuthorizeSafetyTermination(
				context.Background(),
				gatheringapp.GatheringSafetyTerminationAuthorizationRequest{
					ActorPersonaID:           "persona-safety",
					GatheringID:              "gathering-1",
					Action:                   gatheringapp.GatheringSafetyTerminationAction,
					EvidenceRef:              "content.report/report-1",
					DecisionRef:              "content.report/report-1@3#terminate_gathering",
					ExpectedGatheringVersion: 11,
				},
			)
			if test.want == nil {
				if err != nil {
					t.Fatalf("allow decision failed: %v", err)
				}
				return
			}
			if !errors.Is(err, test.want) {
				t.Fatalf("authority error=%v want %v", err, test.want)
			}
		})
	}
}

func gatheringSafetyTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("gathering-safety-test-secret-at-least-32-bytes"),
		Issuer:       "quwoquan-test",
		Audience:     "quwoquan-test",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
		ClockSkew:    time.Second,
	}
}

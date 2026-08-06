package gathering_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	shared "quwoquan_service/generated/serviceclients/hostauthority"
	rtauth "quwoquan_service/runtime/auth"
	gatheringcontract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	gatheringmodel "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	gatheringexternal "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/external"
)

func TestPersonaHostAuthorityHTTPClientRejectsForgedExpiredRevokedAndMismatchedEvidence(
	t *testing.T,
) {
	now := time.Date(2026, 8, 6, 15, 0, 0, 0, time.UTC)
	query := gatheringmodel.HostAuthorityQuery{
		HostSubjectKind: gatheringcontract.GatheringHostSubjectKindPersona,
		HostSubjectID:   "persona-1", ActorPersonaID: "persona-1",
		OrganizerPersonaID:   "persona-1",
		AuthorityEvidenceRef: "persona:persona-1:self",
		AuthorityVersion:     7,
		Action:               gatheringmodel.HostAuthorityCreateDraft,
		EvaluatedAt:          now,
	}
	binding := gatheringcontract.HostBinding{
		HostSubjectKind:      query.HostSubjectKind,
		HostSubjectID:        query.HostSubjectID,
		AuthorityEvidenceRef: query.AuthorityEvidenceRef,
		AuthorityVersion:     query.AuthorityVersion,
		AuthorityExpiresAt:   now.Add(time.Hour),
	}
	baseEvidence := shared.Evidence{
		HostSubjectKind: "persona", HostSubjectID: "persona-1",
		HostSubjectRef: "persona:persona-1",
		ActorPersonaID: "persona-1", OrganizerPersonaID: "persona-1",
		AuthorityEvidenceRef: "persona:persona-1:self",
		AuthorityVersion:     7,
		AuthorityDigest:      "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
		ExpiresAt:            now.Add(5 * time.Minute), Action: "create_draft",
		Valid: true,
	}
	cases := map[string]struct {
		mutate  func(*shared.Evidence)
		wantErr bool
	}{
		"valid": {wantErr: false},
		"forged actor": {
			mutate: func(evidence *shared.Evidence) {
				evidence.ActorPersonaID = "persona-forged"
			},
			wantErr: true,
		},
		"forged subject": {
			mutate: func(evidence *shared.Evidence) {
				evidence.HostSubjectID = "persona-forged"
			},
			wantErr: true,
		},
		"expired": {
			mutate: func(evidence *shared.Evidence) {
				evidence.ExpiresAt = now.Add(-time.Second)
			},
			wantErr: true,
		},
		"revoked": {
			mutate: func(evidence *shared.Evidence) {
				evidence.Revoked = true
			},
			wantErr: true,
		},
		"action mismatch": {
			mutate: func(evidence *shared.Evidence) {
				evidence.Action = "publish"
			},
			wantErr: true,
		},
		"version mismatch": {
			mutate: func(evidence *shared.Evidence) {
				evidence.AuthorityVersion = 8
			},
			wantErr: true,
		},
	}
	for name, testCase := range cases {
		t.Run(name, func(t *testing.T) {
			tokenConfig := authorityHTTPTokenConfig()
			verifier, err := rtauth.NewHS256Verifier(tokenConfig)
			if err != nil {
				t.Fatal(err)
			}
			server := httptest.NewServer(http.HandlerFunc(func(
				writer http.ResponseWriter,
				request *http.Request,
			) {
				if request.Method != http.MethodPost ||
					request.URL.Path !=
						"/internal/user/personas/persona-1/gathering-host-authority:evaluate" {
					t.Errorf("owner request=%s %s", request.Method, request.URL.Path)
				}
				assertAuthorityHTTPServiceGrant(t, verifier, request)
				var received shared.EvaluationQuery
				if decodeErr := json.NewDecoder(request.Body).Decode(&received); decodeErr != nil {
					t.Error(decodeErr)
				}
				if received.AuthorityEvidenceRef != query.AuthorityEvidenceRef ||
					received.Action != string(query.Action) {
					t.Errorf("typed owner query=%+v", received)
				}
				response := baseEvidence
				if testCase.mutate != nil {
					testCase.mutate(&response)
				}
				writer.Header().Set("Content-Type", "application/json")
				_ = json.NewEncoder(writer).Encode(response)
			}))
			defer server.Close()
			credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
				tokenConfig,
				"circle-service",
				[]string{"user.persona.gathering_host_authority.evaluate"},
			)
			if err != nil {
				t.Fatal(err)
			}
			client, err := gatheringexternal.NewPersonaHostAuthorityHTTPClient(
				server.URL,
				credentials,
				server.Client(),
			)
			if err != nil {
				t.Fatal(err)
			}
			evidence, err := client.EvaluatePersonaHostAuthority(
				t.Context(),
				query,
			)
			if err != nil {
				t.Fatal(err)
			}
			validateErr := gatheringmodel.ValidateHostAuthority(binding, query, evidence)
			if (validateErr != nil) != testCase.wantErr {
				t.Fatalf(
					"ValidateHostAuthority() error=%v, wantErr=%v evidence=%+v",
					validateErr,
					testCase.wantErr,
					evidence,
				)
			}
		})
	}
}

func authorityHTTPTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret:       []byte("host-authority-api-integration-secret"),
		Issuer:       "host-authority-api-integration",
		Audience:     "host-authority-api-integration",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
	}
}

func assertAuthorityHTTPServiceGrant(
	t *testing.T,
	verifier *rtauth.Verifier,
	request *http.Request,
) {
	t.Helper()
	token := strings.TrimPrefix(request.Header.Get("Authorization"), "Bearer ")
	claims, err := verifier.Verify(token)
	if err != nil {
		t.Fatal(err)
	}
	if claims.Subject != "service:circle-service" ||
		!strings.Contains(
			claims.Scope,
			"user.persona.gathering_host_authority.evaluate",
		) {
		t.Fatalf("service grant claims=%+v", claims)
	}
}

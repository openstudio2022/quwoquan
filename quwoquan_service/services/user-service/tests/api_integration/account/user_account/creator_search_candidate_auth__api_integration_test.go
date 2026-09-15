package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/auth"
	rt "quwoquan_service/runtime/search"
	inbound "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	app "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	model "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t6
// 真实签名、middleware、generated runtime guard 与生产 handler；对象 port 替身不构成数据库证据。
type candidateAuthSource struct {
	calls    int
	snapshot rt.CreatorSearchCandidateSnapshot
}

func (s *candidateAuthSource) Read(context.Context, rt.ReleaseCandidateBinding) (*rt.CreatorSearchCandidateSnapshot, error) {
	s.calls++
	return &s.snapshot, nil
}
func (*candidateAuthSource) FindByPersonaID(context.Context, string) (*model.Persona, error) {
	return nil, nil
}
func (*candidateAuthSource) FindByUserHandle(context.Context, string) (*model.Persona, error) {
	return nil, nil
}
func (*candidateAuthSource) FindByID(context.Context, string) (*model.UserProfile, error) {
	return nil, nil
}

func TestCreatorCandidateSignedAuthorization(t *testing.T) {
	config := auth.TokenConfig{Secret: bytes.Repeat([]byte{0x37}, 32), Issuer: "creator-auth-test", Audience: "user-service", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	verifier, err := auth.NewHS256Verifier(config)
	if err != nil {
		t.Fatal(err)
	}
	signer, err := auth.NewHS256Signer(config)
	if err != nil {
		t.Fatal(err)
	}
	scope := "user.creator_search.candidate.read"
	serviceToken := func(service, scope string) string {
		p, err := auth.NewHS256ServiceAuthorizationProvider(config, service, []string{scope})
		if err != nil {
			t.Fatal(err)
		}
		h, err := p.AuthorizationHeader(t.Context())
		if err != nil {
			t.Fatal(err)
		}
		return h
	}
	signed := func(subject auth.TokenSubject) string {
		token, err := signer.Sign(subject)
		if err != nil {
			t.Fatal(err)
		}
		return "Bearer " + token
	}
	delegated, err := auth.NewHS256ServiceAccountAuthorizationProvider(config, "content-service", []string{scope})
	if err != nil {
		t.Fatal(err)
	}
	delegatedToken, err := delegated.AuthorizationHeaderForAccount(t.Context(), "account-a")
	if err != nil {
		t.Fatal(err)
	}
	valid := serviceToken("content-service", scope)
	claims, err := verifier.Verify(strings.TrimPrefix(valid, "Bearer "))
	if err != nil || claims.Subject != "service:content-service" || claims.ServiceActorID != "" {
		t.Fatalf("unexpected provider identity: %+v %v", claims, err)
	}
	binding := rt.ReleaseCandidateBinding{Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "auth-candidate", ManifestDigest: "sha256:" + strings.Repeat("a", 64)}
	source := &candidateAuthSource{snapshot: rt.CreatorSearchCandidateSnapshot{Release: binding, SourceClosureDigest: binding.ManifestDigest, Profiles: []rt.CreatorSearchPublicSnapshot{}}}
	if err := source.snapshot.Seal(); err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	inbound.NewCreatorSearchCandidateHandler(app.NewCreatorSearchCandidateQueryFacade(source, source, source, "alpha")).Register(mux)
	handler := auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(auth.EnforceRuntimeOperationContract(operationsecurity.ForDomain("user"))(mux))
	body, err := json.Marshal(struct {
		Release rt.ReleaseCandidateBinding `json:"release"`
	}{binding})
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name, token string
		status      int
	}{
		{"content-service", valid, 200},
		{"other-service-same-scope", serviceToken("search-service", scope), 403},
		{"wrong-scope", serviceToken("content-service", "unrelated.read"), 403},
		{"anonymous-forged-headers", "", 401},
		{"user-token", signed(auth.TokenSubject{AccountID: "account-a", Scopes: []string{scope}}), 403},
		{"delegated-service-actor", delegatedToken, 403},
		{"service-persona-delegation", signed(auth.TokenSubject{AccountID: "service:content-service", PersonaID: "persona-a", Roles: []string{"service"}, Scopes: []string{scope}}), 403},
		{"forged-service-actor", "Bearer invalid.act.content-service", 401},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			before := source.calls
			r := httptest.NewRequest(http.MethodPost, "/internal/user/creator-search-candidate:query", bytes.NewReader(body))
			r.Header.Set("Authorization", tc.token)
			r.Header.Set("X-Client-Account-Id", "service:content-service")
			r.Header.Set("X-Service-Actor-Id", "content-service")
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, r)
			if w.Code != tc.status {
				t.Fatalf("status=%d want=%d body=%s", w.Code, tc.status, w.Body.String())
			}
			if tc.status != 200 && source.calls != before {
				t.Fatal("denied request reached owner reader")
			}
			if tc.status == 200 {
				var result app.CreatorSearchCandidateResult
				if err := json.Unmarshal(w.Body.Bytes(), &result); err != nil || !result.Found || result.Snapshot == nil || result.Snapshot.Release != binding || source.calls != before+1 {
					t.Fatalf("actual handler did not read exact candidate: %+v %v", result, err)
				}
			}
		})
	}
}

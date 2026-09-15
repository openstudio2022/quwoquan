package preparation_test

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
	inbound "quwoquan_service/services/search-service/internal/search/search_release_preparation/adapters/inbound/http"
	app "quwoquan_service/services/search-service/internal/search/search_release_preparation/application"
	"quwoquan_service/services/search-service/internal/search/search_release_preparation/domain"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t7
// 只验证真实 HTTP 认证链与 application 交互；对象级 port 替身不是 Mongo/ES 或并发 CAS 证据。
type authPreparationStore struct {
	state       domain.State
	exists      bool
	receipt     domain.View
	key, digest string
	calls       int
}

func (s *authPreparationStore) Load(context.Context, string) (domain.State, error) {
	s.calls++
	if !s.exists {
		return domain.State{}, domain.ErrNotFound
	}
	return s.state, nil
}
func (s *authPreparationStore) Receipt(_ context.Context, _ string, key, digest string) (domain.View, bool, error) {
	s.calls++
	if s.key != key {
		return domain.View{}, false, nil
	}
	if s.digest != digest {
		return domain.View{}, false, domain.ErrConflict
	}
	return s.receipt, true, nil
}
func (s *authPreparationStore) Create(_ context.Context, state domain.State) error {
	s.state, s.exists = state, true
	return nil
}
func (s *authPreparationStore) Claim(_ context.Context, state domain.State, _ int64, _ time.Time) error {
	s.state = state
	return nil
}
func (s *authPreparationStore) Commit(_ context.Context, state domain.State, _ int64, _ string, key, digest string, _ time.Time) error {
	s.state, s.receipt, s.key, s.digest = state, state.View(), key, digest
	return nil
}

type authPreparationProjection struct{ writes int }

func (p *authPreparationProjection) Prepare(context.Context, rt.ReleaseQueryPreparationBinding, rt.SearchReleaseCandidateSnapshot) ([]string, error) {
	p.writes++
	return []string{}, nil
}
func (*authPreparationProjection) Verify(_ context.Context, _ rt.ReleaseQueryPreparationBinding, s rt.SearchReleaseCandidateSnapshot) ([]rt.ReleaseQueryClassEvidence, error) {
	rows := []rt.ReleaseQueryClassEvidence{}
	for _, class := range []string{"result", "suggest", "retrieval", "ids", "count", "facet"} {
		rows = append(rows, rt.ReleaseQueryClassEvidence{QueryClass: class, ObjectSetDigest: s.ObjectSetDigest(), DocumentsDigest: "sha256:" + strings.Repeat("d", 64)})
	}
	return rows, nil
}

func preparationAuthStack(t *testing.T, mux *http.ServeMux) (http.Handler, auth.TokenConfig) {
	t.Helper()
	config := auth.TokenConfig{Secret: bytes.Repeat([]byte{0x39}, 32), Issuer: "preparation-auth-test", Audience: "search-service", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	verifier, err := auth.NewHS256Verifier(config)
	if err != nil {
		t.Fatal(err)
	}
	return auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(auth.EnforceRuntimeOperationContract(operationsecurity.ForDomain("search"))(mux)), config
}
func preparationServiceToken(t *testing.T, config auth.TokenConfig, service, scope string) string {
	t.Helper()
	provider, err := auth.NewHS256ServiceAuthorizationProvider(config, service, []string{scope})
	if err != nil {
		t.Fatal(err)
	}
	header, err := provider.AuthorizationHeader(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	return header
}
func preparationRequest(t *testing.T, handler http.Handler, path, token, key string, value any) *httptest.ResponseRecorder {
	t.Helper()
	body, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	r := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(body))
	r.Header.Set("Authorization", token)
	r.Header.Set("Idempotency-Key", key)
	r.Header.Set("X-Client-Account-Id", "service:content-service")
	r.Header.Set("X-Service-Actor-Id", "content-service")
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, r)
	return w
}

func TestPreparationSignedAuthorizationAndIdempotency(t *testing.T) {
	generation := "sha256:" + strings.Repeat("a", 64)
	binding := rt.ReleaseQueryPreparationBinding{Release: rt.ReleaseCandidateBinding{"alpha", "qwq_data", "auth-candidate", generation}, Slice: "creator_search", SchemaGeneration: generation, ProviderBindingGeneration: generation}
	snapshot := rt.CreatorSearchCandidateSnapshot{Release: binding.Release, SourceClosureDigest: generation, Profiles: []rt.CreatorSearchPublicSnapshot{}}
	if err := snapshot.Seal(); err != nil {
		t.Fatal(err)
	}
	command := domain.Command{Binding: binding, Snapshot: rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: &snapshot}, IdempotencyKey: "auth-prepare"}
	store, projection := &authPreparationStore{}, &authPreparationProjection{}
	service, err := app.NewService(store, projection, "alpha", generation, time.Now)
	if err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	inbound.NewHandler(service).Register(mux)
	handler, config := preparationAuthStack(t, mux)
	preparePath, queryPath := "/internal/search/release-preparations:prepare", "/internal/search/release-preparations:query"
	valid := preparationServiceToken(t, config, "content-service", "search.release.prepare")
	// 缺失、错配、空 body key 均须在 owner state/provider 被调用前拒绝。
	for _, tc := range []struct {
		name, header, body string
		status             int
	}{
		{"missing-header", "", command.IdempotencyKey, 400},
		{"mismatched-header", "different", command.IdempotencyKey, 422},
		{"missing-body-key", command.IdempotencyKey, "", 422},
		{"whitespace-body-key", command.IdempotencyKey, " " + command.IdempotencyKey + " ", 422},
	} {
		t.Run(tc.name, func(t *testing.T) {
			c := command
			c.IdempotencyKey = tc.body
			w := preparationRequest(t, handler, preparePath, valid, tc.header, c)
			if w.Code != tc.status || store.calls != 0 || projection.writes != 0 {
				t.Fatalf("status=%d calls=%d writes=%d body=%s", w.Code, store.calls, projection.writes, w.Body.String())
			}
		})
	}
	w := preparationRequest(t, handler, preparePath, valid, command.IdempotencyKey, command)
	if w.Code != 200 {
		t.Fatalf("prepare: %d %s", w.Code, w.Body.String())
	}
	var first domain.View
	if err := json.Unmarshal(w.Body.Bytes(), &first); err != nil || first.Status != "completed" || first.Proof == nil {
		t.Fatalf("missing completed proof: %+v %v", first, err)
	}
	w = preparationRequest(t, handler, preparePath, valid, command.IdempotencyKey, command)
	var replay domain.View
	if err := json.Unmarshal(w.Body.Bytes(), &replay); err != nil || w.Code != 200 || replay.Proof == nil || replay.Proof.ProofDigest != first.Proof.ProofDigest || projection.writes != 1 {
		t.Fatalf("replay: %d %s writes=%d", w.Code, w.Body.String(), projection.writes)
	}
	drift := command
	drift.ExpectedVersion = 1
	w = preparationRequest(t, handler, preparePath, valid, drift.IdempotencyKey, drift)
	if w.Code != 409 || projection.writes != 1 {
		t.Fatalf("key reuse: %d %s", w.Code, w.Body.String())
	}
	for _, endpoint := range []struct {
		name, path, scope string
		body              any
	}{
		{"prepare", preparePath, "search.release.prepare", command},
		{"query", queryPath, "search.release.read", domain.Query{Binding: binding, SnapshotDigest: snapshot.SnapshotDigest}},
	} {
		t.Run(endpoint.name, func(t *testing.T) {
			signer, err := auth.NewHS256Signer(config)
			if err != nil {
				t.Fatal(err)
			}
			sign := func(subject auth.TokenSubject) string {
				token, err := signer.Sign(subject)
				if err != nil {
					t.Fatal(err)
				}
				return "Bearer " + token
			}
			delegated, err := auth.NewHS256ServiceAccountAuthorizationProvider(config, "content-service", []string{endpoint.scope})
			if err != nil {
				t.Fatal(err)
			}
			delegatedToken, err := delegated.AuthorizationHeaderForAccount(t.Context(), "account-a")
			if err != nil {
				t.Fatal(err)
			}
			for _, tc := range []struct {
				name, token string
				status      int
			}{
				{"content-service", preparationServiceToken(t, config, "content-service", endpoint.scope), 200},
				{"other-service-same-scope", preparationServiceToken(t, config, "user-service", endpoint.scope), 403},
				{"wrong-scope", preparationServiceToken(t, config, "content-service", "unrelated.read"), 403},
				{"anonymous-forged-headers", "", 401},
				{"user-token", sign(auth.TokenSubject{AccountID: "account-a", Scopes: []string{endpoint.scope}}), 403},
				{"delegated-service-actor", delegatedToken, 403},
				{"service-persona-delegation", sign(auth.TokenSubject{AccountID: "service:content-service", PersonaID: "persona-a", Roles: []string{"service"}, Scopes: []string{endpoint.scope}}), 403},
				{"forged-service-actor", "Bearer invalid.act.content-service", 401},
			} {
				t.Run(tc.name, func(t *testing.T) {
					before := store.calls
					w := preparationRequest(t, handler, endpoint.path, tc.token, command.IdempotencyKey, endpoint.body)
					if w.Code != tc.status {
						t.Fatalf("status=%d want=%d body=%s", w.Code, tc.status, w.Body.String())
					}
					if tc.status != 200 && store.calls != before {
						t.Fatal("denied caller reached owner store")
					}
				})
			}
		})
	}
}

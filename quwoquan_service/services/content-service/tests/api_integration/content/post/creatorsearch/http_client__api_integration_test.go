package creatorsearch_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	rt "quwoquan_service/runtime/search"
	client "quwoquan_service/services/content-service/internal/content/post/infrastructure/creatorsearch"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestUnifiedSearchClientSignedHeaderAndNoOldRoute(t *testing.T) {
	cfg := auth.TokenConfig{Secret: []byte("0123456789abcdef0123456789abcdef"), Issuer: "https://auth.quwoquan.test", Audience: "quwoquan-api", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	verifier, _ := auth.NewHS256Verifier(cfg)
	credential, _ := auth.NewHS256ServiceAuthorizationProvider(cfg, "content-service", []string{"search.release.prepare", "search.release.read"})
	d := "sha256:" + strings.Repeat("a", 64)
	binding := rt.ReleaseQueryPreparationBinding{Release: rt.ReleaseCandidateBinding{"gamma", "qwq_data", "candidate", d}, Slice: "creator_search", SchemaGeneration: d, ProviderBindingGeneration: d}
	creator := rt.CreatorSearchCandidateSnapshot{Release: binding.Release, SourceClosureDigest: d, Profiles: []rt.CreatorSearchPublicSnapshot{}}
	_ = creator.Seal()
	snapshot := rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: &creator}
	writes := 0
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		invocation, _ := operation.FromContext(r.Context())
		if invocation.OperationID != "search.search_release_preparation.PrepareSearchRelease" {
			t.Error("retired operation used")
		}
		var c struct {
			Binding         rt.ReleaseQueryPreparationBinding `json:"binding"`
			Snapshot        rt.SearchReleaseCandidateSnapshot `json:"snapshot"`
			ExpectedVersion int64                             `json:"expectedVersion"`
			IdempotencyKey  string                            `json:"idempotencyKey"`
		}
		if rt.DecodeCreatorValue(r.Body, &c) != nil || c.IdempotencyKey != invocation.IdempotencyKey {
			http.Error(w, "bad key", 422)
			return
		}
		writes++
		_ = json.NewEncoder(w).Encode(struct {
			PreparationID  string                            `json:"preparationId"`
			Binding        rt.ReleaseQueryPreparationBinding `json:"binding"`
			SnapshotDigest string                            `json:"snapshotDigest"`
			Version        int64                             `json:"version"`
			Status         string                            `json:"status"`
			FailureCode    *string                           `json:"failureCode"`
			Proof          *rt.ReleaseQueryReadinessProof    `json:"proof"`
			UpdatedAt      time.Time                         `json:"updatedAt"`
		}{binding.ID(), binding, creator.SnapshotDigest, 1, "accepted", nil, nil, time.Now().UTC()})
	})
	server := httptest.NewServer(auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(auth.EnforceRuntimeOperationContract(operationsecurity.ForDomain("search"))(handler)))
	defer server.Close()
	transport, err := client.NewClient(server.URL, server.URL, credential, credential, credential)
	if err != nil {
		t.Fatal(err)
	}
	if err = transport.PrepareSearchRelease(t.Context(), binding, snapshot, 0, "stable-key"); err != nil || writes != 1 {
		t.Fatal(err, writes)
	}
	if err = transport.PrepareSearchRelease(t.Context(), binding, snapshot, 0, ""); err == nil {
		t.Fatal("missing command identity accepted")
	}
}

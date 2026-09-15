package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"quwoquan_service/runtime/auth"
	rt "quwoquan_service/runtime/search"
	generated "quwoquan_service/services/product-ops-service/generated/product_ops/premium_pool_entry/contract/model"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestPremiumSourceCompositionSignsExactScopeAndRejectsWrongSource(t *testing.T) {
	cfg := auth.TokenConfig{Secret: []byte(strings.Repeat("x", 32)), Issuer: "test", Audience: "services", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	credentials, err := auth.NewHS256ServiceAuthorizationProvider(cfg, "product-ops-service", []string{"content.release.source.read"})
	if err != nil {
		t.Fatal(err)
	}
	d := "sha256:" + strings.Repeat("a", 64)
	release := rt.ReleaseCandidateBinding{Environment: "gamma", SourceOwner: "qwq_data", ReleaseID: "A", ManifestDigest: d}
	source := rt.ReleaseCandidateObjectIdentity{Release: release, ObjectType: "content.post", ObjectID: "p", SourceVersion: 1, SourceDigest: d}
	snapshot := rt.ReleasePostCandidateSnapshot{Release: release, SourceClosureDigest: d, MediaClosureDigest: d, Posts: []rt.ReleasePostPublicSnapshot{{Identity: source, PostRef: "p", AuthorID: "a", AuthorDisplayName: "Author", ContentType: "video", ContentIdentity: "work", Status: "published", Visibility: "public", ModerationStatus: "approved", TagRefs: []string{}, EntityRefs: []string{}, MediaAssetIDs: []string{}, MediaURLs: []string{}, PublishedAt: "2026-09-13T00:00:00Z", UpdatedAt: "2026-09-13T00:00:00Z", DeepLink: "/p"}}}
	_ = snapshot.Seal()
	verifier, err := auth.NewHS256Verifier(cfg)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		claims, err := verifier.Verify(strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer "))
		if err != nil || claims.Subject != "service:product-ops-service" || claims.Scope != "content.release.source.read" {
			http.Error(w, "forbidden", 403)
			return
		}
		if r.URL.Path != "/internal/content/release-candidates:query" {
			t.Error("wrong operation")
		}
		_ = json.NewEncoder(w).Encode(snapshot)
	}))
	defer server.Close()
	reader, err := newPremiumSourceReader(server.URL, credentials)
	if err != nil {
		t.Fatal(err)
	}
	raw, _ := json.Marshal(source)
	var expected generated.ReleaseCandidateObjectIdentity
	_ = json.Unmarshal(raw, &expected)
	if err = reader.VerifyCandidateSource(context.Background(), expected); err != nil {
		t.Fatal(err)
	}
	wrong, _ := auth.NewHS256ServiceAuthorizationProvider(cfg, "product-ops-service", []string{"content.release.fence.read"})
	wrongReader, _ := newPremiumSourceReader(server.URL, wrong)
	if wrongReader.VerifyCandidateSource(context.Background(), expected) == nil {
		t.Fatal("wrong source scope accepted")
	}
	expected.SourceVersion = 2
	if reader.VerifyCandidateSource(context.Background(), expected) == nil {
		t.Fatal("accepted wrong source version")
	}
	for _, endpoint := range []string{"", "file:///tmp/source", "http://user:pass@localhost"} {
		if _, err := newPremiumSourceReader(endpoint, credentials); err == nil {
			t.Fatal("accepted invalid endpoint")
		}
	}
}

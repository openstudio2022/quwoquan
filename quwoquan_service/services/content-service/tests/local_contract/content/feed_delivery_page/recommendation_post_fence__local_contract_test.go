package feed_delivery_page_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	client "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/recommendation"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
type recommendationCredential struct{}

func (recommendationCredential) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer test", nil
}
func TestRecommendationContinuationPostsTypedFence(t *testing.T) {
	called := false
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		if r.Method != "POST" || r.URL.RawQuery != "" {
			t.Error("retired GET/query transport")
		}
		var body map[string]json.RawMessage
		if json.NewDecoder(r.Body).Decode(&body) != nil || body["contentFence"] == nil || body["subjectId"] == nil {
			t.Error("missing typed fence")
		}
		http.Error(w, "typed dependency unavailable", 503)
	}))
	defer server.Close()
	c, err := client.NewHTTPClient(server.URL, recommendationCredential{})
	if err != nil {
		t.Fatal(err)
	}
	_, _ = c.GetPage(t.Context(), transport.GetRankedRecommendationPageQuery{WindowId: "window", SubjectId: "subject", ClientPresentationContract: transport.MissingDeclarationContentPresentationContract(), ContentFence: transport.ReleasePinnedQueryFence{Revision: 7, Release: &transport.ReleaseCandidateBinding{Environment: "gamma", SourceOwner: "qwq_data", ReleaseId: "release", ManifestDigest: "digest"}}})
	if !called {
		t.Fatal("transport not exercised")
	}
}

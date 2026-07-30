package local_contract

import (
	"net/http"
	"net/http/httptest"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	searchhttp "quwoquan_service/services/search-service/internal/search/search_query/adapters/inbound/http"
)

func TestSubjectKeyForUsesOnlyStableCanonicalIdentity(t *testing.T) {
	request := httptest.NewRequest(http.MethodPost, "/search", nil)
	request.Header.Set(searchhttp.SearchSessionIDHeader, "session-123")

	if got, err := searchhttp.SubjectKeyFor(rtsearch.Viewer{UserID: "persona-123"}, request); err != nil || got != "persona-123" {
		t.Fatalf("authenticated subjectKeyFor() = (%q, %v), want persona-123", got, err)
	}
	if got, err := searchhttp.SubjectKeyFor(rtsearch.Viewer{}, request); err != nil || got != "session-123" {
		t.Fatalf("anonymous subjectKeyFor() = (%q, %v), want session-123", got, err)
	}

	requestWithoutSession := httptest.NewRequest(http.MethodPost, "/search", nil)
	requestWithoutSession.Header.Set("X-Request-Id", "request-123")
	if got, err := searchhttp.SubjectKeyFor(rtsearch.Viewer{}, requestWithoutSession); err == nil || got != "" {
		t.Fatalf("identity-less subjectKeyFor() = (%q, %v), want explicit error", got, err)
	}
}

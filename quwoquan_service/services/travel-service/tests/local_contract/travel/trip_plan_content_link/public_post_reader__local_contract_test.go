// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
package local_contract

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/ports"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/infrastructure/contentpost"
)

func TestTripContentLinkReaderOnlyAcceptsPublicPublishedPost(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.EscapedPath() != "/content/posts/post-1" {
			t.Fatalf("path=%q", request.URL.EscapedPath())
		}
		if request.Header.Get("Authorization") != "" || request.Header.Get("Cookie") != "" {
			t.Fatalf("public Post reader inherited credentials")
		}
		_, _ = writer.Write([]byte(`{"postId":"post-1","status":"published","visibility":"public"}`))
	}))
	t.Cleanup(server.Close)
	resolver, err := contentpost.NewPublicPostResolver(server.URL, server.Client())
	if err != nil {
		t.Fatal(err)
	}
	if err := resolver.ValidateVisiblePost(t.Context(), "persona-1", "post-1", false); err != nil {
		t.Fatalf("ValidateVisiblePost() error=%v", err)
	}
}

func TestTripContentLinkReaderRejectsPrivatePostWithoutLeakingExistence(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		_, _ = writer.Write([]byte(`{"postId":"post-1","status":"published","visibility":"private"}`))
	}))
	t.Cleanup(server.Close)
	resolver, err := contentpost.NewPublicPostResolver(server.URL, server.Client())
	if err != nil {
		t.Fatal(err)
	}
	err = resolver.ValidateVisiblePost(t.Context(), "persona-1", "post-1", false)
	if !errors.Is(err, ports.ErrPostUnavailable) {
		t.Fatalf("private Post error=%v", err)
	}
}

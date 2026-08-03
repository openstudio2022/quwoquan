// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
package trip_plan_template_test

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/ports"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/infrastructure/contentreference"
)

func TestPublicPostAttributionReaderUsesCredentialFreePublicContent(t *testing.T) {
	requestedPath := ""
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		requestedPath = request.URL.EscapedPath()
		if request.Header.Get("Authorization") != "" || request.Header.Get("Cookie") != "" {
			t.Fatalf("public reference request inherited credentials")
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"postId":"post_note","authorId":"persona_guide","status":"published","visibility":"public"}`))
	}))
	t.Cleanup(server.Close)
	resolver, err := contentreference.NewPublicPostResolver(server.URL, server.Client())
	if err != nil {
		t.Fatal(err)
	}

	err = resolver.ValidatePublicAttribution(t.Context(), "persona_owner", model.Attribution{
		Kind: model.AttributionProfessionalCommentary, ReferenceObjectTypeRef: "content.Post",
		ReferenceObjectID: "post_note", AuthorPersonaID: "persona_guide",
	})
	if err != nil {
		t.Fatalf("ValidatePublicAttribution() error=%v", err)
	}
	if requestedPath != "/content/posts/post_note" {
		t.Fatalf("requested path=%q", requestedPath)
	}
}

func TestPublicPostAttributionReaderFailsClosedForInvalidOrUnavailableReference(t *testing.T) {
	tests := []struct {
		name       string
		statusCode int
		body       string
		want       error
	}{
		{name: "private", statusCode: http.StatusOK, body: `{"postId":"post_note","authorId":"persona_guide","status":"published","visibility":"private"}`, want: model.ErrInvalidArgument},
		{name: "author mismatch", statusCode: http.StatusOK, body: `{"postId":"post_note","authorId":"persona_other","status":"published","visibility":"public"}`, want: model.ErrInvalidArgument},
		{name: "not found", statusCode: http.StatusNotFound, want: model.ErrInvalidArgument},
		{name: "dependency", statusCode: http.StatusServiceUnavailable, want: ports.ErrReferenceUnavailable},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
				writer.WriteHeader(test.statusCode)
				_, _ = writer.Write([]byte(test.body))
			}))
			t.Cleanup(server.Close)
			resolver, err := contentreference.NewPublicPostResolver(server.URL, server.Client())
			if err != nil {
				t.Fatal(err)
			}
			err = resolver.ValidatePublicAttribution(t.Context(), "persona_owner", model.Attribution{
				Kind: model.AttributionProfessionalCommentary, ReferenceObjectTypeRef: "content.Post",
				ReferenceObjectID: "post_note", AuthorPersonaID: "persona_guide",
			})
			if !errors.Is(err, test.want) {
				t.Fatalf("error=%v want=%v", err, test.want)
			}
		})
	}

	resolver, err := contentreference.NewPublicPostResolver("https://content.example", http.DefaultClient)
	if err != nil {
		t.Fatal(err)
	}
	err = resolver.ValidatePublicAttribution(t.Context(), "persona_owner", model.Attribution{
		Kind: model.AttributionPublicSource, ReferenceObjectTypeRef: "assistant.WebArtifact",
		ReferenceObjectID: "artifact-1",
	})
	if !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("unsupported reference error=%v", err)
	}
}

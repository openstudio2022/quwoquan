// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-moment-content-link/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/travel-service/internal/travel/trip_moment/application"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/ports"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/infrastructure/objectreference"
)

type referenceAuthorization struct{}

func (referenceAuthorization) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer travel-service", nil
}

func TestTripMomentReadersValidateOwnerMediaPublicPostAndPublishedPlace(t *testing.T) {
	content := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.EscapedPath() {
		case "/internal/content/media/media-1:reference":
			if request.URL.Query().Get("ownerPersonaId") != "persona-1" ||
				request.Header.Get("Authorization") != "Bearer travel-service" {
				t.Fatalf("media reference request=%s auth=%q", request.URL.String(), request.Header.Get("Authorization"))
			}
			_, _ = writer.Write([]byte(`{"assetId":"media-1","ownerPersonaId":"persona-1","processingStatus":"ready","mimeType":"image/jpeg"}`))
		case "/content/posts/post-1":
			if request.Header.Get("Authorization") != "" {
				t.Fatalf("public Post request inherited service credential")
			}
			_, _ = writer.Write([]byte(`{"postId":"post-1","status":"published","visibility":"public"}`))
		default:
			http.NotFound(writer, request)
		}
	}))
	t.Cleanup(content.Close)
	entity := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.EscapedPath() != "/homepages/west-lake" || request.Header.Get("Authorization") != "" {
			t.Fatalf("Homepage request=%s auth=%q", request.URL.String(), request.Header.Get("Authorization"))
		}
		_, _ = writer.Write([]byte(`{"homepageId":"west-lake","status":"published"}`))
	}))
	t.Cleanup(entity.Close)

	contentResolver, err := objectreference.NewContentResolver(
		content.URL, content.Client(), referenceAuthorization{},
	)
	if err != nil {
		t.Fatal(err)
	}
	homepageResolver, err := objectreference.NewHomepageResolver(entity.URL, entity.Client())
	if err != nil {
		t.Fatal(err)
	}
	authority := application.NewReferenceAuthority(map[string]application.ObjectReferenceResolver{
		"content.MediaAsset": contentResolver,
		"content.Post":       contentResolver,
		"entity.Homepage":    homepageResolver,
	})
	if err := authority.ValidateMomentReferences(
		t.Context(), model.KindPhoto,
		&model.ObjectRef{ObjectTypeRef: "content.MediaAsset", ObjectID: "media-1"},
		&model.ObjectRef{ObjectTypeRef: "entity.Homepage", ObjectID: "west-lake"},
		"persona-1",
	); err != nil {
		t.Fatalf("photo references error=%v", err)
	}
	if err := authority.ValidateMomentReferences(
		t.Context(), model.KindPostReference,
		&model.ObjectRef{ObjectTypeRef: "content.Post", ObjectID: "post-1"},
		nil,
		"persona-1",
	); err != nil {
		t.Fatalf("Post reference error=%v", err)
	}
}

func TestTripMomentMediaReaderRejectsMismatchedKind(t *testing.T) {
	content := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		_, _ = writer.Write([]byte(`{"assetId":"media-1","ownerPersonaId":"persona-1","processingStatus":"ready","mimeType":"image/jpeg"}`))
	}))
	t.Cleanup(content.Close)
	resolver, err := objectreference.NewContentResolver(
		content.URL, content.Client(), referenceAuthorization{},
	)
	if err != nil {
		t.Fatal(err)
	}
	err = resolver.ValidateObjectReference(
		t.Context(),
		model.ObjectRef{ObjectTypeRef: "content.MediaAsset", ObjectID: "media-1"},
		"persona-1",
		model.KindVoice,
	)
	if !errors.Is(err, ports.ErrReferenceUnavailable) {
		t.Fatalf("mismatched media kind error=%v", err)
	}
}

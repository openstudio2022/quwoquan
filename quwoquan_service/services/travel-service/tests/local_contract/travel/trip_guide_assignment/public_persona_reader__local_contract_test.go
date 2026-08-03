// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-guide-template-assignment/spec.md#gwt-001
package trip_guide_assignment_test

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/infrastructure/userpersona"
)

func TestPublicPersonaReaderValidatesOnlyTheAssigneesPublicPersona(t *testing.T) {
	requestedPath := ""
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		requestedPath = request.URL.EscapedPath()
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"personaId":"persona_guide"}`))
	}))
	t.Cleanup(server.Close)
	resolver, err := userpersona.NewPublicPersonaResolver(server.URL, server.Client())
	if err != nil {
		t.Fatal(err)
	}

	err = resolver.ValidatePublicGuidePersona(
		t.Context(),
		"persona_guide",
		"persona_guide",
		model.RoleLicensedGuide,
	)
	if err != nil {
		t.Fatalf("ValidatePublicGuidePersona() error=%v", err)
	}
	if requestedPath != "/user/persona_guide" {
		t.Fatalf("requested path=%q", requestedPath)
	}

	err = resolver.ValidatePublicGuidePersona(
		t.Context(),
		"persona_other",
		"persona_guide",
		model.RoleLicensedGuide,
	)
	if !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("mismatched public qualification error=%v", err)
	}
}

func TestPublicPersonaReaderFailsClosedWhenProfileIsNotPublic(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.WriteHeader(http.StatusNotFound)
	}))
	t.Cleanup(server.Close)
	resolver, err := userpersona.NewPublicPersonaResolver(server.URL, server.Client())
	if err != nil {
		t.Fatal(err)
	}

	err = resolver.ValidatePublicGuidePersona(
		t.Context(),
		"persona_private",
		"persona_private",
		model.RoleLicensedGuide,
	)
	if !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("private Persona error=%v", err)
	}
}

// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-placement-collaboration/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/infrastructure/surfaceauthority"
)

type surfaceAuthorization struct{}

func (surfaceAuthorization) AuthorizationHeaderForPersona(
	_ context.Context,
	personaID string,
) (string, error) {
	return "Bearer delegated-" + personaID, nil
}

func TestPlacementSurfaceAuthorityVerifiesConversationAndCircleAdmin(t *testing.T) {
	chat := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Header.Get("Authorization") != "Bearer delegated-organizer" {
			t.Fatalf("Chat auth=%q", request.Header.Get("Authorization"))
		}
		switch request.URL.EscapedPath() {
		case "/chat/conversations/conversation-1":
			_, _ = writer.Write([]byte(`{"id":"conversation-1","membersRosterRevision":12,"status":"active"}`))
		case "/chat/conversations/conversation-1/members":
			if request.URL.Query().Get("query") != "organizer" {
				t.Fatalf("member query=%q", request.URL.RawQuery)
			}
			_, _ = writer.Write([]byte(`{"items":[{"userId":"organizer","role":"admin"}]}`))
		default:
			http.NotFound(writer, request)
		}
	}))
	t.Cleanup(chat.Close)
	circle := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Header.Get("Authorization") != "Bearer delegated-organizer" {
			t.Fatalf("Circle request=%s auth=%q", request.URL.String(), request.Header.Get("Authorization"))
		}
		switch request.URL.EscapedPath() {
		case "/circles/circle-1":
			_, _ = writer.Write([]byte(`{"data":{"id":"circle-1","version":20,"status":"active"}}`))
		case "/circles/circle-1/memberships/self":
			_, _ = writer.Write([]byte(`{"version":7,"circleId":"circle-1","personaId":"organizer","role":"owner","state":"active"}`))
		default:
			http.NotFound(writer, request)
		}
	}))
	t.Cleanup(circle.Close)
	authority, err := surfaceauthority.NewHTTPAuthority(
		chat.URL, circle.URL, chat.Client(), circle.Client(), surfaceAuthorization{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := authority.RequireAdmin(
		t.Context(), model.SurfaceConversation, "conversation-1", "organizer", 12,
	); err != nil {
		t.Fatalf("Conversation admin error=%v", err)
	}
	if err := authority.RequireMember(
		t.Context(), model.SurfaceConversation, "conversation-1", "organizer",
	); err != nil {
		t.Fatalf("Conversation member error=%v", err)
	}
	if err := authority.RequireAdmin(
		t.Context(), model.SurfaceCircle, "circle-1", "organizer", 20,
	); err != nil {
		t.Fatalf("Circle admin error=%v", err)
	}
}

func TestPlacementSurfaceAuthorityRejectsStaleOrNonAdminSurface(t *testing.T) {
	chat := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.EscapedPath() {
		case "/chat/conversations/conversation-1":
			_, _ = writer.Write([]byte(`{"id":"conversation-1","membersRosterRevision":12,"status":"active"}`))
		case "/chat/conversations/conversation-1/members":
			_, _ = writer.Write([]byte(`{"items":[{"userId":"member","role":"member"}]}`))
		}
	}))
	t.Cleanup(chat.Close)
	circle := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.EscapedPath() {
		case "/circles/circle-1":
			_, _ = writer.Write([]byte(`{"data":{"id":"circle-1","version":20,"status":"active"}}`))
		case "/circles/circle-1/memberships/self":
			_, _ = writer.Write([]byte(`{"version":7,"circleId":"circle-1","personaId":"member","role":"member","state":"active"}`))
		default:
			http.NotFound(writer, request)
		}
	}))
	t.Cleanup(circle.Close)
	authority, err := surfaceauthority.NewHTTPAuthority(
		chat.URL, circle.URL, chat.Client(), circle.Client(), surfaceAuthorization{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := authority.RequireAdmin(
		t.Context(), model.SurfaceConversation, "conversation-1", "member", 11,
	); !errors.Is(err, model.ErrInvalidArgument) {
		t.Fatalf("stale roster error=%v", err)
	}
	if err := authority.RequireAdmin(
		t.Context(), model.SurfaceCircle, "circle-1", "member", 20,
	); !errors.Is(err, model.ErrPermissionDenied) {
		t.Fatalf("non-admin Circle error=%v", err)
	}
}

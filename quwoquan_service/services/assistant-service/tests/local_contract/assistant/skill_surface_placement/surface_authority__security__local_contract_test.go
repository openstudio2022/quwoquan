// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/infrastructure/authority"
)

type delegatedSurfaceAuthorization struct{}

func (delegatedSurfaceAuthorization) AuthorizationHeaderForPersona(
	_ context.Context,
	personaID string,
) (string, error) {
	if personaID == "" {
		return "", errors.New("persona is required")
	}
	return "Bearer delegated:" + personaID, nil
}

func TestSurfaceAuthorityReadsOwnerServicesAndFailsClosed(t *testing.T) {
	t.Parallel()
	chat := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/chat/conversations/conversation-a/members" ||
			request.URL.Query().Get("query") != "persona-owner" ||
			request.Header.Get("Authorization") != "Bearer delegated:persona-owner" {
			http.Error(writer, "unexpected chat authority request", http.StatusBadRequest)
			return
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"items":[{"userId":"persona-owner","userHandle":"owner","displayName":"Owner","avatarUrl":"","role":"owner","memberType":"user","joinedAt":"2026-08-02T00:00:00Z","isCurrentUser":true}]}`))
	}))
	defer chat.Close()
	circle := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/circles/circle-a/memberships/self" ||
			request.Header.Get("Authorization") != "Bearer delegated:persona-member" {
			http.Error(writer, "unexpected circle authority request", http.StatusBadRequest)
			return
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"membershipId":"membership-a","version":1,"circleId":"circle-a","personaId":"persona-member","role":"member","state":"active","joinedAt":"2026-08-02T00:00:00Z","leftAt":null,"lastActiveAt":null,"contribution":0,"createdAt":"2026-08-02T00:00:00Z","updatedAt":"2026-08-02T00:00:00Z"}`))
	}))
	defer circle.Close()

	client, err := authority.NewClient(
		chat.URL,
		circle.URL,
		chat.Client(),
		circle.Client(),
		delegatedSurfaceAuthorization{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := client.RequireAdmin(
		context.Background(),
		"persona-owner",
		model.SurfaceConversation,
		"conversation-a",
	); err != nil {
		t.Fatalf("conversation owner authority: %v", err)
	}
	if err := client.RequireMember(
		context.Background(),
		"persona-member",
		model.SurfaceCircle,
		"circle-a",
	); err != nil {
		t.Fatalf("circle member authority: %v", err)
	}
	if err := client.RequireAdmin(
		context.Background(),
		"persona-member",
		model.SurfaceCircle,
		"circle-a",
	); !errors.Is(err, model.ErrForbidden) {
		t.Fatalf("circle member admin authority error=%v", err)
	}
}

func TestSurfaceAuthorityRejectsUnknownWireAndForbiddenStatus(t *testing.T) {
	t.Parallel()
	chat := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Query().Get("query") == "persona-forbidden" {
			http.Error(writer, "forbidden", http.StatusForbidden)
			return
		}
		_, _ = writer.Write([]byte(`{"items":[],"uncatalogued":true}`))
	}))
	defer chat.Close()
	circle := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		http.Error(writer, "unused", http.StatusNotFound)
	}))
	defer circle.Close()
	client, err := authority.NewClient(
		chat.URL,
		circle.URL,
		chat.Client(),
		circle.Client(),
		delegatedSurfaceAuthorization{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := client.RequireMember(
		context.Background(),
		"persona-forbidden",
		model.SurfaceConversation,
		"conversation-a",
	); !errors.Is(err, model.ErrForbidden) {
		t.Fatalf("forbidden status error=%v", err)
	}
	if err := client.RequireMember(
		context.Background(),
		"persona-wire-drift",
		model.SurfaceConversation,
		"conversation-a",
	); !errors.Is(err, model.ErrAuthorityUnavailable) {
		t.Fatalf("unknown wire must fail closed, error=%v", err)
	}
}

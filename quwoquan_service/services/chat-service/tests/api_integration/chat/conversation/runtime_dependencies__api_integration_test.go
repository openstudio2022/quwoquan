package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	chathttp "quwoquan_service/services/chat-service/internal/chat/conversation/adapters/inbound/http"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

func eventPublisherForContractTest() application.EventPublisher {
	return testEventPublisher
}

func groupAvatarSchedulerForContractTest() application.GroupAvatarTaskScheduler {
	return testGroupAvatarScheduler
}

func relationshipGateForContractTest(
	t *testing.T,
	defaultCapability application.RelationshipCapability,
	capabilities map[string]application.RelationshipCapability,
) application.RelationshipGate {
	t.Helper()
	server, gate := startRelationshipContractRuntime(defaultCapability, capabilities)
	t.Cleanup(server.Close)
	return gate
}

func startRelationshipContractRuntime(
	defaultCapability application.RelationshipCapability,
	capabilities map[string]application.RelationshipCapability,
) (*httptest.Server, application.RelationshipGate) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || strings.TrimSpace(r.Header.Get("X-Client-User-Id")) == "" {
			http.Error(w, "invalid relationship capability request", http.StatusBadRequest)
			return
		}
		targetID := strings.TrimSuffix(strings.TrimPrefix(
			r.URL.Path,
			"/user/personas/",
		), "/relationship/capability")
		capability := defaultCapability
		if configured, ok := capabilities[targetID]; ok {
			capability = configured
		}
		w.Header().Set("Content-Type", "application/json")
		relationState := "not_following"
		if capability.IsMutual {
			relationState = "mutual"
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"relationState":               relationState,
			"canCreateDirectConversation": capability.CanCreateDirectConversation,
			"canSendMessage":              capability.CanSendMessage,
			"hasFormalConversation":       capability.HasFormalConversation,
			"isBlocked":                   capability.IsBlocked,
			"isBlockedBy":                 capability.IsBlockedBy,
		})
	}))
	return server, chathttp.NewUserRelationshipGate(server.URL, server.Client())
}

func TestRelationshipContractDependenciesAreExplicit(t *testing.T) {
	t.Parallel()
	if eventPublisherForContractTest() == nil || groupAvatarSchedulerForContractTest() == nil ||
		testGroupAvatarMedia == nil || testUserSyncPublisher == nil {
		t.Fatal("relationship contract dependencies must be explicitly configured")
	}
}

func TestAuthorizedRelationshipGateDelegatesViewerPersona(t *testing.T) {
	tokenConfig := rtauth.TokenConfig{
		Secret:       []byte("0123456789abcdef0123456789abcdef"),
		Issuer:       "https://auth.quwoquan.test",
		Audience:     "quwoquan-api",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          5 * time.Minute,
		ClockSkew:    5 * time.Second,
	}
	verifier, err := rtauth.NewHS256Verifier(tokenConfig)
	if err != nil {
		t.Fatalf("new verifier: %v", err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authorization := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
		claims, verifyErr := verifier.Verify(authorization)
		if verifyErr != nil {
			http.Error(w, "invalid delegated authorization", http.StatusUnauthorized)
			return
		}
		if claims.Subject != "service:chat-service" ||
			claims.Persona != "viewer-persona" ||
			claims.Scope != "user.relationship.read" {
			http.Error(w, "delegated principal drift", http.StatusForbidden)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"relationState":               "mutual",
			"canCreateDirectConversation": true,
			"canSendMessage":              true,
		})
	}))
	defer server.Close()

	credentials, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		tokenConfig,
		"chat-service",
		[]string{"user.relationship.read"},
	)
	if err != nil {
		t.Fatalf("new delegated credentials: %v", err)
	}
	gate, err := chathttp.NewAuthorizedUserRelationshipGate(
		server.URL,
		server.Client(),
		credentials,
	)
	if err != nil {
		t.Fatalf("new authorized relationship gate: %v", err)
	}

	capability, err := gate.GetCapability(
		context.Background(),
		"viewer-persona",
		"target-persona",
	)
	if err != nil {
		t.Fatalf("get relationship capability: %v", err)
	}
	if !capability.IsMutual || !capability.CanSendMessage ||
		!capability.CanCreateDirectConversation {
		t.Fatalf("delegated capability=%+v", capability)
	}
	if _, err := chathttp.NewAuthorizedUserRelationshipGate(
		server.URL,
		server.Client(),
		nil,
	); err == nil {
		t.Fatal("production relationship gate accepted missing delegated credentials")
	}
}

package api_integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

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
			"/user/sub-accounts/",
		), "/relationship/capability")
		capability := defaultCapability
		if configured, ok := capabilities[targetID]; ok {
			capability = configured
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]bool{
			"canCreateDirectConversation": capability.CanCreateDirectConversation,
			"canSendMessage":              capability.CanSendMessage,
			"hasFormalConversation":       capability.HasFormalConversation,
			"isMutual":                    capability.IsMutual,
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

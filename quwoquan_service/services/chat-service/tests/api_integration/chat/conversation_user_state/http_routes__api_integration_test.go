// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: mark-as-read-api
// readiness_case: update-conversation-settings-api
package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	userstatehttp "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/adapters/inbound/http"
	userstateapp "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/application"
)

type userStateBackend struct {
	read     userstateapp.MarkAsReadRequest
	settings userstateapp.UpdateSettingsRequest
}

func (backend *userStateBackend) MarkAsRead(_ context.Context, request userstateapp.MarkAsReadRequest) error {
	backend.read = request
	return nil
}

func (backend *userStateBackend) UpdateSettings(_ context.Context, request userstateapp.UpdateSettingsRequest) error {
	backend.settings = request
	return nil
}

func TestConversationUserStateHTTPUsesTrustedPersonaAndStrictWire(t *testing.T) {
	backend := &userStateBackend{}
	routes := http.NewServeMux()
	userstatehttp.NewHandler(backend, backend).Register(routes)

	request := httptest.NewRequest(
		http.MethodPatch,
		"/chat/conversations/conversation-1/settings",
		strings.NewReader(`{"muted":true}`),
	)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{PersonaID: "trusted-persona"},
	}))
	response := httptest.NewRecorder()
	routes.ServeHTTP(response, request)
	if response.Code != http.StatusOK || backend.settings.UserId != "trusted-persona" ||
		backend.settings.ConversationId != "conversation-1" || backend.settings.Muted == nil ||
		!*backend.settings.Muted {
		t.Fatalf("typed settings command drifted: status=%d request=%+v", response.Code, backend.settings)
	}

	readRequest := httptest.NewRequest(
		http.MethodPost,
		"/chat/conversations/conversation-1/messages/message-7/read",
		nil,
	)
	readRequest = readRequest.WithContext(rtauth.WithPrincipal(readRequest.Context(), rtauth.Principal{
		Actor: operation.ActorContext{PersonaID: "trusted-persona"},
	}))
	readResponse := httptest.NewRecorder()
	routes.ServeHTTP(readResponse, readRequest)
	if readResponse.Code != http.StatusOK || backend.read.ConversationId != "conversation-1" ||
		backend.read.MessageId != "message-7" || backend.read.UserId != "trusted-persona" {
		t.Fatalf("typed read command drifted: status=%d request=%+v", readResponse.Code, backend.read)
	}

	invalid := httptest.NewRequest(
		http.MethodPatch,
		"/chat/conversations/conversation-1/settings",
		strings.NewReader(`{"muted":true,"retiredMuted":true}`),
	)
	invalidResponse := httptest.NewRecorder()
	routes.ServeHTTP(invalidResponse, invalid)
	if invalidResponse.Code != http.StatusBadRequest {
		t.Fatalf("second wire key must fail closed: status=%d body=%s", invalidResponse.Code, invalidResponse.Body.String())
	}
}

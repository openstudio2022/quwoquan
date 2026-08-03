// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	messagehttp "quwoquan_service/services/chat-service/internal/chat/message/adapters/inbound/http"
	messageapp "quwoquan_service/services/chat-service/internal/chat/message/application"
)

type messageBackend struct {
	sent messageapp.SendMessageRequest
}

func (backend *messageBackend) SendMessage(
	_ context.Context,
	request messageapp.SendMessageRequest,
) (*messageapp.SendMessageResponse, error) {
	backend.sent = request
	return &messageapp.SendMessageResponse{
		MessageId: "message-1", Seq: 7, Timestamp: "2026-08-02T12:00:00Z",
	}, nil
}

func (*messageBackend) SendAssistantDeliveryMessage(
	context.Context,
	messageapp.AssistantDeliveryMessageRequest,
) (*messageapp.SendMessageResponse, error) {
	return &messageapp.SendMessageResponse{}, nil
}

func (*messageBackend) RecallMessage(context.Context, string, string, string) error { return nil }
func (*messageBackend) ListMessages(context.Context, messageapp.ListMessagesRequest) ([]messageapp.MessageSlice, error) {
	return []messageapp.MessageSlice{}, nil
}
func (*messageBackend) ListAssistantGroundingMessages(context.Context, string, string, string, int64, int) ([]messageapp.MessageSlice, error) {
	return []messageapp.MessageSlice{}, nil
}
func (*messageBackend) SyncMessages(context.Context, messageapp.SyncMessagesRequest) (*messageapp.SyncMessagesResponse, error) {
	return &messageapp.SyncMessagesResponse{}, nil
}

func TestMessageHTTPRoutesUseTrustedPersonaAndTypedCommand(t *testing.T) {
	backend := &messageBackend{}
	routes := http.NewServeMux()
	messagehttp.NewHandler(backend).Register(routes)
	request := httptest.NewRequest(
		http.MethodPost,
		"/chat/conversations/conversation-1/messages",
		strings.NewReader(`{"type":"text","content":"hello","clientMsgId":"client-message-1","personaContextVersion":3}`),
	)
	request.Header.Set("X-Client-Persona-Id", "untrusted-persona")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-1", PersonaID: "trusted-persona"},
	}))
	response := httptest.NewRecorder()
	routes.ServeHTTP(response, request)
	if response.Code != http.StatusCreated {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	if backend.sent.ConversationId != "conversation-1" ||
		backend.sent.SenderId != "trusted-persona" ||
		backend.sent.ClientMsgId != "client-message-1" ||
		backend.sent.PersonaContextVersion != 3 {
		t.Fatalf("typed command drifted: %+v", backend.sent)
	}
	var body map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["messageId"] != "message-1" || body["seq"] != float64(7) {
		t.Fatalf("typed response drifted: %v", body)
	}
}

func TestMessageHTTPRoutesRejectUnknownWireField(t *testing.T) {
	routes := http.NewServeMux()
	messagehttp.NewHandler(&messageBackend{}).Register(routes)
	request := httptest.NewRequest(
		http.MethodPost,
		"/chat/conversations/conversation-1/messages",
		strings.NewReader(`{"type":"text","content":"hello","clientMsgId":"client-message-1","legacyType":"v2"}`),
	)
	response := httptest.NewRecorder()
	routes.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("unknown wire field must fail, status=%d body=%s", response.Code, response.Body.String())
	}
}

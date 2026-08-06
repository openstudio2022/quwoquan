// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: send-message-api
// readiness_case: list-assistant-grounding-messages-api
// readiness_case: send-assistant-delivery-message-api
// readiness_case: recall-message-api
// readiness_case: list-messages-api
// readiness_case: sync-messages-api
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
	sent  messageapp.SendMessageRequest
	calls map[string]int
}

func (backend *messageBackend) record(name string) {
	if backend.calls == nil {
		backend.calls = map[string]int{}
	}
	backend.calls[name]++
}

func (backend *messageBackend) SendMessage(
	_ context.Context,
	request messageapp.SendMessageRequest,
) (*messageapp.SendMessageResponse, error) {
	backend.record("SendMessage")
	backend.sent = request
	return &messageapp.SendMessageResponse{
		MessageId: "message-1", Seq: 7, Timestamp: "2026-08-02T12:00:00Z",
	}, nil
}

func (backend *messageBackend) SendAssistantDeliveryMessage(
	context.Context,
	messageapp.AssistantDeliveryMessageRequest,
) (*messageapp.SendMessageResponse, error) {
	backend.record("SendAssistantDeliveryMessage")
	return &messageapp.SendMessageResponse{MessageId: "assistant-message-1", Seq: 8}, nil
}

func (backend *messageBackend) RecallMessage(context.Context, string, string, string) error {
	backend.record("RecallMessage")
	return nil
}
func (backend *messageBackend) ListMessages(context.Context, messageapp.ListMessagesRequest) ([]messageapp.MessageSlice, error) {
	backend.record("ListMessages")
	return []messageapp.MessageSlice{}, nil
}
func (backend *messageBackend) ListAssistantGroundingMessages(context.Context, string, string, int64, int) ([]messageapp.MessageSlice, error) {
	backend.record("ListAssistantGroundingMessages")
	return []messageapp.MessageSlice{}, nil
}
func (backend *messageBackend) SyncMessages(context.Context, messageapp.SyncMessagesRequest) (*messageapp.SyncMessagesResponse, error) {
	backend.record("SyncMessages")
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

func TestMessageHTTPRoutesExecuteEveryCanonicalOperation(t *testing.T) {
	backend := &messageBackend{calls: map[string]int{}}
	routes := http.NewServeMux()
	messagehttp.NewHandler(backend).Register(routes)
	principal := rtauth.Principal{Actor: operation.ActorContext{AccountID: "account-1", PersonaID: "persona-1"}}
	cases := []struct {
		method, path, body string
		status             int
	}{
		{http.MethodPost, "/chat/conversations/conversation-1/messages", `{"type":"text","content":"hello","clientMsgId":"client-1"}`, http.StatusCreated},
		{http.MethodGet, "/chat/conversations/conversation-1/messages?limit=20", "", http.StatusOK},
		{http.MethodPost, "/chat/conversations/conversation-1/messages/message-1/recall", "", http.StatusOK},
		{http.MethodPost, "/chat/conversations/conversation-1/sync", `{"lastSeq":6,"limit":20}`, http.StatusOK},
		{http.MethodGet, "/internal/chat/conversations/conversation-1/assistant-grounding-messages?creatorPersonaId=persona-1&limit=20", "", http.StatusOK},
		{http.MethodPost, "/internal/chat/conversations/conversation-1/assistant-delivery-messages?creatorPersonaId=persona-1", `{"type":"text","content":"answer","clientMsgId":"assistant-client-1"}`, http.StatusCreated},
	}
	for _, item := range cases {
		request := httptest.NewRequest(item.method, item.path, strings.NewReader(item.body))
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
		response := httptest.NewRecorder()
		routes.ServeHTTP(response, request)
		if response.Code != item.status {
			t.Fatalf("%s %s status=%d want=%d body=%s", item.method, item.path, response.Code, item.status, response.Body.String())
		}
	}
	for _, name := range []string{"SendMessage", "ListMessages", "RecallMessage", "SyncMessages", "ListAssistantGroundingMessages", "SendAssistantDeliveryMessage"} {
		if backend.calls[name] != 1 {
			t.Fatalf("%s calls=%d want=1", name, backend.calls[name])
		}
	}
}

func TestMessageHTTPRoutesRejectUnknownWireField(t *testing.T) {
	routes := http.NewServeMux()
	messagehttp.NewHandler(&messageBackend{}).Register(routes)
	request := httptest.NewRequest(
		http.MethodPost,
		"/chat/conversations/conversation-1/messages",
		strings.NewReader(`{"type":"text","content":"hello","clientMsgId":"client-message-1","retiredType":"unsupported"}`),
	)
	response := httptest.NewRecorder()
	routes.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("unknown wire field must fail, status=%d body=%s", response.Code, response.Body.String())
	}
}

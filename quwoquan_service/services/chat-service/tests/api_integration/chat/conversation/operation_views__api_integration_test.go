// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-003
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-002
// readiness_case: list-message-home-api
// readiness_case: list-contact-home-api
// readiness_case: project-gathering-conversation-api
// readiness_case: get-gathering-chat-board-api
package api_integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
)

func TestConversationViewRoutesAndGatheringProjectionUseProductionHTTPAndStores(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	conversation := createConversation(t, `{"type":"group","title":"readiness views"}`)
	conversationID := conversation["id"].(string)
	for _, path := range []string{"/chat/message-home", "/chat/contact-home"} {
		status, body := doGet(t, path, "user_test_001")
		if status != http.StatusOK || body["items"] == nil {
			t.Fatalf("GET %s status=%d body=%#v", path, status, body)
		}
	}
	status, body := doCircleGatheringPut(
		t,
		"/internal/chat/gathering-conversations/gathering-readiness-1",
		`{"sourceEventId":"gathering-readiness-1:create:1","sourceVersion":1,"ownerPersonaId":"user_test_001","title":"readiness gathering","accessMode":"active","postingPolicy":"member_chat"}`,
	)
	if status != http.StatusOK || body["conversationId"] == nil {
		t.Fatalf("gathering projection status=%d body=%#v existing=%s", status, body, conversationID)
	}
	gatheringConversationID := body["conversationId"].(string)
	status, board := doGet(
		t,
		"/chat/gathering-conversations/"+gatheringConversationID+"/board",
		"user_test_001",
	)
	access, _ := board["access"].(map[string]any)
	if status != http.StatusOK || access["gatheringId"] != "gathering-readiness-1" ||
		access["accessMode"] != "active" || access["postingPolicy"] != "member_chat" ||
		access["canPost"] != true || board["assets"] == nil {
		t.Fatalf("Gathering Board Chat slice status=%d body=%#v", status, board)
	}

	status, updated := doCircleGatheringPut(
		t,
		"/internal/chat/gathering-conversations/gathering-readiness-1",
		`{"sourceEventId":"gathering-readiness-1:cancelled:2","sourceVersion":2,"ownerPersonaId":"user_test_001","title":"readiness gathering","accessMode":"read_only","postingPolicy":"member_chat"}`,
	)
	if status != http.StatusOK || updated["conversationId"] != gatheringConversationID {
		t.Fatalf("read_only projection changed room: status=%d body=%#v", status, updated)
	}
	failure := doPost(
		t,
		"/chat/conversations/"+gatheringConversationID+"/messages",
		`{"type":"text","content":"must be blocked","clientMsgId":"gathering-read-only-1"}`,
		"user_test_001",
		http.StatusForbidden,
	)
	if failure["code"] != "CHAT.USER.blocked" {
		t.Fatalf("read_only public SendMessage must fail closed: %#v", failure)
	}

	status, stale := doCircleGatheringPut(
		t,
		"/internal/chat/gathering-conversations/gathering-readiness-1",
		`{"sourceEventId":"gathering-readiness-1:create:1","sourceVersion":1,"ownerPersonaId":"user_test_001","title":"readiness gathering","accessMode":"active","postingPolicy":"member_chat"}`,
	)
	if status != http.StatusOK || stale["conversationId"] != gatheringConversationID {
		t.Fatalf("stale room projection failed idempotently: status=%d body=%#v", status, stale)
	}
	status, board = doGet(
		t,
		"/chat/gathering-conversations/"+gatheringConversationID+"/board",
		"user_test_001",
	)
	access, _ = board["access"].(map[string]any)
	if status != http.StatusOK || access["accessMode"] != "read_only" || access["canPost"] != false {
		t.Fatalf("stale source version regressed Board access: status=%d body=%#v", status, board)
	}
}

func doCircleGatheringPut(t *testing.T, path, payload string) (int, map[string]any) {
	t.Helper()
	request := httptest.NewRequest(http.MethodPut, path, strings.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{
			Subject: "service:circle-service", Scope: "chat.gathering.write", Roles: []string{"service"},
		},
		Actor: operation.ActorContext{AccountID: "service:circle-service"},
	}))
	response := httptest.NewRecorder()
	testHandler.ServeHTTP(response, request)
	var body map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode Circle projection response: %v body=%s", err, response.Body.String())
	}
	return response.Code, body
}

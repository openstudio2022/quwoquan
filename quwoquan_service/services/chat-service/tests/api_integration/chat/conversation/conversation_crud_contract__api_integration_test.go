package api_integration

import (
	"net/http"
	"testing"
)

func TestCreateConversation(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	result := createConversation(t, `{"type":"group","title":"测试群聊","maxGroupSize":500}`)

	if result["id"] == nil {
		t.Error("response missing _id")
	}
	if result["type"] != "group" {
		t.Errorf("expected type=group, got %v", result["type"])
	}
	if result["title"] != "测试群聊" {
		t.Errorf("expected title=测试群聊, got %v", result["title"])
	}
	if result["status"] != "active" {
		t.Errorf("expected status=active, got %v", result["status"])
	}
	if result["memberCount"] == nil {
		t.Error("response missing memberCount")
	}
}

func TestGetConversation(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	created := createConversation(t, `{"type":"direct","title":"私聊","initialMemberIds":["user_test_002"]}`)
	convId := created["id"].(string)

	code, result := doGet(t, "/chat/conversations/"+convId, "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	if result["id"] != convId {
		t.Errorf("expected _id=%s, got %v", convId, result["id"])
	}
}

func TestListConversations(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	createConversation(t, `{"type":"group","title":"群聊1"}`)
	createConversation(t, `{"type":"group","title":"群聊2"}`)

	code, result := doGet(t, "/chat/conversations?limit=1", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items array")
	}
	if len(items) != 1 {
		t.Fatalf("expected exactly one first-page conversation, got %d", len(items))
	}
	nextCursor, ok := result["nextCursor"].(string)
	if !ok || nextCursor == "" {
		t.Fatalf("first page must return nextCursor, got %#v", result)
	}
	if _, retiredCursorPresent := result["cursor"]; retiredCursorPresent {
		t.Fatalf("response must not emit retired cursor key: %#v", result)
	}

	code, secondPage := doGet(
		t,
		"/chat/conversations?limit=1&cursor="+nextCursor,
		"user_test_001",
	)
	if code != 200 {
		t.Fatalf("second page expected 200, got %d", code)
	}
	secondItems, ok := secondPage["items"].([]any)
	if !ok || len(secondItems) != 1 {
		t.Fatalf("second page must have one remaining conversation, got %#v", secondPage)
	}
	if _, terminalCursorPresent := secondPage["nextCursor"]; terminalCursorPresent {
		t.Fatalf("terminal page must omit nextCursor: %#v", secondPage)
	}
}

func TestListConversationsRejectsIdentifierOnlyCursor(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	createConversation(t, `{"type":"group","title":"cursor test"}`)

	code, result := doGet(
		t,
		"/chat/conversations?cursor=conversation_id_is_not_a_keyset_token",
		"user_test_001",
	)
	if code != http.StatusBadRequest {
		t.Fatalf("invalid cursor status = %d, want %d: %#v", code, http.StatusBadRequest, result)
	}
	if got := result["code"]; got != "CHAT.USER.invalid_argument" {
		t.Fatalf("invalid cursor code = %#v, want CHAT.USER.invalid_argument", got)
	}
}

func TestGetConversation_NotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	code, _ := doGet(t, "/chat/conversations/nonexistent_id_xyz", "user_test_001")
	if code != 404 {
		t.Fatalf("expected 404, got %d", code)
	}
}

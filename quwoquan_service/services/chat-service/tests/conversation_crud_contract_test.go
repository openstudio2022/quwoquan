package tests

import (
	"testing"
)

func TestCreateConversation(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	result := createConversation(t, `{"type":"group","title":"测试群聊","maxGroupSize":500}`)

	if result["_id"] == nil {
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

	created := createConversation(t, `{"type":"direct","title":"私聊"}`)
	convId := created["_id"].(string)

	code, result := doGet(t, "/v1/chat/conversations/"+convId, "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	if result["_id"] != convId {
		t.Errorf("expected _id=%s, got %v", convId, result["_id"])
	}
}

func TestListConversations(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	createConversation(t, `{"type":"group","title":"群聊1"}`)
	createConversation(t, `{"type":"group","title":"群聊2"}`)

	code, result := doGet(t, "/v1/chat/conversations?limit=10", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := result["items"].([]any)
	if !ok {
		t.Fatal("response missing items array")
	}
	if len(items) < 2 {
		t.Errorf("expected >=2 conversations, got %d", len(items))
	}
}

func TestGetConversation_NotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	code, _ := doGet(t, "/v1/chat/conversations/nonexistent_id_xyz", "user_test_001")
	if code != 404 {
		t.Fatalf("expected 404, got %d", code)
	}
}

package tests

import (
	"net/http"
	"testing"
)

func TestContractFixtureSeed_ChatAlphaReadsViaHandler(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	evidence := seedChatContractFixture(t, "chat_core")
	if evidence.InsertedCount < 10 {
		t.Fatalf("expected seeded chat records, got %d", evidence.InsertedCount)
	}

	code, inbox := doGet(t, "/v1/chat/inbox?limit=20", "fixture_user_current")
	if code != http.StatusOK {
		t.Fatalf("inbox expected 200, got %d: %+v", code, inbox)
	}
	assertItemsContainID(t, inbox["items"], "fixture_conv_direct")
	assertItemsContainID(t, inbox["items"], "fixture_conv_group")

	code, detail := doGet(t, "/v1/chat/conversations/fixture_conv_direct", "fixture_user_current")
	if code != http.StatusOK {
		t.Fatalf("conversation detail expected 200, got %d: %+v", code, detail)
	}
	if detail["_id"] != "fixture_conv_direct" && detail["id"] != "fixture_conv_direct" {
		t.Fatalf("unexpected conversation detail: %+v", detail)
	}

	code, messages := doGet(t, "/v1/chat/conversations/fixture_conv_direct/messages?limit=20", "fixture_user_current")
	if code != http.StatusOK {
		t.Fatalf("messages expected 200, got %d: %+v", code, messages)
	}
	assertItemsContainID(t, messages["items"], "fixture_msg_direct_1")
	assertItemsContainText(t, messages["items"], "契约消息已送达")

	code, members := doGet(t, "/v1/chat/conversations/fixture_conv_direct/members?limit=20", "fixture_user_current")
	if code != http.StatusOK {
		t.Fatalf("members expected 200, got %d: %+v", code, members)
	}
	assertItemsContainUserID(t, members["items"], "fixture_user_current")
	assertItemsContainUserID(t, members["items"], "fixture_user_friend")
}

func assertItemsContainID(t *testing.T, raw any, id string) {
	t.Helper()
	items, ok := raw.([]any)
	if !ok {
		t.Fatalf("items is not list: %#v", raw)
	}
	for _, item := range items {
		obj, ok := item.(map[string]any)
		if !ok {
			continue
		}
		if obj["id"] == id || obj["_id"] == id || obj["conversationId"] == id || obj["messageId"] == id {
			return
		}
	}
	t.Fatalf("items did not contain id %s: %+v", id, items)
}

func assertItemsContainUserID(t *testing.T, raw any, userID string) {
	t.Helper()
	items, ok := raw.([]any)
	if !ok {
		t.Fatalf("items is not list: %#v", raw)
	}
	for _, item := range items {
		obj, ok := item.(map[string]any)
		if ok && obj["userId"] == userID {
			return
		}
	}
	t.Fatalf("items did not contain user %s: %+v", userID, items)
}

func assertItemsContainText(t *testing.T, raw any, fragment string) {
	t.Helper()
	items, ok := raw.([]any)
	if !ok {
		t.Fatalf("items is not list: %#v", raw)
	}
	for _, item := range items {
		obj, ok := item.(map[string]any)
		if !ok {
			continue
		}
		if value, ok := obj["content"].(string); ok && contains(value, fragment) {
			return
		}
	}
	t.Fatalf("items did not contain text %q: %+v", fragment, items)
}

func contains(value, fragment string) bool {
	for i := 0; i+len(fragment) <= len(value); i++ {
		if value[i:i+len(fragment)] == fragment {
			return true
		}
	}
	return fragment == ""
}

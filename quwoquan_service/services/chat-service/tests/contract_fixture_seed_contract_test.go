package tests

import (
	"net/http"
	"strings"
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
	if avatarURL, _ := detail["avatarUrl"].(string); !strings.HasPrefix(avatarURL, "http://127.0.0.1:18081/media/avatar/user/") {
		t.Fatalf("expected direct conversation avatar to resolve to public media url, got %+v", detail)
	}

	code, groupDetail := doGet(t, "/v1/chat/conversations/fixture_conv_group", "fixture_user_current")
	if code != http.StatusOK {
		t.Fatalf("group detail expected 200, got %d: %+v", code, groupDetail)
	}
	if got := int(groupDetail["groupAvatarVersion"].(float64)); got <= 0 {
		t.Fatalf("expected seeded group avatar backfill to populate version, got %+v", groupDetail)
	}
	if avatarURL, _ := groupDetail["avatarUrl"].(string); !strings.HasPrefix(avatarURL, "http://127.0.0.1:18081/media/avatar/conversation/fixture_conv_group/") {
		t.Fatalf("expected group conversation avatar to resolve via derived media url, got %+v", groupDetail)
	}

	code, circleBoundDetail := doGet(t, "/v1/chat/conversations/fixture_conv_photo_group", "fixture_user_current")
	if code != http.StatusOK {
		t.Fatalf("circle-bound group detail expected 200, got %d: %+v", code, circleBoundDetail)
	}
	if circleBoundDetail["type"] != "group" {
		t.Fatalf("expected circle-bound conversation to expose type=group, got %+v", circleBoundDetail)
	}
	if circleBoundDetail["circleId"] != "fixture_circle_photo" {
		t.Fatalf("expected fixture circle id to survive seeding, got %+v", circleBoundDetail)
	}
	if avatarURL, _ := circleBoundDetail["avatarUrl"].(string); !strings.HasPrefix(avatarURL, "http://127.0.0.1:18081/media/avatar/conversation/fixture_conv_photo_group/") {
		t.Fatalf("expected circle-bound group avatar to resolve via derived media url, got %+v", circleBoundDetail)
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

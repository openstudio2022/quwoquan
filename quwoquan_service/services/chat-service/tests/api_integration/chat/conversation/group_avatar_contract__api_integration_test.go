package api_integration

import (
	"strings"
	"testing"
)

func TestGroupAvatar_GetConversationReturnsPrecomposedAvatar(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"group avatar test"}`)
	convId := conv["id"].(string)
	waitForConversationAvatarVersion(t, convId, 1)

	code, result := doGet(t, "/chat/conversations/"+convId, "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	avatarURL, _ := result["avatarUrl"].(string)
	if avatarURL == "" {
		t.Fatal("expected non-empty avatarUrl in conversation detail")
	}
	if !strings.Contains(avatarURL, "/media/avatar/s/conversation/"+convId+"/") {
		t.Fatalf("expected precomposed conversation avatar URL, got %q", avatarURL)
	}
	version, ok := result["groupAvatarVersion"].(float64)
	if !ok || int(version) <= 0 {
		t.Fatalf("expected groupAvatarVersion > 0, got %v", result["groupAvatarVersion"])
	}
}

func TestGroupAvatar_InboxReturnsPrecomposedAvatar(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"group avatar inbox"}`)
	convId := conv["id"].(string)
	waitForConversationAvatarVersion(t, convId, 1)

	code, inbox := doGet(t, "/chat/inbox?limit=50", "user_test_001")
	if code != 200 {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := inbox["items"].([]any)
	if !ok {
		t.Fatal("response missing items")
	}
	for _, item := range items {
		row, _ := item.(map[string]any)
		if row["id"] != convId {
			continue
		}
		avatarURL, _ := row["avatarUrl"].(string)
		if avatarURL == "" {
			t.Fatal("expected non-empty avatarUrl in inbox row")
		}
		if !strings.Contains(avatarURL, "/media/avatar/s/conversation/"+convId+"/") {
			t.Fatalf("expected precomposed conversation avatar URL in inbox, got %q", avatarURL)
		}
		return
	}
	t.Fatal("conversation not found in inbox")
}

func TestGroupAvatar_VersionBumpsWhenTopNineChanges(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"group avatar bump"}`)
	convId := conv["id"].(string)
	waitForConversationAvatarVersion(t, convId, 1)

	_, before := doGet(t, "/chat/conversations/"+convId, "user_test_001")
	beforeVersion, _ := before["groupAvatarVersion"].(float64)

	doPost(
		t,
		"/chat/conversations/"+convId+"/members",
		`{"userIds":["group_avatar_new_member"]}`,
		"user_test_001",
		200,
	)

	waitForConversationAvatarVersion(t, convId, int(beforeVersion)+1)
	_, after := doGet(t, "/chat/conversations/"+convId, "user_test_001")
	afterVersion, _ := after["groupAvatarVersion"].(float64)
	if int(afterVersion) <= int(beforeVersion) {
		t.Fatalf("expected groupAvatarVersion to increase, before=%v after=%v", beforeVersion, afterVersion)
	}
}

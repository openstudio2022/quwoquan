package tests

import (
	"context"
	"testing"
	"time"

	runtimesync "quwoquan_service/runtime/sync"
)

func TestGroupAvatar_RecomputePublishesConversationAvatarPatch(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"group avatar sync patch"}`)
	convID := conv["_id"].(string)
	syncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))

	var last runtimesync.Patch
	for i := 0; i < 40; i++ {
		resp, err := syncService.Pull(context.Background(), "user_test_001", 0, 20)
		if err != nil {
			t.Fatalf("Pull: %v", err)
		}
		if len(resp.Patches) == 0 {
			time.Sleep(20 * time.Millisecond)
			continue
		}
		last = resp.Patches[len(resp.Patches)-1]
		if last.Type == "conversation.avatar.updated" && last.Payload["conversationId"] == convID {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if last.Type != "conversation.avatar.updated" {
		t.Fatalf("expected conversation.avatar.updated, got %s", last.Type)
	}
	if last.Payload["conversationId"] != convID {
		t.Fatalf("expected conversationId=%s got %v", convID, last.Payload["conversationId"])
	}
	if last.Payload["avatarUrl"] == "" {
		t.Fatal("expected avatarUrl in patch payload")
	}
}

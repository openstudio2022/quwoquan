package tests

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	runtimesync "quwoquan_service/runtime/sync"
)

func TestGroupAvatar_UserAvatarUpdatedRecomputesWhenMemberIsTopNine(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{
		"type":"group",
		"title":"top9 avatar refresh",
		"initialMemberIds":[
			"user_test_002","user_test_003","user_test_004","user_test_005","user_test_006",
			"user_test_007","user_test_008","user_test_009","user_test_010"
		]
	}`)
	convID := conv["_id"].(string)
	beforeVersion := int(mustConversationAvatarVersion(t, convID))
	syncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	beforeSeq := latestSyncSeq(t, syncService, "user_test_001")

	publishUserAvatarUpdated(t, "user_test_001", "ua_user_test_001", 2, "https://test.avatar/user_test_001?v=2")
	waitForConversationAvatarVersion(t, convID, beforeVersion+1)

	afterVersion := int(mustConversationAvatarVersion(t, convID))
	if afterVersion <= beforeVersion {
		t.Fatalf("expected version increase, before=%d after=%d", beforeVersion, afterVersion)
	}

	resp, err := syncService.Pull(context.Background(), "user_test_001", beforeSeq, 20)
	if err != nil {
		t.Fatalf("Pull: %v", err)
	}
	if len(resp.Patches) == 0 {
		t.Fatal("expected conversation avatar patch after top9 user avatar update")
	}
	last := resp.Patches[len(resp.Patches)-1]
	if last.Type != "conversation.avatar.updated" {
		t.Fatalf("expected conversation.avatar.updated, got %s", last.Type)
	}
	if last.Payload["conversationId"] != convID {
		t.Fatalf("expected conversationId=%s, got %v", convID, last.Payload["conversationId"])
	}
}

func TestGroupAvatar_UserAvatarUpdatedSkipsWhenMemberIsOutsideTopNine(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{
		"type":"group",
		"title":"non top9 avatar refresh",
		"initialMemberIds":[
			"user_test_002","user_test_003","user_test_004","user_test_005","user_test_006",
			"user_test_007","user_test_008","user_test_009","user_test_010"
		]
	}`)
	convID := conv["_id"].(string)
	beforeVersion := int(mustConversationAvatarVersion(t, convID))
	syncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))
	beforeSeq := latestSyncSeq(t, syncService, "user_test_001")

	publishUserAvatarUpdated(t, "user_test_010", "ua_user_test_010", 2, "https://test.avatar/user_test_010?v=2")
	time.Sleep(150 * time.Millisecond)

	afterVersion := int(mustConversationAvatarVersion(t, convID))
	if afterVersion != beforeVersion {
		t.Fatalf("expected version unchanged for non-top9 member, before=%d after=%d", beforeVersion, afterVersion)
	}

	resp, err := syncService.Pull(context.Background(), "user_test_001", beforeSeq, 20)
	if err != nil {
		t.Fatalf("Pull: %v", err)
	}
	if len(resp.Patches) != 0 {
		t.Fatalf("expected no new conversation avatar patch, got %d", len(resp.Patches))
	}
}

func TestGroupAvatar_UserAvatarUpdatedDoesNotBumpWhenSourceHashUnchanged(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{
		"type":"group",
		"title":"duplicate avatar refresh",
		"initialMemberIds":[
			"user_test_002","user_test_003","user_test_004","user_test_005","user_test_006",
			"user_test_007","user_test_008","user_test_009"
		]
	}`)
	convID := conv["_id"].(string)
	beforeVersion := int(mustConversationAvatarVersion(t, convID))
	syncService := runtimesync.NewService(redisRouter.Scene("general"), redisRouter.Scene("realtime"))

	publishUserAvatarUpdated(t, "user_test_001", "ua_user_test_001", 2, "https://test.avatar/user_test_001?v=2")
	waitForConversationAvatarVersion(t, convID, beforeVersion+1)
	afterFirstVersion := int(mustConversationAvatarVersion(t, convID))
	beforeSeq := latestSyncSeq(t, syncService, "user_test_001")

	publishUserAvatarUpdated(t, "user_test_001", "ua_user_test_001", 2, "https://test.avatar/user_test_001?v=2")
	time.Sleep(150 * time.Millisecond)

	afterSecondVersion := int(mustConversationAvatarVersion(t, convID))
	if afterSecondVersion != afterFirstVersion {
		t.Fatalf("expected version unchanged on duplicate update, first=%d second=%d", afterFirstVersion, afterSecondVersion)
	}
	resp, err := syncService.Pull(context.Background(), "user_test_001", beforeSeq, 20)
	if err != nil {
		t.Fatalf("Pull: %v", err)
	}
	if len(resp.Patches) != 0 {
		t.Fatalf("expected no duplicate patch after unchanged source hash, got %d", len(resp.Patches))
	}
}

func publishUserAvatarUpdated(t *testing.T, userID, assetID string, version int64, avatarURL string) {
	t.Helper()
	event := map[string]any{
		"type":      "UserAvatarUpdated",
		"userId":    userID,
		"actorId":   userID,
		"timestamp": time.Now().UTC().Format(time.RFC3339Nano),
		"payload": map[string]any{
			"userId":        userID,
			"avatarAssetId": assetID,
			"avatarVersion": version,
			"avatarUrl":     avatarURL,
		},
	}
	body, err := json.Marshal(event)
	if err != nil {
		t.Fatalf("marshal user avatar event: %v", err)
	}
	if err := redisRouter.Scene("general").Publish(context.Background(), "event:user-profile", string(body)); err != nil {
		t.Fatalf("publish user avatar event: %v", err)
	}
}

func waitForConversationAvatarVersion(t *testing.T, conversationID string, expectedMin int) {
	t.Helper()
	for i := 0; i < 30; i++ {
		if int(mustConversationAvatarVersion(t, conversationID)) >= expectedMin {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatalf("conversation %s avatar version did not reach %d", conversationID, expectedMin)
}

func mustConversationAvatarVersion(t *testing.T, conversationID string) float64 {
	t.Helper()
	code, detail := doGet(t, "/v1/chat/conversations/"+conversationID, "user_test_001")
	if code != 200 {
		t.Fatalf("get conversation %s: expected 200 got %d", conversationID, code)
	}
	version, ok := detail["groupAvatarVersion"].(float64)
	if !ok {
		t.Fatalf("conversation %s missing groupAvatarVersion: %v", conversationID, detail)
	}
	return version
}

func latestSyncSeq(t *testing.T, syncService *runtimesync.Service, userID string) int64 {
	t.Helper()
	resp, err := syncService.Pull(context.Background(), userID, 0, 200)
	if err != nil {
		t.Fatalf("Pull latest sync seq for %s: %v", userID, err)
	}
	return resp.LatestSyncSeq
}

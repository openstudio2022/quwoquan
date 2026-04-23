package runtimesync

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

func TestService_AppendAndPull(t *testing.T) {
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "memory"},
			"realtime": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() {
		_ = router.Close()
	})
	service := NewService(router.Scene("general"), router.Scene("realtime"))

	patch1, err := service.AppendPatch(context.Background(), "user_001", "user.avatar.updated", map[string]any{
		"userId":        "user_001",
		"avatarVersion": 2,
	})
	if err != nil {
		t.Fatalf("AppendPatch patch1: %v", err)
	}
	patch2, err := service.AppendPatch(context.Background(), "user_001", "conversation.avatar.updated", map[string]any{
		"conversationId": "conv_001",
	})
	if err != nil {
		t.Fatalf("AppendPatch patch2: %v", err)
	}

	if patch1.SyncSeq != 1 || patch2.SyncSeq != 2 {
		t.Fatalf("expected sync seq 1,2 got %d,%d", patch1.SyncSeq, patch2.SyncSeq)
	}

	resp, err := service.Pull(context.Background(), "user_001", 0, 10)
	if err != nil {
		t.Fatalf("Pull: %v", err)
	}
	if resp.LatestSyncSeq != 2 {
		t.Fatalf("expected latestSyncSeq=2 got %d", resp.LatestSyncSeq)
	}
	if resp.HasMore {
		t.Fatal("expected hasMore=false")
	}
	if resp.RequiresResync {
		t.Fatal("expected requiresResync=false")
	}
	if len(resp.Patches) != 2 {
		t.Fatalf("expected 2 patches got %d", len(resp.Patches))
	}
	if resp.Patches[0].Type != "user.avatar.updated" || resp.Patches[1].Type != "conversation.avatar.updated" {
		t.Fatalf("unexpected patch order: %+v", resp.Patches)
	}
}

func TestService_PullRequiresResyncWhenGapDetected(t *testing.T) {
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "memory"},
			"realtime": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() {
		_ = router.Close()
	})
	service := NewService(router.Scene("general"), router.Scene("realtime"))

	if _, err := service.AppendPatch(context.Background(), "user_001", "user.avatar.updated", map[string]any{
		"userId": "user_001",
	}); err != nil {
		t.Fatalf("AppendPatch patch1: %v", err)
	}
	if _, err := service.AppendPatch(context.Background(), "user_001", "conversation.avatar.updated", map[string]any{
		"conversationId": "conv_001",
	}); err != nil {
		t.Fatalf("AppendPatch patch2: %v", err)
	}
	if err := service.dataClient.Del(context.Background(), service.patchKey("user_001", 1)); err != nil {
		t.Fatalf("Del patch1: %v", err)
	}

	resp, err := service.Pull(context.Background(), "user_001", 0, 10)
	if err != nil {
		t.Fatalf("Pull: %v", err)
	}
	if !resp.RequiresResync {
		t.Fatal("expected requiresResync=true when patch gap exists")
	}
	if len(resp.Patches) != 0 {
		t.Fatalf("expected no patches after gap detection, got %d", len(resp.Patches))
	}
}

func TestService_AppendPatchBatchAndMetrics(t *testing.T) {
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "memory"},
			"realtime": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() {
		_ = router.Close()
	})
	service := NewService(router.Scene("general"), router.Scene("realtime"))

	result, err := service.AppendPatchBatch(
		context.Background(),
		[]string{"user_001", "user_002", "user_001"},
		"conversation.avatar.updated",
		map[string]any{"conversationId": "conv_001"},
	)
	if err != nil {
		t.Fatalf("AppendPatchBatch: %v", err)
	}
	if len(result.FailedUserIDs) != 0 {
		t.Fatalf("expected no failed recipients, got %+v", result.FailedUserIDs)
	}
	if len(result.Patches) != 2 {
		t.Fatalf("expected 2 stored patches, got %d", len(result.Patches))
	}

	resp, err := service.Pull(context.Background(), "user_002", 0, 10)
	if err != nil {
		t.Fatalf("Pull user_002: %v", err)
	}
	if len(resp.Patches) != 1 {
		t.Fatalf("expected 1 patch for user_002, got %d", len(resp.Patches))
	}

	metrics := service.MetricsSnapshot()
	if metrics[metricSyncAppendBatchTotal] != 1 {
		t.Fatalf("expected append batch metric = 1, got %v", metrics[metricSyncAppendBatchTotal])
	}
	if metrics[metricSyncPullTotal] <= 0 {
		t.Fatalf("expected pull metric recorded, got %v", metrics[metricSyncPullTotal])
	}
}

func TestService_PullSupportsLongOfflineCatchupInBatches(t *testing.T) {
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "memory"},
			"realtime": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() {
		_ = router.Close()
	})
	service := NewService(router.Scene("general"), router.Scene("realtime"))

	for i := 0; i < 450; i++ {
		if _, err := service.AppendPatch(context.Background(), "user_001", "conversation.avatar.updated", map[string]any{
			"conversationId": "conv_001",
			"version":        i + 1,
		}); err != nil {
			t.Fatalf("AppendPatch #%d: %v", i, err)
		}
	}

	var afterSeq int64
	totalPulled := 0
	for rounds := 0; rounds < 4; rounds++ {
		resp, err := service.Pull(context.Background(), "user_001", afterSeq, 200)
		if err != nil {
			t.Fatalf("Pull round %d: %v", rounds, err)
		}
		if resp.RequiresResync {
			t.Fatal("expected no requiresResync during chunked catchup")
		}
		totalPulled += len(resp.Patches)
		if len(resp.Patches) > 0 {
			afterSeq = resp.Patches[len(resp.Patches)-1].SyncSeq
		}
		if !resp.HasMore {
			break
		}
	}

	if totalPulled != 450 {
		t.Fatalf("expected to pull 450 patches, got %d", totalPulled)
	}
}

func TestService_PullRequiresResyncWhenPatchExpired(t *testing.T) {
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "memory"},
			"realtime": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() {
		_ = router.Close()
	})
	service := NewService(
		router.Scene("general"),
		router.Scene("realtime"),
		WithPatchTTL(5*time.Millisecond),
	)

	if _, err := service.AppendPatch(context.Background(), "user_001", "conversation.avatar.updated", map[string]any{
		"conversationId": "conv_001",
	}); err != nil {
		t.Fatalf("AppendPatch: %v", err)
	}
	time.Sleep(15 * time.Millisecond)

	resp, err := service.Pull(context.Background(), "user_001", 0, 10)
	if err != nil {
		t.Fatalf("Pull: %v", err)
	}
	if !resp.RequiresResync {
		t.Fatal("expected requiresResync after patch expiry")
	}
	if len(resp.Patches) != 0 {
		t.Fatalf("expected no patches after expiry gap, got %d", len(resp.Patches))
	}
}

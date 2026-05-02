package reliabletask

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"

	rtredis "quwoquan_service/runtime/redis"
)

func TestRedisReadyIndexStandaloneStreamsClaimAck(t *testing.T) {
	redisAddr := os.Getenv("TEST_REDIS_ADDR")
	if redisAddr == "" {
		mr := miniredis.RunT(t)
		redisAddr = mr.Addr()
	}
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"reliabletask": {Mode: "standalone", Addr: redisAddr},
		},
		DefaultScene: "reliabletask",
	})
	t.Cleanup(func() { _ = router.Close() })

	index, err := NewRedisReadyIndex(RedisReadyIndexConfig{
		Client: router.Scene("reliabletask"),
		Stream: "reliabletask:chat:avatar:ready:test:" + newID("stream"),
		Group:  "chat.group_avatar_worker.alpha",
		Queue:  "reliabletask.chat.avatar",
	})
	if err != nil {
		t.Fatalf("new ready index: %v", err)
	}
	if err := index.Ensure(context.Background()); err != nil {
		t.Fatalf("ensure ready index: %v", err)
	}
	if err := index.EnqueueReadyOrMerge(context.Background(), ReliableAsyncTask{
		TaskID:         "task-1",
		OutboxID:       "outbox-1",
		TaskType:       "chat.group_avatar.recompute",
		DedupeKey:      "chat.group_avatar.recompute:conv-1",
		IdempotencyKey: "chat.group_avatar.recompute:conv-1",
	}); err != nil {
		t.Fatalf("enqueue ready task: %v", err)
	}
	messages, err := index.Claim(context.Background(), "worker-a", 10, time.Millisecond)
	if err != nil {
		t.Fatalf("claim ready task: %v", err)
	}
	if len(messages) != 1 || messages[0].TaskID != "task-1" {
		t.Fatalf("messages = %#v, want task-1", messages)
	}
	if err := index.Ack(context.Background(), messages[0]); err != nil {
		t.Fatalf("ack ready task: %v", err)
	}
	if err := index.Ack(context.Background(), messages[0]); err != nil {
		t.Fatalf("idempotent ack ready task: %v", err)
	}
	messages, err = index.Claim(context.Background(), "worker-a", 10, time.Millisecond)
	if err != nil {
		t.Fatalf("claim after ack: %v", err)
	}
	if len(messages) != 0 {
		t.Fatalf("expected no messages after ack, got %#v", messages)
	}
}

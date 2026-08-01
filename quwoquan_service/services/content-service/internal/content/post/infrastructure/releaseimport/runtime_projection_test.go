package releaseimport

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	goredis "github.com/redis/go-redis/v9"
)

func TestPublishImportedPostLifecycleUsesCanonicalRedisDatabase(t *testing.T) {
	server := miniredis.RunT(t)
	now := time.Date(2026, 8, 1, 2, 49, 50, 0, time.UTC)
	post := PostDoc{
		PostRef:     "video/体验/候选投影/1",
		ContentType: "video",
		AuthorID:    "builtin_travel_blogger",
		TagRefs:     []string{"Topic/旅行"},
		EntityRefs:  []string{"entity/travel"},
		Angle:       "体验",
		PublishedAt: now.Add(-time.Hour),
		UpdatedAt:   now.Add(-time.Minute),
	}

	count, err := PublishImportedPostLifecycle(
		context.Background(),
		server.Addr(),
		1,
		[]PostDoc{post},
		ImportOptions{
			ReleaseID:         "release-a",
			SourceOwner:       "qwq_data",
			ProjectionVersion: 42,
		},
		now,
	)
	if err != nil {
		t.Fatalf("publish imported lifecycle: %v", err)
	}
	if count != 1 {
		t.Fatalf("published count=%d, want 1", count)
	}

	db0 := goredis.NewClient(&goredis.Options{Addr: server.Addr(), DB: 0})
	db1 := goredis.NewClient(&goredis.Options{Addr: server.Addr(), DB: 1})
	t.Cleanup(func() {
		_ = db0.Close()
		_ = db1.Close()
	})
	if got := db0.XLen(context.Background(), "events.content.post_lifecycle").Val(); got != 0 {
		t.Fatalf("db0 lifecycle length=%d, want 0", got)
	}
	messages, err := db1.XRange(
		context.Background(),
		"events.content.post_lifecycle",
		"-",
		"+",
	).Result()
	if err != nil {
		t.Fatalf("read db1 lifecycle: %v", err)
	}
	if len(messages) != 1 {
		t.Fatalf("db1 lifecycle messages=%d, want 1", len(messages))
	}
	values := messages[0].Values
	if values["eventType"] != "PostPublished" ||
		values["aggregateId"] != RuntimePostID(post.PostRef) ||
		values["aggregateVersion"] != "42" {
		t.Fatalf("unexpected lifecycle values: %#v", values)
	}
}

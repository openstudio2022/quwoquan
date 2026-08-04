// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
package releaseimport_test

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	goredis "github.com/redis/go-redis/v9"

	releaseimport "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestPublishImportedPostLifecycleUsesCanonicalRedisDatabase(t *testing.T) {
	server := miniredis.RunT(t)
	now := time.Date(2026, 8, 1, 2, 49, 50, 0, time.UTC)
	post := releaseimport.PostDoc{
		PostRef:         "video/体验/候选投影/1",
		ContentType:     "video",
		ContentIdentity: "work",
		AuthorID:        "builtin_travel_blogger",
		TagRefs:         []string{"Topic/旅行"},
		EntityRefs:      []string{"entity/travel"},
		Angle:           "体验",
		CreatedAt:       now.Add(-2 * time.Hour),
		PublishedAt:     now.Add(-time.Hour),
		UpdatedAt:       now.Add(-time.Minute),
	}

	count, err := releaseimport.PublishImportedPostLifecycle(
		context.Background(),
		server.Addr(),
		1,
		[]releaseimport.PostDoc{post},
		[]string{"removed-post"},
		releaseimport.ImportOptions{
			ReleaseID:         "release-a",
			SourceOwner:       "qwq_data",
			ProjectionVersion: 42,
		},
		now,
	)
	if err != nil {
		t.Fatalf("publish imported lifecycle: %v", err)
	}
	if count != 2 {
		t.Fatalf("published count=%d, want 2", count)
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
	if len(messages) != 2 {
		t.Fatalf("db1 lifecycle messages=%d, want 2", len(messages))
	}
	values := messages[0].Values
	if values["eventType"] != "PostPublished" ||
		values["aggregateId"] != releaseimport.RuntimePostID(post.PostRef) ||
		values["aggregateVersion"] != "42" {
		t.Fatalf("unexpected lifecycle values: %#v", values)
	}
	deleted := messages[1].Values
	if deleted["eventType"] != "PostDeleted" ||
		deleted["aggregateId"] != "removed-post" ||
		deleted["aggregateVersion"] != "42" {
		t.Fatalf("unexpected deletion lifecycle values: %#v", deleted)
	}
}

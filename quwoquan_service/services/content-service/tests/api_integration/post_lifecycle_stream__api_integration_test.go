package api_integration

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	postapp "quwoquan_service/services/content-service/internal/application/post"
	contentmessaging "quwoquan_service/services/content-service/internal/infrastructure/messaging"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

func TestPostOutboxPublishesTypedLifecycleToRealRedisStream(t *testing.T) {
	cleanPosts(t)
	t.Cleanup(func() { cleanPosts(t) })
	ctx := context.Background()
	created := createPostWithAuthor(t, "persona-stream-owner", `{
		"contentType":"micro",
		"contentIdentity":"moment",
		"body":"durable stream contract"
	}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatalf("published Post has no id: %#v", created)
	}

	store := persistence.NewMongoPostStore(mongoDB.Collection("posts"))
	relay := postapp.NewOutboxRelay(
		store,
		store,
		contentmessaging.NewPostLifecycleStreamPublisher(requireTestRouter(t).Scene("general")),
		"api-integration-post-lifecycle-"+postID,
	)
	count, err := relay.Drain(ctx, 100)
	if err != nil {
		t.Fatalf("drain Post lifecycle stream: %v", err)
	}
	if count < 2 {
		t.Fatalf("expected PostCreated and PostPublished, got %d events", count)
	}

	group := "circle-api-integration-" + strings.ReplaceAll(postID, ":", "-")
	redisClient := requireTestRouter(t).Scene("general")
	if err := redisClient.XGroupCreateMkStream(ctx, contentmessaging.PostLifecycleStream, group, "0"); err != nil {
		t.Fatal(err)
	}
	messages, err := redisClient.XReadGroup(ctx, group, "reader",
		map[string]string{contentmessaging.PostLifecycleStream: ">"}, 100, 0)
	if err != nil {
		t.Fatal(err)
	}
	types := map[string]bool{}
	for _, message := range messages {
		if message.Values["aggregateId"] != postID {
			continue
		}
		types[message.Values["eventType"]] = true
		var payload struct {
			ID       string `json:"_id"`
			AuthorID string `json:"authorId"`
		}
		if err := json.Unmarshal([]byte(message.Values["payload"]), &payload); err != nil {
			t.Fatalf("decode stream payload: %v", err)
		}
		if payload.ID != postID || payload.AuthorID != "persona-stream-owner" {
			t.Fatalf("stream payload identity drift: %#v", payload)
		}
		if message.Values["eventId"] == "" || message.Values["aggregateVersion"] == "" {
			t.Fatalf("stream lost durable identity: %#v", message.Values)
		}
	}
	if !types["PostCreated"] || !types["PostPublished"] {
		t.Fatalf("lifecycle event types=%#v", types)
	}
}

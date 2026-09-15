package testsupport

import (
	"context"
	"encoding/json"
	model "quwoquan_service/services/content-service/generated/content/post/contract/model"
	ports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestTypedPostStoreSafetyRevisionAndAtomicity(t *testing.T) {
	s := NewPostStore(nil)
	ctx := context.Background()
	c := ports.Commit{Post: &model.Post{ID: "post", Status: "published", Visibility: "public", ModerationStatus: "approved"}, IdempotencyKey: "create", CommandName: "Create", CommandDigest: "create", ReceiptExpiresAt: time.Now().Add(time.Hour), Events: []ports.OutboxEvent{{EventType: "PostPublished", Payload: json.RawMessage(`{"environment":null}`)}}}
	first, err := s.Commit(ctx, c)
	if err != nil {
		t.Fatal(err)
	}
	if s.safety["post"].revision != 1 {
		t.Fatal("explicit create did not initialize")
	}
	replay, err := s.Commit(ctx, c)
	if err != nil || !replay.Replayed || len(s.OutboxEvents()) != 1 {
		t.Fatal("replay changed state", err)
	}
	c.CommandDigest = "different"
	if _, err = s.Commit(ctx, c); err == nil {
		t.Fatal("different digest replay accepted")
	}
	next := *first.Post
	next.Visibility = "private"
	c.Post = &next
	c.ExpectedVersion = 1
	c.IdempotencyKey = "restrict"
	c.CommandDigest = "restrict"
	c.Events[0].EventType = "PostSettingsUpdated"
	if _, err = s.Commit(ctx, c); err != nil {
		t.Fatal(err)
	}
	if s.safety["post"].revision != 2 {
		t.Fatal("restriction did not advance")
	}
	c.ExpectedVersion = 2
	c.IdempotencyKey = "bad"
	c.Events[0].Payload = json.RawMessage(`{`)
	if _, err = s.Commit(ctx, c); err == nil {
		t.Fatal("invalid wire accepted")
	}
	if s.safety["post"].version != 2 || len(s.OutboxEvents()) != 2 {
		t.Fatal("failed commit leaked state")
	}
	c.IdempotencyKey = "delete"
	c.CommandDigest = "delete"
	next.Status = "deleted"
	c.Events[0].Payload = json.RawMessage(`{}`)
	c.Events[0].EventType = "PostDeleted"
	if _, err = s.Commit(ctx, c); err != nil {
		t.Fatal(err)
	}
	c.ExpectedVersion = 3
	c.IdempotencyKey = "restore"
	next.Status = "published"
	next.Visibility = "public"
	if _, err = s.Commit(ctx, c); err == nil {
		t.Fatal("terminal restored")
	}
	var wire map[string]any
	events := s.OutboxEvents()
	_ = json.Unmarshal(events[2].Payload, &wire)
	if wire["safetyRevision"] != float64(3) || wire["sourceVersion"] != float64(3) {
		t.Fatal(wire)
	}
	delete(s.safety, "post")
	if _, err = s.Commit(ctx, c); err == nil {
		t.Fatal("missing safety silently initialized")
	}
}

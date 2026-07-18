// L2 契约测试：Post 业务对象 — 领域事件发布
package api_integration

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestAtomicPostPublicationEvent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	eventSpy.Reset()

	created := submitPublishedPost(t, `{"contentType":"image","title":"Event test"}`)
	postID, _ := created["postId"].(string)

	events := eventSpy.EventsOfType("PostPublished")
	if len(events) != 1 {
		t.Fatalf("expected 1 PostPublished event, got %d", len(events))
	}
	ev := events[0]
	if ev.AggregateType != "Post" {
		t.Errorf("aggregateType: %s", ev.AggregateType)
	}
	if ev.AggregateID != postID {
		t.Errorf("aggregateID: want %s, got %s", postID, ev.AggregateID)
	}
	if ev.Payload["contentType"] != "image" {
		t.Errorf("payload.contentType: %v", ev.Payload["contentType"])
	}
	if ev.OccurredAt == "" {
		t.Error("occurredAt must not be empty")
	}
}

func TestCommentDeletedEvent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	cleanPosts(t)
	eventSpy.Reset()

	postID := createCommentTestPost(t, "event-post-owner")
	comment := createCommentThroughAPI(t, postID, "event-comment-owner", "to be deleted for event", "")
	eventSpy.Reset()

	deleted := commentAPIRequest(t, http.MethodDelete,
		"/content/posts/"+postID+"/comments/"+comment.ID,
		"event-comment-owner", map[string]any{"version": comment.Version})
	if deleted.Code != http.StatusOK {
		t.Fatalf("delete Comment: %d body=%s", deleted.Code, deleted.Body.String())
	}

	events := eventSpy.EventsOfType("CommentDeleted")
	if len(events) != 1 {
		t.Fatalf("expected 1 CommentDeleted event, got %d", len(events))
	}
	ev := events[0]
	if ev.AggregateType != "Comment" {
		t.Errorf("aggregateType: %s", ev.AggregateType)
	}
	if ev.AggregateID != comment.ID || ev.Payload["commentId"] != comment.ID {
		t.Errorf("CommentDeleted identity: want %s, got aggregate=%s payload=%v", comment.ID, ev.AggregateID, ev.Payload["commentId"])
	}
}

func TestPostSettingsUpdatedEvent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPostWithAuthor(t, "settings_event_author", `{
		"contentType":"article",
		"title":"Event settings",
		"body":"正文"
	}`)
	postID, _ := created["postId"].(string)

	eventSpy.Reset()

	req := httptest.NewRequest(
		http.MethodPatch,
		"/content/posts/"+postID+"/settings",
		strings.NewReader(`{"visibility":"public","assistantUsePolicy":"exclude"}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "settings_event_author")
	ensureIdempotencyHeader(req, "settings-event")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("update settings: %d", rec.Code)
	}

	events := eventSpy.EventsOfType("PostSettingsUpdated")
	if len(events) != 1 {
		t.Fatalf("expected 1 PostSettingsUpdated event, got %d", len(events))
	}
	ev := events[0]
	if ev.Payload["assistantUsePolicy"] != "exclude" {
		t.Errorf("payload.assistantUsePolicy: %v", ev.Payload["assistantUsePolicy"])
	}
	if ev.Payload["visibility"] != "public" {
		t.Errorf("payload.visibility: %v", ev.Payload["visibility"])
	}
	if _, exists := ev.Payload["addedCircleIds"]; exists {
		t.Fatalf("PostSettingsUpdated must not carry CirclePostPlacement state: %#v", ev.Payload)
	}
}

func TestPostPromotedToWorkEvent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPostWithAuthor(t, "promote_event_author", `{
		"contentType":"micro",
		"body":"从点滴升级"
	}`)
	postID, _ := created["postId"].(string)

	eventSpy.Reset()

	req := httptest.NewRequest(
		http.MethodPost,
		"/content/posts/"+postID+":promoteToWork",
		strings.NewReader(`{"contentType":"image","title":"升级后的作品"}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "promote_event_author")
	ensureIdempotencyHeader(req, "promote-event")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("promote post: %d", rec.Code)
	}

	events := eventSpy.EventsOfType("PostPromotedToWork")
	if len(events) != 1 {
		t.Fatalf("expected 1 PostPromotedToWork event, got %d", len(events))
	}
	ev := events[0]
	if ev.Payload["contentIdentity"] != "work" {
		t.Errorf("payload.contentIdentity: %v", ev.Payload["contentIdentity"])
	}
	if ev.Payload["contentType"] != "image" {
		t.Errorf("payload.contentType: %v", ev.Payload["contentType"])
	}
}

func TestPostDeletedEvent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPostWithAuthor(t, "delete_event_author", `{
		"contentType":"image",
		"visibility":"public"
	}`)
	postID, _ := created["postId"].(string)

	eventSpy.Reset()

	req := httptest.NewRequest(http.MethodDelete, "/content/posts/"+postID, nil)
	req.Header.Set("X-Client-User-Id", "delete_event_author")
	ensureIdempotencyHeader(req, "delete-event")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("delete post: %d", rec.Code)
	}

	events := eventSpy.EventsOfType("PostDeleted")
	if len(events) != 1 {
		t.Fatalf("expected 1 PostDeleted event, got %d", len(events))
	}
	ev := events[0]
	if ev.AggregateID != postID {
		t.Errorf("aggregateID: want %s, got %s", postID, ev.AggregateID)
	}
	if ev.Payload["deletedAt"] == "" {
		t.Error("payload.deletedAt must not be empty")
	}
	if ev.Payload["status"] != "published" {
		t.Fatalf("payload.status should keep pre-delete status, got %#v", ev.Payload["status"])
	}
	if _, exists := ev.Payload["circleIds"]; exists {
		t.Fatalf("PostDeleted must not carry CirclePostPlacement state: %#v", ev.Payload)
	}
}

func TestNoSpuriousEventsOnRead(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPost(t, `{"contentType":"image","title":"Read no event"}`)
	postID, _ := created["postId"].(string)

	eventSpy.Reset()

	getReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID, nil)
	getRec := httptest.NewRecorder()
	testHandler.ServeHTTP(getRec, getReq)

	listReq := httptest.NewRequest(http.MethodGet, "/content/posts/"+postID+"/counters", nil)
	listRec := httptest.NewRecorder()
	testHandler.ServeHTTP(listRec, listReq)

	if eventSpy.Count() != 0 {
		t.Errorf("read operations should not emit events, got %d", eventSpy.Count())
	}
}

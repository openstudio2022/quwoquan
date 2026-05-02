// L2 契约测试：Post 业务对象 — 领域事件发布
package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestPostCreatedEvent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	eventSpy.Reset()

	created := createPost(t, `{"contentType":"image","title":"Event test","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	events := eventSpy.EventsOfType("PostCreated")
	if len(events) != 1 {
		t.Fatalf("expected 1 PostCreated event, got %d", len(events))
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
	eventSpy.Reset()

	created := createPost(t, `{"contentType":"image","title":"Event delete test","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	eventSpy.Reset()

	body := `{"content":"to be deleted for event"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/comments", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "event_user")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("create comment: %d", rec.Code)
	}
	var createResp map[string]any
	json.Unmarshal(rec.Body.Bytes(), &createResp)
	comment, _ := createResp["comment"].(map[string]any)
	commentID, _ := comment["_id"].(string)

	eventSpy.Reset()

	delReq := httptest.NewRequest(http.MethodDelete, "/v1/content/posts/"+postID+"/comments/"+commentID, nil)
	delReq.Header.Set("X-Client-User-Id", "event_user")
	delRec := httptest.NewRecorder()
	testHandler.ServeHTTP(delRec, delReq)
	if delRec.Code != http.StatusNoContent {
		t.Fatalf("delete comment: %d", delRec.Code)
	}

	events := eventSpy.EventsOfType("CommentDeleted")
	if len(events) != 1 {
		t.Fatalf("expected 1 CommentDeleted event, got %d", len(events))
	}
	ev := events[0]
	if ev.AggregateType != "Post" {
		t.Errorf("aggregateType: %s", ev.AggregateType)
	}
	if ev.Payload["commentId"] != commentID {
		t.Errorf("payload.commentId: want %s, got %v", commentID, ev.Payload["commentId"])
	}
}

func TestPostSettingsUpdatedEvent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPostWithAuthor(t, "settings_event_author", `{
		"contentType":"article",
		"title":"Event settings",
		"body":"正文"
	}`)
	postID, _ := created["_id"].(string)

	eventSpy.Reset()

	req := httptest.NewRequest(
		http.MethodPatch,
		"/v1/content/posts/"+postID+"/settings",
		strings.NewReader(`{"visibility":"public","assistantUsePolicy":"exclude"}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "settings_event_author")
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
}

func TestPostPromotedToWorkEvent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPostWithAuthor(t, "promote_event_author", `{
		"contentType":"micro",
		"body":"从点滴升级"
	}`)
	postID, _ := created["_id"].(string)

	eventSpy.Reset()

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+":promoteToWork",
		strings.NewReader(`{"contentType":"image","title":"升级后的作品"}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "promote_event_author")
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
	created := createPostWithAuthor(t, "delete_event_author", `{
		"contentType":"image",
		"mediaUrls":["https://example.com/img.jpg"]
	}`)
	postID, _ := created["_id"].(string)

	eventSpy.Reset()

	req := httptest.NewRequest(http.MethodDelete, "/v1/content/posts/"+postID, nil)
	req.Header.Set("X-Client-User-Id", "delete_event_author")
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
}

func TestNoSpuriousEventsOnRead(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Read no event","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)

	eventSpy.Reset()

	getReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	getRec := httptest.NewRecorder()
	testHandler.ServeHTTP(getRec, getReq)

	listReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID+"/counters", nil)
	listRec := httptest.NewRecorder()
	testHandler.ServeHTTP(listRec, listReq)

	if eventSpy.Count() != 0 {
		t.Errorf("read operations should not emit events, got %d", eventSpy.Count())
	}
}

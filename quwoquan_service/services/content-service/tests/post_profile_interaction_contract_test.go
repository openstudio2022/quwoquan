package tests

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestProfileInteractionActivitiesReceived(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(
		t,
		"author_profile_subject",
		`{"contentType":"image","title":"互动流目标内容","mediaUrls":["https://example.com/profile.jpg"]}`,
	)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("missing post id")
	}

	likeReq := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/like", nil)
	likeReq.Header.Set("X-Client-User-Id", "actor_like")
	likeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(likeRec, likeReq)
	if likeRec.Code != http.StatusOK {
		t.Fatalf("like post failed: %d %s", likeRec.Code, likeRec.Body.String())
	}

	commentReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+"/comments",
		strings.NewReader(`{"content":"评论互动"}`),
	)
	commentReq.Header.Set("Content-Type", "application/json")
	commentReq.Header.Set("X-Client-User-Id", "actor_comment")
	commentRec := httptest.NewRecorder()
	testHandler.ServeHTTP(commentRec, commentReq)
	if commentRec.Code != http.StatusCreated {
		t.Fatalf("comment post failed: %d %s", commentRec.Code, commentRec.Body.String())
	}

	if _, err := testPostService.RepostToCircle(
		context.Background(),
		postID,
		"actor_share",
		"circle_profile_interaction",
		"",
	); err != nil {
		t.Fatalf("repost to circle failed: %v", err)
	}

	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/profile-subjects/author_profile_subject/interactions/received?limit=10",
		nil,
	)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("list received interactions: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode received interactions: %v", err)
	}
	items, _ := body["items"].([]any)
	if len(items) < 3 {
		t.Fatalf("expected at least 3 interaction items, got %d", len(items))
	}

	seen := map[string]bool{}
	for _, raw := range items {
		item, _ := raw.(map[string]any)
		seen[item["activityType"].(string)] = true
		if item["direction"] != "received" {
			t.Fatalf("expected received direction, got %v", item["direction"])
		}
	}
	for _, expected := range []string{"like", "comment", "share"} {
		if !seen[expected] {
			t.Fatalf("expected activityType=%s in received list, got %#v", expected, seen)
		}
	}
}

func TestProfileInteractionActivitiesSent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPostWithAuthor(
		t,
		"author_for_sent",
		`{"contentType":"image","title":"发出互动目标","mediaUrls":["https://example.com/sent.jpg"]}`,
	)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("missing post id")
	}

	commentReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+"/comments",
		strings.NewReader(`{"content":"我发出的评论"}`),
	)
	commentReq.Header.Set("Content-Type", "application/json")
	commentReq.Header.Set("X-Client-User-Id", "actor_sent_comment")
	commentRec := httptest.NewRecorder()
	testHandler.ServeHTTP(commentRec, commentReq)
	if commentRec.Code != http.StatusCreated {
		t.Fatalf("comment post failed: %d %s", commentRec.Code, commentRec.Body.String())
	}

	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/profile-subjects/actor_sent_comment/interactions/sent?limit=10",
		nil,
	)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("list sent interactions: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode sent interactions: %v", err)
	}
	items, _ := body["items"].([]any)
	if len(items) == 0 {
		t.Fatal("expected at least one sent interaction item")
	}
	item, _ := items[0].(map[string]any)
	if item["direction"] != "sent" {
		t.Fatalf("expected direction=sent, got %v", item["direction"])
	}
	if item["activityType"] != "comment" {
		t.Fatalf("expected activityType=comment, got %v", item["activityType"])
	}
	if item["actorProfileSubjectId"] != "actor_sent_comment" {
		t.Fatalf("expected actorProfileSubjectId=actor_sent_comment, got %v", item["actorProfileSubjectId"])
	}
}

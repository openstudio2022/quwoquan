package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestContractFixtureSeed_ContentAlphaReadsViaHandler(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	evidence := seedContentContractFixture(t, "content_discovery_core")
	if evidence.InsertedCount < 4 {
		t.Fatalf("expected at least 4 seeded content records, got %d", evidence.InsertedCount)
	}

	feedReq := httptest.NewRequest(http.MethodGet, "/v1/content/feed?limit=10", nil)
	feedRec := httptest.NewRecorder()
	testHandler.ServeHTTP(feedRec, feedReq)
	if feedRec.Code != http.StatusOK {
		t.Fatalf("feed expected 200, got %d: %s", feedRec.Code, feedRec.Body.String())
	}
	var feed map[string]any
	if err := json.Unmarshal(feedRec.Body.Bytes(), &feed); err != nil {
		t.Fatalf("decode feed: %v", err)
	}
	assertItemsContainID(t, feed["items"], "fixture_photo_001")
	assertItemsContainID(t, feed["items"], "fixture_article_001")

	getReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/fixture_photo_001", nil)
	getRec := httptest.NewRecorder()
	testHandler.ServeHTTP(getRec, getReq)
	if getRec.Code != http.StatusOK {
		t.Fatalf("get post expected 200, got %d: %s", getRec.Code, getRec.Body.String())
	}
	var detail map[string]any
	if err := json.Unmarshal(getRec.Body.Bytes(), &detail); err != nil {
		t.Fatalf("decode detail: %v", err)
	}
	if detail["_id"] != "fixture_photo_001" && detail["id"] != "fixture_photo_001" {
		t.Fatalf("detail did not return fixture photo: %+v", detail)
	}

	commentsReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/fixture_photo_001/comments?limit=10", nil)
	commentsRec := httptest.NewRecorder()
	testHandler.ServeHTTP(commentsRec, commentsReq)
	if commentsRec.Code != http.StatusOK {
		t.Fatalf("comments expected 200, got %d: %s", commentsRec.Code, commentsRec.Body.String())
	}
	var comments map[string]any
	if err := json.Unmarshal(commentsRec.Body.Bytes(), &comments); err != nil {
		t.Fatalf("decode comments: %v", err)
	}
	assertItemsContainText(t, comments["items"], "这是一条契约评论")

	reactionReq := httptest.NewRequest(http.MethodGet, "/v1/content/posts/fixture_photo_001/reactions", nil)
	reactionReq.Header.Set("X-Client-User-Id", "fixture_user_current")
	reactionRec := httptest.NewRecorder()
	testHandler.ServeHTTP(reactionRec, reactionReq)
	if reactionRec.Code != http.StatusOK {
		t.Fatalf("reaction expected 200, got %d: %s", reactionRec.Code, reactionRec.Body.String())
	}
	var reaction map[string]any
	if err := json.Unmarshal(reactionRec.Body.Bytes(), &reaction); err != nil {
		t.Fatalf("decode reaction: %v", err)
	}
	if reaction["liked"] != true || reaction["favorited"] != true {
		t.Fatalf("expected seeded reaction state, got %+v", reaction)
	}
}

func assertItemsContainID(t *testing.T, raw any, id string) {
	t.Helper()
	items, ok := raw.([]any)
	if !ok {
		t.Fatalf("items is not list: %#v", raw)
	}
	for _, item := range items {
		obj, ok := item.(map[string]any)
		if !ok {
			continue
		}
		if obj["id"] == id || obj["_id"] == id || obj["postId"] == id {
			return
		}
	}
	t.Fatalf("items did not contain id %s: %+v", id, items)
}

func assertItemsContainText(t *testing.T, raw any, fragment string) {
	t.Helper()
	items, ok := raw.([]any)
	if !ok {
		t.Fatalf("items is not list: %#v", raw)
	}
	for _, item := range items {
		obj, ok := item.(map[string]any)
		if !ok {
			continue
		}
		if value, ok := obj["content"].(string); ok && contains(value, fragment) {
			return
		}
	}
	t.Fatalf("items did not contain text %q: %+v", fragment, items)
}

func contains(value, fragment string) bool {
	return len(fragment) == 0 || (len(value) >= len(fragment) && value[:len(fragment)] == fragment) || jsonContains(value, fragment)
}

func jsonContains(value, fragment string) bool {
	for i := 0; i+len(fragment) <= len(value); i++ {
		if value[i:i+len(fragment)] == fragment {
			return true
		}
	}
	return false
}

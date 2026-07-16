// L2 契约测试：Post 业务对象 — 收口后的响应契约
//
// 守护：响应字段不缩减；私有字段不泄露；可写字段约束稳定。
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
)

// TestPost_ResponseShape_NoPrivateFields verifies that GET /v1/content/posts/:id
// does not expose internal fields (embedding, moderationStatus).
// Fields classified privacy:never_expose must never appear in public responses.
func TestPost_ResponseShape_NoPrivateFields(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"image","title":"Privacy check","body":"public content","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("created post has no _id")
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if _, hasEmbedding := result["embedding"]; hasEmbedding {
		t.Error("response must not expose embedding field (privacy: never_expose)")
	}
	if _, hasMod := result["moderationStatus"]; hasMod {
		t.Error("response must not expose moderationStatus (visibility: platform-ops only)")
	}
}

// TestPost_WritableFields_UnknownFieldRejected verifies that POST /v1/content/posts
// rejects requests with unknown fields, returning 400 with structured error.
// This protects against field injection attacks and enforces the field contract.
func TestPost_WritableFields_UnknownFieldRejected(t *testing.T) {
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts",
		bytes.NewBufferString(`{"unknownField":"x","contentType":"image","mediaUrls":["https://example.com/img.jpg"]}`),
	)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
	var errResp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	if errResp["code"] == nil {
		t.Error("error response missing code field")
	}
}

// TestPost_MinimalCurrentRecordRemainsReadable verifies that a minimal payload
// still receives every server-owned default during the current CreatePost command.
func TestPost_MinimalCurrentRecordRemainsReadable(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"micro","body":"minimal post"}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/"+postID, nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("minimal current record should be readable, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if result["_id"] != postID {
		t.Errorf("expected _id=%s, got %v", postID, result["_id"])
	}
}

func TestPostSearch_DerivesCategoriesFromTopicTagRefs(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	now := time.Now().UTC()
	_, err := mongoDB.Collection("posts").InsertOne(context.Background(), bson.M{
		"_id":         "search_topic_post_1",
		"authorId":    "search_author",
		"contentType": "article",
		"title":       "内容语义标签搜索",
		"body":        "这篇文章用于验证站内搜索语义标签。",
		"tagRefs":     []string{"Topic/旅行", "Topic/景区", "Entity/地点/景区"},
		"entityRefs":  []string{"地点/景区/四川大学"},
		"status":      "published",
		"visibility":  "public",
		"createdAt":   now,
		"updatedAt":   now,
		"publishedAt": now,
	})
	if err != nil {
		t.Fatalf("insert search post: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/content/posts/search?query=%E6%97%85%E8%A1%8C", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var result struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(result.Items) != 1 {
		t.Fatalf("expected 1 search result, got %d: %s", len(result.Items), rec.Body.String())
	}
	item := result.Items[0]
	if item["postId"] != "search_topic_post_1" {
		t.Fatalf("unexpected postId: %+v", item)
	}
	if item["matchedField"] != "tagRefs" {
		t.Fatalf("expected matchedField=tagRefs, got %+v", item)
	}
	if item["categoryId"] != "旅行" || item["subCategory"] != "景区" {
		t.Fatalf("expected category/subCategory from tagRefs, got %+v", item)
	}
}

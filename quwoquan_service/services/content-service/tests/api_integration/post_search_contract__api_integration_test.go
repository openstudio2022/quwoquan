package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestPostSearchUsesCanonicalSearchSignals(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	createPostWithAuthor(t, "search_author_a", `{
		"contentType":"article",
		"contentIdentity":"work",
		"title":"四川露营旅行攻略",
		"summary":"川西营地、路线和装备建议",
		"body":"适合周末出行游玩",
		"semanticMentions":[
			{"mentionId":"m_tag_camp","kind":"tag","surface":"露营","location":"title","rangeStart":2,"rangeEnd":4,"status":"published","targetRef":"Topic/四川/露营"},
			{"mentionId":"m_entity_west_sichuan","kind":"entity","surface":"川西","location":"summary","rangeStart":0,"rangeEnd":2,"status":"published","targetRef":"entity:region:川西"}
		],
		"visibility":"public"
	}`)
	createPostWithAuthor(t, "search_author_b", `{
		"contentType":"article",
		"contentIdentity":"work",
		"title":"城市散步记录",
		"summary":"商圈拍照路线",
		"body":"轻松散步",
		"visibility":"public"
	}`)

	body := searchPosts(t, "scly")
	items := asSlice(t, body["items"])
	if len(items) != 1 {
		t.Fatalf("expected one pinyin-initial search hit, got %d: %#v", len(items), items)
	}
	first := asMap(t, items[0])
	if first["title"] != "四川露营旅行攻略" {
		t.Fatalf("unexpected top hit: %#v", first)
	}
	if first["matchedField"] == "" || first["highlightText"] == "" {
		t.Fatalf("expected matchedField/highlightText from canonical scorer: %#v", first)
	}

	body = searchPosts(t, "路营")
	items = asSlice(t, body["items"])
	if len(items) != 1 {
		t.Fatalf("expected correction search hit, got %#v", items)
	}
}

func TestPostSearchBlocksSensitiveQuery(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	createPost(t, `{"contentType":"micro","body":"普通公开内容","visibility":"public"}`)

	body := searchPosts(t, "博彩")
	items := asSlice(t, body["items"])
	if len(items) != 0 {
		t.Fatalf("sensitive query should return no content hits, got %#v", items)
	}
}

func TestPendingSemanticMentionRemainsFullTextOnly(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPostWithAuthor(t, "semantic_search_author", `{
		"contentType":"article",
		"title":"高原旅行笔记",
		"body":"神秘雪谷仍在候选治理中，但这段普通正文应当可以搜索。",
		"semanticMentions":[
			{"mentionId":"pending_entity_1","kind":"entity","surface":"神秘雪谷","location":"body","rangeStart":0,"rangeEnd":4,"status":"pending_review","candidateId":"candidate_entity_1"},
			{"mentionId":"published_tag_1","kind":"tag","surface":"高原旅行","location":"title","rangeStart":0,"rangeEnd":4,"status":"published","targetRef":"Topic/旅行/高原"}
		],
		"visibility":"public"
	}`)
	postID, _ := created["_id"].(string)
	publishPostWithAuthor(t, "semantic_search_author", postID, `{"visibility":"public"}`)

	body := searchPosts(t, "神秘雪谷")
	items := asSlice(t, body["items"])
	if len(items) != 1 {
		t.Fatalf("pending mention surface should remain full-text searchable: %#v", items)
	}
	first := asMap(t, items[0])
	if first["matchedField"] != "body" {
		t.Fatalf("pending mention must match ordinary body, got %#v", first)
	}

	var stored struct {
		EntityRefs []string `bson:"entityRefs"`
		TagRefs    []string `bson:"tagRefs"`
	}
	if err := mongoDB.Collection("posts").FindOne(
		context.Background(),
		bson.M{"_id": postID},
	).Decode(&stored); err != nil {
		t.Fatal(err)
	}
	if len(stored.EntityRefs) != 0 {
		t.Fatalf("pending entity leaked into active refs: %#v", stored.EntityRefs)
	}
	if len(stored.TagRefs) != 1 || stored.TagRefs[0] != "Topic/旅行/高原" {
		t.Fatalf("published tag projection mismatch: %#v", stored.TagRefs)
	}

	var projected struct {
		EntityRefs []string `bson:"entityRefs"`
		TagRefs    []string `bson:"tagRefs"`
	}
	if err := mongoDB.Collection("rm_discovery_feed").FindOne(
		context.Background(),
		bson.M{"postId": postID},
	).Decode(&projected); err != nil {
		t.Fatal(err)
	}
	if len(projected.EntityRefs) != 0 {
		t.Fatalf("pending entity leaked into recommendation projection: %#v", projected.EntityRefs)
	}
	if len(projected.TagRefs) != 1 || projected.TagRefs[0] != "Topic/旅行/高原" {
		t.Fatalf("recommendation tag projection mismatch: %#v", projected.TagRefs)
	}
}

func TestCreatePostRejectsManualActiveRefs(t *testing.T) {
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts",
		strings.NewReader(`{
			"contentType":"article",
			"title":"非法候选引用",
			"body":"候选只应作为普通文字",
			"entityRefs":["candidate:entity:1"]
		}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "semantic_reject_author")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("manual active refs must be rejected, got %d: %s", rec.Code, rec.Body.String())
	}
}

func searchPosts(t *testing.T, query string) map[string]any {
	t.Helper()
	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/posts/search?query="+url.QueryEscape(query)+"&limit=10",
		nil,
	)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("search posts status=%d body=%s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode search response: %v", err)
	}
	return body
}

func asSlice(t *testing.T, value any) []any {
	t.Helper()
	items, ok := value.([]any)
	if !ok {
		t.Fatalf("expected []any, got %T", value)
	}
	return items
}

func asMap(t *testing.T, value any) map[string]any {
	t.Helper()
	item, ok := value.(map[string]any)
	if !ok {
		t.Fatalf("expected map[string]any, got %T", value)
	}
	return item
}

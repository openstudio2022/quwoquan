package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
)

func TestPostSearchUsesCanonicalSearchSignals(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	createPostWithAuthor(t, "search_author_a", `{
		"contentType":"article",
		"contentIdentity":"work",
		"title":"四川露营旅行攻略",
		"summary":"川西营地、路线和装备建议",
		"body":"适合周末出行游玩",
		"tagRefs":["Topic/四川/露营","entity:川西"],
		"entityRefs":["entity:川西"],
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

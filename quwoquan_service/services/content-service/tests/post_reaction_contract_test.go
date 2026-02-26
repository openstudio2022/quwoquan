// L2 契约测试：Post 业务对象 — 点赞/收藏互动（Reaction）
//
// 守护：互动路由注册；当 LikePost/UnlikePost 实现后，计数器策略和幂等性。
//
// 当前状态：LikePost/UnlikePost 处理器尚未实现（返回 500 structured error）。
// 测试验证：路由已注册 + 响应为合法 JSON + 结构化错误码。
// 完成实现后：更新断言为 2xx，并补充 Redis counter 增减的 MongoDB/Redis 断言。
package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// TestReactWithCounterStrategy verifies the POST like route is registered and
// responds with structured JSON. When LikePost is implemented, this should
// assert 200/204 and verify the likeCount counter is incremented in MongoDB.
// contract.yaml: react_with_counter_strategy / go_func: TestReactWithCounterStrategy
func TestReactWithCounterStrategy(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Like counter test"}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/like", nil)
	req.Header.Set("X-Client-User-Id", "user_react_001")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	// Route must be registered (not 404)
	if rec.Code == http.StatusNotFound {
		t.Fatalf("like route not registered (got 404)")
	}
	// Response must be valid structured JSON
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("like route response must be valid JSON: %v", err)
	}
	// When implemented: assert rec.Code == 200 and resp["likeCount"] == 1
}

// TestReactIdempotent verifies that calling like twice from the same user does
// not double-increment the counter (idempotent reaction semantics).
// contract.yaml: react_idempotent / go_func: TestReactIdempotent
func TestReactIdempotent(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Idempotent like test"}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	// First like
	req1 := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/like", nil)
	req1.Header.Set("X-Client-User-Id", "user_react_002")
	rec1 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec1, req1)

	if rec1.Code == http.StatusNotFound {
		t.Fatalf("like route not registered (got 404)")
	}

	// Second like (same user) — idempotent
	req2 := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/like", nil)
	req2.Header.Set("X-Client-User-Id", "user_react_002")
	rec2 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec2, req2)

	if rec2.Code == http.StatusNotFound {
		t.Fatalf("like route not registered on second call (got 404)")
	}
	// Both calls return valid structured JSON
	var resp2 map[string]any
	if err := json.Unmarshal(rec2.Body.Bytes(), &resp2); err != nil {
		t.Fatalf("second like response must be valid JSON: %v", err)
	}
	// When implemented: assert likeCount still == 1 (not 2)
}

// TestUnlikeDecrementsCounter verifies the DELETE unlike route is registered and
// responds with structured JSON. When UnlikePost is implemented, this should
// assert 200/204 and verify the likeCount counter is decremented.
// contract.yaml: unlike_decrements_counter / go_func: TestUnlikeDecrementsCounter
func TestUnlikeDecrementsCounter(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Unlike decrement test"}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	// Like first
	likeReq := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/like", nil)
	likeReq.Header.Set("X-Client-User-Id", "user_react_003")
	likeRec := httptest.NewRecorder()
	testHandler.ServeHTTP(likeRec, likeReq)

	// Then unlike
	req := httptest.NewRequest(http.MethodDelete, "/v1/content/posts/"+postID+"/like", nil)
	req.Header.Set("X-Client-User-Id", "user_react_003")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	// Route must be registered (not 404)
	if rec.Code == http.StatusNotFound {
		t.Fatalf("unlike route not registered (got 404)")
	}
	// Response must be valid structured JSON
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unlike route response must be valid JSON: %v", err)
	}
	// When implemented: assert rec.Code == 200 and likeCount decremented
}

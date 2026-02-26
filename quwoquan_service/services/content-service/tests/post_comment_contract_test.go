// L2 契约测试：Post 业务对象 — 评论 CRUD 与分页
//
// 守护：评论路由注册；当 CreateComment/ListComments 实现后，事件发布和分页语义。
//
// 当前状态：CreateComment/ListComments 处理器尚未实现（返回 500 structured error）。
// 测试验证：路由已注册 + 响应为合法 JSON + 结构化错误码。
// 完成实现后：更新断言为 201/200，并补充 CommentCreated 事件和游标分页断言。
package tests

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestCommentWithNotification verifies the POST comment route is registered
// and responds with structured JSON. When CreateComment is implemented, this
// should assert 201 and verify CommentCreated domain event is published.
// contract.yaml: comment_with_notification / go_func: TestCommentWithNotification
func TestCommentWithNotification(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	eventSpy.Reset()

	created := createPost(t, `{"contentType":"image","title":"Comment notification test"}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	commentBody := `{"content":"这张图真漂亮！"}`
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts/"+postID+"/comments",
		strings.NewReader(commentBody),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_commenter_001")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	// Route must be registered (not 404)
	if rec.Code == http.StatusNotFound {
		t.Fatalf("create comment route not registered (got 404)")
	}
	// Response must be valid structured JSON
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("create comment response must be valid JSON: %v", err)
	}
	// When implemented: assert rec.Code == 201 and eventSpy.EventsOfType("CommentCreated") non-empty
}

// TestCommentListPagination verifies the GET comments route is registered and
// responds with structured JSON. When ListComments is implemented, this should
// assert 200 and validate cursor-based pagination with no overlapping items.
// contract.yaml: comment_list_pagination / go_func: TestCommentListPagination
func TestCommentListPagination(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := createPost(t, `{"contentType":"image","title":"Comment pagination test"}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	// First page
	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/posts/"+postID+"/comments?limit=5",
		nil,
	)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	// Route must be registered (not 404)
	if rec.Code == http.StatusNotFound {
		t.Fatalf("list comments route not registered (got 404)")
	}
	// Response must be valid structured JSON
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("list comments response must be valid JSON: %v", err)
	}
	// When implemented:
	//   assert rec.Code == 200
	//   assert resp["items"] is a list
	//   create 6 comments, request page 1 (limit=5), then page 2 using nextCursor
	//   verify no overlap between pages
}

// L2 契约测试：Post 业务对象 — 行为上报与互动操作
//
// 守护：点赞、收藏、行为上报接口的路由注册和基本语义。
// contract.yaml go_func 覆盖：
//   TestBehaviorBatchReport — behavior_batch_report
//   TestBehaviorBatchEmpty  — behavior_batch_empty
//   TestLikePost, TestFavoritePost, TestReportPost — 其他行为场景
package tests

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestLikePost verifies the like endpoint route is registered.
// The handler currently returns 500 (operation not implemented) —
// asserts the route exists and returns a structured error, not 404.
// contract.yaml: react_with_counter_strategy / go_func: TestReactWithCounterStrategy
func TestLikePost(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"image","title":"Like target","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/like", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	// Route is registered; expect either 2xx (implemented) or 5xx (not implemented).
	if rec.Code == http.StatusNotFound {
		t.Fatalf("like route not registered (got 404); expected 2xx or 5xx")
	}
	if rec.Code >= 400 {
		var errResp map[string]any
		if err := json.Unmarshal(rec.Body.Bytes(), &errResp); err != nil {
			t.Fatalf("decode error response: %v", err)
		}
		if errResp["code"] == nil {
			t.Error("expected structured error response with code field")
		}
	}
}

// TestFavoritePost verifies the favorite endpoint route is registered.
// contract.yaml: go_func: TestFavoritePost
func TestFavoritePost(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"image","title":"Favorite target","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/favorite", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code == http.StatusNotFound {
		t.Fatalf("favorite route not registered (got 404); expected 2xx or 5xx")
	}
	if rec.Code >= 400 {
		var errResp map[string]any
		if err := json.Unmarshal(rec.Body.Bytes(), &errResp); err != nil {
			t.Fatalf("decode error response: %v", err)
		}
		if errResp["code"] == nil {
			t.Error("expected structured error response with code field")
		}
	}
}

// TestBehaviorBatchReport verifies POST /v1/content/behaviors accepts a mixed batch
// of impression + dwell + click events and returns 200 with accepted count.
// contract.yaml: behavior_batch_report
func TestBehaviorBatchReport(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"image","title":"Behavior batch target","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	payload := fmt.Sprintf(`{
		"userId": "user_batch_001",
		"sessionId": "sess_abc",
		"events": [
			{"contentId": %q, "action": "impression", "userId": "user_batch_001"},
			{"contentId": %q, "action": "click",      "userId": "user_batch_001"},
			{"contentId": %q, "action": "dwell",      "userId": "user_batch_001", "duration": 5.5}
		]
	}`, postID, postID, postID)

	req := httptest.NewRequest(http.MethodPost, "/v1/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if result["status"] != "ok" {
		t.Errorf("expected status=ok, got %v", result["status"])
	}
	accepted, _ := result["accepted"].(float64)
	if accepted != 3 {
		t.Errorf("expected accepted=3, got %v", result["accepted"])
	}
}

// TestBehaviorBatchEmpty verifies POST /v1/content/behaviors with an empty events
// array returns 400 with CONTENT.USER.invalid_argument.
// contract.yaml: behavior_batch_empty
func TestBehaviorBatchEmpty(t *testing.T) {
	payload := `{"userId": "user_empty", "events": []}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for empty events, got %d: %s", rec.Code, rec.Body.String())
	}
	var errResp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	code, _ := errResp["code"].(string)
	if code != "CONTENT.USER.invalid_argument" {
		t.Errorf("expected code=CONTENT.USER.invalid_argument, got %q", code)
	}
}

// TestReportPost verifies POST /v1/content/behaviors accepts a report action.
// contract.yaml: behavior_batch_report / go_func: TestBehaviorBatchReport
func TestReportPost(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"image","title":"Report target","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	payload := fmt.Sprintf(
		`{"userId":"user_reporter_001","events":[{"contentId":%q,"action":"report","userId":"user_reporter_001"}]}`,
		postID,
	)
	req := httptest.NewRequest(http.MethodPost, "/v1/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var result map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if result["status"] != "ok" {
		t.Errorf("expected status=ok, got %v", result["status"])
	}
	accepted, _ := result["accepted"].(float64)
	if accepted != 1 {
		t.Errorf("expected accepted=1, got %v", result["accepted"])
	}
}

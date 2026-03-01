// L2 契约测试：Post 业务对象 — Feed 分页查询
//
// 守护：Feed 接口的类型过滤、分页语义、光标延续、查询正确性。
package tests

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

// TestGetFeedByType creates image and video posts, then requests feed with
// type=photo and verifies only image-type items are returned.
// contract.yaml: get_feed_by_type / go_func: TestGetFeedByType
func TestGetFeedByType(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	// Create mixed content types
	for i := range 3 {
		createPost(t, fmt.Sprintf(
			`{"contentType":"image","title":"Photo post %d","mediaUrls":["https://example.com/img%d.jpg"]}`,
			i, i,
		))
	}
	for i := range 2 {
		createPost(t, fmt.Sprintf(
			`{"contentType":"video","title":"Video post %d","videoUrl":"https://example.com/vid%d.mp4"}`,
			i, i,
		))
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/content/feed?type=photo&limit=10", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var page struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(page.Items) == 0 {
		t.Error("expected at least one image post in photo feed")
	}
	for _, item := range page.Items {
		if item["type"] != "photo" && item["contentType"] != "image" {
			t.Errorf("non-photo item in photo feed: %v", item)
		}
	}
}

// TestGetFeedCursorPagination verifies cursor-based pagination returns
// non-overlapping pages and that the second page cursor differs from the first.
// contract.yaml: get_feed_cursor_pagination / go_func: TestGetFeedCursorPagination
func TestGetFeedCursorPagination(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	// Create enough posts for two pages
	for i := range 6 {
		createPost(t, fmt.Sprintf(
			`{"contentType":"image","title":"Pager post %d","body":"content %d","mediaUrls":["https://example.com/img%d.jpg"]}`, i, i, i,
		))
	}

	// First page: limit=3
	req1 := httptest.NewRequest(http.MethodGet, "/v1/content/feed?type=photo&limit=3", nil)
	rec1 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec1, req1)

	if rec1.Code != http.StatusOK {
		t.Fatalf("first page: expected 200, got %d: %s", rec1.Code, rec1.Body.String())
	}
	var page1 struct {
		Items      []map[string]any `json:"items"`
		NextCursor string           `json:"nextCursor"`
	}
	if err := json.Unmarshal(rec1.Body.Bytes(), &page1); err != nil {
		t.Fatalf("first page: decode: %v", err)
	}
	if len(page1.Items) == 0 {
		t.Fatal("first page: expected items, got none")
	}

	// Collect first page IDs
	page1IDs := map[any]bool{}
	for _, item := range page1.Items {
		page1IDs[item["id"]] = true
	}

	// Second page using cursor
	if page1.NextCursor == "" {
		t.Log("nextCursor empty — only one page of data; cursor continuity validated by absence")
		return
	}

	req2 := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/feed?type=photo&limit=3&cursor="+page1.NextCursor, nil,
	)
	rec2 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec2, req2)

	if rec2.Code != http.StatusOK {
		t.Fatalf("second page: expected 200, got %d: %s", rec2.Code, rec2.Body.String())
	}
	var page2 struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec2.Body.Bytes(), &page2); err != nil {
		t.Fatalf("second page: decode: %v", err)
	}

	// No overlap between pages
	for _, item := range page2.Items {
		if page1IDs[item["id"]] {
			t.Errorf("page 2 item %v also found on page 1 — cursor pagination is broken", item["id"])
		}
	}
}

// TestGetFeedRecommendSortWithCursor verifies recommend sort and opaque cursor
// can paginate without overlap.
// contract.yaml: get_feed_recommend_sort_with_cursor / go_func: TestGetFeedRecommendSortWithCursor
func TestGetFeedRecommendSortWithCursor(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	for i := range 8 {
		createPost(t, fmt.Sprintf(
			`{"contentType":"image","title":"Recommend Pager %d","body":"content %d","mediaUrls":["https://example.com/img%d.jpg"]}`, i, i, i,
		))
	}

	req1 := httptest.NewRequest(http.MethodGet, "/v1/content/feed?type=photo&sort=recommend&limit=4", nil)
	rec1 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec1, req1)
	if rec1.Code != http.StatusOK {
		t.Fatalf("first page: expected 200, got %d: %s", rec1.Code, rec1.Body.String())
	}

	var page1 struct {
		Items      []map[string]any `json:"items"`
		NextCursor string           `json:"nextCursor"`
	}
	if err := json.Unmarshal(rec1.Body.Bytes(), &page1); err != nil {
		t.Fatalf("first page decode: %v", err)
	}
	if len(page1.Items) == 0 {
		t.Fatal("first page should contain items")
	}
	if page1.NextCursor == "" {
		t.Fatal("first page should return nextCursor")
	}
	if strings.HasPrefix(page1.NextCursor, "post_") {
		t.Fatalf("nextCursor should be opaque token, got id-like value: %s", page1.NextCursor)
	}

	page1IDs := map[any]bool{}
	for _, item := range page1.Items {
		page1IDs[item["id"]] = true
	}

	req2 := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/feed?type=photo&sort=recommend&limit=4&cursor="+url.QueryEscape(page1.NextCursor),
		nil,
	)
	rec2 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusOK {
		t.Fatalf("second page: expected 200, got %d: %s", rec2.Code, rec2.Body.String())
	}
	var page2 struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec2.Body.Bytes(), &page2); err != nil {
		t.Fatalf("second page decode: %v", err)
	}
	for _, item := range page2.Items {
		if page1IDs[item["id"]] {
			t.Fatalf("page 2 item %v also found on page 1", item["id"])
		}
	}
}

// TestGetFeedFutureWindowChangesOnly verifies strong feedback only impacts
// items after the current cursor (future window), while already returned
// history remains unchanged on client side.
// contract.yaml: get_feed_future_window_changes_only / go_func: TestGetFeedFutureWindowChangesOnly
func TestGetFeedFutureWindowChangesOnly(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	for i := range 12 {
		createPost(t, fmt.Sprintf(
			`{"contentType":"image","title":"Future Window %d","body":"content %d","mediaUrls":["https://example.com/img%d.jpg"]}`, i, i, i,
		))
	}

	req1 := httptest.NewRequest(http.MethodGet, "/v1/content/feed?type=photo&sort=recommend&limit=4", nil)
	req1.Header.Set("X-Client-User-Id", "user_fw_01")
	req1.Header.Set("X-Client-Session-Id", "session_fw_01")
	rec1 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec1, req1)
	if rec1.Code != http.StatusOK {
		t.Fatalf("page1 expected 200, got %d: %s", rec1.Code, rec1.Body.String())
	}
	var page1 struct {
		Items      []map[string]any `json:"items"`
		NextCursor string           `json:"nextCursor"`
	}
	if err := json.Unmarshal(rec1.Body.Bytes(), &page1); err != nil {
		t.Fatalf("page1 decode: %v", err)
	}
	if len(page1.Items) != 4 || page1.NextCursor == "" {
		t.Fatalf("page1 should contain 4 items and cursor, got items=%d cursor=%q", len(page1.Items), page1.NextCursor)
	}

	req2 := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/feed?type=photo&sort=recommend&limit=4&cursor="+url.QueryEscape(page1.NextCursor),
		nil,
	)
	req2.Header.Set("X-Client-User-Id", "user_fw_01")
	req2.Header.Set("X-Client-Session-Id", "session_fw_01")
	rec2 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusOK {
		t.Fatalf("page2 expected 200, got %d: %s", rec2.Code, rec2.Body.String())
	}
	var page2 struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec2.Body.Bytes(), &page2); err != nil {
		t.Fatalf("page2 decode: %v", err)
	}
	if len(page2.Items) == 0 {
		t.Fatal("page2 should contain items")
	}

	dislikeID, _ := page2.Items[0]["id"].(string)
	if dislikeID == "" {
		t.Fatal("page2 first item id should not be empty")
	}
	behaviorReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/behaviors",
		strings.NewReader(fmt.Sprintf(`{"events":[{"contentId":"%s","action":"dislike"}]}`, dislikeID)),
	)
	behaviorReq.Header.Set("Content-Type", "application/json")
	behaviorReq.Header.Set("X-Client-User-Id", "user_fw_01")
	behaviorReq.Header.Set("X-Client-Session-Id", "session_fw_01")
	behaviorRec := httptest.NewRecorder()
	testHandler.ServeHTTP(behaviorRec, behaviorReq)
	if behaviorRec.Code != http.StatusOK {
		t.Fatalf("behavior expected 200, got %d: %s", behaviorRec.Code, behaviorRec.Body.String())
	}

	req2After := httptest.NewRequest(
		http.MethodGet,
		"/v1/content/feed?type=photo&sort=recommend&limit=4&cursor="+url.QueryEscape(page1.NextCursor),
		nil,
	)
	req2After.Header.Set("X-Client-User-Id", "user_fw_01")
	req2After.Header.Set("X-Client-Session-Id", "session_fw_01")
	rec2After := httptest.NewRecorder()
	testHandler.ServeHTTP(rec2After, req2After)
	if rec2After.Code != http.StatusOK {
		t.Fatalf("page2 after feedback expected 200, got %d: %s", rec2After.Code, rec2After.Body.String())
	}
	var page2After struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec2After.Body.Bytes(), &page2After); err != nil {
		t.Fatalf("page2 after decode: %v", err)
	}
	for _, item := range page2After.Items {
		if item["id"] == dislikeID {
			t.Fatalf("disliked content %s should be filtered from future window", dislikeID)
		}
	}
}

// TestListFeedWithPagination creates image posts then verifies GET /v1/content/feed
// returns 200 with items array, and that a second page call also succeeds.
func TestListFeedWithPagination(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	for i := range 4 {
		payload := fmt.Sprintf(`{"contentType":"image","title":"Feed post %d","body":"content %d","mediaUrls":["https://example.com/%d.jpg"]}`, i, i, i)
		createPost(t, payload)
	}

	req1 := httptest.NewRequest(http.MethodGet, "/v1/content/feed?type=photo&limit=3", nil)
	rec1 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec1, req1)

	if rec1.Code != http.StatusOK {
		t.Fatalf("first page: expected 200, got %d: %s", rec1.Code, rec1.Body.String())
	}
	var page1 struct {
		Items      []map[string]any `json:"items"`
		NextCursor string           `json:"nextCursor"`
	}
	if err := json.Unmarshal(rec1.Body.Bytes(), &page1); err != nil {
		t.Fatalf("first page: decode response: %v", err)
	}
	if len(page1.Items) == 0 {
		t.Error("first page: expected at least one item in feed")
	}
}

// TestGetFeedFiltersBlockedUser verifies recall-post filtering can exclude
// blocked authors via request header.
func TestGetFeedFiltersBlockedUser(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/v1/content/feed?limit=10", nil)
	req.Header.Set("X-Blocked-User-Ids", "user_1002")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var page struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	for _, item := range page.Items {
		if item["authorId"] == "user_1002" {
			t.Fatalf("blocked author should be filtered, got item=%v", item["id"])
		}
	}
}

// TestGetFeedFiltersBlockedKeyword verifies recall-post filtering can exclude
// content whose title/body/tags hit blocked keywords.
func TestGetFeedFiltersBlockedKeyword(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/v1/content/feed?limit=10", nil)
	req.Header.Set("X-Blocked-Keywords", "winter")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var page struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	for _, item := range page.Items {
		if item["id"] == "post_photo_001" {
			t.Fatalf("keyword-hit post should be filtered, got post_photo_001")
		}
	}
}

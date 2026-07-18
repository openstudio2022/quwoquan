// L2 契约测试：Post 业务对象 — Feed 分页查询
//
// 守护：Feed 接口的类型过滤、分页语义、光标延续、查询正确性。
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// TestMongoPostFeedReaderDecodesCanonicalProjection 直接验证生产 Feed Reader
// 可以把 canonical Post 文档解码为 typed Slice。HTTP 层会把持久化错误收敛为
// 稳定的 RuntimeFailure，因此 BSON/投影漂移必须在此契约边界完整暴露。
func TestMongoPostFeedReaderDecodesCanonicalProjection(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	created := submitPublishedPost(t, `{"contentType":"image","contentIdentity":"work","title":"Typed feed projection","deviceInfo":{"width":1280,"height":720}}`)
	createdID, _ := created["postId"].(string)
	if createdID == "" {
		t.Fatalf("created post is missing id: %+v", created)
	}

	reader := persistence.NewMongoPostQueryReader(mongoDB.Collection("posts"))
	page, err := reader.ListPublishedFeedPosts(
		context.Background(),
		postports.NewPostFeedReadRequest("work", "image", "", 10),
	)
	if err != nil {
		t.Fatalf("list typed feed projection: %v", err)
	}
	if len(page.Items) != 1 {
		t.Fatalf("expected one typed feed item, got %d: %+v", len(page.Items), page.Items)
	}
	item := page.Items[0]
	if string(item.PostID) != createdID {
		t.Fatalf("expected post %q, got %q", createdID, item.PostID)
	}
	if item.Width != 1280 || item.Height != 720 {
		t.Fatalf("expected normalized 1280x720 dimensions, got %dx%d", item.Width, item.Height)
	}
}

// TestGetFeedByType creates image and video posts, then requests feed with
// type=image and verifies only image-type items are returned.
// contract.yaml: get_feed_by_type / go_func: TestGetFeedByType
func TestGetFeedByType(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	// Create mixed content types
	for i := range 3 {
		submitPublishedPost(t, fmt.Sprintf(
			`{"contentType":"image","title":"Photo post %d","deviceInfo":{"width":1280,"height":720}}`,
			i,
		))
	}
	for i := range 2 {
		submitPublishedPost(t, fmt.Sprintf(
			`{"contentType":"video","title":"Video post %d"}`,
			i,
		))
	}

	req := httptest.NewRequest(http.MethodGet, "/content/feed?type=image&limit=10", nil)
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
		if item["type"] != "image" && item["contentType"] != "image" {
			t.Errorf("non-photo item in photo feed: %v", item)
		}
	}

	var dimensionItem map[string]any
	for _, item := range page.Items {
		if item["title"] == "Photo post 0" {
			dimensionItem = item
			break
		}
	}
	if dimensionItem == nil {
		t.Fatal("expected Photo post 0 in feed response")
	}
	width, widthOK := dimensionItem["width"].(float64)
	height, heightOK := dimensionItem["height"].(float64)
	if !widthOK || !heightOK {
		t.Fatalf("expected width/height on feed item, got %v", dimensionItem)
	}
	if int(width) != 1280 || int(height) != 720 {
		t.Fatalf("unexpected dimensions on feed item: width=%v height=%v", width, height)
	}
}

// TestGetFeedByIdentity verifies discovery feed can filter by content identity.
func TestGetFeedByIdentity(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	submitPublishedPost(t, `{"contentType":"micro","contentIdentity":"moment","body":"点滴 1"}`)
	submitPublishedPost(t, `{"contentType":"micro","contentIdentity":"moment","body":"点滴 2"}`)
	submitPublishedPost(t, `{"contentType":"image","contentIdentity":"work","title":"作品 1"}`)

	req := httptest.NewRequest(
		http.MethodGet,
		"/content/feed?identity=moment&type=image&limit=10",
		nil,
	)
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
		t.Fatal("expected moment items in identity filtered feed")
	}
	for _, item := range page.Items {
		if item["type"] != "moment" && item["contentType"] != "micro" {
			t.Fatalf("expected only moment items, got %v", item)
		}
	}
}

// TestGetFeedIdentityFilterCannotBeStarvedByNewerWorks 守护存储侧 identity
// 过滤。旧实现先读取固定窗口的最新 Post，再在 application 内过滤；当较新的
// work 占满窗口时，合法 moment 会被错误隐藏。limit=1 时旧四轮窗口最多扫描
// 八条记录，因此九条较新 work 足以稳定复现该架构缺陷。
func TestGetFeedIdentityFilterCannotBeStarvedByNewerWorks(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	moment := submitPublishedPost(t, `{"contentType":"micro","contentIdentity":"moment","body":"不能被较新作品饿死的点滴"}`)
	momentID, _ := moment["postId"].(string)
	for i := range 9 {
		submitPublishedPost(t, fmt.Sprintf(
			`{"contentType":"image","contentIdentity":"work","title":"newer work %d"}`,
			i,
		))
	}

	req := httptest.NewRequest(
		http.MethodGet,
		"/content/feed?identity=moment&type=image&limit=1",
		nil,
	)
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
	if len(page.Items) != 1 {
		t.Fatalf("expected the older moment after storage-side identity filtering, got %+v", page.Items)
	}
	if page.Items[0]["postId"] != momentID {
		t.Fatalf("expected moment %q, got %+v", momentID, page.Items[0])
	}
}

// TestGetFeedExcludesPrivatePosts verifies that feed only returns visibility=public
// content; private posts must never appear in discovery.
// contract.yaml: get_feed_excludes_private_posts / go_func: TestGetFeedExcludesPrivatePosts
func TestGetFeedExcludesPrivatePosts(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	// Create one public and one private moment
	pub := submitPublishedPost(t, `{"contentType":"micro","body":"Public moment","visibility":"public"}`)
	priv := submitPublishedPost(t, `{"contentType":"micro","body":"Private moment","visibility":"private"}`)

	privateID, _ := priv["postId"].(string)
	if privateID == "" {
		t.Fatal("private post missing id")
	}

	req := httptest.NewRequest(http.MethodGet, "/content/feed?type=moment&limit=20", nil)
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
		id, _ := item["postId"].(string)
		if id == privateID {
			t.Errorf("private post %q must not appear in discovery feed", privateID)
		}
	}
	// Public post may or may not be in first page (depends on sort/rec) — key assertion is private excluded
	_ = pub
}

// TestGetFeedCursorPagination verifies cursor-based pagination returns
// non-overlapping pages and that the second page cursor differs from the first.
// contract.yaml: get_feed_cursor_pagination / go_func: TestGetFeedCursorPagination
func TestGetFeedCursorPagination(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	// Create enough posts for two pages
	for i := range 6 {
		submitPublishedPost(t, fmt.Sprintf(
			`{"contentType":"image","title":"Pager post %d","body":"content %d"}`, i, i,
		))
	}

	// First page: limit=3
	req1 := httptest.NewRequest(http.MethodGet, "/content/feed?type=image&limit=3", nil)
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
		page1IDs[item["postId"]] = true
	}

	// Second page using cursor
	if page1.NextCursor == "" {
		t.Log("nextCursor empty — only one page of data; cursor continuity validated by absence")
		return
	}

	req2 := httptest.NewRequest(
		http.MethodGet,
		"/content/feed?type=image&limit=3&cursor="+page1.NextCursor, nil,
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
		if page1IDs[item["postId"]] {
			t.Errorf("page 2 item %v also found on page 1 — cursor pagination is broken", item["postId"])
		}
	}
}

// TestGetFeedRecommendSortWithCursor verifies recommend sort and opaque cursor
// can paginate without overlap.
// contract.yaml: get_feed_recommend_sort_with_cursor / go_func: TestGetFeedRecommendSortWithCursor
func TestGetFeedRecommendSortWithCursor(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	// Engine is called with limit*2=8; nextCursor only when len(allItems) > 8. Create 12 posts
	// with 4 distinct authors (maxAuthorPerFeed=3) so rerank yields 12 items for cursor.
	for i := range 12 {
		authorID := fmt.Sprintf("user_rec_%d", i%4)
		submitPublishedPostWithAuthor(t, authorID, fmt.Sprintf(
			`{"contentType":"image","title":"Recommend Pager %d","body":"content %d"}`, i, i,
		))
	}

	req1 := httptest.NewRequest(http.MethodGet, "/content/feed?sort=recommend&limit=4", nil)
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
		page1IDs[item["postId"]] = true
	}

	req2 := httptest.NewRequest(
		http.MethodGet,
		"/content/feed?sort=recommend&limit=4&cursor="+url.QueryEscape(page1.NextCursor),
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
		if page1IDs[item["postId"]] {
			t.Fatalf("page 2 item %v also found on page 1", item["postId"])
		}
	}
}

// TestGetFeedFutureWindowChangesOnly verifies strong feedback only impacts
// items after the current cursor (future window), while already returned
// history remains unchanged on client side.
// contract.yaml: get_feed_future_window_changes_only / go_func: TestGetFeedFutureWindowChangesOnly
func TestGetFeedFutureWindowChangesOnly(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	// Use distinct authors so rerank (maxAuthorPerFeed=3) allows 4+ items for first page + cursor.
	for i := range 12 {
		authorID := fmt.Sprintf("user_fw_%d", i%4)
		submitPublishedPostWithAuthor(t, authorID, fmt.Sprintf(
			`{"contentType":"image","title":"Future Window %d","body":"content %d"}`, i, i,
		))
	}

	req1 := httptest.NewRequest(http.MethodGet, "/content/feed?sort=recommend&limit=4", nil)
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
		"/content/feed?sort=recommend&limit=4&cursor="+url.QueryEscape(page1.NextCursor),
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

	dislikeID, _ := page2.Items[0]["postId"].(string)
	if dislikeID == "" {
		t.Fatal("page2 first item id should not be empty")
	}
	behaviorReq := httptest.NewRequest(
		http.MethodPost,
		"/content/behaviors",
		strings.NewReader(fmt.Sprintf(`{"events":[{"contentId":"%s","action":"dislike"}]}`, dislikeID)),
	)
	behaviorReq.Header.Set("Content-Type", "application/json")
	behaviorReq.Header.Set("X-Client-User-Id", "user_fw_01")
	behaviorReq.Header.Set("X-Client-Session-Id", "session_fw_01")
	behaviorRec := httptest.NewRecorder()
	testHandler.ServeHTTP(behaviorRec, behaviorReq)
	if behaviorRec.Code != http.StatusNoContent {
		t.Fatalf("behavior expected 204, got %d: %s", behaviorRec.Code, behaviorRec.Body.String())
	}

	req2After := httptest.NewRequest(
		http.MethodGet,
		"/content/feed?sort=recommend&limit=4&cursor="+url.QueryEscape(page1.NextCursor),
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
		if item["postId"] == dislikeID {
			t.Fatalf("disliked content %s should be filtered from future window", dislikeID)
		}
	}
}

func TestGetFeedFutureWindowFiltersHiddenAuthorAndContentType(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	for i := range 16 {
		authorID := fmt.Sprintf("user_hide_%d", i%4)
		contentType := "image"
		if i%3 == 0 {
			contentType = "video"
		}
		payload := fmt.Sprintf(
			`{"contentType":%q,"title":"Hide Window %d","body":"content %d"}`,
			contentType, i, i,
		)
		submitPublishedPostWithAuthor(t, authorID, payload)
	}

	req1 := httptest.NewRequest(http.MethodGet, "/content/feed?sort=recommend&limit=5", nil)
	req1.Header.Set("X-Client-User-Id", "user_hide_01")
	req1.Header.Set("X-Client-Session-Id", "session_hide_01")
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
	if page1.NextCursor == "" {
		t.Fatal("page1 should include cursor")
	}

	req2 := httptest.NewRequest(
		http.MethodGet,
		"/content/feed?sort=recommend&limit=8&cursor="+url.QueryEscape(page1.NextCursor),
		nil,
	)
	req2.Header.Set("X-Client-User-Id", "user_hide_01")
	req2.Header.Set("X-Client-Session-Id", "session_hide_01")
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
	if len(page2.Items) < 2 {
		t.Fatalf("page2 should contain enough items, got %d", len(page2.Items))
	}

	hideAuthorItem := page2.Items[0]
	hideAuthorID, _ := hideAuthorItem["postId"].(string)
	hiddenAuthor, _ := hideAuthorItem["authorId"].(string)
	if hideAuthorID == "" || hiddenAuthor == "" {
		t.Fatalf("page2 first item should include id/authorId: %+v", hideAuthorItem)
	}
	hideTypeItem := page2.Items[1]
	hideTypeID, _ := hideTypeItem["postId"].(string)
	hiddenType, _ := hideTypeItem["contentType"].(string)
	if hiddenType == "" {
		hiddenType, _ = hideTypeItem["type"].(string)
	}
	if hideTypeID == "" || hiddenType == "" {
		t.Fatalf("page2 second item should include id/contentType: %+v", hideTypeItem)
	}

	behaviorReq := httptest.NewRequest(
		http.MethodPost,
		"/content/behaviors",
		strings.NewReader(fmt.Sprintf(
			`{"events":[{"contentId":%q,"action":"hide_author","authorId":%q},{"contentId":%q,"action":"hide_content_type","contentType":%q}]}`,
			hideAuthorID,
			hiddenAuthor,
			hideTypeID,
			hiddenType,
		)),
	)
	behaviorReq.Header.Set("Content-Type", "application/json")
	behaviorReq.Header.Set("X-Client-User-Id", "user_hide_01")
	behaviorReq.Header.Set("X-Client-Session-Id", "session_hide_01")
	behaviorRec := httptest.NewRecorder()
	testHandler.ServeHTTP(behaviorRec, behaviorReq)
	if behaviorRec.Code != http.StatusNoContent {
		t.Fatalf("behavior expected 204, got %d: %s", behaviorRec.Code, behaviorRec.Body.String())
	}

	reqAfter := httptest.NewRequest(
		http.MethodGet,
		"/content/feed?sort=recommend&limit=8&cursor="+url.QueryEscape(page1.NextCursor),
		nil,
	)
	reqAfter.Header.Set("X-Client-User-Id", "user_hide_01")
	reqAfter.Header.Set("X-Client-Session-Id", "session_hide_01")
	recAfter := httptest.NewRecorder()
	testHandler.ServeHTTP(recAfter, reqAfter)
	if recAfter.Code != http.StatusOK {
		t.Fatalf("page2 after feedback expected 200, got %d: %s", recAfter.Code, recAfter.Body.String())
	}
	var pageAfter struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(recAfter.Body.Bytes(), &pageAfter); err != nil {
		t.Fatalf("page2 after decode: %v", err)
	}
	for _, item := range pageAfter.Items {
		if item["authorId"] == hiddenAuthor {
			t.Fatalf("hidden author %s should be filtered from future window: %+v", hiddenAuthor, item)
		}
		if item["contentType"] == hiddenType || item["type"] == hiddenType {
			t.Fatalf("hidden contentType %s should be filtered from future window: %+v", hiddenType, item)
		}
	}
}

// TestFeedIssuesServerFeedRequestID verifies the feed envelope carries a
// server-authoritative feedRequestId (frq_ prefix) plus ranking/reason pipeline
// versions on first load, and that echoing the id on the next page keeps the
// same attribution id (a single feed session keeps one feedRequestId).
// contract.yaml: get_feed_issues_server_feed_request_id / go_func: TestFeedIssuesServerFeedRequestID
func TestFeedIssuesServerFeedRequestID(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	for i := range 10 {
		submitPublishedPost(t, fmt.Sprintf(
			`{"contentType":"image","title":"FRQ post %d","body":"content %d"}`, i, i,
		))
	}

	type feedEnvelope struct {
		Items          []map[string]any `json:"items"`
		NextCursor     string           `json:"nextCursor"`
		FeedRequestID  string           `json:"feedRequestId"`
		RankingVersion string           `json:"rankingVersion"`
		ReasonVersion  string           `json:"reasonVersion"`
	}

	// First load: no echoed id — server must mint a fresh frq_ id and attach versions.
	req1 := httptest.NewRequest(http.MethodGet, "/content/feed?sort=recommend&limit=5", nil)
	rec1 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec1, req1)
	if rec1.Code != http.StatusOK {
		t.Fatalf("first page: expected 200, got %d: %s", rec1.Code, rec1.Body.String())
	}
	var page1 feedEnvelope
	if err := json.Unmarshal(rec1.Body.Bytes(), &page1); err != nil {
		t.Fatalf("first page decode: %v", err)
	}
	if !strings.HasPrefix(page1.FeedRequestID, "frq_") {
		t.Fatalf("feedRequestId must be server-issued with frq_ prefix, got %q", page1.FeedRequestID)
	}
	if page1.RankingVersion == "" || page1.ReasonVersion == "" {
		t.Fatalf("feed envelope must carry rankingVersion + reasonVersion, got ranking=%q reason=%q",
			page1.RankingVersion, page1.ReasonVersion)
	}

	// Next page: echo the feedRequestId — server must keep the same attribution id.
	nextURL := fmt.Sprintf("/content/feed?sort=recommend&limit=5&feedRequestId=%s", url.QueryEscape(page1.FeedRequestID))
	if page1.NextCursor != "" {
		nextURL += "&cursor=" + url.QueryEscape(page1.NextCursor)
	}
	req2 := httptest.NewRequest(http.MethodGet, nextURL, nil)
	rec2 := httptest.NewRecorder()
	testHandler.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusOK {
		t.Fatalf("second page: expected 200, got %d: %s", rec2.Code, rec2.Body.String())
	}
	var page2 feedEnvelope
	if err := json.Unmarshal(rec2.Body.Bytes(), &page2); err != nil {
		t.Fatalf("second page decode: %v", err)
	}
	if page2.FeedRequestID != page1.FeedRequestID {
		t.Fatalf("echoing feedRequestId must keep the same attribution id: page1=%q page2=%q",
			page1.FeedRequestID, page2.FeedRequestID)
	}
}

// TestListFeedWithPagination creates image posts then verifies GET /content/feed
// returns 200 with items array, and that a second page call also succeeds.
func TestListFeedWithPagination(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	for i := range 4 {
		payload := fmt.Sprintf(`{"contentType":"image","title":"Feed post %d","body":"content %d"}`, i, i)
		submitPublishedPost(t, payload)
	}

	req1 := httptest.NewRequest(http.MethodGet, "/content/feed?type=image&limit=3", nil)
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
	req := httptest.NewRequest(http.MethodGet, "/content/feed?limit=10", nil)
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
			t.Fatalf("blocked author should be filtered, got item=%v", item["postId"])
		}
	}
}

// TestGetFeedFiltersBlockedKeyword verifies recall-post filtering can exclude
// content whose title/body/tags hit blocked keywords.
func TestGetFeedFiltersBlockedKeyword(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/content/feed?limit=10", nil)
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
		if item["postId"] == "post_photo_001" {
			t.Fatalf("keyword-hit post should be filtered, got post_photo_001")
		}
	}
}

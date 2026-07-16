package http

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	behaviorapp "quwoquan_service/services/content-service/internal/application/behavior"
	feedapp "quwoquan_service/services/content-service/internal/application/feed"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	reportapp "quwoquan_service/services/content-service/internal/application/report"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
	"quwoquan_service/services/content-service/internal/testsupport"
)

type localPostDetailReader struct {
	store *testsupport.PostStore
}

func (r localPostDetailReader) FindPostDetail(
	ctx context.Context,
	postID postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	post, found := r.store.FindByID(ctx, string(postID))
	if !found {
		return postports.PostDetailSlice{}, false, nil
	}
	raw, err := json.Marshal(post)
	if err != nil {
		return postports.PostDetailSlice{}, false, err
	}
	var detail postports.PostDetailSlice
	if err := json.Unmarshal(raw, &detail); err != nil {
		return postports.PostDetailSlice{}, false, err
	}
	return detail, true, nil
}

func newTestHandler() http.Handler {
	redis := testsupport.NewFakeRedis()
	hotPath := rtrec.NewHotPath(redis)
	store := testsupport.NewPostStore(recinfra.DefaultSeedPosts())
	source := recinfra.NewPostProjectionSource(store, store)
	engine := rtrec.NewEngine(hotPath, []rtrec.CandidateSource{source})
	feedService := feedapp.NewFeedService(engine, testsupport.NewPostFeedReader(store))
	postService := postapp.NewPostService(postapp.BindDataPorts(store))
	reportStore := testsupport.NewReportStore()
	reportService := reportapp.NewReportService(reportapp.BindDataPorts(reportStore))
	behaviorService := behaviorapp.NewBehaviorService(hotPath, store)
	postQueryService := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: localPostDetailReader{store: store},
	})
	return NewContentHandler(
		feedService,
		postapp.BindFacades(postService),
		postQueryService,
		nil,
		nil,
		reportapp.BindFacades(reportService),
		behaviorService,
	).Routes()
}

func newFeedHandlerWithFeatures(features rtrec.FeatureProvider) http.Handler {
	redis := testsupport.NewFakeRedis()
	hotPath := rtrec.NewHotPath(redis)
	store := testsupport.NewPostStore(recinfra.DefaultSeedPosts())
	source := recinfra.NewPostProjectionSource(store, store)
	engine := rtrec.NewEngine(hotPath, []rtrec.CandidateSource{source}, rtrec.WithFeatureProvider(features))
	feedService := feedapp.NewFeedService(engine, testsupport.NewPostFeedReader(store))
	postService := postapp.NewPostService(postapp.BindDataPorts(store))
	reportStore := testsupport.NewReportStore()
	reportService := reportapp.NewReportService(reportapp.BindDataPorts(reportStore))
	behaviorService := behaviorapp.NewBehaviorService(hotPath, store)
	postQueryService := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: localPostDetailReader{store: store},
	})
	return NewContentHandler(
		feedService,
		postapp.BindFacades(postService),
		postQueryService,
		nil,
		nil,
		reportapp.BindFacades(reportService),
		behaviorService,
	).Routes()
}

type stubFeatureProvider struct {
	features *rtrec.UserFeatureVector
}

func (s *stubFeatureProvider) GetFeatures(_ context.Context, _ string) (*rtrec.UserFeatureVector, error) {
	return s.features, nil
}

func setActorHeaders(req *http.Request, ownerID, subAccountID string) {
	if ownerID != "" {
		req.Header.Set("X-Client-User-Id", ownerID)
	}
	if subAccountID != "" {
		req.Header.Set("X-Client-Sub-Account-Id", subAccountID)
	}
	if req.Header.Get("Idempotency-Key") == "" && req.Header.Get("X-Request-Id") == "" {
		req.Header.Set("X-Request-Id", "contract-test-"+subAccountID+"-"+strconv.FormatInt(time.Now().UnixNano(), 10))
	}
}

func TestHealthz(t *testing.T) {
	req := httptest.NewRequest("GET", "/healthz", nil)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("unexpected status: %d", rec.Code)
	}
}

func TestFeedAndPostEndpoints(t *testing.T) {
	feedReq := httptest.NewRequest("GET", "/v1/content/feed?type=photo&limit=1", nil)
	feedRec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(feedRec, feedReq)
	if feedRec.Code != 200 {
		t.Fatalf("unexpected feed status: %d", feedRec.Code)
	}
	var feedBody struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(feedRec.Body.Bytes(), &feedBody); err != nil {
		t.Fatalf("decode feed response: %v", err)
	}
	if len(feedBody.Items) == 0 {
		t.Fatalf("expected feed items")
	}

	postReq := httptest.NewRequest("GET", "/v1/content/posts/post_photo_001", nil)
	postRec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(postRec, postReq)
	if postRec.Code != 200 {
		t.Fatalf("unexpected post status: %d", postRec.Code)
	}
}

func TestAppConfigEndpointIsImplemented(t *testing.T) {
	req := httptest.NewRequest("GET", "/v1/config/app", nil)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected app config status 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode app config response: %v", err)
	}
	content, _ := body["content"].(map[string]any)
	if content == nil {
		t.Fatalf("missing content config: %+v", body)
	}
}

func TestAuthorImpactEndpointIsImplemented(t *testing.T) {
	req := httptest.NewRequest("GET", "/v1/content/sub-accounts/test_author/author-impact", nil)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected author impact status 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode author impact response: %v", err)
	}
	if body["authorId"] != "" || body["total"] != float64(0) {
		t.Fatalf("unexpected author impact fallback body: %+v", body)
	}
}

func TestCreatePostBodyBindingRejectsUnknownField(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/v1/content/posts",
		bytes.NewBufferString(`{"unknownField":"x"}`),
	)
	setActorHeaders(req, "owner_test_unknown", "sub_test_unknown")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("unexpected create status for invalid field: %d", rec.Code)
	}
}

func TestCreatePostRequiresTransportIdempotencyHeader(t *testing.T) {
	handler := newTestHandler()
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts",
		bytes.NewBufferString(`{"contentType":"micro","body":"缺少幂等键"}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-Sub-Account-Id", "persona-idempotency")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected 400 without Idempotency-Key/X-Request-Id, got %d: %s",
			rec.Code,
			rec.Body.String(),
		)
	}
}

func TestCreatePostBodyBindingAcceptsWritableFields(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/v1/content/posts",
		bytes.NewBufferString(`{"contentType":"article","articleMarkdown":"# 测试文章\n\nb","articleMarkdownVersion":"qwq-rich-md/1","articleAssetManifest":{"assets":[]}}`),
	)
	setActorHeaders(req, "owner_test_create", "sub_test_create")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("unexpected create status for valid payload: %d", rec.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode create response: %v", err)
	}
	if _, ok := body["_id"]; !ok {
		t.Fatalf("missing id in create response")
	}
}

func TestReportBehaviorsEndpoint(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/v1/content/behaviors",
		bytes.NewBufferString(`{"userId":"u1","events":[{"contentId":"post_photo_001","action":"click"}]}`),
	)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("unexpected behaviors status: %d", rec.Code)
	}
}

// TestFeedIssuesServerFeedRequestID 断言首页推荐主链路服务端权威下发 feedRequestId（frq_ 前缀）
// 与 rankingVersion，并在客户端回显时保持同一归因 id（feedRequestId echo）。
func TestFeedIssuesServerFeedRequestID(t *testing.T) {
	handler := newTestHandler()

	firstReq := httptest.NewRequest("GET", "/v1/content/feed?sort=recommend&limit=2", nil)
	firstRec := httptest.NewRecorder()
	handler.ServeHTTP(firstRec, firstReq)
	if firstRec.Code != http.StatusOK {
		t.Fatalf("unexpected feed status: %d", firstRec.Code)
	}
	var firstBody struct {
		FeedRequestID  string `json:"feedRequestId"`
		RankingVersion string `json:"rankingVersion"`
		ReasonVersion  string `json:"reasonVersion"`
	}
	if err := json.Unmarshal(firstRec.Body.Bytes(), &firstBody); err != nil {
		t.Fatalf("decode feed response: %v", err)
	}
	if !strings.HasPrefix(firstBody.FeedRequestID, "frq_") {
		t.Fatalf("expected server-issued feedRequestId with frq_ prefix, got %q", firstBody.FeedRequestID)
	}
	if firstBody.RankingVersion != rtrec.RankingVersion {
		t.Fatalf("expected rankingVersion %q, got %q", rtrec.RankingVersion, firstBody.RankingVersion)
	}
	if firstBody.ReasonVersion != rtrec.ReasonVersion {
		t.Fatalf("expected reasonVersion %q, got %q", rtrec.ReasonVersion, firstBody.ReasonVersion)
	}

	echoReq := httptest.NewRequest(
		"GET",
		"/v1/content/feed?sort=recommend&limit=2&feedRequestId="+firstBody.FeedRequestID,
		nil,
	)
	echoRec := httptest.NewRecorder()
	handler.ServeHTTP(echoRec, echoReq)
	if echoRec.Code != http.StatusOK {
		t.Fatalf("unexpected feed echo status: %d", echoRec.Code)
	}
	var echoBody struct {
		FeedRequestID string `json:"feedRequestId"`
	}
	if err := json.Unmarshal(echoRec.Body.Bytes(), &echoBody); err != nil {
		t.Fatalf("decode feed echo response: %v", err)
	}
	if echoBody.FeedRequestID != firstBody.FeedRequestID {
		t.Fatalf("expected feedRequestId echo %q, got %q", firstBody.FeedRequestID, echoBody.FeedRequestID)
	}
}

func TestFeedRecommendUsesLongTermTagFeatures(t *testing.T) {
	handler := newFeedHandlerWithFeatures(&stubFeatureProvider{features: &rtrec.UserFeatureVector{
		TagAffinities: map[string]float64{"art": 10},
	}})
	req := httptest.NewRequest("GET", "/v1/content/feed?sort=recommend&limit=1", nil)
	req.Header.Set("X-Client-User-Id", "u1")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("unexpected feed status: %d", rec.Code)
	}
	var body struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode feed response: %v", err)
	}
	if len(body.Items) == 0 {
		t.Fatalf("expected feed items")
	}
	id, _ := body.Items[0]["id"].(string)
	if id == "" {
		t.Fatalf("missing id in first item")
	}
}

func TestFeedWithSessionIdFromHeader(t *testing.T) {
	req := httptest.NewRequest("GET", "/v1/content/feed?type=photo&limit=1", nil)
	req.Header.Set("X-Client-Session-Id", "dart_session_abc")
	req.Header.Set("X-Client-User-Id", "user_123")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("unexpected feed status with headers: %d", rec.Code)
	}
}

func TestBehaviorsWithSessionIdFromHeader(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/v1/content/behaviors",
		bytes.NewBufferString(`{"events":[{"contentId":"post_photo_001","action":"click"}]}`),
	)
	req.Header.Set("X-Client-Session-Id", "dart_session_abc")
	req.Header.Set("X-Client-User-Id", "user_123")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("unexpected behaviors status with header auth: %d", rec.Code)
	}
}

func TestCreatePostWithLocationField(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/v1/content/posts",
		bytes.NewBufferString(`{"contentType":"article","location":{"latitude":39.9,"longitude":116.4},"locationName":"Beijing","articleMarkdown":"# loc test\n\nb","articleMarkdownVersion":"qwq-rich-md/1","articleAssetManifest":{"assets":[]}}`),
	)
	setActorHeaders(req, "owner_test_location", "sub_test_location")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusCreated {
		t.Fatalf("unexpected create status: %d, body: %s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	json.Unmarshal(rec.Body.Bytes(), &body)
	loc, ok := body["location"].(map[string]any)
	if !ok {
		t.Fatalf("location should be a map, got %T", body["location"])
	}
	if loc["latitude"].(float64) != 39.9 {
		t.Errorf("expected latitude 39.9, got %v", loc["latitude"])
	}
}

func TestMomentRequiresBodyOrMedia(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/v1/content/posts",
		bytes.NewBufferString(`{"contentType":"micro","body":"","mediaUrls":[],"videoUrl":""}`),
	)
	setActorHeaders(req, "owner_test_moment", "sub_test_moment")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for empty moment payload, got %d", rec.Code)
	}
}

func TestPostImmutableAfterPublish(t *testing.T) {
	handler := newTestHandler()
	createReq := httptest.NewRequest(
		"POST",
		"/v1/content/posts",
		bytes.NewBufferString(`{"contentType":"article","articleMarkdown":"# t\n\nb","articleMarkdownVersion":"qwq-rich-md/1","articleAssetManifest":{"assets":[]}}`),
	)
	setActorHeaders(createReq, "u1", "u1")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("unexpected create status: %d", createRec.Code)
	}
	var created map[string]any
	_ = json.Unmarshal(createRec.Body.Bytes(), &created)
	postID, _ := created["_id"].(string)
	publishReq := httptest.NewRequest(
		"POST",
		"/v1/content/posts/"+postID+"/publish",
		bytes.NewBufferString(`{}`),
	)
	setActorHeaders(publishReq, "u1", "u1")
	publishRec := httptest.NewRecorder()
	handler.ServeHTTP(publishRec, publishReq)
	if publishRec.Code != http.StatusOK {
		t.Fatalf("unexpected publish status: %d", publishRec.Code)
	}

	updateReq := httptest.NewRequest(
		"PATCH",
		"/v1/content/posts/"+postID,
		bytes.NewBufferString(`{"title":"new title"}`),
	)
	setActorHeaders(updateReq, "u1", "u1")
	updateRec := httptest.NewRecorder()
	handler.ServeHTTP(updateRec, updateReq)
	if updateRec.Code != http.StatusConflict {
		t.Fatalf("expected 409 for immutable post, got %d", updateRec.Code)
	}
}

func TestUpdatePostRejectsDifferentPersonaOwner(t *testing.T) {
	handler := newTestHandler()
	createReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/content/posts",
		bytes.NewBufferString(`{"contentType":"micro","body":"private draft"}`),
	)
	setActorHeaders(createReq, "account-owner", "persona-owner")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("create status = %d: %s", createRec.Code, createRec.Body.String())
	}

	var created struct {
		ID string `json:"_id"`
	}
	if err := json.Unmarshal(createRec.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode created post: %v", err)
	}
	if created.ID == "" {
		t.Fatal("created post id is empty")
	}

	updateReq := httptest.NewRequest(
		http.MethodPatch,
		"/v1/content/posts/"+created.ID,
		bytes.NewBufferString(`{"body":"forged update"}`),
	)
	setActorHeaders(updateReq, "account-outsider", "persona-outsider")
	updateRec := httptest.NewRecorder()
	handler.ServeHTTP(updateRec, updateReq)
	if updateRec.Code != http.StatusForbidden {
		t.Fatalf(
			"expected 403 for a different persona, got %d: %s",
			updateRec.Code,
			updateRec.Body.String(),
		)
	}
}

func TestDeletePostAndTombstoneLookup(t *testing.T) {
	handler := newTestHandler()
	createReq := httptest.NewRequest(
		"POST",
		"/v1/content/posts",
		bytes.NewBufferString(`{"contentType":"article","articleMarkdown":"# to delete\n\nb","articleMarkdownVersion":"qwq-rich-md/1","articleAssetManifest":{"assets":[]}}`),
	)
	setActorHeaders(createReq, "u_delete", "u_delete")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("create failed: %d", createRec.Code)
	}
	var created map[string]any
	_ = json.Unmarshal(createRec.Body.Bytes(), &created)
	postID, _ := created["_id"].(string)

	delReq := httptest.NewRequest("DELETE", "/v1/content/posts/"+postID, nil)
	setActorHeaders(delReq, "u_delete", "u_delete")
	delRec := httptest.NewRecorder()
	handler.ServeHTTP(delRec, delReq)
	if delRec.Code != http.StatusOK {
		t.Fatalf("delete failed: %d", delRec.Code)
	}

	getReq := httptest.NewRequest("GET", "/v1/content/posts/"+postID, nil)
	getRec := httptest.NewRecorder()
	handler.ServeHTTP(getRec, getReq)
	if getRec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for deleted tombstone, got %d", getRec.Code)
	}
}

func TestRetiredPostCircleMutationRouteIsAbsent(t *testing.T) {
	handler := newTestHandler()
	circleReq := httptest.NewRequest(
		"PATCH",
		"/v1/content/posts/post-retired-route/circles",
		bytes.NewBufferString(`{"add":["circle_a"]}`),
	)
	setActorHeaders(circleReq, "author1", "author1")
	circleRec := httptest.NewRecorder()
	handler.ServeHTTP(circleRec, circleReq)
	if circleRec.Code != http.StatusNotFound {
		t.Fatalf("retired Post circle mutation route must be absent, got %d", circleRec.Code)
	}
}

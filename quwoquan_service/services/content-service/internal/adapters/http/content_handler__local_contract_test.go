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
	var asMap map[string]any
	if err := json.Unmarshal(raw, &asMap); err != nil {
		return postports.PostDetailSlice{}, false, err
	}
	if _, ok := asMap["postId"]; !ok {
		asMap["postId"] = asMap["id"]
	}
	delete(asMap, "id")
	delete(asMap, "_id")
	normalized, err := json.Marshal(asMap)
	if err != nil {
		return postports.PostDetailSlice{}, false, err
	}
	var detail postports.PostDetailSlice
	if err := json.Unmarshal(normalized, &detail); err != nil {
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
	if req.Header.Get("Idempotency-Key") == "" {
		req.Header.Set("Idempotency-Key", "contract-test-"+subAccountID+"-"+strconv.FormatInt(time.Now().UnixNano(), 10))
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
	feedReq := httptest.NewRequest("GET", "/content/feed?type=photo&limit=1", nil)
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

	postReq := httptest.NewRequest("GET", "/content/posts/post_photo_001", nil)
	postRec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(postRec, postReq)
	if postRec.Code != 200 {
		t.Fatalf("unexpected post status: %d", postRec.Code)
	}
	var postBody map[string]any
	if err := json.Unmarshal(postRec.Body.Bytes(), &postBody); err != nil {
		t.Fatalf("decode post response: %v", err)
	}
	if postBody["postId"] != "post_photo_001" {
		t.Fatalf("GetPost must expose the generated postId wire field: %+v", postBody)
	}
	if _, legacyID := postBody["_id"]; legacyID {
		t.Fatalf("GetPost must not expose storage _id as a client wire field: %+v", postBody)
	}
}

func TestAppConfigEndpointIsImplemented(t *testing.T) {
	req := httptest.NewRequest("GET", "/config/app", nil)
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
	req := httptest.NewRequest("GET", "/content/sub-accounts/test_author/author-impact", nil)
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

func TestSubmitPostPublicationBodyBindingRejectsUnknownField(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/content/posts:publish",
		bytes.NewBufferString(`{"unknownField":"x"}`),
	)
	setActorHeaders(req, "owner_test_unknown", "sub_test_unknown")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("unexpected create status for invalid field: %d", rec.Code)
	}
}

func TestSubmitPostPublicationRequiresTransportIdempotencyHeader(t *testing.T) {
	handler := newTestHandler()
	req := httptest.NewRequest(
		http.MethodPost,
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-missing-key","localDraftId":"draft-missing-key","contentType":"micro","body":"缺少幂等键"}`),
	)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-Sub-Account-Id", "persona-idempotency")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf(
			"expected 400 without Idempotency-Key, got %d: %s",
			rec.Code,
			rec.Body.String(),
		)
	}
}

func TestSubmitPostPublicationBodyBindingAcceptsWritableFields(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-create","localDraftId":"draft-create","contentType":"article","articleMarkdown":"# 测试文章\n\nb","markdownDialect":"qwq-rich-md","articleAssetManifest":{"assets":[]}}`),
	)
	setActorHeaders(req, "owner_test_create", "sub_test_create")
	req.Header.Set("Idempotency-Key", "intent-create")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("unexpected create status for valid payload: %d", rec.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode create response: %v", err)
	}
	postID, _ := body["postId"].(string)
	if strings.TrimSpace(postID) == "" {
		t.Fatalf("missing postId in create response: %+v", body)
	}
	if body["publishIntentId"] != "intent-create" ||
		body["localDraftId"] != "draft-create" ||
		body["state"] != "published" {
		t.Fatalf("publication receipt is incomplete: %+v", body)
	}
}

func TestReportBehaviorsEndpoint(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/content/behaviors",
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

	firstReq := httptest.NewRequest("GET", "/content/feed?sort=recommend&limit=2", nil)
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
		"/content/feed?sort=recommend&limit=2&feedRequestId="+firstBody.FeedRequestID,
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
	req := httptest.NewRequest("GET", "/content/feed?sort=recommend&limit=1", nil)
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
	postID, _ := body.Items[0]["postId"].(string)
	if postID == "" {
		t.Fatalf("missing postId in first item: %+v", body.Items[0])
	}
	if _, legacyID := body.Items[0]["_id"]; legacyID {
		t.Fatalf("feed item must not expose storage _id: %+v", body.Items[0])
	}
}

func TestFeedWithSessionIdFromHeader(t *testing.T) {
	req := httptest.NewRequest("GET", "/content/feed?type=photo&limit=1", nil)
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
		"/content/behaviors",
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

func TestSubmitPostPublicationWithLocationField(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-location","localDraftId":"draft-location","contentType":"article","location":{"latitude":39.9,"longitude":116.4},"locationName":"Beijing","articleMarkdown":"# loc test\n\nb","markdownDialect":"qwq-rich-md","articleAssetManifest":{"assets":[]}}`),
	)
	setActorHeaders(req, "owner_test_location", "sub_test_location")
	req.Header.Set("Idempotency-Key", "intent-location")
	rec := httptest.NewRecorder()
	handler := newTestHandler()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("unexpected create status: %d, body: %s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	json.Unmarshal(rec.Body.Bytes(), &body)
	postID, _ := body["postId"].(string)
	getReq := httptest.NewRequest("GET", "/content/posts/"+postID, nil)
	getRec := httptest.NewRecorder()
	handler.ServeHTTP(getRec, getReq)
	var detail map[string]any
	json.Unmarshal(getRec.Body.Bytes(), &detail)
	loc, ok := detail["location"].(map[string]any)
	if !ok {
		t.Fatalf("location should be a map, got %T", detail["location"])
	}
	if loc["latitude"].(float64) != 39.9 {
		t.Errorf("expected latitude 39.9, got %v", loc["latitude"])
	}
}

func TestMomentRequiresBodyOrMedia(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-empty","localDraftId":"draft-empty","contentType":"micro","body":""}`),
	)
	setActorHeaders(req, "owner_test_moment", "sub_test_moment")
	req.Header.Set("Idempotency-Key", "intent-empty")
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for empty moment payload, got %d", rec.Code)
	}
}

func TestRetiredPostDraftMutationRoutesAreAbsent(t *testing.T) {
	handler := newTestHandler()
	createReq := httptest.NewRequest(
		"POST",
		"/content/posts",
		bytes.NewBufferString(`{"contentType":"micro","body":"retired"}`),
	)
	setActorHeaders(createReq, "u1", "u1")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusNotFound {
		t.Fatalf("retired CreatePost route must be absent, got %d", createRec.Code)
	}
	publishReq := httptest.NewRequest(
		"POST",
		"/content/posts/post-retired/publish",
		bytes.NewBufferString(`{}`),
	)
	setActorHeaders(publishReq, "u1", "u1")
	publishRec := httptest.NewRecorder()
	handler.ServeHTTP(publishRec, publishReq)
	if publishRec.Code != http.StatusNotFound {
		t.Fatalf("retired PublishPost route must be absent, got %d", publishRec.Code)
	}
	updateReq := httptest.NewRequest(
		"PATCH",
		"/content/posts/post-retired",
		bytes.NewBufferString(`{"title":"new title"}`),
	)
	setActorHeaders(updateReq, "u1", "u1")
	updateRec := httptest.NewRecorder()
	handler.ServeHTTP(updateRec, updateReq)
	if updateRec.Code != http.StatusNotFound {
		t.Fatalf("retired UpdatePost route must be absent, got %d", updateRec.Code)
	}
}

func TestDeletePostAndTombstoneLookup(t *testing.T) {
	handler := newTestHandler()
	createReq := httptest.NewRequest(
		"POST",
		"/content/posts:publish",
		bytes.NewBufferString(`{"publishIntentId":"intent-delete","localDraftId":"draft-delete","contentType":"article","articleMarkdown":"# to delete\n\nb","markdownDialect":"qwq-rich-md","articleAssetManifest":{"assets":[]}}`),
	)
	setActorHeaders(createReq, "u_delete", "u_delete")
	createReq.Header.Set("Idempotency-Key", "intent-delete")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusAccepted {
		t.Fatalf("create failed: %d", createRec.Code)
	}
	var created map[string]any
	_ = json.Unmarshal(createRec.Body.Bytes(), &created)
	postID, _ := created["postId"].(string)

	delReq := httptest.NewRequest("DELETE", "/content/posts/"+postID, nil)
	setActorHeaders(delReq, "u_delete", "u_delete")
	delRec := httptest.NewRecorder()
	handler.ServeHTTP(delRec, delReq)
	if delRec.Code != http.StatusOK {
		t.Fatalf("delete failed: %d", delRec.Code)
	}

	getReq := httptest.NewRequest("GET", "/content/posts/"+postID, nil)
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
		"/content/posts/post-retired-route/circles",
		bytes.NewBufferString(`{"add":["circle_a"]}`),
	)
	setActorHeaders(circleReq, "author1", "author1")
	circleRec := httptest.NewRecorder()
	handler.ServeHTTP(circleRec, circleReq)
	if circleRec.Code != http.StatusNotFound {
		t.Fatalf("retired Post circle mutation route must be absent, got %d", circleRec.Code)
	}
}

func TestPostDetailProjectionUsesCanonicalMediaURLsWire(t *testing.T) {
	wire := projectPostDetailForClient(postports.PostDetailSlice{
		PostID:      postports.NewPostID("post_media_wire"),
		ContentType: postports.ContentType("image"),
		MediaURLs:   []string{"media/image/s/asset/example"},
	})
	payload, err := json.Marshal(wire)
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatal(err)
	}
	if _, found := decoded["imageUrls"]; found {
		t.Fatalf("post detail must not expose non-canonical imageUrls: %s", payload)
	}
	mediaURLs, found := decoded["mediaUrls"].([]any)
	if !found || len(mediaURLs) != 1 || mediaURLs[0] != "media/image/s/asset/example" {
		t.Fatalf("post detail mediaUrls mismatch: %s", payload)
	}
}

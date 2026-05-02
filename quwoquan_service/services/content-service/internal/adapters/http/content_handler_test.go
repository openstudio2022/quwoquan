package http

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/services/content-service/internal/application"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

func newTestHandler() http.Handler {
	redis := recinfra.NewMemoryRedis()
	hotPath := rtrec.NewHotPath(redis)
	store := persistence.NewPostStore(recinfra.DefaultSeedPosts())
	source := recinfra.NewPostRepositorySource(store)
	engine := rtrec.NewEngine(hotPath, []rtrec.CandidateSource{source})
	feedService := application.NewFeedService(engine, source)
	postService := application.NewPostService(store)
	reportService := application.NewReportService(persistence.NewInMemoryReportStore(), nil)
	behaviorService := application.NewBehaviorService(hotPath, store)
	return NewContentHandler(feedService, postService, reportService, behaviorService).Routes()
}

func newRecommendationHandlerWithFeatures(features rtrec.FeatureProvider) http.Handler {
	redis := recinfra.NewMemoryRedis()
	hotPath := rtrec.NewHotPath(redis)
	store := persistence.NewPostStore(recinfra.DefaultSeedPosts())
	source := recinfra.NewPostRepositorySource(store)
	engine := rtrec.NewEngine(hotPath, []rtrec.CandidateSource{source}, rtrec.WithFeatureProvider(features))
	feedService := application.NewFeedService(engine, source)
	postService := application.NewPostService(store)
	reportService := application.NewReportService(persistence.NewInMemoryReportStore(), nil)
	behaviorService := application.NewBehaviorService(hotPath, store)
	return NewContentHandler(feedService, postService, reportService, behaviorService).Routes()
}

type stubFeatureProvider struct {
	features *rtrec.UserFeatureVector
}

func (s *stubFeatureProvider) GetFeatures(_ context.Context, _ string) (*rtrec.UserFeatureVector, error) {
	return s.features, nil
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

func TestCreatePostBodyBindingRejectsUnknownField(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/v1/content/posts",
		bytes.NewBufferString(`{"unknownField":"x"}`),
	)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("unexpected create status for invalid field: %d", rec.Code)
	}
}

func TestCreatePostBodyBindingAcceptsWritableFields(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/v1/content/posts",
		bytes.NewBufferString(`{"contentType":"article","articleDocument":{"template":"gentle","fontPreset":"clean","titleStyle":"major","nodes":[{"id":"p1","type":"paragraph","text":"b"}]}}`),
	)
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

func TestRecommendEndpoint(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/v1/content/recommend",
		bytes.NewBufferString(`{"userId":"u1","limit":2}`),
	)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("unexpected recommend status: %d", rec.Code)
	}
}

func TestRecommendEndpoint_UsesLongTermTagFeatures(t *testing.T) {
	handler := newRecommendationHandlerWithFeatures(&stubFeatureProvider{features: &rtrec.UserFeatureVector{
		TagAffinities: map[string]float64{"art": 10},
	}})
	req := httptest.NewRequest(
		"POST",
		"/v1/content/recommend",
		bytes.NewBufferString(`{"userId":"u1","limit":1}`),
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("unexpected recommend status: %d", rec.Code)
	}
	var body struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode recommend response: %v", err)
	}
	if len(body.Items) == 0 {
		t.Fatalf("expected recommend items")
	}
	contentID, _ := body.Items[0]["contentId"].(string)
	if contentID == "" {
		t.Fatalf("missing contentId in first item")
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
		bytes.NewBufferString(`{"contentType":"article","location":{"latitude":39.9,"longitude":116.4},"locationName":"Beijing","articleDocument":{"template":"gentle","fontPreset":"clean","titleStyle":"major","nodes":[{"id":"title","type":"documentTitle","text":"loc test"},{"id":"p1","type":"paragraph","text":"b"}]}}`),
	)
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
		bytes.NewBufferString(`{"contentType":"article","articleDocument":{"template":"gentle","fontPreset":"clean","titleStyle":"major","nodes":[{"id":"title","type":"documentTitle","text":"t"},{"id":"p1","type":"paragraph","text":"b"}]}}`),
	)
	createReq.Header.Set("X-Client-User-Id", "u1")
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
	publishReq.Header.Set("X-Client-User-Id", "u1")
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
	updateRec := httptest.NewRecorder()
	handler.ServeHTTP(updateRec, updateReq)
	if updateRec.Code != http.StatusConflict {
		t.Fatalf("expected 409 for immutable post, got %d", updateRec.Code)
	}
}

func TestDeletePostAndTombstoneLookup(t *testing.T) {
	handler := newTestHandler()
	createReq := httptest.NewRequest(
		"POST",
		"/v1/content/posts",
		bytes.NewBufferString(`{"contentType":"article","articleDocument":{"template":"gentle","fontPreset":"clean","titleStyle":"major","nodes":[{"id":"title","type":"documentTitle","text":"to delete"},{"id":"p1","type":"paragraph","text":"b"}]}}`),
	)
	createReq.Header.Set("X-Client-User-Id", "u_delete")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("create failed: %d", createRec.Code)
	}
	var created map[string]any
	_ = json.Unmarshal(createRec.Body.Bytes(), &created)
	postID, _ := created["_id"].(string)

	delReq := httptest.NewRequest("DELETE", "/v1/content/posts/"+postID, nil)
	delReq.Header.Set("X-Client-User-Id", "u_delete")
	delRec := httptest.NewRecorder()
	handler.ServeHTTP(delRec, delReq)
	if delRec.Code != http.StatusOK {
		t.Fatalf("delete failed: %d", delRec.Code)
	}

	getReq := httptest.NewRequest("GET", "/v1/content/posts/"+postID, nil)
	getRec := httptest.NewRecorder()
	handler.ServeHTTP(getRec, getReq)
	if getRec.Code != http.StatusConflict {
		t.Fatalf("expected 409 for deleted tombstone, got %d", getRec.Code)
	}
}

func TestUpdatePostCirclesRequiresPublic(t *testing.T) {
	handler := newTestHandler()
	createReq := httptest.NewRequest(
		"POST",
		"/v1/content/posts",
		bytes.NewBufferString(`{"contentType":"article","visibility":"private","articleDocument":{"template":"gentle","fontPreset":"clean","titleStyle":"major","nodes":[{"id":"title","type":"documentTitle","text":"private"},{"id":"p1","type":"paragraph","text":"仅圈子分发测试"}]}}`),
	)
	createReq.Header.Set("X-Client-User-Id", "author1")
	createRec := httptest.NewRecorder()
	handler.ServeHTTP(createRec, createReq)
	if createRec.Code != http.StatusCreated {
		t.Fatalf("create failed: %d", createRec.Code)
	}
	var created map[string]any
	_ = json.Unmarshal(createRec.Body.Bytes(), &created)
	postID, _ := created["_id"].(string)

	circleReq := httptest.NewRequest(
		"PATCH",
		"/v1/content/posts/"+postID+"/circles",
		bytes.NewBufferString(`{"add":["circle_a"]}`),
	)
	circleReq.Header.Set("X-Client-User-Id", "author1")
	circleRec := httptest.NewRecorder()
	handler.ServeHTTP(circleRec, circleReq)
	if circleRec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 when private post distributed to circles, got %d", circleRec.Code)
	}
}

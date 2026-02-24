package http

import (
	"bytes"
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
	behaviorService := application.NewBehaviorService(hotPath, store)
	return NewContentHandler(feedService, postService, behaviorService).Routes()
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
		bytes.NewBufferString(`{"title":"t","body":"b","contentType":"article"}`),
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
		bytes.NewBufferString(`{"userId":"u1","events":[{"contentId":"post_photo_001","action":"like"}]}`),
	)
	rec := httptest.NewRecorder()
	newTestHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
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
	if rec.Code != http.StatusOK {
		t.Fatalf("unexpected behaviors status with header auth: %d", rec.Code)
	}
}

func TestCreatePostWithLocationField(t *testing.T) {
	req := httptest.NewRequest(
		"POST",
		"/v1/content/posts",
		bytes.NewBufferString(`{"title":"loc test","body":"b","contentType":"article","location":{"latitude":39.9,"longitude":116.4},"locationName":"Beijing"}`),
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

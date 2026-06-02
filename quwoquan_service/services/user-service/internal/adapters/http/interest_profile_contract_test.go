package http

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/user-service/internal/application"
)

// fakeInterestReader implements application.InterestProfileReader for contract
// tests without Mongo.
type fakeInterestReader struct {
	view *application.InterestProfileView
	err  error
}

func (f *fakeInterestReader) GetInterestProfile(_ context.Context, _ string) (*application.InterestProfileView, error) {
	return f.view, f.err
}

func newInterestHandler(reader application.InterestProfileReader) *UserHandler {
	return &UserHandler{interestProfile: application.NewInterestProfileService(reader)}
}

// Contract: GET /v1/users/{userId}/interest-profile returns 200 with the
// service.yaml response_fields when a profile has been derived.
func TestInterestProfileEndpoint_Computed(t *testing.T) {
	reader := &fakeInterestReader{view: &application.InterestProfileView{
		TopInterests: []application.InterestTopInterest{
			{TagRef: "旅行", Dimension: "topic", Score: 1.0, Level: 5},
		},
		DimensionTops:     map[string][]string{"topic": {"旅行"}},
		LifecycleStage:    "active",
		FreshnessDays:     2,
		DecayHalfLifeDays: 30,
		Segments:          []string{"travel_enthusiast"},
	}}
	mux := newInterestHandler(reader).Routes()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/users/u1/interest-profile", nil)
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200; body=%s", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	// service.yaml response_fields must all be present.
	for _, field := range []string{"userId", "topInterests", "dimensionTops", "lifecycleStage", "freshnessDays", "decayHalfLifeDays", "recomputedAt", "segments"} {
		if _, ok := body[field]; !ok {
			t.Fatalf("response missing field %q; body=%s", field, rec.Body.String())
		}
	}
	if body["userId"] != "u1" {
		t.Fatalf("userId = %v, want u1", body["userId"])
	}
	if body["lifecycleStage"] != "active" {
		t.Fatalf("lifecycleStage = %v, want active", body["lifecycleStage"])
	}
	tops, _ := body["topInterests"].([]any)
	if len(tops) != 1 {
		t.Fatalf("topInterests len = %d, want 1", len(tops))
	}
	segs, _ := body["segments"].([]any)
	if len(segs) != 1 || segs[0] != "travel_enthusiast" {
		t.Fatalf("segments = %v, want [travel_enthusiast]", body["segments"])
	}
}

// Contract: a user with no derived profile yet still gets 200 with an empty
// profile (lifecycleStage="new"), so consumers never special-case 404.
func TestInterestProfileEndpoint_NotYetComputed(t *testing.T) {
	mux := newInterestHandler(&fakeInterestReader{view: nil}).Routes()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/users/u2/interest-profile", nil)
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	if body["lifecycleStage"] != "new" {
		t.Fatalf("lifecycleStage = %v, want new", body["lifecycleStage"])
	}
	if tops, _ := body["topInterests"].([]any); len(tops) != 0 {
		t.Fatalf("expected empty topInterests, got %v", tops)
	}
	if body["userId"] != "u2" {
		t.Fatalf("userId = %v, want u2", body["userId"])
	}
}

// Contract: a reader failure surfaces as a server error, not a silent 200.
func TestInterestProfileEndpoint_ReaderError(t *testing.T) {
	mux := newInterestHandler(&fakeInterestReader{err: context.DeadlineExceeded}).Routes()

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/users/u3/interest-profile", nil)
	mux.ServeHTTP(rec, req)

	if rec.Code < 500 {
		t.Fatalf("status = %d, want >=500 on reader error", rec.Code)
	}
}

// Contract: missing userId path segment is rejected with 400.
func TestInterestProfileEndpoint_MissingUserID(t *testing.T) {
	h := newInterestHandler(&fakeInterestReader{})
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/users//interest-profile", nil)
	h.handleGetUserInterestProfile(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400 for missing userId", rec.Code)
	}
}

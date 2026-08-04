package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/userprofile"
	"testing"
)

func TestClient_GetInterestProfile_MapsContractFields(t *testing.T) {
	var gotPath, gotUserHeader string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotUserHeader = r.Header.Get("X-Client-User-Id")
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"userId":"user_1",
			"topInterests":[
				{"tagRef":"川西自驾","dimension":"topic","score":0.91,"level":4},
				{"tagRef":"高原摄影","dimension":"topic","score":0.7,"level":3}
			],
			"dimensionTops":{"topic":["川西自驾","高原摄影"]},
			"lifecycleStage":"active",
			"freshnessDays":3,
			"decayHalfLifeDays":30,
			"recomputedAt":"2026-04-29T08:00:00Z",
			"segments":["travel_enthusiast"]
		}`))
	}))
	defer srv.Close()

	client := NewClient(srv.Client(), srv.URL)
	profile, err := client.GetInterestProfile(context.Background(), "user_1")
	if err != nil {
		t.Fatalf("GetInterestProfile error: %v", err)
	}
	if profile == nil {
		t.Fatalf("expected non-nil profile")
	}
	if gotPath != "/users/user_1/interest-profile" {
		t.Fatalf("path=%q", gotPath)
	}
	if gotUserHeader != "user_1" {
		t.Fatalf("X-Client-User-Id=%q want user_1", gotUserHeader)
	}
	if profile.LifecycleStage != "active" || profile.FreshnessDays != 3 {
		t.Fatalf("profile lifecycle/freshness wrong: %+v", profile)
	}
	if len(profile.TopInterests) != 2 || profile.TopInterests[0].TagRef != "川西自驾" || profile.TopInterests[0].Score != 0.91 {
		t.Fatalf("top interests mapping wrong: %+v", profile.TopInterests)
	}
	if len(profile.Segments) != 1 || profile.Segments[0] != "travel_enthusiast" {
		t.Fatalf("segments mapping wrong: %v", profile.Segments)
	}
	if got := profile.DimensionTops["topic"]; len(got) != 2 {
		t.Fatalf("dimensionTops mapping wrong: %+v", profile.DimensionTops)
	}
}

func TestClient_GetInterestProfile_NotConfiguredReturnsNil(t *testing.T) {
	// empty base url -> reader disabled, no error
	client := NewClient(http.DefaultClient, "")
	profile, err := client.GetInterestProfile(context.Background(), "user_1")
	if err != nil || profile != nil {
		t.Fatalf("disabled reader must return (nil,nil): profile=%+v err=%v", profile, err)
	}

	// blank userID -> nil
	client2 := NewClient(http.DefaultClient, "http://example.invalid")
	profile2, err2 := client2.GetInterestProfile(context.Background(), "  ")
	if err2 != nil || profile2 != nil {
		t.Fatalf("blank userID must return (nil,nil): profile=%+v err=%v", profile2, err2)
	}
}

func TestClient_GetInterestProfile_NonOKIsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	client := NewClient(srv.Client(), srv.URL)
	if _, err := client.GetInterestProfile(context.Background(), "user_1"); err == nil {
		t.Fatalf("expected error on non-200 status")
	}
}

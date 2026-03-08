package tests

import (
	"net/http"
	"testing"
)

// --- section_config_update (contract.yaml scenario) ---

func TestSectionConfigUpdate(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "板块配置圈子")

	newSections := []map[string]any{
		{"sectionType": "chat", "visible": true, "order": 0},
		{"sectionType": "works", "visible": true, "order": 1},
		{"sectionType": "storage", "visible": false, "order": 2},
		{"sectionType": "interaction", "visible": true, "order": 3},
	}

	rec := doRequest(t, http.MethodPatch, "/v1/circles/"+circleID+"/sections", map[string]any{
		"sections": newSections,
	})
	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204, got %d: %s", rec.Code, rec.Body.String())
	}

	if events := eventSpy.EventsOfType("CircleSectionsUpdated"); len(events) == 0 {
		t.Error("expected CircleSectionsUpdated event to be published")
	}

	// Verify persisted
	rec = doRequest(t, http.MethodGet, "/v1/circles/"+circleID, nil)
	body := decodeBody(t, rec)
	data := body["data"].(map[string]any)
	sections := data["sectionConfig"].([]any)
	if len(sections) != 4 {
		t.Errorf("expected 4 sections, got %d", len(sections))
	}
	first := sections[0].(map[string]any)
	if first["sectionType"] != "chat" {
		t.Errorf("expected first section=chat, got %v", first["sectionType"])
	}
}

// --- feed_pin_and_feature (contract.yaml scenario) ---

func TestFeedPinAndFeature(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "Feed管理圈子")

	rec := doRequest(t, http.MethodPatch, "/v1/circles/"+circleID+"/feed/post_001/pin", map[string]any{
		"pinned": true,
	})
	if rec.Code != http.StatusNoContent {
		t.Fatalf("pin: expected 204, got %d", rec.Code)
	}

	rec = doRequest(t, http.MethodPatch, "/v1/circles/"+circleID+"/feed/post_001/feature", map[string]any{
		"featured": true,
	})
	if rec.Code != http.StatusNoContent {
		t.Fatalf("feature: expected 204, got %d", rec.Code)
	}
}

func TestReportBehavior(t *testing.T) {
	defer cleanCollections(t)

	rec := doRequest(t, http.MethodPost, "/v1/circles/behaviors", map[string]any{
		"userId":    "test_user_001",
		"circleId":  "circle_001",
		"eventType": "impression",
		"sessionId": "sess_001",
	})
	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204, got %d: %s", rec.Code, rec.Body.String())
	}

	if events := eventSpy.EventsOfType("CircleBehaviorReported"); len(events) == 0 {
		t.Error("expected CircleBehaviorReported event to be published")
	}
}

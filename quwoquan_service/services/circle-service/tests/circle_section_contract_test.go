package tests

import (
	"context"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
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
	insertPost(t, bson.M{
		"_id":       "post_001",
		"circleIds": []string{circleID},
		"title":     "待管理帖子",
	})

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

	var doc bson.M
	if err := mongoDB.Collection("posts").FindOne(context.Background(), bson.M{"_id": "post_001"}).Decode(&doc); err != nil {
		t.Fatalf("find post_001 failed: %v", err)
	}
	if doc["pinned"] != true {
		t.Fatalf("expected pinned=true, got %#v", doc["pinned"])
	}
	if _, ok := doc["pinnedAt"]; !ok {
		t.Fatalf("expected pinnedAt to be set: %#v", doc)
	}
	if doc["featured"] != true {
		t.Fatalf("expected featured=true, got %#v", doc["featured"])
	}
	if _, ok := doc["featuredAt"]; !ok {
		t.Fatalf("expected featuredAt to be set: %#v", doc)
	}
}

func TestReportBehavior(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "周活行为圈子")
	rec := doRequestAs(t, http.MethodPost, "/v1/circles/"+circleID+"/join", "test_user_001", nil)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("join expected 204, got %d: %s", rec.Code, rec.Body.String())
	}

	rec = doRequest(t, http.MethodPost, "/v1/circles/behaviors", map[string]any{
		"userId":    "test_user_001",
		"circleId":  circleID,
		"eventType": "impression",
		"sessionId": "sess_001",
	})
	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204, got %d: %s", rec.Code, rec.Body.String())
	}

	if events := eventSpy.EventsOfType("CircleBehaviorReported"); len(events) == 0 {
		t.Error("expected CircleBehaviorReported event to be published")
	}

	var memberDoc bson.M
	if err := mongoDB.Collection("circle_members").FindOne(context.Background(), bson.M{
		"circleId": circleID,
		"userId":   "test_user_001",
	}).Decode(&memberDoc); err != nil {
		t.Fatalf("find member after behavior: %v", err)
	}
	if _, ok := memberDoc["lastActiveAt"]; !ok {
		t.Fatalf("expected lastActiveAt to be set: %#v", memberDoc)
	}

	var circleDoc bson.M
	if err := mongoDB.Collection("circles").FindOne(context.Background(), bson.M{"_id": circleID}).Decode(&circleDoc); err != nil {
		t.Fatalf("find circle after behavior: %v", err)
	}
	if toInt64(circleDoc["weeklyActiveCount"]) != 1 {
		t.Fatalf("expected weeklyActiveCount=1, got %d", toInt64(circleDoc["weeklyActiveCount"]))
	}
}

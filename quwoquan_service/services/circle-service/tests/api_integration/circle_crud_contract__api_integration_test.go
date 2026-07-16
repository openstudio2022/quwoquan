package api_integration

import (
	"context"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

// Circle creation writes only the Circle aggregate. The owner
// CircleMembership is a separate aggregate and must never be inserted by the
// Circle store as a hidden cross-aggregate write.

func TestCreateCircleWithOwner(t *testing.T) {
	defer cleanCollections(t)

	rec := doRequest(t, http.MethodPost, "/v1/circles", map[string]any{
		"name":     "摄影圈",
		"category": "interest",
		"tags":     []string{"photography", "art"},
	})

	if rec.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d: %s", rec.Code, rec.Body.String())
	}

	body := decodeBody(t, rec)
	data := body["data"].(map[string]any)
	circleID := data["_id"].(string)

	// Verify circle exists in MongoDB
	var doc bson.M
	err := mongoDB.Collection("circles").FindOne(context.Background(), bson.M{"_id": circleID}).Decode(&doc)
	if err != nil {
		t.Fatalf("circle not found in MongoDB: %v", err)
	}
	if doc["name"] != "摄影圈" {
		t.Errorf("expected name=摄影圈, got %v", doc["name"])
	}

	memberCount, err := mongoDB.Collection("circle_memberships").CountDocuments(context.Background(), bson.M{"circleId": circleID})
	if err != nil || memberCount != 0 {
		t.Fatalf("Circle store performed a hidden membership write: count=%d err=%v", memberCount, err)
	}
	if toInt64(doc["memberCount"]) != 0 {
		t.Errorf("memberCount must be projection-owned, got %v", doc["memberCount"])
	}

	// Verify CircleCreated event
	if events := eventSpy.EventsOfType("CircleCreated"); len(events) == 0 {
		t.Error("expected CircleCreated event to be published")
	}
}

func TestGetCircleSuccess(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "测试圈子")

	rec := doRequest(t, http.MethodGet, "/v1/circles/"+circleID, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	body := decodeBody(t, rec)
	data := body["data"].(map[string]any)
	if data["name"] != "测试圈子" {
		t.Errorf("expected name=测试圈子, got %v", data["name"])
	}
}

func TestListCirclesSuccess(t *testing.T) {
	defer cleanCollections(t)

	createTestCircle(t, "圈子A")
	createTestCircle(t, "圈子B")

	rec := doRequest(t, http.MethodGet, "/v1/circles?limit=10", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	body := decodeBody(t, rec)
	items := body["items"].([]any)
	if len(items) < 2 {
		t.Errorf("expected at least 2 circles, got %d", len(items))
	}
}

func TestUpdateCircleSuccess(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "原名")

	rec := doRequest(t, http.MethodPatch, "/v1/circles/"+circleID, map[string]any{
		"name": "新名",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	data := body["data"].(map[string]any)
	if data["name"] != "新名" {
		t.Errorf("expected name=新名, got %v", data["name"])
	}

	if events := eventSpy.EventsOfType("CircleUpdated"); len(events) == 0 {
		t.Error("expected CircleUpdated event to be published")
	}
}

func TestArchiveCircleSuccess(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "待归档圈子")

	rec := doRequest(t, http.MethodDelete, "/v1/circles/"+circleID, nil)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204, got %d", rec.Code)
	}

	// Verify status in MongoDB
	var doc bson.M
	mongoDB.Collection("circles").FindOne(context.Background(), bson.M{"_id": circleID}).Decode(&doc)
	if doc["status"] != "archived" {
		t.Errorf("expected status=archived, got %v", doc["status"])
	}

	if events := eventSpy.EventsOfType("CircleArchived"); len(events) == 0 {
		t.Error("expected CircleArchived event to be published")
	}
}

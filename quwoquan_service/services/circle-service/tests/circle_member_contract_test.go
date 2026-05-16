package tests

import (
	"context"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
)

// --- join_circle_open (contract.yaml scenario) ---

func TestJoinOpenCircle(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "开放圈子")

	rec := doRequestAs(t, http.MethodPost, "/v1/circles/"+circleID+"/join", "user_joiner_01", nil)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204, got %d: %s", rec.Code, rec.Body.String())
	}

	// Verify member created
	var memberDoc bson.M
	err := mongoDB.Collection("circle_members").FindOne(context.Background(), bson.M{
		"circleId": circleID, "userId": "user_joiner_01",
	}).Decode(&memberDoc)
	if err != nil {
		t.Fatalf("member not found: %v", err)
	}
	if memberDoc["role"] != "member" {
		t.Errorf("expected role=member, got %v", memberDoc["role"])
	}

	// Verify memberCount incremented
	var circleDoc bson.M
	mongoDB.Collection("circles").FindOne(context.Background(), bson.M{"_id": circleID}).Decode(&circleDoc)
	mc := toInt64(circleDoc["memberCount"])
	if mc != 2 {
		t.Errorf("expected memberCount=2, got %d", mc)
	}

	if events := eventSpy.EventsOfType("CircleMemberJoined"); len(events) == 0 {
		t.Error("expected CircleMemberJoined event to be published")
	}

	// Verify cache invalidated (miniredis should not have the key)
	exists := mr.Exists("cache:circle:" + circleID)
	if exists {
		t.Error("expected cache invalidated after join, but key still exists")
	}
}

func TestJoinCircle_UsesPersonaSubjectHeader(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "分身透传圈子")
	rec := doRequestAsWithHeaders(
		t,
		http.MethodPost,
		"/v1/circles/"+circleID+"/join",
		"user_joiner_owner",
		map[string]string{
			"X-Client-User-Id":                     "user_joiner_owner",
			"X-Client-Sub-Account-Id":              "persona_joiner_01",
			"X-Client-Sub-Account-Context-Version": "ctx_v1",
		},
		nil,
	)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204, got %d: %s", rec.Code, rec.Body.String())
	}

	count, err := mongoDB.Collection("circle_members").CountDocuments(
		context.Background(),
		bson.M{"circleId": circleID, "userId": "persona_joiner_01"},
	)
	if err != nil {
		t.Fatalf("count persona member: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected persona member persisted once, got %d", count)
	}

	ownerCount, err := mongoDB.Collection("circle_members").CountDocuments(
		context.Background(),
		bson.M{"circleId": circleID, "userId": "user_joiner_owner"},
	)
	if err != nil {
		t.Fatalf("count owner member: %v", err)
	}
	if ownerCount != 0 {
		t.Fatalf("expected owner id not persisted as member, got %d", ownerCount)
	}
}

// --- join_circle_idempotent (contract.yaml scenario) ---

func TestJoinDuplicateIdempotent(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "幂等测试圈子")

	// First join
	rec := doRequestAs(t, http.MethodPost, "/v1/circles/"+circleID+"/join", "user_dup_01", nil)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("first join: expected 204, got %d", rec.Code)
	}

	// Second join — should return conflict
	rec = doRequestAs(t, http.MethodPost, "/v1/circles/"+circleID+"/join", "user_dup_01", nil)
	if rec.Code != http.StatusConflict {
		t.Fatalf("second join: expected 409, got %d: %s", rec.Code, rec.Body.String())
	}

	// Verify exactly 1 member record (plus owner)
	count, _ := mongoDB.Collection("circle_members").CountDocuments(context.Background(), bson.M{
		"circleId": circleID, "userId": "user_dup_01",
	})
	if count != 1 {
		t.Errorf("expected exactly 1 member record, got %d", count)
	}
}

// --- leave_circle + member_count_consistency (contract.yaml scenario) ---

func TestMemberCountConsistency(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "计数一致性圈子")

	// Join
	doRequestAs(t, http.MethodPost, "/v1/circles/"+circleID+"/join", "user_leave_01", nil)

	var circleDoc bson.M
	mongoDB.Collection("circles").FindOne(context.Background(), bson.M{"_id": circleID}).Decode(&circleDoc)
	if toInt64(circleDoc["memberCount"]) != 2 {
		t.Fatalf("expected memberCount=2 after join, got %d", toInt64(circleDoc["memberCount"]))
	}

	// Leave
	rec := doRequestAs(t, http.MethodPost, "/v1/circles/"+circleID+"/leave", "user_leave_01", nil)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("leave: expected 204, got %d: %s", rec.Code, rec.Body.String())
	}

	mongoDB.Collection("circles").FindOne(context.Background(), bson.M{"_id": circleID}).Decode(&circleDoc)
	if toInt64(circleDoc["memberCount"]) != 1 {
		t.Errorf("expected memberCount=1 after leave, got %d", toInt64(circleDoc["memberCount"]))
	}

	// Verify member count matches actual documents
	memberCount, _ := mongoDB.Collection("circle_members").CountDocuments(context.Background(), bson.M{
		"circleId": circleID,
	})
	if memberCount != toInt64(circleDoc["memberCount"]) {
		t.Errorf("memberCount mismatch: field=%d actual=%d", toInt64(circleDoc["memberCount"]), memberCount)
	}

	if events := eventSpy.EventsOfType("CircleMemberLeft"); len(events) == 0 {
		t.Error("expected CircleMemberLeft event to be published")
	}
}

func TestListMembers(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "成员列表圈子")
	doRequestAs(t, http.MethodPost, "/v1/circles/"+circleID+"/join", "user_list_01", nil)

	rec := doRequest(t, http.MethodGet, "/v1/circles/"+circleID+"/members?limit=10", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	body := decodeBody(t, rec)
	items := body["items"].([]any)
	if len(items) < 2 {
		t.Errorf("expected at least 2 members, got %d", len(items))
	}
}

func TestListUserCircles(t *testing.T) {
	defer cleanCollections(t)

	createTestCircle(t, "用户圈子A")
	createTestCircle(t, "用户圈子B")

	rec := doRequest(t, http.MethodGet, "/v1/users/test_user_001/circles?limit=10", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	body := decodeBody(t, rec)
	items := body["items"].([]any)
	if len(items) < 2 {
		t.Errorf("expected at least 2 user circles, got %d", len(items))
	}
}

func toInt64(v any) int64 {
	switch n := v.(type) {
	case int64:
		return n
	case int32:
		return int64(n)
	case float64:
		return int64(n)
	default:
		return 0
	}
}

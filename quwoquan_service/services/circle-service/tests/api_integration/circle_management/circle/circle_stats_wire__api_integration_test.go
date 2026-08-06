// spec_ref: specs/feature-tree/circle-community/circle-management-and-stats/kpi-reporting/spec.md#gwt-001
// readiness_case: get-circle-stats-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func TestGetCircleStatsUsesCanonicalWireKeys(t *testing.T) {
	cleanCollections(t)
	now := time.Now().UTC()
	if _, err := mongoDB.Collection("circles").InsertOne(context.Background(), bson.M{
		"_id": "circle-stats-wire", "name": "统计契约圈子", "ownerId": "persona-owner",
		"status": "active", "memberCount": int64(12), "postCount": int64(5),
		"weeklyActiveCount": int64(3), "storageUsedBytes": int64(1024),
		"storageQuotaBytes": int64(2048), "createdAt": now, "updatedAt": now,
	}); err != nil {
		t.Fatal(err)
	}

	request := httptest.NewRequest(http.MethodGet, "/circles/circle-stats-wire/stats", nil)
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("GetCircleStats status=%d body=%s", recorder.Code, recorder.Body.String())
	}

	var response struct {
		Data map[string]any `json:"data"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatal(err)
	}
	want := map[string]any{
		"circleId": "circle-stats-wire", "memberCount": float64(12),
		"postCount": float64(5), "discussionCount": float64(0),
		"weeklyActiveCount": float64(3), "likeCount": float64(0),
		"storageUsedBytes": float64(1024), "storageQuotaBytes": float64(2048),
	}
	if len(response.Data) != len(want) {
		t.Fatalf("stats wire key count=%d want=%d payload=%#v", len(response.Data), len(want), response.Data)
	}
	for key, expected := range want {
		if actual, found := response.Data[key]; !found || actual != expected {
			t.Fatalf("stats wire %s=%#v found=%v want=%#v payload=%#v", key, actual, found, expected, response.Data)
		}
	}
	for _, alias := range []string{"totalMembers", "weeklyActive", "totalPosts", "totalDiscussions"} {
		if _, found := response.Data[alias]; found {
			t.Fatalf("stats wire must not emit retired alias %q: %#v", alias, response.Data)
		}
	}
}

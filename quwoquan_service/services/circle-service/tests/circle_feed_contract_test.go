package tests

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
)

func insertPost(t *testing.T, doc bson.M) {
	t.Helper()
	_, err := mongoDB.Collection("posts").InsertOne(context.Background(), doc)
	if err != nil {
		t.Fatalf("insertPost failed: %v", err)
	}
}

func TestGetCircleFeed_Empty(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "空feed圈子")

	rec := doRequest(t, http.MethodGet, fmt.Sprintf("/v1/circles/%s/feed?limit=10", circleID), nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := decodeBody(t, rec)
	items := body["items"].([]any)
	if len(items) != 0 {
		t.Errorf("expected 0 items, got %d", len(items))
	}
	if cursor, ok := body["cursor"].(string); ok && cursor != "" {
		t.Errorf("expected empty cursor, got %q", cursor)
	}
}

func TestGetCircleFeed_Latest(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "最新排序圈子")
	now := time.Now()

	insertPost(t, bson.M{
		"_id":       "post_old",
		"circleIds": []string{circleID},
		"title":     "旧帖子",
		"createdAt": now.Add(-2 * time.Hour),
	})
	insertPost(t, bson.M{
		"_id":       "post_mid",
		"circleIds": []string{circleID},
		"title":     "中间帖子",
		"createdAt": now.Add(-1 * time.Hour),
	})
	insertPost(t, bson.M{
		"_id":       "post_new",
		"circleIds": []string{circleID},
		"title":     "新帖子",
		"createdAt": now,
	})

	rec := doRequest(t, http.MethodGet, fmt.Sprintf("/v1/circles/%s/feed?sort=latest&limit=10", circleID), nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := decodeBody(t, rec)
	items := body["items"].([]any)
	if len(items) != 3 {
		t.Fatalf("expected 3 items, got %d", len(items))
	}

	first := items[0].(map[string]any)
	second := items[1].(map[string]any)
	third := items[2].(map[string]any)
	if first["_id"] != "post_new" {
		t.Errorf("expected first item post_new, got %v", first["_id"])
	}
	if second["_id"] != "post_mid" {
		t.Errorf("expected second item post_mid, got %v", second["_id"])
	}
	if third["_id"] != "post_old" {
		t.Errorf("expected third item post_old, got %v", third["_id"])
	}
}

func TestGetCircleFeed_Pagination(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "分页圈子")
	now := time.Now()

	for i := 0; i < 5; i++ {
		insertPost(t, bson.M{
			"_id":       fmt.Sprintf("page_post_%d", i),
			"circleIds": []string{circleID},
			"title":     fmt.Sprintf("帖子%d", i),
			"createdAt": now.Add(time.Duration(i) * time.Minute),
		})
	}

	// Page 1: limit=2, sorted latest (newest first → 4,3)
	rec := doRequest(t, http.MethodGet, fmt.Sprintf("/v1/circles/%s/feed?sort=latest&limit=2", circleID), nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("page1: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := decodeBody(t, rec)
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("page1: expected 2 items, got %d", len(items))
	}

	cursor, _ := body["cursor"].(string)
	if cursor == "" {
		t.Fatal("page1: expected non-empty cursor")
	}

	firstPage := make(map[string]bool)
	for _, item := range items {
		id := item.(map[string]any)["_id"].(string)
		firstPage[id] = true
	}

	// Page 2: use cursor
	rec2 := doRequest(t, http.MethodGet, fmt.Sprintf("/v1/circles/%s/feed?sort=latest&limit=2&cursor=%s", circleID, cursor), nil)
	if rec2.Code != http.StatusOK {
		t.Fatalf("page2: expected 200, got %d: %s", rec2.Code, rec2.Body.String())
	}

	body2 := decodeBody(t, rec2)
	items2 := body2["items"].([]any)
	if len(items2) != 2 {
		t.Fatalf("page2: expected 2 items, got %d", len(items2))
	}

	for _, item := range items2 {
		id := item.(map[string]any)["_id"].(string)
		if firstPage[id] {
			t.Errorf("page2: item %s overlaps with page1", id)
		}
	}

	// Page 3: one remaining item
	cursor2, _ := body2["cursor"].(string)
	if cursor2 == "" {
		t.Fatal("page2: expected non-empty cursor")
	}

	rec3 := doRequest(t, http.MethodGet, fmt.Sprintf("/v1/circles/%s/feed?sort=latest&limit=2&cursor=%s", circleID, cursor2), nil)
	if rec3.Code != http.StatusOK {
		t.Fatalf("page3: expected 200, got %d: %s", rec3.Code, rec3.Body.String())
	}

	body3 := decodeBody(t, rec3)
	items3 := body3["items"].([]any)
	if len(items3) != 1 {
		t.Fatalf("page3: expected 1 item, got %d", len(items3))
	}

	cursor3, _ := body3["cursor"].(string)
	if cursor3 != "" {
		t.Errorf("page3: expected empty cursor for last page, got %q", cursor3)
	}
}

func TestGetCircleFeed_Featured(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "精选排序圈子")
	now := time.Now()

	insertPost(t, bson.M{
		"_id":       "feat_normal",
		"circleIds": []string{circleID},
		"title":     "普通帖子",
		"createdAt": now,
	})
	insertPost(t, bson.M{
		"_id":        "feat_pinned",
		"circleIds":  []string{circleID},
		"title":      "置顶帖子",
		"createdAt":  now.Add(-1 * time.Hour),
		"pinnedAt":   now,
	})
	insertPost(t, bson.M{
		"_id":        "feat_featured",
		"circleIds":  []string{circleID},
		"title":      "精选帖子",
		"createdAt":  now.Add(-2 * time.Hour),
		"featuredAt": now.Add(-30 * time.Minute),
	})

	rec := doRequest(t, http.MethodGet, fmt.Sprintf("/v1/circles/%s/feed?sort=featured&limit=10", circleID), nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := decodeBody(t, rec)
	items := body["items"].([]any)
	if len(items) != 3 {
		t.Fatalf("expected 3 items, got %d", len(items))
	}

	first := items[0].(map[string]any)
	if first["_id"] != "feat_pinned" {
		t.Errorf("expected pinned post first, got %v", first["_id"])
	}

	second := items[1].(map[string]any)
	if second["_id"] != "feat_featured" {
		t.Errorf("expected featured post second, got %v", second["_id"])
	}

	third := items[2].(map[string]any)
	if third["_id"] != "feat_normal" {
		t.Errorf("expected normal post third, got %v", third["_id"])
	}
}

// decodeItems is a helper to decode the items array from a JSON body.
func decodeItems(t *testing.T, body []byte) []map[string]any {
	t.Helper()
	var resp map[string]any
	if err := json.Unmarshal(body, &resp); err != nil {
		t.Fatalf("decode body: %v", err)
	}
	rawItems := resp["items"].([]any)
	items := make([]map[string]any, len(rawItems))
	for i, raw := range rawItems {
		items[i] = raw.(map[string]any)
	}
	return items
}

// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002.t1
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002.t2
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002.t6
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002.t7
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002.t8
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002.t9
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002.t11
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/spec.md#sit-002.t3
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/spec.md#sit-002.t6
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/spec.md#sit-002.t7
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/spec.md#sit-002.t8
// readiness_case: list-circle-discovery-feed-api
// readiness_case: get-circle-feed-api
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sort"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/cache"
)

func insertCircleFeedItem(t *testing.T, doc bson.M) {
	t.Helper()
	postDoc := bson.M{}
	for key, value := range doc {
		postDoc[key] = value
	}
	if _, ok := postDoc["status"]; !ok {
		postDoc["status"] = "published"
	}
	if _, ok := postDoc["contentType"]; !ok {
		postDoc["contentType"] = "image"
	}
	circleIDs := stringSlice(postDoc["circleIds"])
	delete(postDoc, "circleIds")
	delete(postDoc, "circleId")
	pinnedAt, _ := postDoc["pinnedAt"].(time.Time)
	featuredAt, _ := postDoc["featuredAt"].(time.Time)
	pinned, _ := postDoc["pinned"].(bool)
	featured, _ := postDoc["featured"].(bool)
	pinned = pinned || !pinnedAt.IsZero()
	featured = featured || !featuredAt.IsZero()
	delete(postDoc, "pinned")
	delete(postDoc, "featured")
	delete(postDoc, "pinnedAt")
	delete(postDoc, "featuredAt")

	_, err := mongoDB.Collection("circle_feed_items").InsertOne(context.Background(), postDoc)
	if err != nil {
		t.Fatalf("insertCircleFeedItem failed: %v", err)
	}
	postID := fmt.Sprint(postDoc["_id"])
	now, _ := postDoc["createdAt"].(time.Time)
	if now.IsZero() {
		now = time.Now().UTC()
	}
	for _, circleID := range circleIDs {
		placement := bson.M{
			"_id":          fmt.Sprintf("fixture-placement-%s-%s", circleID, postID),
			"version":      int64(1),
			"postId":       postID,
			"circleId":     circleID,
			"groupId":      "",
			"state":        "active",
			"pinned":       pinned,
			"featured":     featured,
			"lastActiveAt": now,
			"createdAt":    now,
			"updatedAt":    now,
		}
		if !pinnedAt.IsZero() {
			placement["pinnedAt"] = pinnedAt
		}
		if !featuredAt.IsZero() {
			placement["featuredAt"] = featuredAt
		}
		if _, err := mongoDB.Collection("circle_post_placements").InsertOne(
			context.Background(),
			placement,
		); err != nil {
			t.Fatalf("insert feed placement failed: %v", err)
		}
	}
}

func stringSlice(value any) []string {
	switch typed := value.(type) {
	case []string:
		return typed
	case bson.A:
		result := make([]string, 0, len(typed))
		for _, item := range typed {
			result = append(result, fmt.Sprint(item))
		}
		return result
	default:
		return nil
	}
}

func TestListCircleDiscoveryFeed(t *testing.T) {
	defer cleanCollections(t)

	mineCircleID := createTestCircleAs(t, "我的校园摄影圈", "persona-owner-mine")
	recommendedCircleID := createTestCircleAs(t, "推荐校园摄影圈", "persona-owner-recommended")
	otherCircleID := createTestCircleAs(t, "其他分类圈", "persona-owner-other")
	now := time.Now().UTC()
	for circleID, category := range map[string]string{
		mineCircleID: "campus", recommendedCircleID: "campus", otherCircleID: "travel",
	} {
		_, err := mongoDB.Collection("circles").UpdateOne(
			context.Background(),
			bson.M{"_id": circleID},
			bson.M{"$set": bson.M{
				"category": category, "subCategory": "photography",
				"visibility": "public", "status": "active",
			}},
		)
		if err != nil {
			t.Fatalf("update circle category: %v", err)
		}
	}
	if _, err := mongoDB.Collection("circle_memberships").InsertOne(context.Background(), bson.M{
		"_id": "membership-discovery-mine", "circleId": mineCircleID,
		"personaId": "persona-viewer", "state": "active", "role": "member",
	}); err != nil {
		t.Fatalf("insert discovery membership: %v", err)
	}
	insertCircleFeedItem(t, bson.M{
		"_id": "post-discovery-mine", "circleIds": []string{mineCircleID},
		"title": "我的圈帖子", "createdAt": now.Add(-time.Minute),
	})
	insertCircleFeedItem(t, bson.M{
		"_id": "post-discovery-recommended", "circleIds": []string{recommendedCircleID},
		"title": "推荐圈帖子", "createdAt": now,
	})
	insertCircleFeedItem(t, bson.M{
		"_id": "post-discovery-draft", "circleIds": []string{recommendedCircleID},
		"title": "不可见草稿", "status": "draft", "createdAt": now.Add(time.Minute),
	})
	insertCircleFeedItem(t, bson.M{
		"_id": "post-discovery-other", "circleIds": []string{otherCircleID},
		"title": "其他分类帖子", "createdAt": now,
	})

	recommended := doCircleDiscoveryRequest(
		t,
		"/circles/discovery-feed?category=campus&subCategory=photography&scope=recommended&sort=latest&limit=10",
		"persona-viewer",
	)
	if recommended.Code != http.StatusOK {
		t.Fatalf("recommended feed status=%d body=%s", recommended.Code, recommended.Body.String())
	}
	recommendedBody := decodeBody(t, recommended)
	assertDiscoveryIDs(
		t,
		recommendedBody,
		[]string{recommendedCircleID},
		[]string{"post-discovery-recommended"},
	)

	mine := doCircleDiscoveryRequest(
		t,
		"/circles/discovery-feed?category=campus&subCategory=photography&scope=mine&sort=latest&limit=10",
		"persona-viewer",
	)
	if mine.Code != http.StatusOK {
		t.Fatalf("mine feed status=%d body=%s", mine.Code, mine.Body.String())
	}
	mineBody := decodeBody(t, mine)
	assertDiscoveryIDs(
		t,
		mineBody,
		[]string{mineCircleID},
		[]string{"post-discovery-mine"},
	)
}

func TestListCircleDiscoveryFeed_IsReachableThroughGeneratedOperationGuard(t *testing.T) {
	defer cleanCollections(t)

	request := httptest.NewRequest(
		http.MethodGet,
		"/circles/discovery-feed?scope=recommended&sort=recommended&limit=20",
		nil,
	)
	recorder := httptest.NewRecorder()
	rtauth.RequireGeneratedOperationAuthorizationForRoute(
		operationsecurity.ForDomain("circle"),
		http.MethodGet,
		"/circles/discovery-feed",
	)(testHandler).ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"ready public discovery operation must pass generated guard, got %d: %s",
			recorder.Code,
			recorder.Body.String(),
		)
	}
}

func TestListCircleDiscoveryFeed_KeysetCursorAndCacheInvalidation(t *testing.T) {
	defer cleanCollections(t)

	now := time.Now().UTC().Truncate(time.Millisecond)
	circleIDs := []string{
		createTestCircleAs(t, "缓存排序圈甲", "persona-owner-alpha"),
		createTestCircleAs(t, "缓存排序圈乙", "persona-owner-beta"),
		createTestCircleAs(t, "缓存排序圈丙", "persona-owner-gamma"),
	}
	for _, circleID := range circleIDs {
		if _, err := mongoDB.Collection("circles").UpdateOne(
			context.Background(),
			bson.M{"_id": circleID},
			bson.M{"$set": bson.M{
				"category":          "campus",
				"subCategory":       "photography",
				"visibility":        "public",
				"status":            "active",
				"memberCount":       int64(42),
				"weeklyActiveCount": int64(7),
				"createdAt":         now,
			}},
		); err != nil {
			t.Fatalf("prepare ordered discovery circle %s: %v", circleID, err)
		}
	}

	path := "/circles/discovery-feed?category=campus&subCategory=photography&scope=recommended&sort=recommended&limit=1"
	first := doCircleDiscoveryRequest(t, path, "persona-viewer")
	if first.Code != http.StatusOK {
		t.Fatalf("first discovery page status=%d body=%s", first.Code, first.Body.String())
	}
	firstBody := decodeBody(t, first)
	firstCircles := firstBody["circles"].([]any)
	if len(firstCircles) != 1 {
		t.Fatalf("first page circle count=%d", len(firstCircles))
	}
	firstCircle := firstCircles[0].(map[string]any)
	firstID := fmt.Sprint(firstCircle["id"])
	cursor := fmt.Sprint(firstBody["cursor"])
	if cursor == "" {
		t.Fatal("first page must return a keyset cursor")
	}

	second := doCircleDiscoveryRequest(t, path+"&cursor="+cursor, "persona-viewer")
	if second.Code != http.StatusOK {
		t.Fatalf("second discovery page status=%d body=%s", second.Code, second.Body.String())
	}
	secondBody := decodeBody(t, second)
	secondCircles := secondBody["circles"].([]any)
	if len(secondCircles) != 1 {
		t.Fatalf("second page circle count=%d", len(secondCircles))
	}
	if got := fmt.Sprint(secondCircles[0].(map[string]any)["id"]); got == firstID {
		t.Fatalf("keyset pagination duplicated circle %s", firstID)
	}

	if _, err := mongoDB.Collection("circles").UpdateOne(
		context.Background(),
		bson.M{"_id": firstID},
		bson.M{"$set": bson.M{"name": "缓存失效后名称"}},
	); err != nil {
		t.Fatalf("mutate cached circle: %v", err)
	}
	cached := doCircleDiscoveryRequest(t, path, "persona-viewer")
	if cached.Code != http.StatusOK {
		t.Fatalf("cached discovery page status=%d body=%s", cached.Code, cached.Body.String())
	}
	cachedName := fmt.Sprint(
		decodeBody(t, cached)["circles"].([]any)[0].(map[string]any)["name"],
	)
	if cachedName != fmt.Sprint(firstCircle["name"]) {
		t.Fatalf("same cache key must return the cached slice before invalidation, got=%q", cachedName)
	}

	if err := cache.InvalidateCircleDiscoveryFeed(
		context.Background(),
		redisRouter.Scene("general"),
	); err != nil {
		t.Fatalf("invalidate discovery feed cache: %v", err)
	}
	invalidated := doCircleDiscoveryRequest(t, path, "persona-viewer")
	if invalidated.Code != http.StatusOK {
		t.Fatalf("invalidated discovery page status=%d body=%s", invalidated.Code, invalidated.Body.String())
	}
	invalidatedName := fmt.Sprint(
		decodeBody(t, invalidated)["circles"].([]any)[0].(map[string]any)["name"],
	)
	if invalidatedName != "缓存失效后名称" {
		t.Fatalf("cache invalidation did not reload source slice, got=%q", invalidatedName)
	}
}

func TestListCircleDiscoveryFeed_CommercialScaleUsesIndexAndMeetsP95(t *testing.T) {
	defer cleanCollections(t)

	for _, scale := range []int{10_000, 100_000} {
		t.Run(fmt.Sprintf("%d_circles", scale), func(t *testing.T) {
			category := fmt.Sprintf("perf-%d", scale)
			seedDiscoveryPerformanceCircles(t, category, scale)
			assertDiscoveryRecommendedExplainUsesIndex(t, category)

			durations := make([]time.Duration, 0, 20)
			path := fmt.Sprintf(
				"/circles/discovery-feed?category=%s&subCategory=scale&scope=recommended&sort=recommended&limit=20",
				category,
			)
			for run := 0; run < 20; run++ {
				if err := cache.InvalidateCircleDiscoveryFeed(
					context.Background(),
					redisRouter.Scene("general"),
				); err != nil {
					t.Fatalf("invalidate before source-read measurement: %v", err)
				}
				startedAt := time.Now()
				response := doCircleDiscoveryRequest(t, path, "persona-performance")
				durations = append(durations, time.Since(startedAt))
				if response.Code != http.StatusOK {
					t.Fatalf(
						"scale=%d run=%d status=%d body=%s",
						scale,
						run,
						response.Code,
						response.Body.String(),
					)
				}
			}
			sort.Slice(durations, func(left, right int) bool {
				return durations[left] < durations[right]
			})
			p95Index := (len(durations)*95 + 99) / 100
			p95 := durations[p95Index-1]
			if p95 > 800*time.Millisecond {
				t.Fatalf("scale=%d discovery feed p95=%s exceeds 800ms", scale, p95)
			}
			t.Logf("scale=%d discovery feed source-read p95=%s", scale, p95)
		})
	}
}

func seedDiscoveryPerformanceCircles(t *testing.T, category string, count int) {
	t.Helper()
	ctx := context.Background()
	now := time.Now().UTC()
	const batchSize = 1_000
	for start := 0; start < count; start += batchSize {
		end := start + batchSize
		if end > count {
			end = count
		}
		documents := make([]any, 0, end-start)
		for index := start; index < end; index++ {
			documents = append(documents, bson.M{
				"_id":               fmt.Sprintf("%s-%06d", category, index),
				"name":              fmt.Sprintf("商业规模圈子-%06d", index),
				"ownerId":           "persona-performance-owner",
				"category":          category,
				"subCategory":       "scale",
				"status":            "active",
				"visibility":        "public",
				"memberCount":       int64(index % 100),
				"weeklyActiveCount": int64(index % 50),
				"createdAt":         now.Add(-time.Duration(index) * time.Second),
				"updatedAt":         now,
			})
		}
		if _, err := mongoDB.Collection("circles").InsertMany(ctx, documents); err != nil {
			t.Fatalf(
				"seed discovery scale %s[%d:%d]: %v",
				category,
				start,
				end,
				err,
			)
		}
	}
}

func assertDiscoveryRecommendedExplainUsesIndex(t *testing.T, category string) {
	t.Helper()
	var explain bson.M
	err := mongoDB.RunCommand(
		context.Background(),
		bson.D{{Key: "explain", Value: bson.D{
			{Key: "find", Value: "circles"},
			{Key: "filter", Value: bson.M{
				"status":      "active",
				"visibility":  "public",
				"category":    category,
				"subCategory": "scale",
			}},
			{Key: "sort", Value: bson.D{
				{Key: "memberCount", Value: -1},
				{Key: "weeklyActiveCount", Value: -1},
				{Key: "_id", Value: -1},
			}},
		}}},
	).Decode(&explain)
	if err != nil {
		t.Fatalf("explain discovery query: %v", err)
	}
	serialized, err := json.Marshal(explain)
	if err != nil {
		t.Fatalf("marshal discovery explain: %v", err)
	}
	plan := string(serialized)
	if !contains(plan, `"stage":"IXSCAN"`) || contains(plan, `"stage":"COLLSCAN"`) {
		t.Fatalf("discovery query must use declared index, explain=%s", plan)
	}
}

func contains(value, fragment string) bool {
	for index := 0; index+len(fragment) <= len(value); index++ {
		if value[index:index+len(fragment)] == fragment {
			return true
		}
	}
	return false
}

func doCircleDiscoveryRequest(
	t *testing.T,
	path string,
	personaID string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(http.MethodGet, path, nil)
	request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
		OperationID: "circle.circle.ListCircleDiscoveryFeed",
		RequestID:   "request-circle-discovery", TraceID: "trace-circle-discovery",
		Actor: operation.ActorContext{
			AccountID: "account-" + personaID,
			PersonaID: personaID,
		},
	}))
	recorder := httptest.NewRecorder()
	testHandler.ServeHTTP(recorder, request)
	return recorder
}

func assertDiscoveryIDs(
	t *testing.T,
	body map[string]any,
	wantCircleIDs []string,
	wantPostIDs []string,
) {
	t.Helper()
	rawCircles, ok := body["circles"].([]any)
	if !ok {
		t.Fatalf("discovery circles missing: %#v", body)
	}
	gotCircleIDs := make([]string, 0, len(rawCircles))
	for _, raw := range rawCircles {
		gotCircleIDs = append(gotCircleIDs, raw.(map[string]any)["id"].(string))
	}
	if fmt.Sprint(gotCircleIDs) != fmt.Sprint(wantCircleIDs) {
		t.Fatalf("circle ids=%v want=%v", gotCircleIDs, wantCircleIDs)
	}
	rawItems, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("discovery items missing: %#v", body)
	}
	gotPostIDs := make([]string, 0, len(rawItems))
	for _, raw := range rawItems {
		item := raw.(map[string]any)
		gotPostIDs = append(gotPostIDs, item["postId"].(string))
		if item["circleId"] == "" {
			t.Fatalf("circleId missing from typed feed item: %#v", item)
		}
	}
	if fmt.Sprint(gotPostIDs) != fmt.Sprint(wantPostIDs) {
		t.Fatalf("post ids=%v want=%v", gotPostIDs, wantPostIDs)
	}
}

func TestGetCircleFeed_Empty(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "空feed圈子")

	rec := doRequest(t, http.MethodGet, fmt.Sprintf("/circles/%s/feed?limit=10", circleID), nil)
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

func TestGetCircleFeed_HidesInactiveAndNonPublicCircles(t *testing.T) {
	for _, tc := range []struct {
		name    string
		updates bson.M
	}{
		{
			name: "private",
			updates: bson.M{
				"visibility": "private",
			},
		},
		{
			name: "archived",
			updates: bson.M{
				"status": "archived",
			},
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			defer cleanCollections(t)
			circleID := createTestCircle(t, "不可公开读取的圈子")
			if _, err := mongoDB.Collection("circles").UpdateOne(
				context.Background(),
				bson.M{"_id": circleID},
				bson.M{"$set": tc.updates},
			); err != nil {
				t.Fatalf("set non-public circle state: %v", err)
			}

			rec := doRequest(
				t,
				http.MethodGet,
				fmt.Sprintf("/circles/%s/feed?limit=10", circleID),
				nil,
			)
			if rec.Code != http.StatusNotFound {
				t.Fatalf(
					"public feed must not disclose %s circle, got %d: %s",
					tc.name,
					rec.Code,
					rec.Body.String(),
				)
			}
		})
	}
}

func TestGetCircleFeed_Latest(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "最新排序圈子")
	now := time.Now()

	insertCircleFeedItem(t, bson.M{
		"_id":       "post_old",
		"circleIds": []string{circleID},
		"title":     "旧帖子",
		"createdAt": now.Add(-2 * time.Hour),
	})
	insertCircleFeedItem(t, bson.M{
		"_id":       "post_mid",
		"circleIds": []string{circleID},
		"title":     "中间帖子",
		"createdAt": now.Add(-1 * time.Hour),
	})
	insertCircleFeedItem(t, bson.M{
		"_id":       "post_new",
		"circleIds": []string{circleID},
		"title":     "新帖子",
		"createdAt": now,
	})

	rec := doRequest(t, http.MethodGet, fmt.Sprintf("/circles/%s/feed?sort=latest&limit=10", circleID), nil)
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
	if first["postId"] != "post_new" {
		t.Errorf("expected first item post_new, got %v", first["postId"])
	}
	if second["postId"] != "post_mid" {
		t.Errorf("expected second item post_mid, got %v", second["postId"])
	}
	if third["postId"] != "post_old" {
		t.Errorf("expected third item post_old, got %v", third["postId"])
	}
}

func TestGetCircleFeed_Pagination(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "分页圈子")
	now := time.Now()

	for i := 0; i < 5; i++ {
		insertCircleFeedItem(t, bson.M{
			"_id":       fmt.Sprintf("page_post_%d", i),
			"circleIds": []string{circleID},
			"title":     fmt.Sprintf("帖子%d", i),
			"createdAt": now.Add(time.Duration(i) * time.Minute),
		})
	}

	// Page 1: limit=2, sorted latest (newest first → 4,3)
	rec := doRequest(t, http.MethodGet, fmt.Sprintf("/circles/%s/feed?sort=latest&limit=2", circleID), nil)
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
		id := item.(map[string]any)["postId"].(string)
		firstPage[id] = true
	}

	// Page 2: use cursor
	rec2 := doRequest(t, http.MethodGet, fmt.Sprintf("/circles/%s/feed?sort=latest&limit=2&cursor=%s", circleID, cursor), nil)
	if rec2.Code != http.StatusOK {
		t.Fatalf("page2: expected 200, got %d: %s", rec2.Code, rec2.Body.String())
	}

	body2 := decodeBody(t, rec2)
	items2 := body2["items"].([]any)
	if len(items2) != 2 {
		t.Fatalf("page2: expected 2 items, got %d", len(items2))
	}

	for _, item := range items2 {
		id := item.(map[string]any)["postId"].(string)
		if firstPage[id] {
			t.Errorf("page2: item %s overlaps with page1", id)
		}
	}

	// Page 3: one remaining item
	cursor2, _ := body2["cursor"].(string)
	if cursor2 == "" {
		t.Fatal("page2: expected non-empty cursor")
	}

	rec3 := doRequest(t, http.MethodGet, fmt.Sprintf("/circles/%s/feed?sort=latest&limit=2&cursor=%s", circleID, cursor2), nil)
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

	insertCircleFeedItem(t, bson.M{
		"_id":       "feat_normal",
		"circleIds": []string{circleID},
		"title":     "普通帖子",
		"createdAt": now,
	})
	insertCircleFeedItem(t, bson.M{
		"_id":       "feat_pinned",
		"circleIds": []string{circleID},
		"title":     "置顶帖子",
		"createdAt": now.Add(-1 * time.Hour),
		"pinnedAt":  now,
	})
	insertCircleFeedItem(t, bson.M{
		"_id":        "feat_featured",
		"circleIds":  []string{circleID},
		"title":      "精选帖子",
		"createdAt":  now.Add(-2 * time.Hour),
		"featuredAt": now.Add(-30 * time.Minute),
	})

	rec := doRequest(t, http.MethodGet, fmt.Sprintf("/circles/%s/feed?sort=featured&limit=10", circleID), nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}

	body := decodeBody(t, rec)
	items := body["items"].([]any)
	if len(items) != 3 {
		t.Fatalf("expected 3 items, got %d", len(items))
	}

	first := items[0].(map[string]any)
	if first["postId"] != "feat_pinned" {
		t.Errorf("expected pinned post first, got %v", first["postId"])
	}

	second := items[1].(map[string]any)
	if second["postId"] != "feat_featured" {
		t.Errorf("expected featured post second, got %v", second["postId"])
	}

	third := items[2].(map[string]any)
	if third["postId"] != "feat_normal" {
		t.Errorf("expected normal post third, got %v", third["postId"])
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

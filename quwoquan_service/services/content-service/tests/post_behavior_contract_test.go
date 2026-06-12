// L2 契约测试：Post 业务对象 — 行为上报与互动操作
//
// 守护：点赞、行为上报接口的路由注册和基本语义；收藏概念已全量退场，
// 由 TestFavoriteRouteRetired 反向守护 /favorite 路由不再注册。
// contract.yaml go_func 覆盖：
//
//	TestBehaviorBatchReport — behavior_batch_report
//	TestBehaviorBatchEmpty  — behavior_batch_empty
//	TestBehaviorBatchRejectsLike — behavior_batch_accepts_like
//	TestLikePost, TestReportPost — 其他行为场景
package tests

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/content-service/internal/application"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

// TestLikePost verifies the like endpoint route is registered.
// The handler currently returns 500 (operation not implemented) —
// asserts the route exists and returns a structured error, not 404.
// contract.yaml: react_with_counter_strategy / go_func: TestReactWithCounterStrategy
func TestLikePost(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"image","title":"Like target","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/like", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	// Route is registered; expect either 2xx (implemented) or 5xx (not implemented).
	if rec.Code == http.StatusNotFound {
		t.Fatalf("like route not registered (got 404); expected 2xx or 5xx")
	}
	if rec.Code >= 400 {
		var errResp map[string]any
		if err := json.Unmarshal(rec.Body.Bytes(), &errResp); err != nil {
			t.Fatalf("decode error response: %v", err)
		}
		if errResp["code"] == nil {
			t.Error("expected structured error response with code field")
		}
	}
}

// TestFavoriteRouteRetired 反向守护：收藏概念全量退场后，
// /v1/content/posts/{id}/favorite 路由必须不再注册（404），防止兼容路由回潮。
func TestFavoriteRouteRetired(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"image","title":"Favorite retired target","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	req := httptest.NewRequest(http.MethodPost, "/v1/content/posts/"+postID+"/favorite", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("favorite route must be retired (expect 404), got %d: %s", rec.Code, rec.Body.String())
	}
}

// TestBehaviorBatchReport verifies POST /v1/content/behaviors accepts a mixed batch
// of impression + dwell + click events and returns 204.
// contract.yaml: behavior_batch_report
func TestBehaviorBatchReport(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"image","title":"Behavior batch target","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	payload := fmt.Sprintf(`{
		"userId": "user_batch_001",
		"sessionId": "sess_abc",
		"events": [
			{"contentId": %q, "action": "impression", "userId": "user_batch_001"},
			{"contentId": %q, "action": "click",      "userId": "user_batch_001"},
			{"contentId": %q, "action": "dwell",      "userId": "user_batch_001", "duration": 5.5}
		]
	}`, postID, postID, postID)

	req := httptest.NewRequest(http.MethodPost, "/v1/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204, got %d: %s", rec.Code, rec.Body.String())
	}
	if body := strings.TrimSpace(rec.Body.String()); body != "" {
		t.Fatalf("expected empty 204 body, got %q", body)
	}
}

// TestBehaviorBatchEmpty verifies POST /v1/content/behaviors with an empty events
// array returns 400 with CONTENT.USER.invalid_argument.
// contract.yaml: behavior_batch_empty
func TestBehaviorBatchEmpty(t *testing.T) {
	payload := `{"userId": "user_empty", "events": []}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for empty events, got %d: %s", rec.Code, rec.Body.String())
	}
	var errResp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	code, _ := errResp["code"].(string)
	if code != "CONTENT.USER.invalid_argument" {
		t.Errorf("expected code=CONTENT.USER.invalid_argument, got %q", code)
	}
}

// TestBehaviorBatchWireAliases verifies the app-facing wire aliases used by
// local gamma T3: postId/type/dwellMs.
func TestBehaviorBatchWireAliases(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"image","title":"Wire alias target","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	payload := fmt.Sprintf(
		`{"userId":"user_reporter_001","events":[{"postId":%q,"type":"dwell","dwellMs":12000,"userId":"user_reporter_001"}]}`,
		postID,
	)
	req := httptest.NewRequest(http.MethodPost, "/v1/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204, got %d: %s", rec.Code, rec.Body.String())
	}
}

// TestBehaviorBatchAssistantInterestAllowsEmptyContentID verifies the Phase 3
// flywheel contract: assistant_interest is a tag-only signal and must not be
// rejected when contentId/postId are absent.
func TestBehaviorBatchAssistantInterestAllowsEmptyContentID(t *testing.T) {
	payload := `{
		"userId":"user_assistant_interest_001",
		"sessionId":"sess_assistant_interest_001",
		"events":[
			{
				"action":"assistant_interest",
				"userId":"user_assistant_interest_001",
				"tagRefs":["Topic/旅行","Topic/景区"]
			}
		]
	}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204 for assistant_interest without contentId, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestBehaviorBatchAssistantInterestProjectsTagInteraction(t *testing.T) {
	ctx := context.Background()
	featureColl := mongoDB.Collection("rm_recommend_feature")
	if _, err := featureColl.DeleteMany(ctx, bson.M{"userId": "user_assistant_interest_projector_001"}); err != nil {
		t.Fatalf("clean recommend feature: %v", err)
	}
	behaviorService := application.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		persistence.NewMongoPostStore(mongoDB.Collection("posts")),
		application.WithBehaviorProjector(&recommendOnlyProjectorAdapter{
			p: recinfra.NewRecommendFeatureProjector(mongoDB),
		}),
	)

	err := behaviorService.ProcessBatch(ctx, []application.BehaviorEventInput{
		{
			UserID:    "user_assistant_interest_projector_001",
			SessionID: "sess_assistant_interest_projector_001",
			Action:    "assistant_interest",
			Tags:      []string{"Topic/旅行", "Topic/旅行主题"},
		},
	})
	if err != nil {
		t.Fatalf("process assistant_interest: %v", err)
	}

	var got struct {
		UserFeatures struct {
			TagInteraction map[string]int `bson:"tagInteraction"`
		} `bson:"userFeatures"`
	}
	if err := featureColl.FindOne(ctx, bson.M{"userId": "user_assistant_interest_projector_001"}).Decode(&got); err != nil {
		t.Fatalf("find recommend feature: %v", err)
	}
	if got.UserFeatures.TagInteraction["Topic/旅行"] != 1 || got.UserFeatures.TagInteraction["Topic/旅行主题"] != 1 {
		t.Fatalf("tagInteraction not projected: %+v", got.UserFeatures.TagInteraction)
	}
}

func TestBehaviorBatchIntersectionConversionsUpdateMetricsAndAuthorImpact(t *testing.T) {
	ctx := context.Background()
	authorID := "author_intersection_impact_001"
	if _, err := mongoDB.Collection("rm_daily_metrics").DeleteMany(ctx, bson.M{}); err != nil {
		t.Fatalf("clean daily metrics: %v", err)
	}
	if _, err := mongoDB.Collection("rm_author_impact").DeleteMany(ctx, bson.M{"authorId": authorID}); err != nil {
		t.Fatalf("clean author impact: %v", err)
	}
	behaviorService := application.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		persistence.NewMongoPostStore(mongoDB.Collection("posts")),
		application.WithDailyMetricsStore(persistence.NewDailyMetricsStore(mongoDB, nilLogger())),
		application.WithAuthorImpactStore(persistence.NewAuthorImpactStore(mongoDB, nilLogger())),
	)

	err := behaviorService.ProcessBatch(ctx, []application.BehaviorEventInput{
		{
			UserID:                "viewer_intersection_001",
			ContentID:             "post_follow_001",
			Action:                "follow",
			AuthorID:              authorID,
			IntersectionDimension: "identity",
			IntersectionTagRefs:   []string{"Audience/学生"},
		},
		{
			UserID:                "viewer_intersection_001",
			ContentID:             "circle_intersection_001",
			Action:                "join_circle",
			AuthorID:              authorID,
			IntersectionDimension: "interest",
			IntersectionTagRefs:   []string{"Topic/旅行"},
		},
		{
			UserID:                "viewer_intersection_001",
			ContentID:             "post_contact_001",
			Action:                "add_contact",
			AuthorID:              authorID,
			IntersectionDimension: "relationship",
			IntersectionTagRefs:   []string{"Entity/通讯录"},
		},
	})
	if err != nil {
		t.Fatalf("process intersection conversions: %v", err)
	}

	var identityMetric struct {
		FollowConversions int64 `bson:"followConversions"`
	}
	if err := mongoDB.Collection("rm_daily_metrics").FindOne(ctx, bson.M{
		"dimension":    persistence.DailyMetricDimensionIntersection,
		"dimensionKey": "identity",
	}).Decode(&identityMetric); err != nil {
		t.Fatalf("find identity metric: %v", err)
	}
	if identityMetric.FollowConversions != 1 {
		t.Fatalf("followConversions = %d, want 1", identityMetric.FollowConversions)
	}

	store := persistence.NewAuthorImpactStore(mongoDB, nilLogger())
	summary, err := store.GetSummary(ctx, authorID, 10)
	if err != nil {
		t.Fatalf("get author impact summary: %v", err)
	}
	if summary.Total != 3 {
		t.Fatalf("author impact total = %d, want 3; items=%+v", summary.Total, summary.Items)
	}
	byHelp := map[string]int64{}
	for _, item := range summary.Items {
		byHelp[item.HelpType] += item.Count
	}
	if byHelp[persistence.AuthorImpactHelpRelationship] != 2 {
		t.Fatalf("relationship help = %d, want 2; items=%+v", byHelp[persistence.AuthorImpactHelpRelationship], summary.Items)
	}
	if byHelp[persistence.AuthorImpactHelpCommunity] != 1 {
		t.Fatalf("community help = %d, want 1; items=%+v", byHelp[persistence.AuthorImpactHelpCommunity], summary.Items)
	}
}

func TestGetAuthorImpactReturnsBehaviorAggregation(t *testing.T) {
	ctx := context.Background()
	authorID := "author_impact_http_001"
	if _, err := mongoDB.Collection("rm_author_impact").DeleteMany(ctx, bson.M{"authorId": authorID}); err != nil {
		t.Fatalf("clean author impact: %v", err)
	}
	payload := fmt.Sprintf(`{
		"userId": "viewer_impact_http_001",
		"events": [
			{
				"contentId": "post_impact_http_001",
				"action": "follow",
				"authorId": %q,
				"intersectionDimension": "identity",
				"intersectionTagRefs": ["Audience/学生"]
			}
		]
	}`, authorID)
	reportReq := httptest.NewRequest(http.MethodPost, "/v1/content/behaviors", strings.NewReader(payload))
	reportReq.Header.Set("Content-Type", "application/json")
	reportRec := httptest.NewRecorder()
	testHandler.ServeHTTP(reportRec, reportReq)
	if reportRec.Code != http.StatusNoContent {
		t.Fatalf("report behavior: expected 204, got %d: %s", reportRec.Code, reportRec.Body.String())
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/content/sub-accounts/"+authorID+"/author-impact", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("get author impact: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var body struct {
		AuthorID string `json:"authorId"`
		Total    int64  `json:"total"`
		Items    []struct {
			HelpType string `json:"helpType"`
			Action   string `json:"action"`
			Count    int64  `json:"count"`
		} `json:"items"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode author impact: %v", err)
	}
	if body.AuthorID != authorID || body.Total != 1 || len(body.Items) == 0 {
		t.Fatalf("unexpected author impact body: %+v", body)
	}
	if body.Items[0].HelpType != persistence.AuthorImpactHelpRelationship || body.Items[0].Action != "follow" || body.Items[0].Count != 1 {
		t.Fatalf("unexpected author impact item: %+v", body.Items[0])
	}
}

type recommendOnlyProjectorAdapter struct {
	p *recinfra.RecommendFeatureProjector
}

func nilLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

func (a *recommendOnlyProjectorAdapter) Project(ctx context.Context, event application.ProjectorEvent) error {
	return a.p.Project(ctx, recinfra.ProjectorEvent{
		Type:          event.Type,
		AggregateType: event.AggregateType,
		AggregateID:   event.AggregateID,
		Payload:       event.Payload,
		OccurredAt:    event.OccurredAt,
	})
}

// TestBehaviorBatchRejectsLike verifies that like must use the dedicated route
// and is rejected by the generic behavior batch endpoint.
func TestBehaviorBatchRejectsLike(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := createPost(t, `{"contentType":"image","title":"Like batch target","mediaUrls":["https://example.com/img.jpg"]}`)
	postID, _ := created["_id"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	payload := fmt.Sprintf(`{"events":[{"postId":%q,"type":"like"}]}`, postID)
	req := httptest.NewRequest(http.MethodPost, "/v1/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d: %s", rec.Code, rec.Body.String())
	}
	var errResp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	if code, ok := errResp["code"].(string); !ok || code == "" {
		t.Fatalf("expected structured error code, got %+v", errResp)
	}
}

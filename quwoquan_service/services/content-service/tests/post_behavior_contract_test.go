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
	"quwoquan_service/services/content-service/internal/application/authorimpact"
	behaviorapp "quwoquan_service/services/content-service/internal/application/behavior"
	"quwoquan_service/services/content-service/internal/application/ports"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtimpact "quwoquan_service/runtime/impact"
	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
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

func TestGetMyFootprintContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	const userID = "footprint_user_001"
	created := createPost(t, `{"contentType":"image","title":"Footprint target","mediaUrls":["https://example.com/img.jpg"]}`)
	postID := asTestString(created["_id"])
	if postID == "" {
		postID = asTestString(created["id"])
	}
	if postID == "" {
		t.Fatalf("missing post id: %+v", created)
	}

	payload := fmt.Sprintf(`{
		"userId": %q,
		"events": [
			{"clientEventId": "evt-footprint-001", "contentId": %q, "contentType": "image", "action": "click", "userId": %q}
		]
	}`, userID, postID, userID)
	reportReq := httptest.NewRequest(http.MethodPost, "/v1/content/behaviors", strings.NewReader(payload))
	reportReq.Header.Set("Content-Type", "application/json")
	reportRec := httptest.NewRecorder()
	testHandler.ServeHTTP(reportRec, reportReq)
	if reportRec.Code != http.StatusNoContent {
		t.Fatalf("report behavior: expected 204, got %d: %s", reportRec.Code, reportRec.Body.String())
	}

	footprintReq := httptest.NewRequest(http.MethodGet, "/v1/content/footprint?type=viewed&limit=10", nil)
	footprintReq.Header.Set("X-Client-User-Id", userID)
	footprintRec := httptest.NewRecorder()
	testHandler.ServeHTTP(footprintRec, footprintReq)
	if footprintRec.Code != http.StatusOK {
		t.Fatalf("get footprint: expected 200, got %d: %s", footprintRec.Code, footprintRec.Body.String())
	}
	var resp map[string]any
	if err := json.Unmarshal(footprintRec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode footprint response: %v", err)
	}
	items, _ := resp["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("expected one footprint item, got %d: %#v", len(items), resp)
	}
	item, _ := items[0].(map[string]any)
	if item["postId"] != postID || item["action"] != "click" {
		t.Fatalf("unexpected footprint item: %#v", item)
	}
	if _, ok := item["post"].(map[string]any); !ok {
		t.Fatalf("footprint item must hydrate post projection: %#v", item)
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

// TestBehaviorEventInputDecodesAttributionFields 冻结推荐归因 wire 契约：
// channelId/rankingVersion/reasonVersion/recallPath/contentVertical/supplySource/
// feedRequestId/referralSource/position/state 与交集分桶字段必须从批量 JSON
// 正确解析进 BehaviorEventInput（端云 DTO↔struct↔YAML common_fields 对齐，R08）。
func TestBehaviorEventInputDecodesAttributionFields(t *testing.T) {
	raw := `{"contentId":"post_attr_1","action":"impression","state":"impressed",` +
		`"feedRequestId":"frq_01H","referralSource":"organic_feed","position":7,` +
		`"channelId":"following","rankingVersion":"rank-v3","reasonVersion":"reason-v2",` +
		`"recallPath":"collab_i2i","contentVertical":"travel_photography","supplySource":"data_engineering",` +
		`"intersectionSourceRef":"shared_city","intersectionClass":"fact","intersectionEvidenceId":"ev_attr_1",` +
		`"commentLength":42}`
	var in behaviorapp.BehaviorEventInput
	if err := json.Unmarshal([]byte(raw), &in); err != nil {
		t.Fatalf("decode behavior event input: %v", err)
	}
	if in.State != "impressed" {
		t.Errorf("state: want impressed, got %q", in.State)
	}
	if in.FeedRequestID != "frq_01H" {
		t.Errorf("feedRequestId: want frq_01H, got %q", in.FeedRequestID)
	}
	if in.ReferralSource != "organic_feed" {
		t.Errorf("referralSource: want organic_feed, got %q", in.ReferralSource)
	}
	if in.Position != 7 {
		t.Errorf("position: want 7, got %d", in.Position)
	}
	if in.ChannelID != "following" {
		t.Errorf("channelId: want following, got %q", in.ChannelID)
	}
	if in.RankingVersion != "rank-v3" {
		t.Errorf("rankingVersion: want rank-v3, got %q", in.RankingVersion)
	}
	if in.ReasonVersion != "reason-v2" {
		t.Errorf("reasonVersion: want reason-v2, got %q", in.ReasonVersion)
	}
	if in.RecallPath != "collab_i2i" {
		t.Errorf("recallPath: want collab_i2i, got %q", in.RecallPath)
	}
	if in.ContentVertical != "travel_photography" {
		t.Errorf("contentVertical: want travel_photography, got %q", in.ContentVertical)
	}
	if in.SupplySource != "data_engineering" {
		t.Errorf("supplySource: want data_engineering, got %q", in.SupplySource)
	}
	if in.IntersectionSourceRef != "shared_city" {
		t.Errorf("intersectionSourceRef: want shared_city, got %q", in.IntersectionSourceRef)
	}
	if in.IntersectionClass != "fact" {
		t.Errorf("intersectionClass: want fact, got %q", in.IntersectionClass)
	}
	if in.IntersectionEvidenceID != "ev_attr_1" {
		t.Errorf("intersectionEvidenceId: want ev_attr_1, got %q", in.IntersectionEvidenceID)
	}
	if in.CommentLength != 42 {
		t.Errorf("commentLength: want 42, got %d", in.CommentLength)
	}
}

func TestBehaviorBatchDeduplicatesClientEventID(t *testing.T) {
	ctx := context.Background()
	behaviorService := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		persistence.NewMongoPostStore(mongoDB.Collection("posts")),
	)

	err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
		{
			ClientEventID: "evt-dedup-001",
			UserID:        "user_dedup_001",
			SessionID:     "sess_dedup_001",
			ContentID:     "post_dedup_001",
			Action:        "impression",
			State:         "impressed",
		},
		{
			ClientEventID: "evt-dedup-001",
			UserID:        "user_dedup_001",
			SessionID:     "sess_dedup_001",
			ContentID:     "post_dedup_001",
			Action:        "impression",
			State:         "impressed",
		},
	})
	if err != nil {
		t.Fatalf("process duplicate clientEventId: %v", err)
	}

	filtered, err := rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))).FilterCandidates(
		ctx,
		"user_dedup_001",
		[]rtrec.ContentCandidate{{ContentID: "post_dedup_001"}, {ContentID: "post_fresh_001"}},
		time.Now(),
	)
	if err != nil {
		t.Fatalf("filter candidates: %v", err)
	}
	if len(filtered) != 1 || filtered[0].ContentID != "post_fresh_001" {
		t.Fatalf("impressed event should filter only deduped content once, got %+v", filtered)
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

func TestBehaviorBatchWishlistProjectsEntityWishlistEvent(t *testing.T) {
	ctx := context.Background()
	coll := mongoDB.Collection("entity_wishlist_events")
	if _, err := coll.DeleteMany(ctx, bson.M{"userId": "user_wishlist_http_001"}); err != nil {
		t.Fatalf("clean wishlist events: %v", err)
	}
	payload := `{
		"userId":"user_wishlist_http_001",
		"sessionId":"sess_wishlist_http_001",
		"events":[
			{
				"clientEventId":"evt_wishlist_http_001",
				"action":"wishlist_add",
				"objectId":"homepage_west_lake",
				"objectKind":"homepage",
				"displayName":"西湖日落机位",
				"sourceSurface":"object_homepage",
				"referralSource":"entity_page",
				"feedRequestId":"frq_wishlist_http_001"
			}
		]
	}`
	req := httptest.NewRequest(http.MethodPost, "/v1/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("expected 204 for wishlist_add, got %d: %s", rec.Code, rec.Body.String())
	}

	var got struct {
		UserID         string `bson:"userId"`
		EntityID       string `bson:"entityId"`
		ObjectType     string `bson:"objectType"`
		DisplayName    string `bson:"displayName"`
		Status         string `bson:"status"`
		SourceSurface  string `bson:"sourceSurface"`
		ReferralSource string `bson:"referralSource"`
		FeedRequestID  string `bson:"feedRequestId"`
	}
	if err := coll.FindOne(ctx, bson.M{"userId": "user_wishlist_http_001", "entityId": "homepage_west_lake"}).Decode(&got); err != nil {
		t.Fatalf("find projected wishlist event: %v", err)
	}
	if got.Status != "active" || got.ObjectType != "homepage" || got.DisplayName != "西湖日落机位" {
		t.Fatalf("unexpected wishlist projection: %+v", got)
	}
	if got.SourceSurface != "object_homepage" || got.ReferralSource != "entity_page" || got.FeedRequestID != "frq_wishlist_http_001" {
		t.Fatalf("unexpected wishlist attribution: %+v", got)
	}
}

func TestBehaviorBatchAssistantInterestProjectsTagInteraction(t *testing.T) {
	ctx := context.Background()
	featureColl := mongoDB.Collection("rm_recommend_feature")
	if _, err := featureColl.DeleteMany(ctx, bson.M{"userId": "user_assistant_interest_projector_001"}); err != nil {
		t.Fatalf("clean recommend feature: %v", err)
	}
	behaviorService := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		persistence.NewMongoPostStore(mongoDB.Collection("posts")),
		behaviorapp.WithBehaviorProjector(&recommendOnlyProjectorAdapter{
			p: recinfra.NewRecommendFeatureProjector(mongoDB),
		}),
	)

	err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
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

// TestBehaviorBatchSevenStateImpressionExcludesVisibleCountsClick 验证阶段五七态漏斗在
// 特征投影中的语义：弱可见 visible 不计入 typeImpressions（served/impressed 双轨的 impressed 侧），
// 仅真实曝光 impressed 计入；click 计入 typeEngagements（CTR 分子）。同时携带 channelId/rankingVersion
// 归因字段，验证其可随批次贯穿。
func TestBehaviorBatchSevenStateImpressionExcludesVisibleCountsClick(t *testing.T) {
	ctx := context.Background()
	userID := "user_seven_state_001"
	featureColl := mongoDB.Collection("rm_recommend_feature")
	if _, err := featureColl.DeleteMany(ctx, bson.M{"userId": userID}); err != nil {
		t.Fatalf("clean recommend feature: %v", err)
	}
	behaviorService := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		persistence.NewMongoPostStore(mongoDB.Collection("posts")),
		behaviorapp.WithBehaviorProjector(&recommendOnlyProjectorAdapter{
			p: recinfra.NewRecommendFeatureProjector(mongoDB),
		}),
	)

	err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
		{UserID: userID, ContentID: "post_ss_visible", Action: "impression", State: "visible", ContentType: "image", ChannelID: "following", RankingVersion: "rank-v3", FeedRequestID: "frq_ss"},
		{UserID: userID, ContentID: "post_ss_impressed", Action: "impression", State: "impressed", ContentType: "image", ChannelID: "following", RankingVersion: "rank-v3", FeedRequestID: "frq_ss"},
		{UserID: userID, ContentID: "post_ss_click", Action: "click", State: "click", ContentType: "image", ChannelID: "following", RankingVersion: "rank-v3", FeedRequestID: "frq_ss"},
	})
	if err != nil {
		t.Fatalf("process seven-state batch: %v", err)
	}

	var got struct {
		UserFeatures struct {
			TypeImpressions map[string]int `bson:"typeImpressions"`
			TypeEngagements map[string]int `bson:"typeEngagements"`
		} `bson:"userFeatures"`
	}
	if err := featureColl.FindOne(ctx, bson.M{"userId": userID}).Decode(&got); err != nil {
		t.Fatalf("find recommend feature: %v", err)
	}
	if got.UserFeatures.TypeImpressions["image"] != 1 {
		t.Fatalf("typeImpressions[image] want 1 (impressed only, exclude weak visible), got %d", got.UserFeatures.TypeImpressions["image"])
	}
	if got.UserFeatures.TypeEngagements["image"] < 1 {
		t.Fatalf("typeEngagements[image] want >=1 (click counted as CTR numerator), got %d", got.UserFeatures.TypeEngagements["image"])
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
	behaviorService := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		persistence.NewMongoPostStore(mongoDB.Collection("posts")),
		behaviorapp.WithDailyMetricsStore(persistence.NewDailyMetricsStore(mongoDB, nilLogger())),
		behaviorapp.WithAuthorImpactStore(persistence.NewAuthorImpactStore(mongoDB, nilLogger())),
	)

	err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
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
	if byHelp[rtimpact.HelpRelationship] != 2 {
		t.Fatalf("relationship help = %d, want 2; items=%+v", byHelp[rtimpact.HelpRelationship], summary.Items)
	}
	if byHelp[rtimpact.HelpCommunity] != 1 {
		t.Fatalf("community help = %d, want 1; items=%+v", byHelp[rtimpact.HelpCommunity], summary.Items)
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
	if body.Items[0].HelpType != rtimpact.HelpRelationship || body.Items[0].Action != "follow" || body.Items[0].Count != 1 {
		t.Fatalf("unexpected author impact item: %+v", body.Items[0])
	}
}

// TestAuthorImpactTravelCountTargetFromBehaviorAggregation 端到端验证 WS3 旅行影响力真算：
// 真实行为聚合（viewer 在旅行 tag 内容上的 decision 行为）→ rm_author_impact 聚合 → 云侧
// DecorateAuthorImpact 按 tagRef 派生下钻目标对象 route/photo_spot（§22.5），被计数对象 person。
func TestAuthorImpactTravelCountTargetFromBehaviorAggregation(t *testing.T) {
	ctx := context.Background()
	authorID := "author_travel_impact_realcompute_001"
	if _, err := mongoDB.Collection("rm_author_impact").DeleteMany(ctx, bson.M{"authorId": authorID}); err != nil {
		t.Fatalf("clean author impact: %v", err)
	}
	behaviorService := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		persistence.NewMongoPostStore(mongoDB.Collection("posts")),
		behaviorapp.WithAuthorImpactStore(persistence.NewAuthorImpactStore(mongoDB, nilLogger())),
	)

	// viewer 在作者旅行攻略上的真实 decision 行为（entity_page_view → decision），
	// 携带旅行 tagRef；两条同 route tag 聚合为 count=2。
	if err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
		{
			UserID:                "viewer_travel_impact_001",
			ContentID:             "post_travel_route_001",
			Action:                "entity_page_view",
			AuthorID:              authorID,
			IntersectionDimension: "location",
			IntersectionTagRefs:   []string{"tag/travel/route"},
		},
		{
			UserID:                "viewer_travel_impact_002",
			ContentID:             "post_travel_route_001",
			Action:                "entity_page_view",
			AuthorID:              authorID,
			IntersectionDimension: "location",
			IntersectionTagRefs:   []string{"tag/travel/route"},
		},
		{
			UserID:                "viewer_travel_impact_003",
			ContentID:             "post_travel_spot_001",
			Action:                "entity_page_view",
			AuthorID:              authorID,
			IntersectionDimension: "location",
			IntersectionTagRefs:   []string{"tag/travel/photo_spot"},
		},
	}); err != nil {
		t.Fatalf("process travel behaviors: %v", err)
	}

	store := persistence.NewAuthorImpactStore(mongoDB, nilLogger())
	summary, err := store.GetSummary(ctx, authorID, 10)
	if err != nil {
		t.Fatalf("get author impact summary: %v", err)
	}
	// 云侧装饰（与 handler 同路径）后派生旅行下钻目标。
	decorated := authorimpact.DecorateAuthorImpact(summary, false)

	byTag := map[string]persistence.AuthorImpactItem{}
	for _, item := range decorated.Items {
		byTag[item.TagRef] = item
	}
	route, ok := byTag["tag/travel/route"]
	if !ok {
		t.Fatalf("missing route impact; items=%+v", decorated.Items)
	}
	if route.Count != 2 {
		t.Fatalf("route impact count = %d, want 2 (aggregated)", route.Count)
	}
	if route.CountTarget == nil || route.CountTarget.ObjectKind != "route" || route.CountTarget.RouteID != "homepageDetail" {
		t.Fatalf("route impact countTarget = %+v, want objectKind=route routeId=homepageDetail", route.CountTarget)
	}
	if route.CountObjectKind != "person" {
		t.Fatalf("route impact countObjectKind = %q, want person", route.CountObjectKind)
	}
	spot, ok := byTag["tag/travel/photo_spot"]
	if !ok {
		t.Fatalf("missing photo_spot impact; items=%+v", decorated.Items)
	}
	if spot.CountTarget == nil || spot.CountTarget.ObjectKind != "photo_spot" {
		t.Fatalf("spot impact countTarget = %+v, want objectKind=photo_spot", spot.CountTarget)
	}
}

type recommendOnlyProjectorAdapter struct {
	p *recinfra.RecommendFeatureProjector
}

func nilLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

func (a *recommendOnlyProjectorAdapter) Project(ctx context.Context, event ports.ProjectorEvent) error {
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

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
package api_integration

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
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	rtimpact "quwoquan_service/runtime/impact"
	rtoperation "quwoquan_service/runtime/operation"
	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	behaviorpersistence "quwoquan_service/services/content-service/internal/content/content_behavior_fact/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/content/post/application/authorimpact"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

// TestLikePost verifies persona/device actors occupy disjoint reaction identities.
func TestLikePost(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPost(t, `{"contentType":"image","title":"Like target"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	type actorCase struct {
		name      string
		principal rtauth.Principal
	}
	cases := []actorCase{
		{
			name: "persona",
			principal: rtauth.Principal{
				Actor: rtoperation.ActorContext{
					AccountID: "account_like_persona",
					PersonaID: "persona_like_001",
				},
			},
		},
		{
			name: "device",
			principal: rtauth.Principal{
				Actor: rtoperation.ActorContext{
					DeviceActorID: "device_like_001",
				},
			},
		},
	}
	reactionIDs := map[string]struct{}{}
	for _, testCase := range cases {
		req := httptest.NewRequest(http.MethodPost, "/content/posts/"+postID+"/like", nil)
		req.Header.Set("Idempotency-Key", "like-identity-"+testCase.name)
		req = req.WithContext(rtauth.WithPrincipal(req.Context(), testCase.principal))
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("%s like status=%d body=%s", testCase.name, rec.Code, rec.Body.String())
		}
		var result struct {
			ReactionID string `json:"reactionId"`
			Liked      bool   `json:"liked"`
		}
		if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
			t.Fatalf("decode %s like response: %v", testCase.name, err)
		}
		if result.ReactionID == "" || !result.Liked {
			t.Fatalf("%s like response is incomplete: %+v", testCase.name, result)
		}
		reactionIDs[result.ReactionID] = struct{}{}
	}
	if len(reactionIDs) != len(cases) {
		t.Fatalf("persona/device identities collapsed into one reaction: %+v", reactionIDs)
	}
	for dimension, actorID := range map[string]string{
		"persona": "persona_like_001",
		"device":  "device_like_001",
	} {
		count, err := requireMongoDB(t).Collection("content_reaction_aggregates").
			CountDocuments(t.Context(), bson.M{
				"targetKind":     "post",
				"targetId":       postID,
				"actorDimension": dimension,
				"actorId":        actorID,
			})
		if err != nil || count != 1 {
			t.Fatalf("%s identity aggregate count=%d err=%v", dimension, count, err)
		}
	}
}

// TestFavoriteRouteRetired 反向守护：收藏概念全量退场后，
// /content/content/posts/{id}/favorite 路由必须不再注册（404），防止兼容路由回潮。
func TestFavoriteRouteRetired(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPost(t, `{"contentType":"image","title":"Favorite retired target"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	req := httptest.NewRequest(http.MethodPost, "/content/posts/"+postID+"/favorite", nil)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("favorite route must be retired (expect 404), got %d: %s", rec.Code, rec.Body.String())
	}
}

// TestBehaviorBatchReport verifies POST /content/behaviors accepts a mixed batch
// of impression + dwell + click events and returns 204.
// contract.yaml: behavior_batch_report
func TestBehaviorBatchReport(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPost(t, `{"contentType":"image","title":"Behavior batch target"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
	payload := fmt.Sprintf(`{
		"userId": "user_batch_001",
		"sessionId": "sess_abc",
		"events": [
			{"clientEventId":"evt-batch-impression-001","occurredAt":%q,"contentId": %q, "action": "impression", "state": "impressed", "userId": "user_batch_001"},
			{"clientEventId":"evt-batch-click-001","occurredAt":%q,"contentId": %q, "action": "click",      "userId": "user_batch_001"},
			{"clientEventId":"evt-batch-dwell-001","occurredAt":%q,"contentId": %q, "action": "dwell",      "userId": "user_batch_001", "duration": 5.5}
		]
	}`, occurredAt, postID, occurredAt, postID, occurredAt, postID)

	req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
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

func TestBehaviorBatchRejectsImpressionWithoutCanonicalState(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPost(t, `{"contentType":"image","title":"Impression state target"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("no postId in created post")
	}

	payload := fmt.Sprintf(
		`{"events":[{"clientEventId":"evt-impression-missing-state","occurredAt":%q,"contentId":%q,"action":"impression"}]}`,
		time.Now().UTC().Format(time.RFC3339Nano),
		postID,
	)
	req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
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

func TestEffectivePlayRejectsScrubAndAcceptsForegroundEvidence(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPost(t, `{"contentType":"video","title":"Effective play target"}`)
	postID := asTestString(created["postId"])
	if postID == "" {
		t.Fatalf("missing post id: %+v", created)
	}

	request := func(state string) *httptest.ResponseRecorder {
		occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
		payload := fmt.Sprintf(`{
			"userId":"effective_play_user",
			"sessionId":"video-playback-session-1",
			"events":[{
				"clientEventId":%q,
				"occurredAt":%q,
				"contentId":%q,
				"action":"effective_play",
				"state":%q,
				"effectivePlayMs":8000,
				"consumedRatio":0.064,
				"totalUnits":125
			}]
		}`, "evt-effective-play-"+state, occurredAt, postID, state)
		req := httptest.NewRequest(
			http.MethodPost,
			"/content/behaviors",
			strings.NewReader(payload),
		)
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		return rec
	}

	if rec := request("scrubbing"); rec.Code != http.StatusBadRequest {
		t.Fatalf("scrub evidence must fail closed, got %d: %s", rec.Code, rec.Body.String())
	}
	if rec := request("foreground_visible_playing"); rec.Code != http.StatusNoContent {
		t.Fatalf("effective play evidence rejected, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestGetMyFootprintContract(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	const userID = "footprint_user_001"
	created := submitPublishedPost(t, `{"contentType":"image","title":"Footprint target"}`)
	postID := asTestString(created["postId"])
	if postID == "" {
		t.Fatalf("missing post id: %+v", created)
	}

	payload := fmt.Sprintf(`{
		"userId": %q,
		"events": [
			{"clientEventId": "evt-footprint-001", "occurredAt": %q, "contentId": %q, "contentType": "image", "action": "click", "userId": %q}
		]
	}`, userID, time.Now().UTC().Format(time.RFC3339Nano), postID, userID)
	reportReq := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
	reportReq.Header.Set("Content-Type", "application/json")
	reportReq.Header.Set("X-Client-User-Id", userID)
	reportReq.Header.Set("X-Client-Persona-Id", userID)
	reportRec := httptest.NewRecorder()
	testHandler.ServeHTTP(reportRec, reportReq)
	if reportRec.Code != http.StatusNoContent {
		t.Fatalf("report behavior: expected 204, got %d: %s", reportRec.Code, reportRec.Body.String())
	}

	footprintReq := httptest.NewRequest(http.MethodGet, "/content/footprint?type=viewed&limit=10", nil)
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

// TestBehaviorBatchEmpty verifies POST /content/behaviors with an empty events
// array returns 400 with CONTENT.USER.invalid_argument.
// contract.yaml: behavior_batch_empty
func TestBehaviorBatchEmpty(t *testing.T) {
	payload := `{"userId": "user_empty", "events": []}`
	req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
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

// TestBehaviorBatchCanonicalWire verifies the app-facing canonical wire used by
// local gamma T3: postId/type/dwellMs.
// TestBehaviorBatchCanonicalWire 冻结契约单轨：唯一 wire 键
// contentId/action/duration/position 可解析；旧键
// postId/type/dwellMs/feedPosition 已删除且不再被双读（安全负例）。
func TestBehaviorBatchCanonicalWire(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPost(t, `{"contentType":"image","title":"Wire canonical target"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	canonical := fmt.Sprintf(
		`{"userId":"user_reporter_001","events":[{"clientEventId":"evt-canonical-wire-001","occurredAt":%q,"contentId":%q,"action":"dwell","duration":12,"userId":"user_reporter_001"}]}`,
		time.Now().UTC().Format(time.RFC3339Nano), postID,
	)
	req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(canonical))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("canonical wire expected 204, got %d: %s", rec.Code, rec.Body.String())
	}

	// 旧键 payload（postId/type/dwellMs）不再承载对象与动作语义：
	// contentId/action 缺失必须被拒绝，服务端不得回退双读。
	legacy := fmt.Sprintf(
		`{"userId":"user_reporter_001","events":[{"clientEventId":"evt-legacy-wire-001","occurredAt":%q,"postId":%q,"type":"dwell","dwellMs":12000,"userId":"user_reporter_001"}]}`,
		time.Now().UTC().Format(time.RFC3339Nano), postID,
	)
	legacyReq := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(legacy))
	legacyReq.Header.Set("Content-Type", "application/json")
	legacyRec := httptest.NewRecorder()
	testHandler.ServeHTTP(legacyRec, legacyReq)
	if legacyRec.Code != http.StatusBadRequest {
		t.Fatalf("legacy dual-read keys must be rejected with 400, got %d: %s", legacyRec.Code, legacyRec.Body.String())
	}
}

// TestBehaviorEventInputDecodesAttributionFields 冻结推荐归因 wire 契约：
// channelId/policyDigest/recallPath/contentVertical/supplySource/
// feedRequestId/referralSource/position/state 与交集分桶字段必须从批量 JSON
// 正确解析进 BehaviorEventInput（端云 DTO↔struct↔YAML common_fields 对齐，R08）。
func TestBehaviorEventInputDecodesAttributionFields(t *testing.T) {
	raw := `{"clientEventId":"evt-attr-001","occurredAt":"2026-07-19T07:00:00Z","contentId":"post_attr_1","action":"impression","state":"impressed",` +
		`"feedRequestId":"frq_01H","referralSource":"organic_feed","position":7,` +
		`"channelId":"following","policyDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",` +
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
	if in.PolicyDigest != "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" {
		t.Errorf("policyDigest: got %q", in.PolicyDigest)
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
	occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
	behaviorService := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		persistence.NewMongoPostStore(mongoDB.Collection("posts")),
	)

	err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
		{
			ClientEventID: "evt-dedup-001",
			OccurredAt:    occurredAt,
			UserID:        "user_dedup_001",
			SessionID:     "sess_dedup_001",
			ContentID:     "post_dedup_001",
			Action:        "impression",
			State:         "impressed",
		},
		{
			ClientEventID: "evt-dedup-001",
			OccurredAt:    occurredAt,
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
	payload := fmt.Sprintf(`{
		"userId":"user_assistant_interest_001",
		"sessionId":"sess_assistant_interest_001",
		"events":[
			{
				"clientEventId":"evt-assistant-interest-http-001",
				"occurredAt":%q,
				"action":"assistant_interest",
				"userId":"user_assistant_interest_001",
				"tagRefs":["Topic/旅行","Topic/景区"]
			}
		]
	}`, time.Now().UTC().Format(time.RFC3339Nano))
	req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
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
	payload := fmt.Sprintf(`{
		"userId":"user_wishlist_http_001",
		"sessionId":"sess_wishlist_http_001",
		"events":[
			{
				"clientEventId":"evt_wishlist_http_001",
				"occurredAt":%q,
				"action":"wishlist_add",
				"objectId":"homepage_west_lake",
				"objectKind":"homepage",
				"displayName":"西湖日落机位",
				"sourceSurface":"object_homepage",
				"referralSource":"entity_page",
			"feedRequestId":"frq_wishlist_http_001"
			}
		]
	}`, time.Now().UTC().Format(time.RFC3339Nano))
	req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", "user_wishlist_http_001")
	req.Header.Set("X-Client-Persona-Id", "user_wishlist_http_001")
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
	// 生产同构装配（N0-2）：行为写持久轨 rm_behavior_events，特征投影由
	// BehaviorProjectionRelay 游标驱动（与 main.go 相同管线），不再经进程内
	// publisher 直连 projector（那会掩盖生产 Pub/Sub 断链）。
	behaviorService := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		persistence.NewMongoPostStore(mongoDB.Collection("posts")),
		behaviorapp.WithBehaviorEventStore(behaviorpersistence.NewMongoBehaviorEventStore(mongoDB, nilLogger())),
	)

	err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
		{
			ClientEventID: "evt-assistant-interest-projector-001",
			OccurredAt:    time.Now().UTC().Format(time.RFC3339Nano),
			UserID:        "user_assistant_interest_projector_001",
			SessionID:     "sess_assistant_interest_projector_001",
			Action:        "assistant_interest",
			Tags:          []string{"Topic/旅行", "Topic/旅行主题"},
		},
	})
	if err != nil {
		t.Fatalf("process assistant_interest: %v", err)
	}
	drainBehaviorProjection(t, ctx)

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

func TestBehaviorBatchOnboardingInterestProjectsCanonicalPriorExactlyOnce(t *testing.T) {
	ctx := context.Background()
	runID := fmt.Sprintf("%d", time.Now().UnixNano())
	userID := "user_onboarding_interest_" + runID
	eventID := "evt-onboarding-interest-" + runID
	featureColl := mongoDB.Collection("rm_recommend_feature")
	eventColl := mongoDB.Collection("rm_behavior_events")
	t.Cleanup(func() {
		_, _ = featureColl.DeleteMany(context.Background(), bson.M{"userId": userID})
		_, _ = eventColl.DeleteMany(context.Background(), bson.M{"userId": userID})
	})

	payload := fmt.Sprintf(
		`{"userId":%q,"events":[{"clientEventId":%q,"occurredAt":%q,"sessionId":"onboarding-feed-session","action":"onboarding_interest","taxonomyReleaseId":"tag-taxonomy-test-001","tagRefs":["Topic/兴趣/旅行","Audience/用户/兴趣偏好/摄影"]}]}`,
		userID,
		eventID,
		time.Now().UTC().Format(time.RFC3339Nano),
	)
	for attempt := 0; attempt < 2; attempt++ {
		req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Client-User-Id", userID)
		req.Header.Set("X-Client-Persona-Id", userID)
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)
		if rec.Code != http.StatusNoContent {
			t.Fatalf("onboarding_interest attempt=%d status=%d body=%s", attempt, rec.Code, rec.Body.String())
		}
	}

	drainBehaviorProjection(t, ctx)
	count, err := eventColl.CountDocuments(ctx, bson.M{
		"userId":        userID,
		"clientEventId": eventID,
	})
	if err != nil {
		t.Fatalf("count persisted onboarding event: %v", err)
	}
	if count != 1 {
		t.Fatalf("onboarding event replay stored %d facts, want exactly one", count)
	}
	var persistedBinding bson.M
	if err := eventColl.FindOne(ctx, bson.M{
		"userId": userID, "clientEventId": eventID,
	}).Decode(&persistedBinding); err != nil {
		t.Fatalf("load persisted onboarding binding: %v", err)
	}
	if persistedBinding["taxonomyReleaseId"] != "tag-taxonomy-test-001" {
		t.Fatalf("persisted catalog binding = %+v", persistedBinding)
	}
	// Retired catalogVersion must not survive in the raw behavior fact.
	if _, exists := persistedBinding["catalogVersion"]; exists {
		t.Fatalf("persisted onboarding fact retained retired catalogVersion: %+v", persistedBinding)
	}

	var got struct {
		UserFeatures struct {
			TagInteraction map[string]int `bson:"tagInteraction"`
		} `bson:"userFeatures"`
	}
	if err := featureColl.FindOne(ctx, bson.M{"userId": userID}).Decode(&got); err != nil {
		t.Fatalf("find onboarding recommend feature: %v", err)
	}
	for _, tagRef := range []string{
		"Topic/兴趣/旅行",
		"Audience/用户/兴趣偏好/摄影",
	} {
		if got.UserFeatures.TagInteraction[tagRef] != 1 {
			t.Fatalf("tagInteraction[%q]=%d, want exactly one: %+v", tagRef, got.UserFeatures.TagInteraction[tagRef], got.UserFeatures.TagInteraction)
		}
	}
}

// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/interest-onboarding-prior/spec.md#gwt-001
func TestBehaviorBatchInvalidOnboardingCatalogWritesNoFacts(t *testing.T) {
	ctx := context.Background()
	runID := fmt.Sprintf("%d", time.Now().UnixNano())
	userID := "user_onboarding_interest_invalid_" + runID
	eventIDs := []string{
		"evt-onboarding-interest-click-" + runID,
		"evt-onboarding-interest-invalid-" + runID,
	}
	eventColl := mongoDB.Collection("rm_behavior_events")
	featureColl := mongoDB.Collection("rm_recommend_feature")
	t.Cleanup(func() {
		_, _ = eventColl.DeleteMany(context.Background(), bson.M{"userId": userID})
		_, _ = featureColl.DeleteMany(context.Background(), bson.M{"userId": userID})
	})

	payload := fmt.Sprintf(
		`{"userId":%q,"events":[`+
			`{"clientEventId":%q,"occurredAt":%q,"sessionId":"onboarding-feed-session","action":"click","contentId":"post-preflight-must-not-write"},`+
			`{"clientEventId":%q,"occurredAt":%q,"sessionId":"onboarding-feed-session","action":"onboarding_interest","taxonomyReleaseId":"tag-taxonomy-old-release","tagRefs":["Topic/兴趣/旅行"]}`+
			`]}`,
		userID,
		eventIDs[0],
		time.Now().UTC().Format(time.RFC3339Nano),
		eventIDs[1],
		time.Now().UTC().Format(time.RFC3339Nano),
	)
	req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", userID)
	req.Header.Set("X-Client-Persona-Id", userID)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("invalid onboarding catalog status=%d body=%s", rec.Code, rec.Body.String())
	}

	factCount, err := eventColl.CountDocuments(ctx, bson.M{
		"userId":        userID,
		"clientEventId": bson.M{"$in": eventIDs},
	})
	if err != nil {
		t.Fatalf("count behavior facts: %v", err)
	}
	if factCount != 0 {
		t.Fatalf("invalid onboarding batch wrote %d behavior facts, want 0", factCount)
	}
	featureCount, err := featureColl.CountDocuments(ctx, bson.M{"userId": userID})
	if err != nil {
		t.Fatalf("count recommendation features: %v", err)
	}
	if featureCount != 0 {
		t.Fatalf("invalid onboarding batch projected %d recommendation feature documents, want 0", featureCount)
	}
}

// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/interest-onboarding-prior/spec.md#gwt-001
func TestBehaviorBatchOnboardingTaxonomyDependencyFailureWritesNoFacts(t *testing.T) {
	ctx := context.Background()
	runID := fmt.Sprintf("%d", time.Now().UnixNano())
	userID := "user_onboarding_interest_dependency_" + runID
	eventIDs := []string{
		"evt-onboarding-interest-click-" + runID,
		"evt-onboarding-interest-dependency-" + runID,
	}
	eventColl := mongoDB.Collection("rm_behavior_events")
	featureColl := mongoDB.Collection("rm_recommend_feature")
	t.Cleanup(func() {
		_, _ = eventColl.DeleteMany(context.Background(), bson.M{"userId": userID})
		_, _ = featureColl.DeleteMany(context.Background(), bson.M{"userId": userID})
	})

	payload := fmt.Sprintf(
		`{"userId":%q,"events":[`+
			`{"clientEventId":%q,"occurredAt":%q,"sessionId":"onboarding-feed-session","action":"click","contentId":"post-preflight-must-not-write"},`+
			`{"clientEventId":%q,"occurredAt":%q,"sessionId":"onboarding-feed-session","action":"onboarding_interest","taxonomyReleaseId":"tag-taxonomy-test-001","tagRefs":["Topic/dependency-unavailable"]}`+
			`]}`,
		userID,
		eventIDs[0],
		time.Now().UTC().Format(time.RFC3339Nano),
		eventIDs[1],
		time.Now().UTC().Format(time.RFC3339Nano),
	)
	req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Client-User-Id", userID)
	req.Header.Set("X-Client-Persona-Id", userID)
	rec := httptest.NewRecorder()
	testHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("taxonomy dependency status=%d body=%s", rec.Code, rec.Body.String())
	}

	factCount, err := eventColl.CountDocuments(ctx, bson.M{
		"userId":        userID,
		"clientEventId": bson.M{"$in": eventIDs},
	})
	if err != nil {
		t.Fatalf("count behavior facts: %v", err)
	}
	if factCount != 0 {
		t.Fatalf("taxonomy dependency failure wrote %d behavior facts, want 0", factCount)
	}
	featureCount, err := featureColl.CountDocuments(ctx, bson.M{"userId": userID})
	if err != nil {
		t.Fatalf("count recommendation features: %v", err)
	}
	if featureCount != 0 {
		t.Fatalf(
			"taxonomy dependency failure projected %d recommendation feature documents, want 0",
			featureCount,
		)
	}
}

// TestBehaviorBatchSevenStateImpressionExcludesVisibleCountsClick 验证阶段五七态漏斗在
// 特征投影中的语义：弱可见 visible 不计入 typeImpressions（served/impressed 双轨的 impressed 侧），
// 仅真实曝光 impressed 计入；click 计入 typeEngagements（CTR 分子）。同时携带 channelId/policyDigest
// 归因字段，验证其可随批次贯穿。
func TestBehaviorBatchSevenStateImpressionExcludesVisibleCountsClick(t *testing.T) {
	ctx := context.Background()
	runID := fmt.Sprintf("%d", time.Now().UnixNano())
	userID := "user_seven_state_" + runID
	visibleID := "post_ss_visible_" + runID
	impressedID := "post_ss_impressed_" + runID
	clickID := "post_ss_click_" + runID
	featureColl := mongoDB.Collection("rm_recommend_feature")
	if _, err := featureColl.DeleteMany(ctx, bson.M{"userId": userID}); err != nil {
		t.Fatalf("clean recommend feature: %v", err)
	}
	feedColl := mongoDB.Collection("rm_discovery_feed")
	contentIDs := []string{visibleID, impressedID, clickID}
	if _, err := feedColl.DeleteMany(ctx, bson.M{"postId": bson.M{"$in": contentIDs}}); err != nil {
		t.Fatalf("clean DiscoveryFeed seven-state fixtures: %v", err)
	}
	t.Cleanup(func() {
		_, _ = featureColl.DeleteMany(context.Background(), bson.M{"userId": userID})
		_, _ = feedColl.DeleteMany(context.Background(), bson.M{"postId": bson.M{"$in": contentIDs}})
		_, _ = mongoDB.Collection("rm_behavior_events").DeleteMany(
			context.Background(),
			bson.M{"userId": userID},
		)
	})
	fixtures := make([]any, 0, len(contentIDs))
	for _, contentID := range contentIDs {
		fixtures = append(fixtures, bson.M{"postId": contentID, "viewCount": int64(0)})
	}
	if _, err := feedColl.InsertMany(ctx, fixtures); err != nil {
		t.Fatalf("seed DiscoveryFeed seven-state fixtures: %v", err)
	}
	// 生产同构装配（N0-2）：持久轨 + relay 驱动投影，与 main.go 一致。
	behaviorService := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		persistence.NewMongoPostStore(mongoDB.Collection("posts")),
		behaviorapp.WithBehaviorEventStore(behaviorpersistence.NewMongoBehaviorEventStore(mongoDB, nilLogger())),
	)

	occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
	err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
		{ClientEventID: "evt-seven-visible-" + runID, OccurredAt: occurredAt, UserID: userID, ContentID: visibleID, Action: "impression", State: "visible", ContentType: "image", ChannelID: "following", PolicyDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", FeedRequestID: "frq_ss"},
		{ClientEventID: "evt-seven-impressed-" + runID, OccurredAt: occurredAt, UserID: userID, ContentID: impressedID, Action: "impression", State: "impressed", ContentType: "image", ChannelID: "following", PolicyDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", FeedRequestID: "frq_ss"},
		{ClientEventID: "evt-seven-click-" + runID, OccurredAt: occurredAt, UserID: userID, ContentID: clickID, Action: "click", State: "click", ContentType: "image", ChannelID: "following", PolicyDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", FeedRequestID: "frq_ss"},
	})
	if err != nil {
		t.Fatalf("process seven-state batch: %v", err)
	}
	drainBehaviorProjection(t, ctx)

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
	wantViews := map[string]int64{
		visibleID:   0,
		impressedID: 1,
		clickID:     0,
	}
	for contentID, want := range wantViews {
		var row struct {
			ViewCount int64 `bson:"viewCount"`
		}
		if err := feedColl.FindOne(ctx, bson.M{"postId": contentID}).Decode(&row); err != nil {
			t.Fatalf("read DiscoveryFeed viewCount for %s: %v", contentID, err)
		}
		if row.ViewCount != want {
			t.Fatalf("DiscoveryFeed viewCount[%s]=%d want=%d", contentID, row.ViewCount, want)
		}
	}
}

func TestBehaviorBatchIntersectionConversionsUpdateMetricsWithoutForgedAuthorImpact(t *testing.T) {
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

	occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
	err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
		{
			ClientEventID:         "evt-intersection-follow-001",
			OccurredAt:            occurredAt,
			UserID:                "viewer_intersection_001",
			ContentID:             "post_follow_001",
			Action:                "follow",
			AuthorID:              authorID,
			IntersectionDimension: "identity",
			IntersectionTagRefs:   []string{"Audience/学生"},
		},
		{
			ClientEventID:         "evt-intersection-join-circle-001",
			OccurredAt:            occurredAt,
			UserID:                "viewer_intersection_001",
			ContentID:             "circle_intersection_001",
			Action:                "join_circle",
			AuthorID:              authorID,
			IntersectionDimension: "interest",
			IntersectionTagRefs:   []string{"Topic/旅行"},
		},
		{
			ClientEventID:         "evt-intersection-add-contact-001",
			OccurredAt:            occurredAt,
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

	store := persistence.NewAuthorImpactEvidenceStore(mongoDB, nilLogger())
	summary, err := store.GetSummary(ctx, authorID, 10)
	if err != nil {
		t.Fatalf("get author impact summary: %v", err)
	}
	if summary.Total != 0 || len(summary.Items) != 0 {
		t.Fatalf("generic social behavior must not forge author impact facts: %+v", summary)
	}
}

func TestGetAuthorImpactReturnsPostBackedBehaviorAggregation(t *testing.T) {
	ctx := context.Background()
	authorID := "author_impact_http_001"
	if _, err := mongoDB.Collection("rm_author_impact").DeleteMany(ctx, bson.M{"authorId": authorID}); err != nil {
		t.Fatalf("clean author impact: %v", err)
	}
	t.Cleanup(func() {
		cleanPosts(t)
		cleanAuthorImpact(t, authorID)
	})
	created := submitPublishedPostWithAuthor(
		t,
		authorID,
		`{"contentType":"image","title":"Impact aggregation target"}`,
	)
	postID := postIDFrom(t, created)
	setPostTagRefsForAuthorImpactTest(t, postID, []string{"Topic/旅行/路线"})
	payload := fmt.Sprintf(`{
		"userId": "viewer_impact_http_001",
		"events": [
			{
				"clientEventId":"evt-impact-http-001",
				"occurredAt":%q,
				"contentId": %q,
				"action": "share",
				"authorId": "forged_impact_author",
				"intersectionDimension": "identity",
				"intersectionTagRefs": ["Audience/学生"]
			}
		]
	}`, time.Now().UTC().Format(time.RFC3339Nano), postID)
	reportReq := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
	reportReq.Header.Set("Content-Type", "application/json")
	reportRec := httptest.NewRecorder()
	testHandler.ServeHTTP(reportRec, reportReq)
	if reportRec.Code != http.StatusNoContent {
		t.Fatalf("report behavior: expected 204, got %d: %s", reportRec.Code, reportRec.Body.String())
	}

	req := httptest.NewRequest(http.MethodGet, "/content/personas/"+authorID+"/author-impact", nil)
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
	if body.Items[0].HelpType != rtimpact.HelpSpread || body.Items[0].Action != "share" || body.Items[0].Count != 1 {
		t.Fatalf("unexpected author impact item: %+v", body.Items[0])
	}
}

// TestAuthorImpactTravelCountTargetFromBehaviorAggregation 端到端验证 WS3 旅行影响力真算：
// 真实行为聚合（viewer 在旅行 tag 内容上的 decision 行为）→ rm_author_impact 聚合 → 云侧
// DecorateAuthorImpact 按 tagRef 派生下钻目标对象 route/photo_spot（§22.5），被计数对象 person。
func TestAuthorImpactTravelCountTargetFromBehaviorAggregation(t *testing.T) {
	ctx := context.Background()
	authorID := "author_travel_impact_realcompute_001"
	cleanAuthorImpact(t, authorID)
	t.Cleanup(func() {
		cleanPosts(t)
		cleanAuthorImpact(t, authorID)
	})
	routePost := submitPublishedPostWithAuthor(
		t,
		authorID,
		`{"contentType":"article","title":"路线攻略"}`,
	)
	routePostID := postIDFrom(t, routePost)
	setPostTagRefsForAuthorImpactTest(t, routePostID, []string{"tag/travel/route"})
	spotPost := submitPublishedPostWithAuthor(
		t,
		authorID,
		`{"contentType":"article","title":"拍摄点攻略"}`,
	)
	spotPostID := postIDFrom(t, spotPost)
	setPostTagRefsForAuthorImpactTest(t, spotPostID, []string{"tag/travel/photo_spot"})
	behaviorService := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		persistence.NewMongoPostStore(mongoDB.Collection("posts")),
		behaviorapp.WithAuthorImpactStore(persistence.NewAuthorImpactStore(mongoDB, nilLogger())),
		behaviorapp.WithAuthorImpactEvidenceStore(
			persistence.NewAuthorImpactEvidenceStore(mongoDB, nilLogger()),
		),
	)

	// viewer 在作者旅行攻略上的真实 decision 行为（content_depth → decision），
	// 携带旅行 tagRef；两条同 route tag 聚合为 count=2。
	occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
	if err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
		{
			ClientEventID:         "evt-travel-route-001",
			OccurredAt:            occurredAt,
			UserID:                "viewer_travel_impact_001",
			ContentID:             routePostID,
			Action:                "content_depth",
			AuthorID:              "forged_travel_author",
			IntersectionDimension: "forged_dimension",
			IntersectionTagRefs:   []string{"forged/tag"},
		},
		{
			ClientEventID:         "evt-travel-route-002",
			OccurredAt:            occurredAt,
			UserID:                "viewer_travel_impact_002",
			ContentID:             routePostID,
			Action:                "content_depth",
			AuthorID:              "forged_travel_author",
			IntersectionDimension: "forged_dimension",
			IntersectionTagRefs:   []string{"forged/tag"},
		},
		{
			ClientEventID:         "evt-travel-spot-001",
			OccurredAt:            occurredAt,
			UserID:                "viewer_travel_impact_003",
			ContentID:             spotPostID,
			Action:                "content_depth",
			AuthorID:              "forged_travel_author",
			IntersectionDimension: "forged_dimension",
			IntersectionTagRefs:   []string{"forged/tag"},
		},
	}); err != nil {
		t.Fatalf("process travel behaviors: %v", err)
	}

	store := persistence.NewAuthorImpactEvidenceStore(mongoDB, nilLogger())
	summary, err := store.GetSummary(ctx, authorID, 10)
	if err != nil {
		t.Fatalf("get author impact summary: %v", err)
	}
	// 云侧装饰（与 handler 同路径）后派生旅行下钻目标。
	decorated := authorimpact.DecorateAuthorImpact(summary, false)

	byTag := map[string]ports.AuthorImpactItem{}
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

func nilLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

func setPostTagRefsForAuthorImpactTest(t *testing.T, postID string, tagRefs []string) {
	t.Helper()
	result, err := mongoDB.Collection("posts").UpdateOne(
		t.Context(),
		bson.M{"_id": postID},
		bson.M{"$set": bson.M{"tagRefs": tagRefs}},
	)
	if err != nil {
		t.Fatalf("set authoritative post tagRefs: %v", err)
	}
	if result.MatchedCount != 1 {
		t.Fatalf("set authoritative post tagRefs matched %d posts for %q", result.MatchedCount, postID)
	}
}

// drainBehaviorProjection 以生产同构方式驱动行为→特征投影（N0-2）：
// 循环 Drain 直到 rm_behavior_events 持久轨全部消费（checkpoint 为全局游标，
// 需要清空积压才能保证本测试新写入的事件已投影）。
func drainBehaviorProjection(t *testing.T, ctx context.Context) {
	t.Helper()
	if testBehaviorProjectionRelay == nil {
		t.Fatal("content-service api_integration requires a behavior projection relay")
	}
	testBehaviorProjectionMu.Lock()
	defer testBehaviorProjectionMu.Unlock()

	for {
		n, err := testBehaviorProjectionRelay.Drain(ctx, 500)
		if err != nil {
			t.Fatalf("behavior projection relay drain: %v", err)
		}
		if n == 0 {
			return
		}
	}
}

// TestBehaviorBatchRejectsLike verifies that server-authoritative actions
// (like/comment/report, N0-3) are rejected by the generic behavior batch
// endpoint — they are injected from object command outbox facts instead.
func TestBehaviorBatchRejectsLike(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })
	created := submitPublishedPost(t, `{"contentType":"image","title":"Like batch target"}`)
	postID, _ := created["postId"].(string)
	if postID == "" {
		t.Fatal("no _id in created post")
	}

	for _, action := range []string{"like", "comment", "report"} {
		payload := fmt.Sprintf(`{"events":[{"contentId":%q,"action":%q}]}`, postID, action)
		req := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()
		testHandler.ServeHTTP(rec, req)

		if rec.Code != http.StatusBadRequest {
			t.Fatalf("action %s: expected 400, got %d: %s", action, rec.Code, rec.Body.String())
		}
		var errResp map[string]any
		if err := json.Unmarshal(rec.Body.Bytes(), &errResp); err != nil {
			t.Fatalf("action %s: decode error response: %v", action, err)
		}
		if code, ok := errResp["code"].(string); !ok || code == "" {
			t.Fatalf("action %s: expected structured error code, got %+v", action, errResp)
		}
	}
}

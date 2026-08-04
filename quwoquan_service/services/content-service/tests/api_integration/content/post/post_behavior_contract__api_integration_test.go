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
	rtoperation "quwoquan_service/runtime/operation"
	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	behaviorpersistence "quwoquan_service/services/content-service/internal/content/content_behavior_fact/infrastructure/persistence"
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
	noncanonical := fmt.Sprintf(
		`{"userId":"user_reporter_001","events":[{"clientEventId":"evt-retired-wire-001","occurredAt":%q,"postId":%q,"type":"dwell","dwellMs":12000,"userId":"user_reporter_001"}]}`,
		time.Now().UTC().Format(time.RFC3339Nano), postID,
	)
	noncanonicalReq := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(noncanonical))
	noncanonicalReq.Header.Set("Content-Type", "application/json")
	noncanonicalRec := httptest.NewRecorder()
	testHandler.ServeHTTP(noncanonicalRec, noncanonicalReq)
	if noncanonicalRec.Code != http.StatusBadRequest {
		t.Fatalf("retired keys must be rejected with 400, got %d: %s", noncanonicalRec.Code, noncanonicalRec.Body.String())
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
		newMongoPostStore(mongoDB.Collection("posts")),
	)

	_, err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
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

func TestBehaviorBatchOnboardingInterestProjectsCanonicalPriorExactlyOnce(t *testing.T) {
	ctx := context.Background()
	runID := fmt.Sprintf("%d", time.Now().UnixNano())
	userID := "user_onboarding_interest_" + runID
	eventID := "evt-onboarding-interest-" + runID
	eventColl := mongoDB.Collection("rm_behavior_events")
	t.Cleanup(func() {
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
	t.Cleanup(func() {
		_, _ = eventColl.DeleteMany(context.Background(), bson.M{"userId": userID})
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
	t.Cleanup(func() {
		_, _ = eventColl.DeleteMany(context.Background(), bson.M{"userId": userID})
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
}

// TestBehaviorBatchPersistsCanonicalFunnelStates verifies ContentBehaviorFact's
// typed source facts and attribution only. Recommendation derives its feature
// counters in recommendation-service and must never write them in Content.
func TestBehaviorBatchPersistsCanonicalFunnelStates(t *testing.T) {
	ctx := context.Background()
	runID := fmt.Sprintf("%d", time.Now().UnixNano())
	userID := "user_seven_state_" + runID
	visibleID := "post_ss_visible_" + runID
	impressedID := "post_ss_impressed_" + runID
	clickID := "post_ss_click_" + runID
	eventColl := mongoDB.Collection("rm_behavior_events")
	contentIDs := []string{visibleID, impressedID, clickID}
	t.Cleanup(func() {
		_, _ = eventColl.DeleteMany(context.Background(), bson.M{"userId": userID})
	})
	behaviorService := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(testRouter.Scene("rec"))),
		newMongoPostStore(mongoDB.Collection("posts")),
		behaviorapp.WithBehaviorEventStore(behaviorpersistence.NewMongoBehaviorEventStore(mongoDB, nilLogger())),
	)

	occurredAt := time.Now().UTC().Format(time.RFC3339Nano)
	_, err := behaviorService.ProcessBatch(ctx, []behaviorapp.BehaviorEventInput{
		{ClientEventID: "evt-seven-visible-" + runID, OccurredAt: occurredAt, UserID: userID, ContentID: visibleID, Action: "impression", State: "visible", ContentType: "image", ChannelID: "following", PolicyDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", FeedRequestID: "frq_ss"},
		{ClientEventID: "evt-seven-impressed-" + runID, OccurredAt: occurredAt, UserID: userID, ContentID: impressedID, Action: "impression", State: "impressed", ContentType: "image", ChannelID: "following", PolicyDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", FeedRequestID: "frq_ss"},
		{ClientEventID: "evt-seven-click-" + runID, OccurredAt: occurredAt, UserID: userID, ContentID: clickID, Action: "click", State: "click", ContentType: "image", ChannelID: "following", PolicyDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", FeedRequestID: "frq_ss"},
	})
	if err != nil {
		t.Fatalf("process seven-state batch: %v", err)
	}
	cursor, err := eventColl.Find(ctx, bson.M{
		"userId":    userID,
		"contentId": bson.M{"$in": contentIDs},
	})
	if err != nil {
		t.Fatalf("query canonical behavior facts: %v", err)
	}
	defer cursor.Close(ctx)
	var facts []struct {
		ContentID     string `bson:"contentId"`
		Action        string `bson:"action"`
		State         string `bson:"state"`
		ChannelID     string `bson:"channelId"`
		PolicyDigest  string `bson:"policyDigest"`
		FeedRequestID string `bson:"feedRequestId"`
	}
	if err := cursor.All(ctx, &facts); err != nil {
		t.Fatalf("decode canonical behavior facts: %v", err)
	}
	if len(facts) != 3 {
		t.Fatalf("behavior fact count=%d, want 3", len(facts))
	}
	wantState := map[string]string{
		visibleID: "visible", impressedID: "impressed", clickID: "click",
	}
	for _, fact := range facts {
		if fact.State != wantState[fact.ContentID] || fact.ChannelID != "following" ||
			fact.PolicyDigest != "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" ||
			fact.FeedRequestID != "frq_ss" {
			t.Fatalf("canonical funnel fact mismatch: %+v", fact)
		}
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

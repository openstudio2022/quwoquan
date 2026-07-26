package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

// W3 精品流读路径闭环（B3 / R-IX04）：product-ops `events.ops.*` 事件 →
// PremiumPoolEventConsumer（真实 Redis pub/sub）→ rm_premium_pool 投影（真实
// Mongo）→ PremiumPoolSource fail-closed 召回 → FeedService premium 频道返回
// recallPath=premium_pool 的端到端链路。takedown 后 premium feed 立即回空
// （fail-closed，禁止回退时间流）。
func TestPremiumPoolEventChainServesAndEjectsPremiumFeed(t *testing.T) {
	db := requireMongoDB(t)
	router := requireTestRouter(t)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	poolColl := db.Collection("rm_premium_pool")
	feedColl := db.Collection("rm_discovery_feed")
	postsColl := db.Collection("posts")
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cleanupCancel()
		_, _ = poolColl.DeleteMany(cleanupCtx, bson.M{"contentId": bson.M{"$regex": "^premium_chain_"}})
		_, _ = feedColl.DeleteMany(cleanupCtx, bson.M{"postId": bson.M{"$regex": "^premium_chain_"}})
		_, _ = postsColl.DeleteMany(cleanupCtx, bson.M{"_id": bson.M{"$regex": "^premium_chain_"}})
	})

	const contentID = "premium_chain_post_001"
	now := time.Now().UTC()
	// 精品候选的召回 join rm_discovery_feed 读模型；渲染详情读 posts 聚合。
	if _, err := feedColl.InsertOne(ctx, bson.M{
		"postId":          contentID,
		"contentType":     "article",
		"authorId":        "premium_chain_author",
		"title":           "精品池端到端链路验证",
		"tagRefs":         []string{"Topic/旅行/玩法/摄影旅拍"},
		"contentVertical": "travel_photography",
		"supplySource":    "data_engineering",
		"publishedAt":     now,
		"qualityScore":    0.9,
		"recScore":        0.9,
	}); err != nil {
		t.Fatalf("seed rm_discovery_feed: %v", err)
	}
	if _, err := postsColl.InsertOne(ctx, bson.M{
		"_id":              contentID,
		"contentType":      "article",
		"contentIdentity":  "work",
		"authorId":         "premium_chain_author",
		"title":            "精品池端到端链路验证",
		"body":             "精品池事件链 api_integration 正文",
		"status":           "published",
		"visibility":       "public",
		"moderationStatus": "approved",
		"tagRefs":          []string{"Topic/旅行/玩法/摄影旅拍"},
		"contentVertical":  "travel_photography",
		"createdAt":        now,
		"publishedAt":      now,
	}); err != nil {
		t.Fatalf("seed posts: %v", err)
	}

	// 真实 pub/sub 消费者（与生产 main.go 同源组件）。
	generalRedis := router.Scene("general")
	consumer := recinfra.NewPremiumPoolEventConsumer(
		generalRedis,
		recinfra.NewPremiumPoolProjector(db),
		nil,
	)
	consumerCtx, stopConsumer := context.WithCancel(ctx)
	defer stopConsumer()
	go consumer.Run(consumerCtx)
	// 等待订阅建立后再发布，避免 pub/sub 消息在订阅前丢失。
	time.Sleep(300 * time.Millisecond)

	publishOpsEvent := func(eventType string, data map[string]any) {
		t.Helper()
		envelope := map[string]any{
			"payload": map[string]any{
				"type":          eventType,
				"aggregateType": "PremiumPoolEntry",
				"aggregateId":   contentID,
				"data":          data,
				"occurredAt":    time.Now().UTC().Format(time.RFC3339),
			},
		}
		raw, err := json.Marshal(envelope)
		if err != nil {
			t.Fatalf("marshal ops event: %v", err)
		}
		if err := generalRedis.Publish(ctx, "events.ops."+eventType, string(raw)); err != nil {
			t.Fatalf("publish ops event: %v", err)
		}
	}

	publishOpsEvent(recinfra.PremiumPoolEntryUpsertedEvent, map[string]any{
		"contentId":        contentID,
		"scope":            "global",
		"status":           "active",
		"qualityAdmission": "approved",
		"qualityScore":     0.9,
		"supplySource":     "data_engineering",
		"sourceTaskId":     "task_premium_chain",
		"auditId":          "audit_premium_chain",
		"rollbackToken":    "rollback_premium_chain",
		"expiresAt":        time.Now().UTC().Add(24 * time.Hour).Format(time.RFC3339),
	})

	if err := waitForPremiumEligibility(ctx, poolColl, contentID, "eligible"); err != nil {
		t.Fatalf("premium projection not materialized: %v", err)
	}

	feedSvc := newPremiumChainFeedService(db, router)
	resp, err := feedSvc.ListFeed(ctx, feedapp.ListFeedRequest{
		UserID:    "premium_chain_viewer",
		SessionID: "premium_chain_session",
		ChannelID: "premium",
		Limit:     10,
	})
	if err != nil {
		t.Fatalf("ListFeed premium: %v", err)
	}
	var premiumItem *feedapp.FeedItemView
	for i := range resp.Items {
		if resp.Items[i].PostID == contentID {
			premiumItem = &resp.Items[i]
			break
		}
	}
	if premiumItem == nil {
		t.Fatalf("premium feed must serve pool candidate, got %+v", resp.Items)
	}
	if premiumItem.RecallPath != recinfra.PremiumPoolRecallPath {
		t.Fatalf(
			"premium item recallPath=%q want %q",
			premiumItem.RecallPath,
			recinfra.PremiumPoolRecallPath,
		)
	}

	// takedown 下架 → 池内失效 → premium feed fail-closed 回空（不回退时间流）。
	publishOpsEvent(recinfra.PremiumPoolEntryTakedownEjectedEvent, map[string]any{
		"contentId":       contentID,
		"scope":           "global",
		"status":          "active",
		"takedownEjected": true,
	})
	if err := waitForPremiumEligibility(ctx, poolColl, contentID, "ineligible"); err != nil {
		t.Fatalf("premium takedown not materialized: %v", err)
	}
	after, err := feedSvc.ListFeed(ctx, feedapp.ListFeedRequest{
		UserID:    "premium_chain_viewer",
		SessionID: "premium_chain_session_2",
		ChannelID: "premium",
		Limit:     10,
	})
	if err != nil {
		t.Fatalf("ListFeed premium after takedown: %v", err)
	}
	for _, item := range after.Items {
		if item.PostID == contentID {
			t.Fatalf("ejected premium content must not be served (fail-closed), got %+v", after.Items)
		}
	}
}

// newPremiumChainFeedService 按生产 main.go 同源方式装配 premium fail-closed
// 召回：所有源统一包 GatePremiumStreamSource，premium_stream surface 只允许
// PremiumPoolSource 供给。
func newPremiumChainFeedService(db *mongo.Database, router *rtredis.Router) *feedapp.FeedService {
	hotPath := rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec")))
	rawSources := []rtrec.CandidateSource{
		recinfra.NewTagRecallSource(db),
		recinfra.NewHotRecallSource(db, 48*time.Hour),
		recinfra.NewPremiumPoolSource(recinfra.NewMongoPremiumPoolCandidateReader(db)),
	}
	gated := make([]rtrec.CandidateSource, 0, len(rawSources))
	for _, source := range rawSources {
		gated = append(gated, recinfra.GatePremiumStreamSource(source))
	}
	engine := rtrec.NewEngine(hotPath, gated)
	return feedapp.NewFeedService(
		engine,
		persistence.NewMongoPostQueryReader(db.Collection("posts")),
	)
}

func waitForPremiumEligibility(
	ctx context.Context,
	poolColl *mongo.Collection,
	contentID string,
	wantEligibility string,
) error {
	deadline := time.Now().Add(10 * time.Second)
	var lastState string
	for time.Now().Before(deadline) {
		var doc struct {
			EligibilityState string `bson:"eligibilityState"`
			TakedownEjected  bool   `bson:"takedownEjected"`
		}
		err := poolColl.FindOne(ctx, bson.M{"contentId": contentID}).Decode(&doc)
		if err == nil {
			lastState = doc.EligibilityState
			if wantEligibility == "ineligible" && doc.TakedownEjected {
				return nil
			}
			if doc.EligibilityState == wantEligibility {
				return nil
			}
		} else if err != mongo.ErrNoDocuments {
			return err
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(200 * time.Millisecond):
		}
	}
	return fmt.Errorf(
		"rm_premium_pool eligibility for %s did not reach %q (last=%q)",
		contentID,
		wantEligibility,
		lastState,
	)
}

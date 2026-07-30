package api_integration

import (
	"context"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	behaviorpersistence "quwoquan_service/services/content-service/internal/content/content_behavior_fact/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

func TestBehaviorEventIdempotencyIndexExcludesEmptyClientEventIDs(t *testing.T) {
	ctx := t.Context()
	if mongoClient == nil {
		t.Fatal("content-service tests require mongoClient")
	}
	db := mongoClient.Database("content_behavior_event_index_current")
	t.Cleanup(func() {
		if err := db.Drop(context.Background()); err != nil {
			t.Errorf("drop behavior event index database: %v", err)
		}
	})
	events := db.Collection("rm_behavior_events")

	store := behaviorpersistence.NewMongoBehaviorEventStore(db, nilLogger())
	cursor, err := events.Indexes().List(ctx)
	if err != nil {
		t.Fatalf("list migrated behavior event indexes: %v", err)
	}
	defer cursor.Close(ctx)
	var indexes []bson.M
	if err := cursor.All(ctx, &indexes); err != nil {
		t.Fatalf("decode migrated behavior event indexes: %v", err)
	}
	var idempotencyIndex bson.M
	for _, index := range indexes {
		if index["name"] == "uq_behavior_events_user_client_event" {
			idempotencyIndex = index
			break
		}
	}
	if idempotencyIndex == nil {
		t.Fatal("behavior event idempotency index was not created")
	}
	if unique, ok := idempotencyIndex["unique"].(bool); !ok || !unique {
		t.Fatalf("behavior event idempotency index must stay unique: %#v", idempotencyIndex)
	}
	partial, ok := bsonDocumentToMap(idempotencyIndex["partialFilterExpression"])
	if !ok {
		t.Fatalf("behavior event idempotency index must use partial filter: %#v", idempotencyIndex)
	}
	clientEventID, ok := bsonDocumentToMap(partial["clientEventId"])
	if !ok || clientEventID["$type"] != "string" || clientEventID["$gt"] != "" {
		t.Fatalf("unexpected clientEventId partial filter: %#v", partial)
	}

	if _, err := events.InsertMany(ctx, []any{
		bson.M{"_id": "missing-client-event-id", "userId": "anonymous-event-user"},
		bson.M{"_id": "empty-client-event-id", "userId": "anonymous-event-user", "clientEventId": ""},
	}); err != nil {
		t.Fatalf("events without an idempotency key must remain writable: %v", err)
	}
	event := ports.RawBehaviorEvent{
		ClientEventID: "event-replay",
		UserID:        "replay-user",
		SessionID:     "session",
		ContentID:     "post",
		Action:        "click",
		OccurredAt:    time.Now().UTC().Format(time.RFC3339Nano),
		CreatedAt:     time.Now().UTC(),
	}
	if err := store.InsertBatch(ctx, []ports.RawBehaviorEvent{event}); err != nil {
		t.Fatalf("insert initial behavior event: %v", err)
	}
	if err := store.InsertBatch(ctx, []ports.RawBehaviorEvent{event}); err != nil {
		t.Fatalf("replay behavior event must be idempotent: %v", err)
	}
	count, err := events.CountDocuments(ctx, bson.M{
		"userId":        event.UserID,
		"clientEventId": event.ClientEventID,
	})
	if err != nil {
		t.Fatalf("count replayed behavior events: %v", err)
	}
	if count != 1 {
		t.Fatalf("replayed behavior event count=%d, want 1", count)
	}
}

func bsonDocumentToMap(value any) (bson.M, bool) {
	switch document := value.(type) {
	case bson.M:
		return document, true
	case bson.D:
		result := make(bson.M, len(document))
		for _, element := range document {
			result[element.Key] = element.Value
		}
		return result, true
	default:
		return nil, false
	}
}

// TestBehaviorProjectionReplayDoesNotDoubleIncrement 以真实 Mongo 验证行为 relay
// 的 at-least-once 语义：不同事实各应用一次，同一事实重放或旧事实晚到均不得重复 $inc。
func TestBehaviorProjectionReplayDoesNotDoubleIncrement(t *testing.T) {
	ctx := t.Context()
	db := requireMongoDB(t)
	const (
		userID  = "behavior_projection_idempotency_user"
		content = "behavior_projection_idempotency_post"
		tag     = "Topic/幂等投影"
	)
	features := db.Collection("rm_recommend_feature")
	feed := db.Collection("rm_discovery_feed")
	_, _ = features.DeleteMany(ctx, bson.M{"userId": userID})
	_, _ = feed.DeleteMany(ctx, bson.M{"postId": content})
	t.Cleanup(func() {
		_, _ = features.DeleteMany(ctx, bson.M{"userId": userID})
		_, _ = feed.DeleteMany(ctx, bson.M{"postId": content})
	})
	if _, err := feed.InsertOne(ctx, bson.M{
		"postId":    content,
		"viewCount": int64(0),
	}); err != nil {
		t.Fatalf("seed DiscoveryFeed row: %v", err)
	}

	recommendProjector := recinfra.NewRecommendFeatureProjector(db)
	if err := recommendProjector.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure RecommendFeature indexes: %v", err)
	}
	discoveryProjector := recinfra.NewDiscoveryFeedProjector(db)

	firstID := bson.NewObjectID().Hex()
	secondID := bson.NewObjectID().Hex()
	event := func(id string) recinfra.ProjectorEvent {
		return recinfra.ProjectorEvent{
			ID:            id,
			Type:          "BehaviorBatchReported",
			AggregateType: "BehaviorBatch",
			AggregateID:   userID,
			Payload: map[string]any{
				"userId": userID,
				"events": []map[string]any{{
					"contentId":       content,
					"action":          "impression",
					"state":           "impressed",
					"contentType":     "article",
					"tagRefs":         []string{tag},
					"engagementDepth": 1,
				}},
			},
		}
	}

	for _, projected := range []recinfra.ProjectorEvent{
		event(firstID),
		event(firstID),  // checkpoint 重放
		event(secondID), // 新事实
		event(firstID),  // 旧事实晚到
	} {
		if err := recommendProjector.Project(ctx, projected); err != nil {
			t.Fatalf("project RecommendFeature event %s: %v", projected.ID, err)
		}
		if err := discoveryProjector.Project(ctx, projected); err != nil {
			t.Fatalf("project DiscoveryFeed event %s: %v", projected.ID, err)
		}
	}

	var featureRow struct {
		LastID       string `bson:"behaviorProjectionLastId"`
		UserFeatures struct {
			TagInteraction map[string]int `bson:"tagInteraction"`
			TotalEvents    int            `bson:"totalEvents"`
		} `bson:"userFeatures"`
	}
	if err := features.FindOne(ctx, bson.M{"userId": userID}).Decode(&featureRow); err != nil {
		t.Fatalf("read RecommendFeature row: %v", err)
	}
	if got := featureRow.UserFeatures.TagInteraction[tag]; got != 2 {
		t.Fatalf("tagInteraction=%d, want two distinct facts only", got)
	}
	if got := featureRow.UserFeatures.TotalEvents; got != 2 {
		t.Fatalf("totalEvents=%d, want two distinct facts only", got)
	}
	if featureRow.LastID != secondID {
		t.Fatalf("RecommendFeature watermark=%q, want %q", featureRow.LastID, secondID)
	}

	var feedRow struct {
		ViewCount int64  `bson:"viewCount"`
		LastID    string `bson:"behaviorProjectionLastId"`
	}
	if err := feed.FindOne(ctx, bson.M{"postId": content}).Decode(&feedRow); err != nil {
		t.Fatalf("read DiscoveryFeed row: %v", err)
	}
	if feedRow.ViewCount != 2 {
		t.Fatalf("viewCount=%d, want two distinct facts only", feedRow.ViewCount)
	}
	if feedRow.LastID != secondID {
		t.Fatalf("DiscoveryFeed watermark=%q, want %q", feedRow.LastID, secondID)
	}
}

// TestBehaviorProjectionMaintainsCumulativeEngagementDepth 守住单行 relay 路径：
// 每个事件必须贡献一个深度样本，不能用最新批次均值覆盖历史均值。
func TestBehaviorProjectionMaintainsCumulativeEngagementDepth(t *testing.T) {
	ctx := t.Context()
	db := requireMongoDB(t)
	const userID = "behavior_projection_depth_average_user"
	features := db.Collection("rm_recommend_feature")
	_, _ = features.DeleteMany(ctx, bson.M{"userId": userID})
	t.Cleanup(func() {
		_, _ = features.DeleteMany(ctx, bson.M{"userId": userID})
	})

	projector := recinfra.NewRecommendFeatureProjector(db)
	if err := projector.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure RecommendFeature indexes: %v", err)
	}

	firstID := bson.NewObjectID().Hex()
	secondID := bson.NewObjectID().Hex()
	event := func(id string, depth int) recinfra.ProjectorEvent {
		return recinfra.ProjectorEvent{
			ID:            id,
			Type:          "BehaviorBatchReported",
			AggregateType: "BehaviorBatch",
			AggregateID:   userID,
			Payload: map[string]any{
				"userId": userID,
				"events": []map[string]any{{
					"contentId":       "behavior_projection_depth_average_post",
					"action":          "dwell",
					"engagementDepth": depth,
				}},
			},
		}
	}
	for _, projected := range []recinfra.ProjectorEvent{
		event(firstID, 1),
		event(secondID, 3),
	} {
		if err := projector.Project(ctx, projected); err != nil {
			t.Fatalf("project depth event %s: %v", projected.ID, err)
		}
	}

	var row struct {
		UserFeatures struct {
			EngagementDepthSum   int `bson:"engagementDepthSum"`
			EngagementDepthCount int `bson:"engagementDepthCount"`
		} `bson:"userFeatures"`
	}
	if err := features.FindOne(ctx, bson.M{"userId": userID}).Decode(&row); err != nil {
		t.Fatalf("read RecommendFeature row: %v", err)
	}
	if row.UserFeatures.EngagementDepthSum != 4 {
		t.Fatalf("engagementDepthSum=%d, want 4", row.UserFeatures.EngagementDepthSum)
	}
	if row.UserFeatures.EngagementDepthCount != 2 {
		t.Fatalf("engagementDepthCount=%d, want 2", row.UserFeatures.EngagementDepthCount)
	}

	vector, err := recinfra.NewFeatureStore(db).GetFeatures(ctx, userID)
	if err != nil {
		t.Fatalf("read derived feature vector: %v", err)
	}
	if vector == nil || vector.AvgEngagementDepth != 2 {
		t.Fatalf("avgEngagementDepth=%v, want 2", vector)
	}
}

// TestBehaviorProjectionRelaySerializesSharedCheckpoint 证明 standby 副本不能在
// active 副本仍处理较低 ObjectID 事件时推进同一全局游标。测试刻意等待超过 lease TTL：
// 活跃行事务必须栅栏化过期租约接管，否则逐文档水位会把此竞态变成丢失增量。
func TestBehaviorProjectionRelaySerializesSharedCheckpoint(t *testing.T) {
	ctx := t.Context()
	db := requireMongoDB(t)
	now := time.Now().UTC()
	// 选一个隔离的历史 ObjectID 区间，使共享测试库的真实行为事实不进入本批。
	previousID := bson.NewObjectIDFromTimestamp(time.Unix(2, 0))
	eventID := bson.NewObjectIDFromTimestamp(time.Unix(3, 0))
	events := db.Collection("rm_behavior_events")
	checkpoints := db.Collection("rec_projection_checkpoints")
	_, _ = events.DeleteOne(ctx, bson.M{"_id": eventID})
	_, _ = checkpoints.DeleteOne(ctx, bson.M{"_id": "behavior-feature-projection"})
	t.Cleanup(func() {
		_, _ = events.DeleteOne(ctx, bson.M{"_id": eventID})
		_, _ = checkpoints.DeleteOne(ctx, bson.M{"_id": "behavior-feature-projection"})
	})
	if _, err := checkpoints.InsertOne(ctx, bson.M{
		"_id":    "behavior-feature-projection",
		"lastId": previousID,
	}); err != nil {
		t.Fatalf("seed isolated relay checkpoint: %v", err)
	}
	if _, err := events.InsertOne(ctx, bson.M{
		"_id":           eventID,
		"userId":        "behavior_projection_lease_user",
		"sessionId":     "behavior_projection_lease_session",
		"contentId":     "behavior_projection_lease_post",
		"action":        "click",
		"createdAt":     now,
		"occurredAt":    now.Format(time.RFC3339Nano),
		"clientEventId": "behavior_projection_lease_event",
	}); err != nil {
		t.Fatalf("seed relay event: %v", err)
	}

	releaseFirst := make(chan struct{})
	var releaseOnce sync.Once
	releaseActiveProjector := func() {
		releaseOnce.Do(func() {
			close(releaseFirst)
		})
	}
	defer releaseActiveProjector()
	firstProjector := &leaseBlockingProjector{
		started: make(chan struct{}, 1),
		release: releaseFirst,
	}
	secondProjector := &leaseCountingProjector{}
	const leaseTTL = 100 * time.Millisecond
	firstRelay := recinfra.NewBehaviorProjectionRelay(db, firstProjector).
		WithWatermarkLag(0).
		WithLeaseTTL(leaseTTL)
	secondRelay := recinfra.NewBehaviorProjectionRelay(db, secondProjector).
		WithWatermarkLag(0).
		WithLeaseTTL(leaseTTL)

	type drainResult struct {
		count int
		err   error
	}
	firstDone := make(chan drainResult, 1)
	go func() {
		count, err := firstRelay.Drain(ctx, 1)
		firstDone <- drainResult{count: count, err: err}
	}()
	select {
	case <-firstProjector.started:
	case <-time.After(2 * time.Second):
		t.Fatal("active relay did not reach projector")
	}

	time.Sleep(2 * leaseTTL)
	secondDone := make(chan drainResult, 1)
	go func() {
		count, err := secondRelay.Drain(ctx, 1)
		secondDone <- drainResult{count: count, err: err}
	}()

	releaseActiveProjector()
	select {
	case result := <-firstDone:
		if result.err != nil || result.count != 1 {
			t.Fatalf("active relay result=%+v, want one successful event", result)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("active relay did not finish")
	}
	select {
	case result := <-secondDone:
		if result.err != nil {
			t.Fatalf("standby relay drain: %v", result.err)
		}
		if result.count != 0 {
			t.Fatalf("standby relay advanced shared checkpoint with %d events", result.count)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("standby relay did not release after active transaction committed")
	}
	if firstProjector.Count() != 1 {
		t.Fatalf("active relay projected %d events, want 1", firstProjector.Count())
	}
	if secondProjector.Count() != 0 {
		t.Fatalf("standby relay must not project while lease is active, got %d calls", secondProjector.Count())
	}
}

type leaseBlockingProjector struct {
	started chan struct{}
	release <-chan struct{}

	mu    sync.Mutex
	count int
}

func (p *leaseBlockingProjector) Project(_ context.Context, _ recinfra.ProjectorEvent) error {
	p.mu.Lock()
	p.count++
	p.mu.Unlock()
	select {
	case p.started <- struct{}{}:
	default:
	}
	<-p.release
	return nil
}

func (p *leaseBlockingProjector) Count() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.count
}

type leaseCountingProjector struct {
	mu    sync.Mutex
	count int
}

func (p *leaseCountingProjector) Project(_ context.Context, _ recinfra.ProjectorEvent) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.count++
	return nil
}

func (p *leaseCountingProjector) Count() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.count
}

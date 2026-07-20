package api_integration

import (
	"context"
	"fmt"
	"testing"
	"time"

	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	reviewmodel "quwoquan_service/services/entity-service/internal/domain/homepage_review/model"
	reviewports "quwoquan_service/services/entity-service/internal/domain/homepage_review/ports"
	reviewpersistence "quwoquan_service/services/entity-service/internal/infrastructure/homepage_review/persistence"
)

// tryRunReviewMongoContainer 启动 mongo:7 副本集容器；依赖不可用时测试失败关闭。
func tryRunReviewMongoContainer(ctx context.Context) (c *mongomod.MongoDBContainer, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("testcontainers panic (Docker unavailable?): %v", r)
		}
	}()
	c, err = mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
	return
}

// TestHomepageReviewMongoStoreRealCASAndReceipts 用真实 Mongo 验证：
// 唯一索引（一人一主页一条）、CAS commit predicate、事务提交、
// receipt 幂等重放与 digest 冲突、keyset 分页与真实摘要聚合。
func TestHomepageReviewMongoStoreRealCASAndReceipts(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	defer cancel()
	container, err := tryRunReviewMongoContainer(ctx)
	if err != nil {
		t.Fatalf("mongo testcontainer unavailable: %v", err)
	}
	defer func() { _ = container.Terminate(context.Background()) }()
	uri, err := container.ConnectionString(ctx)
	if err != nil {
		t.Fatalf("mongo connection string: %v", err)
	}
	// Colima 经 localhost 端口转发暴露副本集成员，而 Mongo 广告容器内网 IP；
	// direct 模式让 driver 停留在可达地址，rs0 事务能力不受影响。
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(uri).SetDirect(true))
	if err != nil {
		t.Fatalf("mongo connect: %v", err)
	}
	defer func() { _ = client.Disconnect(context.Background()) }()
	db := client.Database("entity_review_it")
	store := reviewpersistence.NewMongoReviewStore(db, true)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure indexes: %v", err)
	}

	now := time.Now().UTC().Truncate(time.Second)
	aggregate, err := reviewmodel.Create(reviewmodel.CreateParams{
		ID:              "hpr_it_1",
		HomepageID:      "hp-it",
		AuthorPersonaID: "persona-it",
		Rating:          5,
		Body:            "真实体验",
		TagRefs:         []string{"publish/tags/scenery"},
		Now:             now,
	})
	if err != nil {
		t.Fatalf("create aggregate: %v", err)
	}
	commit := reviewports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  0,
		IdempotencyKey:   "it-key-1",
		CommandName:      "CreateHomepageReview",
		CommandDigest:    "digest-1",
		ReceiptExpiresAt: now.Add(24 * time.Hour),
		Events: []reviewports.OutboxEvent{{
			EventID:          "evt-1",
			EventType:        "HomepageReviewPublished",
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          []byte(`{"_id":"hpr_it_1"}`),
			OccurredAt:       now,
		}},
	}
	if _, err := store.Commit(ctx, commit); err != nil {
		t.Fatalf("first commit: %v", err)
	}

	// receipt 幂等重放。
	replayed, found, err := store.FindReceipt(ctx, "it-key-1", "CreateHomepageReview", "digest-1")
	if err != nil || !found || !replayed.Replayed {
		t.Fatalf("receipt replay mismatch: found=%v err=%v", found, err)
	}
	// 相同 key 不同 digest 拒绝。
	if _, _, err := store.FindReceipt(ctx, "it-key-1", "CreateHomepageReview", "digest-2"); err == nil {
		t.Fatalf("expected idempotency conflict for digest mismatch")
	}

	// 唯一索引：同一 persona 对同一主页第二个聚合被拒绝。
	duplicate, err := reviewmodel.Create(reviewmodel.CreateParams{
		ID:              "hpr_it_dup",
		HomepageID:      "hp-it",
		AuthorPersonaID: "persona-it",
		Rating:          4,
		Now:             now.Add(time.Second),
	})
	if err != nil {
		t.Fatalf("create duplicate aggregate: %v", err)
	}
	if _, err := store.Commit(ctx, reviewports.Commit{
		Aggregate:        duplicate,
		ExpectedVersion:  0,
		IdempotencyKey:   "it-key-dup",
		CommandName:      "CreateHomepageReview",
		CommandDigest:    "digest-dup",
		ReceiptExpiresAt: now.Add(24 * time.Hour),
		Events: []reviewports.OutboxEvent{{
			EventID:          "evt-dup",
			EventType:        "HomepageReviewPublished",
			AggregateID:      duplicate.ID(),
			AggregateVersion: duplicate.Version(),
			Payload:          []byte(`{}`),
			OccurredAt:       now,
		}},
	}); err == nil {
		t.Fatalf("expected unique index violation for duplicate author+homepage")
	}

	// CAS：过期 expectedVersion 冲突。
	loaded, found, err := store.Load(ctx, "hpr_it_1")
	if err != nil || !found {
		t.Fatalf("load aggregate: found=%v err=%v", found, err)
	}
	if err := loaded.Update("persona-it", reviewmodel.MutationParams{
		Rating:  4,
		TagRefs: []string{"publish/tags/scenery"},
		Now:     now.Add(2 * time.Second),
	}); err != nil {
		t.Fatalf("update aggregate: %v", err)
	}
	if _, err := store.Commit(ctx, reviewports.Commit{
		Aggregate:        loaded,
		ExpectedVersion:  99,
		IdempotencyKey:   "it-key-2",
		CommandName:      "UpdateHomepageReview",
		CommandDigest:    "digest-2",
		ReceiptExpiresAt: now.Add(24 * time.Hour),
		Events: []reviewports.OutboxEvent{{
			EventID:          "evt-2",
			EventType:        "HomepageReviewUpdated",
			AggregateID:      loaded.ID(),
			AggregateVersion: loaded.Version(),
			Payload:          []byte(`{}`),
			OccurredAt:       now,
		}},
	}); err == nil {
		t.Fatalf("expected version predicate mismatch for stale expected version")
	}
	if _, err := store.Commit(ctx, reviewports.Commit{
		Aggregate:        loaded,
		ExpectedVersion:  1,
		IdempotencyKey:   "it-key-2b",
		CommandName:      "UpdateHomepageReview",
		CommandDigest:    "digest-2b",
		ReceiptExpiresAt: now.Add(24 * time.Hour),
		Events: []reviewports.OutboxEvent{{
			EventID:          "evt-2b",
			EventType:        "HomepageReviewUpdated",
			AggregateID:      loaded.ID(),
			AggregateVersion: loaded.Version(),
			Payload:          []byte(`{}`),
			OccurredAt:       now,
		}},
	}); err != nil {
		t.Fatalf("expected CAS commit with correct version: %v", err)
	}

	// 真实摘要聚合。
	summary, err := store.SummarizeByHomepage(ctx, "hp-it")
	if err != nil {
		t.Fatalf("summarize: %v", err)
	}
	if summary.RatingCount != 1 || summary.AverageRating == nil || *summary.AverageRating != 4 {
		t.Fatalf("unexpected summary: %+v", summary)
	}
	if len(summary.HighlightTags) != 1 || summary.HighlightTags[0] != "publish/tags/scenery" {
		t.Fatalf("unexpected highlight tags: %+v", summary.HighlightTags)
	}

	// 分页读取。
	page, err := store.ListByHomepage(ctx, "hp-it", reviewports.PageRequest{Limit: 10})
	if err != nil || len(page.Items) != 1 {
		t.Fatalf("list page mismatch: %+v err=%v", page, err)
	}

	// outbox 重放顺序可读。
	events, err := store.ReadAfter(ctx, "", 10)
	if err != nil || len(events) != 2 {
		t.Fatalf("outbox read mismatch: %d err=%v", len(events), err)
	}
}

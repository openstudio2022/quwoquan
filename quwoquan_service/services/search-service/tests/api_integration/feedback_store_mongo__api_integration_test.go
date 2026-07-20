package api_integration

import (
	"context"
	"log/slog"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/search-service/internal/application"
	"quwoquan_service/services/search-service/internal/infrastructure/feedbackstore"
)

func newFeedbackStore(t *testing.T) *feedbackstore.Store {
	t.Helper()
	store := feedbackstore.NewStore(mongoDB, slog.Default())
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure search feedback indexes: %v", err)
	}
	return store
}

// TestFeedbackRecordDedupesSemanticKey 验证 (searchRequestId, eventType, objectId)
// 语义键唯一索引：客户端重试/双击重放安全，只落一条事实。
func TestFeedbackRecordDedupesSemanticKey(t *testing.T) {
	cleanSearchCollections(t)
	store := newFeedbackStore(t)
	ctx := context.Background()

	event := application.FeedbackEvent{
		SearchRequestID: "req-dedupe-1",
		ViewerID:        "persona-feedback-owner",
		EventType:       "click",
		ObjectID:        "post-1",
		Target:          "posts",
		RankPosition:    3,
		ReferralSource:  "searchResults",
	}
	if err := store.Record(ctx, event); err != nil {
		t.Fatalf("first record: %v", err)
	}
	if err := store.Record(ctx, event); err != nil {
		t.Fatalf("duplicate record must be replay-safe: %v", err)
	}
	count, err := mongoDB.Collection("search_feedback_events").CountDocuments(ctx, bson.M{
		"searchRequestId": "req-dedupe-1",
	})
	if err != nil || count != 1 {
		t.Fatalf("dedupe must keep one fact: count=%d err=%v", count, err)
	}
	count, err = mongoDB.Collection("search_feedback_events").CountDocuments(ctx, bson.M{
		"searchRequestId": "req-dedupe-1",
		"viewerId":       "persona-feedback-owner",
	})
	if err != nil || count != 1 {
		t.Fatalf(
			"feedback must retain server-derived viewer for lifecycle cleanup: count=%d err=%v",
			count,
			err,
		)
	}

	// 不同 objectId / eventType 是不同事实。
	other := event
	other.ObjectID = "post-2"
	if err := store.Record(ctx, other); err != nil {
		t.Fatalf("different object: %v", err)
	}
	impression := event
	impression.EventType = "impression"
	impression.ObjectID = ""
	if err := store.Record(ctx, impression); err != nil {
		t.Fatalf("impression fact: %v", err)
	}
	count, err = mongoDB.Collection("search_feedback_events").CountDocuments(ctx, bson.M{
		"searchRequestId": "req-dedupe-1",
	})
	if err != nil || count != 3 {
		t.Fatalf("distinct semantic keys must append: count=%d err=%v", count, err)
	}
}

// TestFeedbackAndQueryLogTTLIndexes 验证 TTL 索引与 metadata 声明一致落库。
func TestFeedbackAndQueryLogTTLIndexes(t *testing.T) {
	cleanSearchCollections(t)
	_ = newFeedbackStore(t)
	ctx := context.Background()

	assertTTL := func(coll, indexName string, want int32) {
		t.Helper()
		cursor, err := mongoDB.Collection(coll).Indexes().List(ctx)
		if err != nil {
			t.Fatalf("list %s indexes: %v", coll, err)
		}
		var indexes []bson.M
		if err := cursor.All(ctx, &indexes); err != nil {
			t.Fatalf("decode indexes: %v", err)
		}
		for _, index := range indexes {
			if index["name"] == indexName {
				ttl, ok := index["expireAfterSeconds"]
				if !ok {
					t.Fatalf("%s.%s missing expireAfterSeconds", coll, indexName)
				}
				switch v := ttl.(type) {
				case int32:
					if v != want {
						t.Fatalf("%s.%s ttl=%d want=%d", coll, indexName, v, want)
					}
				case int64:
					if int32(v) != want {
						t.Fatalf("%s.%s ttl=%d want=%d", coll, indexName, v, want)
					}
				}
				return
			}
		}
		t.Fatalf("%s missing index %s", coll, indexName)
	}
	assertTTL("search_queries", "idx_search_queries_created", int32(feedbackstore.QueriesTTLSeconds))
	assertTTL("search_feedback_events", "idx_search_feedback_ttl", int32(feedbackstore.FeedbackTTLSeconds))
}

// TestQueryLogUpsertIdempotent 验证查询日志按 searchRequestId 幂等 upsert。
func TestQueryLogUpsertIdempotent(t *testing.T) {
	cleanSearchCollections(t)
	store := newFeedbackStore(t)
	ctx := context.Background()

	qlog := application.QueryLog{
		SearchRequestID: "req-log-1",
		Query:           "chengdu",
		Mode:            "result",
		ResultCount:     7,
	}
	if err := store.Log(ctx, qlog); err != nil {
		t.Fatalf("first log: %v", err)
	}
	qlog.ResultCount = 9
	if err := store.Log(ctx, qlog); err != nil {
		t.Fatalf("retry log: %v", err)
	}
	count, err := mongoDB.Collection("search_queries").CountDocuments(ctx, bson.M{
		"searchRequestId": "req-log-1",
	})
	if err != nil || count != 1 {
		t.Fatalf("query log must upsert once per request: count=%d err=%v", count, err)
	}
}

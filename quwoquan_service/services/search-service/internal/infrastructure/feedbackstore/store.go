// Package feedbackstore is the MongoDB persistence for search query logs and
// feedback events. It is the ONLY place the search-service touches a storage
// driver (DDD: infrastructure owns drivers; application/domain stay decoupled).
// Collections + TTL mirror contracts/metadata/search/query/storage.yaml; the
// TTLSeconds constants are pinned to that single source by a contract test.
package feedbackstore

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/search-service/internal/application"
)

const (
	// Collection names — single source: storage.yaml collections.
	queriesCollection  = "search_queries"
	feedbackCollection = "search_feedback_events"

	// TTL seconds — single source: storage.yaml ttl.seconds (90 天). Exported and
	// pinned by TestStorageTTLMatchesMetadata so the constant cannot drift.
	QueriesTTLSeconds  = 7776000
	FeedbackTTLSeconds = 7776000
)

// Store persists query logs + feedback events. It satisfies both application
// ports (QueryLogSink, FeedbackSink) from one Mongo-backed implementation.
type Store struct {
	queries  *mongo.Collection
	feedback *mongo.Collection
	logger   *slog.Logger
}

var (
	_ application.QueryLogSink = (*Store)(nil)
	_ application.FeedbackSink = (*Store)(nil)
)

// NewStore only binds collections. Production composition must call
// [Store.EnsureIndexes] and fail fast: feedback replay correctness depends on
// the unique semantic-key index and cannot degrade to duplicate facts.
func NewStore(db *mongo.Database, logger *slog.Logger) *Store {
	if logger == nil {
		logger = slog.Default()
	}
	return &Store{
		queries:  db.Collection(queriesCollection),
		feedback: db.Collection(feedbackCollection),
		logger:   logger,
	}
}

// EnsureIndexes installs all required lookup, TTL and semantic-key indexes.
func (s *Store) EnsureIndexes(ctx context.Context) error {
	queryIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "searchRequestId", Value: 1}},
			Options: options.Index().SetUnique(true).SetName("idx_search_queries_request"),
		},
		{
			Keys:    bson.D{{Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_search_queries_created").SetExpireAfterSeconds(int32(QueriesTTLSeconds)),
		},
		{
			Keys:    bson.D{{Key: "query", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_search_queries_query_created"),
		},
	}
	feedbackIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "searchRequestId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_search_feedback_request"),
		},
		{
			Keys:    bson.D{{Key: "viewerId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_search_feedback_viewer_created"),
		},
		{
			Keys:    bson.D{{Key: "objectId", Value: 1}, {Key: "eventType", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_search_feedback_object"),
		},
		{
			// 语义键 dedupe：同一次搜索请求对同一对象的同类反馈只追加一次
			// （fact typed append + dedupe key；重放安全，见 service.yaml）。
			Keys: bson.D{
				{Key: "searchRequestId", Value: 1},
				{Key: "eventType", Value: 1},
				{Key: "objectId", Value: 1},
			},
			Options: options.Index().SetUnique(true).SetName("uq_search_feedback_dedupe"),
		},
		{
			Keys:    bson.D{{Key: "createdAt", Value: 1}},
			Options: options.Index().SetName("idx_search_feedback_ttl").SetExpireAfterSeconds(int32(FeedbackTTLSeconds)),
		},
	}

	if _, err := s.queries.Indexes().CreateMany(ctx, queryIndexes); err != nil {
		return fmt.Errorf("ensure search query indexes: %w", err)
	}
	if _, err := s.feedback.Indexes().CreateMany(ctx, feedbackIndexes); err != nil {
		return fmt.Errorf("ensure search feedback indexes: %w", err)
	}
	return nil
}

// queryDoc is the persistent form of a SearchQuery log row (bson mirrors the
// metadata field names so storage stays contract-aligned).
type queryDoc struct {
	SearchRequestID  string    `bson:"searchRequestId"`
	Query            string    `bson:"query"`
	Mode             string    `bson:"mode,omitempty"`
	ViewerID         string    `bson:"viewerId,omitempty"`
	ObjectTypes      []string  `bson:"objectTypes,omitempty"`
	ResultCount      int       `bson:"resultCount"`
	RankingVersion   string    `bson:"rankingVersion,omitempty"`
	ExperimentBucket string    `bson:"experimentBucket,omitempty"`
	CreatedAt        time.Time `bson:"createdAt"`
}

// Log upserts the query log keyed by searchRequestId so retries are idempotent
// (the unique index forbids duplicates). createdAt is set on insert only.
func (s *Store) Log(ctx context.Context, q application.QueryLog) error {
	now := time.Now().UTC()
	doc := bson.M{
		"searchRequestId":  q.SearchRequestID,
		"query":            q.Query,
		"mode":             q.Mode,
		"viewerId":         q.ViewerID,
		"objectTypes":      q.ObjectTypes,
		"resultCount":      q.ResultCount,
		"rankingVersion":   q.RankingVersion,
		"experimentBucket": q.ExperimentBucket,
	}
	_, err := s.queries.UpdateOne(ctx,
		bson.M{"searchRequestId": q.SearchRequestID},
		bson.M{"$set": doc, "$setOnInsert": bson.M{"createdAt": now}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

// feedbackDoc is the persistent form of a SearchFeedbackEvent row.
type feedbackDoc struct {
	SearchRequestID string    `bson:"searchRequestId"`
	ViewerID        string    `bson:"viewerId,omitempty"`
	EventType       string    `bson:"eventType"`
	ObjectID        string    `bson:"objectId,omitempty"`
	Target          string    `bson:"target,omitempty"`
	RankPosition    int       `bson:"rankPosition,omitempty"`
	ReferralSource  string    `bson:"referralSource,omitempty"`
	FeedRequestID   string    `bson:"feedRequestId,omitempty"`
	DwellMs         int       `bson:"dwellMs,omitempty"`
	CreatedAt       time.Time `bson:"createdAt"`
}

// Record appends a feedback event. The (searchRequestId, eventType, objectId)
// semantic key is unique: a duplicate append (client retry / double tap) is a
// replay-safe no-op — the fact is already recorded, so the duplicate-key error
// is swallowed and the caller sees the same accepted outcome.
func (s *Store) Record(ctx context.Context, ev application.FeedbackEvent) error {
	doc := feedbackDoc{
		SearchRequestID: ev.SearchRequestID,
		ViewerID:        ev.ViewerID,
		EventType:       ev.EventType,
		ObjectID:        ev.ObjectID,
		Target:          ev.Target,
		RankPosition:    ev.RankPosition,
		ReferralSource:  ev.ReferralSource,
		FeedRequestID:   ev.FeedRequestID,
		DwellMs:         ev.DwellMs,
		CreatedAt:       time.Now().UTC(),
	}
	_, err := s.feedback.InsertOne(ctx, doc)
	if mongo.IsDuplicateKeyError(err) {
		return nil
	}
	return err
}

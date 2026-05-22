package persistence

import (
	"context"
	"log/slog"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	behaviorEventsCollection = "rm_behavior_events"
	behaviorEventTTLDays     = 30
)

// BehaviorEventStore persists raw user behavior events for offline analytics.
type BehaviorEventStore interface {
	InsertBatch(ctx context.Context, events []RawBehaviorEvent) error
}

// RawBehaviorEvent is the persistent form of a user behavior event.
type RawBehaviorEvent struct {
	UserID          string   `bson:"userId"`
	SessionID       string   `bson:"sessionId"`
	ContentID       string   `bson:"contentId"`
	Action          string   `bson:"action"`
	Tags            []string `bson:"tags,omitempty"`
	Duration        float64  `bson:"duration,omitempty"`
	AuthorID        string   `bson:"authorId,omitempty"`
	ReferralSource  string   `bson:"referralSource,omitempty"`
	EngagementDepth int      `bson:"engagementDepth,omitempty"`
	ConsumedRatio   float64  `bson:"consumedRatio,omitempty"`
	TotalUnits      int      `bson:"totalUnits,omitempty"`
	EntityRefs      []string `bson:"entityRefs,omitempty"`
	FeedRequestID   string   `bson:"feedRequestId,omitempty"`
	OccurredAt      string   `bson:"occurredAt"`
	CreatedAt       time.Time `bson:"createdAt"`
}

// MongoBehaviorEventStore persists raw behavior events to MongoDB with TTL.
type MongoBehaviorEventStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

// NewMongoBehaviorEventStore creates a store and ensures TTL + analytics indexes.
func NewMongoBehaviorEventStore(db *mongo.Database, logger *slog.Logger) *MongoBehaviorEventStore {
	s := &MongoBehaviorEventStore{
		coll:   db.Collection(behaviorEventsCollection),
		logger: logger,
	}
	s.ensureIndexes()
	return s
}

func (s *MongoBehaviorEventStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	ttl := int32(behaviorEventTTLDays * 24 * 60 * 60)

	indexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "createdAt", Value: 1}},
			Options: options.Index().SetExpireAfterSeconds(ttl),
		},
		{
			Keys: bson.D{{Key: "userId", Value: 1}, {Key: "action", Value: 1}, {Key: "createdAt", Value: -1}},
		},
		{
			Keys: bson.D{{Key: "contentId", Value: 1}, {Key: "createdAt", Value: -1}},
		},
	}

	for _, idx := range indexes {
		if _, err := s.coll.Indexes().CreateOne(ctx, idx); err != nil {
			s.logger.Warn("behavior_event_store: index creation failed", slog.String("error", err.Error()))
		}
	}
}

func (s *MongoBehaviorEventStore) InsertBatch(ctx context.Context, events []RawBehaviorEvent) error {
	if len(events) == 0 {
		return nil
	}

	docs := make([]interface{}, len(events))
	for i := range events {
		docs[i] = events[i]
	}

	_, err := s.coll.InsertMany(ctx, docs)
	if err != nil {
		s.logger.Error("behavior_event_store: insert failed",
			slog.String("error", err.Error()),
			slog.Int("count", len(events)),
		)
	}
	return err
}

// NoopBehaviorEventStore discards events (used when MongoDB is not available).
type NoopBehaviorEventStore struct{}

func (NoopBehaviorEventStore) InsertBatch(_ context.Context, _ []RawBehaviorEvent) error {
	return nil
}

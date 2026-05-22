package runtimelearning

import (
	"context"
	"log/slog"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	learningEventsCollection    = "rec_learning_events"
	learningScorecardCollection = "rec_learning_scorecards"
	defaultTTLDays              = 30
)

// MongoSink persists learning events and scorecards to MongoDB with TTL indexes.
type MongoSink struct {
	events     *mongo.Collection
	scorecards *mongo.Collection
	logger     *slog.Logger
}

// NewMongoSink creates a MongoSink and ensures TTL indexes exist.
func NewMongoSink(db *mongo.Database, logger *slog.Logger) *MongoSink {
	s := &MongoSink{
		events:     db.Collection(learningEventsCollection),
		scorecards: db.Collection(learningScorecardCollection),
		logger:     logger,
	}
	s.ensureIndexes()
	return s
}

func (s *MongoSink) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	ttl := int32(defaultTTLDays * 24 * 60 * 60)

	eventIdx := mongo.IndexModel{
		Keys:    bson.D{{Key: "createdAt", Value: 1}},
		Options: options.Index().SetExpireAfterSeconds(ttl),
	}
	if _, err := s.events.Indexes().CreateOne(ctx, eventIdx); err != nil {
		s.logger.Warn("learning: events TTL index creation failed", slog.String("error", err.Error()))
	}

	scorecardIdx := mongo.IndexModel{
		Keys:    bson.D{{Key: "createdAt", Value: 1}},
		Options: options.Index().SetExpireAfterSeconds(ttl),
	}
	if _, err := s.scorecards.Indexes().CreateOne(ctx, scorecardIdx); err != nil {
		s.logger.Warn("learning: scorecards TTL index creation failed", slog.String("error", err.Error()))
	}

	userIdx := mongo.IndexModel{
		Keys: bson.D{{Key: "userId", Value: 1}, {Key: "eventType", Value: 1}},
	}
	if _, err := s.events.Indexes().CreateOne(ctx, userIdx); err != nil {
		s.logger.Warn("learning: user+eventType index creation failed", slog.String("error", err.Error()))
	}

	scenarioIdx := mongo.IndexModel{
		Keys: bson.D{{Key: "scenario", Value: 1}, {Key: "createdAt", Value: -1}},
	}
	if _, err := s.events.Indexes().CreateOne(ctx, scenarioIdx); err != nil {
		s.logger.Warn("learning: scenario+createdAt index creation failed", slog.String("error", err.Error()))
	}
}

func (s *MongoSink) FlushEvents(ctx context.Context, events []Event) error {
	if len(events) == 0 {
		return nil
	}

	now := time.Now()
	docs := make([]interface{}, len(events))
	for i, e := range events {
		docs[i] = bson.M{
			"eventId":     e.EventID,
			"eventType":   e.EventType,
			"scenario":    e.Scenario,
			"occurredAt":  e.OccurredAt,
			"userId":      e.UserID,
			"personaId":   e.PersonaID,
			"pageId":      e.PageID,
			"traceId":     e.TraceID,
			"causationId": e.CausationID,
			"targetId":    e.TargetID,
			"labels":      e.Labels,
			"context":     e.Context,
			"createdAt":   now,
		}
	}

	_, err := s.events.InsertMany(ctx, docs)
	if err != nil {
		s.logger.Error("learning: flush events to mongo failed",
			slog.String("error", err.Error()),
			slog.Int("count", len(events)),
		)
		return err
	}
	return nil
}

func (s *MongoSink) FlushScorecards(ctx context.Context, scorecards []Scorecard) error {
	if len(scorecards) == 0 {
		return nil
	}

	now := time.Now()
	docs := make([]interface{}, len(scorecards))
	for i, sc := range scorecards {
		docs[i] = bson.M{
			"scorecardId": sc.ScorecardID,
			"runId":       sc.RunID,
			"score":       sc.Score,
			"comment":     sc.Comment,
			"version":     sc.Version,
			"createdAt":   now,
		}
	}

	_, err := s.scorecards.InsertMany(ctx, docs)
	if err != nil {
		s.logger.Error("learning: flush scorecards to mongo failed",
			slog.String("error", err.Error()),
			slog.Int("count", len(scorecards)),
		)
		return err
	}
	return nil
}

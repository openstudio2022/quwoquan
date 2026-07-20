package learning

import (
	"context"
	"errors"
	"log/slog"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	runtimelearning "quwoquan_service/runtime/learning"
)

const (
	eventsCollection    = "rec_learning_events"
	scorecardCollection = "rec_learning_scorecards"
	defaultTTLDays      = 30
)

type MongoSink struct {
	events     *mongo.Collection
	scorecards *mongo.Collection
	logger     *slog.Logger
}

func NewMongoSink(db *mongo.Database, logger *slog.Logger) *MongoSink {
	sink := &MongoSink{
		events:     db.Collection(eventsCollection),
		scorecards: db.Collection(scorecardCollection),
		logger:     logger,
	}
	sink.ensureIndexes()
	return sink
}

func (s *MongoSink) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	ttlSeconds := int32(defaultTTLDays * 24 * 60 * 60)
	indexes := []struct {
		collection *mongo.Collection
		model      mongo.IndexModel
		name       string
	}{
		{
			collection: s.events,
			model: mongo.IndexModel{
				Keys:    bson.D{{Key: "createdAt", Value: 1}},
				Options: options.Index().SetExpireAfterSeconds(ttlSeconds),
			},
			name: "events_ttl",
		},
		{
			collection: s.scorecards,
			model: mongo.IndexModel{
				Keys:    bson.D{{Key: "createdAt", Value: 1}},
				Options: options.Index().SetExpireAfterSeconds(ttlSeconds),
			},
			name: "scorecards_ttl",
		},
		{
			collection: s.events,
			model: mongo.IndexModel{
				Keys: bson.D{{Key: "userId", Value: 1}, {Key: "eventType", Value: 1}},
			},
			name: "events_user_type",
		},
		{
			collection: s.events,
			model: mongo.IndexModel{
				Keys: bson.D{{Key: "scenario", Value: 1}, {Key: "createdAt", Value: -1}},
			},
			name: "events_scenario_time",
		},
	}
	for _, index := range indexes {
		if _, err := index.collection.Indexes().CreateOne(ctx, index.model); err != nil {
			s.logger.Warn(
				"learning index creation failed",
				slog.String("index", index.name),
				slog.String("error", err.Error()),
			)
		}
	}
}

func (s *MongoSink) FlushEvents(
	ctx context.Context,
	events []runtimelearning.Event,
) error {
	if len(events) == 0 {
		return nil
	}
	now := time.Now().UTC()
	documents := make([]interface{}, len(events))
	for index, event := range events {
		documents[index] = bson.M{
			// 确定性 eventId 作为 _id 承载 dedupe（rec_model/storage.yaml）：
			// 重放写入被唯一约束拒绝后按已存在处理，事实不重复。
			"_id":     event.EventID,
			"eventId": event.EventID, "eventType": event.EventType,
			"scenario": event.Scenario, "occurredAt": event.OccurredAt,
			"userId": event.UserID, "personaId": event.PersonaID,
			"pageId": event.PageID, "traceId": event.TraceID,
			"causationId": event.CausationID, "targetId": event.TargetID,
			"labels": event.Labels, "context": event.Context, "createdAt": now,
		}
	}
	_, err := s.events.InsertMany(ctx, documents, options.InsertMany().SetOrdered(false))
	if err != nil && !allDuplicateKeyErrors(err) {
		s.logger.Error(
			"learning events flush failed",
			slog.String("error", err.Error()),
			slog.Int("count", len(events)),
		)
		return err
	}
	return nil
}

// allDuplicateKeyErrors 判断批量写失败是否全部由 _id dedupe 拒绝构成
// （重放收敛路径，不是故障）。
func allDuplicateKeyErrors(err error) bool {
	var bulkErr mongo.BulkWriteException
	if !errors.As(err, &bulkErr) {
		return false
	}
	if bulkErr.WriteConcernError != nil || len(bulkErr.WriteErrors) == 0 {
		return false
	}
	for _, writeError := range bulkErr.WriteErrors {
		if !mongo.IsDuplicateKeyError(writeError.WriteError) {
			return false
		}
	}
	return true
}

func (s *MongoSink) FlushScorecards(
	ctx context.Context,
	scorecards []runtimelearning.Scorecard,
) error {
	if len(scorecards) == 0 {
		return nil
	}
	now := time.Now().UTC()
	documents := make([]interface{}, len(scorecards))
	for index, scorecard := range scorecards {
		documents[index] = bson.M{
			"scorecardId": scorecard.ScorecardID,
			"runId":       scorecard.RunID,
			"score":       scorecard.Score,
			"comment":     scorecard.Comment,
			"version":     scorecard.Version,
			"createdAt":   now,
		}
	}
	_, err := s.scorecards.InsertMany(ctx, documents)
	if err != nil {
		s.logger.Error(
			"learning scorecards flush failed",
			slog.String("error", err.Error()),
			slog.Int("count", len(scorecards)),
		)
	}
	return err
}

var _ runtimelearning.Sink = (*MongoSink)(nil)

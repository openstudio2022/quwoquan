package persistence

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type MongoEventStore struct {
	interactionEvents *mongo.Collection
	scorecards        *mongo.Collection
}

func NewMongoEventStore(db *mongo.Database) *MongoEventStore {
	return &MongoEventStore{
		interactionEvents: db.Collection("interaction_events"),
		scorecards:        db.Collection("scorecards"),
	}
}

func (s *MongoEventStore) EnsureIndexes(ctx context.Context) error {
	interactionIndexes := []mongo.IndexModel{
		{Keys: bson.D{{Key: "runId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_ie_run")},
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "eventType", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_ie_user_type")},
		{Keys: bson.D{{Key: "feedbackType", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_ie_feedback").SetSparse(true)},
		{Keys: bson.D{{Key: "traceId", Value: 1}}, Options: options.Index().SetName("idx_ie_trace").SetSparse(true)},
	}
	if _, err := s.interactionEvents.Indexes().CreateMany(ctx, interactionIndexes); err != nil {
		return fmt.Errorf("create interaction indexes: %w", err)
	}
	scoreIndexes := []mongo.IndexModel{
		{Keys: bson.D{{Key: "runId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_score_run")},
		{Keys: bson.D{{Key: "eventId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_score_event")},
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "metricId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_score_user_metric")},
	}
	_, err := s.scorecards.Indexes().CreateMany(ctx, scoreIndexes)
	return err
}

func (s *MongoEventStore) InsertInteractionEvent(ctx context.Context, event assistant.InteractionEvent) error {
	_, err := s.interactionEvents.InsertOne(ctx, event)
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			return nil
		}
		return rterr.NewUnavailable(rterr.ModuleAssistant, "交互事件暂时不可写入", err.Error())
	}
	return nil
}

func (s *MongoEventStore) InsertScorecard(ctx context.Context, score assistant.Scorecard) error {
	_, err := s.scorecards.InsertOne(ctx, score)
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			return nil
		}
		return rterr.NewUnavailable(rterr.ModuleAssistant, "评分卡暂时不可写入", err.Error())
	}
	return nil
}

func (s *MongoEventStore) ListLatestInteractionEvents(ctx context.Context, userID string, limit int) ([]assistant.InteractionEvent, error) {
	if limit <= 0 {
		limit = 20
	}
	cur, err := s.interactionEvents.Find(ctx, bson.M{"userId": userID}, options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleAssistant, "读取交互事件失败", err.Error())
	}
	defer cur.Close(ctx)
	items := []assistant.InteractionEvent{}
	if err := cur.All(ctx, &items); err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleAssistant, "解析交互事件失败", err.Error())
	}
	return items, nil
}

func (s *MongoEventStore) ListLatestScorecards(ctx context.Context, userID string, limit int) ([]assistant.Scorecard, error) {
	if limit <= 0 {
		limit = 20
	}
	cur, err := s.scorecards.Find(ctx, bson.M{"userId": userID}, options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleAssistant, "读取评分卡失败", err.Error())
	}
	defer cur.Close(ctx)
	items := []assistant.Scorecard{}
	if err := cur.All(ctx, &items); err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleAssistant, "解析评分卡失败", err.Error())
	}
	return items, nil
}

type MemoryEventStore struct {
	interactionEvents map[string]assistant.InteractionEvent
	scorecards        map[string]assistant.Scorecard
	order             []string
	scoreOrder        []string
}

func NewMemoryEventStore() *MemoryEventStore {
	return &MemoryEventStore{interactionEvents: map[string]assistant.InteractionEvent{}, scorecards: map[string]assistant.Scorecard{}, order: []string{}, scoreOrder: []string{}}
}

func (s *MemoryEventStore) InsertInteractionEvent(_ context.Context, event assistant.InteractionEvent) error {
	if _, ok := s.interactionEvents[event.EventID]; !ok {
		s.order = append(s.order, event.EventID)
	}
	s.interactionEvents[event.EventID] = event
	return nil
}

func (s *MemoryEventStore) InsertScorecard(_ context.Context, score assistant.Scorecard) error {
	if _, ok := s.scorecards[score.ScoreID]; !ok {
		s.scoreOrder = append(s.scoreOrder, score.ScoreID)
	}
	s.scorecards[score.ScoreID] = score
	return nil
}

func (s *MemoryEventStore) ListLatestInteractionEvents(_ context.Context, userID string, limit int) ([]assistant.InteractionEvent, error) {
	if limit <= 0 {
		limit = 20
	}
	items := make([]assistant.InteractionEvent, 0, limit)
	for i := len(s.order) - 1; i >= 0 && len(items) < limit; i-- {
		item := s.interactionEvents[s.order[i]]
		if item.UserID == userID {
			items = append(items, item)
		}
	}
	return items, nil
}

func (s *MemoryEventStore) ListLatestScorecards(_ context.Context, userID string, limit int) ([]assistant.Scorecard, error) {
	if limit <= 0 {
		limit = 20
	}
	items := make([]assistant.Scorecard, 0, limit)
	for i := len(s.scoreOrder) - 1; i >= 0 && len(items) < limit; i-- {
		item := s.scorecards[s.scoreOrder[i]]
		if item.UserID == userID {
			items = append(items, item)
		}
	}
	return items, nil
}

func (s *MemoryEventStore) EnsureIndexes(_ context.Context) error { return nil }

var _ = time.Now

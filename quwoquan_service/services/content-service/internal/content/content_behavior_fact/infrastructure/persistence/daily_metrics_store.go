package persistence

import (
	"context"
	"log/slog"
	"time"

	behaviorports "quwoquan_service/services/content-service/internal/content/content_behavior_fact/domain/ports"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	dailyMetricsCollection = "rm_daily_metrics"
	dailyMetricsTTLDays    = 90
)

type DailyMetricsStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewDailyMetricsStore(db *mongo.Database, logger *slog.Logger) *DailyMetricsStore {
	store := &DailyMetricsStore{
		coll:   db.Collection(dailyMetricsCollection),
		logger: logger,
	}
	store.ensureIndexes()
	return store
}

func (s *DailyMetricsStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	ttl := int32(dailyMetricsTTLDays * 24 * 60 * 60)
	indexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "createdAt", Value: 1}},
			Options: options.Index().SetExpireAfterSeconds(ttl),
		},
		{
			Keys: bson.D{
				{Key: "date", Value: 1},
				{Key: "dimension", Value: 1},
				{Key: "dimensionKey", Value: 1},
			},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "dimension", Value: 1}, {Key: "date", Value: -1}},
		},
	}

	for _, index := range indexes {
		if _, err := s.coll.Indexes().CreateOne(ctx, index); err != nil {
			s.logger.Warn(
				"daily_metrics: index creation failed",
				slog.String("error", err.Error()),
			)
		}
	}
}

func (s *DailyMetricsStore) IncrementMetric(
	ctx context.Context,
	date string,
	dimension string,
	dimensionKey string,
	action string,
	dwellMs int64,
	depth int,
) error {
	_ = depth
	filter := bson.M{
		"date":         date,
		"dimension":    dimension,
		"dimensionKey": dimensionKey,
	}
	incFields := bson.M{}
	switch action {
	case "impression":
		incFields["impressions"] = int64(1)
	case "click":
		incFields["clicks"] = int64(1)
	case "dwell":
		incFields["dwells"] = int64(1)
		incFields["totalDwellMs"] = dwellMs
	case "like":
		incFields["likes"] = int64(1)
	case "share":
		incFields["shares"] = int64(1)
	case "comment":
		incFields["comments"] = int64(1)
	case "dislike":
		incFields["dislikes"] = int64(1)
	case "report":
		incFields["reports"] = int64(1)
	case "follow":
		incFields["followConversions"] = int64(1)
	case "join_circle":
		incFields["joinCircleConversions"] = int64(1)
	case "add_contact":
		incFields["addContactConversions"] = int64(1)
	}

	update := bson.M{"$setOnInsert": bson.M{"createdAt": time.Now()}}
	if len(incFields) > 0 {
		update["$inc"] = incFields
	}
	_, err := s.coll.UpdateOne(
		ctx,
		filter,
		update,
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		s.logger.Error(
			"daily_metrics: increment failed",
			slog.String("error", err.Error()),
			slog.String("date", date),
			slog.String("dimension", dimension),
		)
	}
	return err
}

var _ behaviorports.DailyMetricsStore = (*DailyMetricsStore)(nil)

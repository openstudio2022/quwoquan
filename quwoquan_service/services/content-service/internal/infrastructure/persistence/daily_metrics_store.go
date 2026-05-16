package persistence

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	dailyMetricsCollection = "rm_daily_metrics"
	dailyMetricsTTLDays    = 90
)

// DailyMetric is a pre-aggregated daily metric row.
type DailyMetric struct {
	Date          string  `bson:"date"`
	Dimension     string  `bson:"dimension"`
	DimensionKey  string  `bson:"dimensionKey"`
	Impressions   int64   `bson:"impressions"`
	Clicks        int64   `bson:"clicks"`
	Dwells        int64   `bson:"dwells"`
	Likes         int64   `bson:"likes"`
	Shares        int64   `bson:"shares"`
	Comments      int64   `bson:"comments"`
	TotalDwellMs  int64   `bson:"totalDwellMs"`
	AvgDepth      float64 `bson:"avgDepth"`
	UniqueUsers   int64   `bson:"uniqueUsers"`
	CreatedAt     time.Time `bson:"createdAt"`
}

// DailyMetricsStore manages pre-aggregated daily metrics.
type DailyMetricsStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

// NewDailyMetricsStore creates a store with TTL and compound indexes.
func NewDailyMetricsStore(db *mongo.Database, logger *slog.Logger) *DailyMetricsStore {
	s := &DailyMetricsStore{
		coll:   db.Collection(dailyMetricsCollection),
		logger: logger,
	}
	s.ensureIndexes()
	return s
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
			Keys:    bson.D{{Key: "date", Value: 1}, {Key: "dimension", Value: 1}, {Key: "dimensionKey", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "dimension", Value: 1}, {Key: "date", Value: -1}},
		},
	}

	for _, idx := range indexes {
		if _, err := s.coll.Indexes().CreateOne(ctx, idx); err != nil {
			s.logger.Warn("daily_metrics: index creation failed", slog.String("error", err.Error()))
		}
	}
}

// IncrementMetric atomically increments a daily metric using upsert.
func (s *DailyMetricsStore) IncrementMetric(ctx context.Context, date, dimension, dimensionKey, action string, dwellMs int64, depth int) error {
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
	}

	update := bson.M{
		"$inc":         incFields,
		"$setOnInsert": bson.M{"createdAt": time.Now()},
	}

	opts := options.UpdateOne().SetUpsert(true)
	_, err := s.coll.UpdateOne(ctx, filter, update, opts)
	if err != nil {
		s.logger.Error("daily_metrics: increment failed",
			slog.String("error", err.Error()),
			slog.String("date", date),
			slog.String("dimension", dimension),
		)
	}
	return err
}

// RunAggregation runs a MongoDB aggregation pipeline on raw behavior events
// and populates daily metrics for the given date.
func (s *DailyMetricsStore) RunAggregation(ctx context.Context, behaviorColl *mongo.Collection, date string) error {
	startOfDay, err := time.Parse("2006-01-02", date)
	if err != nil {
		return fmt.Errorf("invalid date %s: %w", date, err)
	}
	endOfDay := startOfDay.Add(24 * time.Hour)

	dimensions := []struct {
		name     string
		groupKey string
	}{
		{"content", "$contentId"},
		{"action", "$action"},
		{"author", "$authorId"},
		{"referral", "$referralSource"},
	}

	for _, dim := range dimensions {
		pipeline := mongo.Pipeline{
			{{Key: "$match", Value: bson.M{
				"createdAt": bson.M{"$gte": startOfDay, "$lt": endOfDay},
			}}},
			{{Key: "$group", Value: bson.M{
				"_id":          dim.groupKey,
				"impressions":  bson.M{"$sum": bson.M{"$cond": bson.A{bson.M{"$eq": bson.A{"$action", "impression"}}, 1, 0}}},
				"clicks":       bson.M{"$sum": bson.M{"$cond": bson.A{bson.M{"$eq": bson.A{"$action", "click"}}, 1, 0}}},
				"dwells":       bson.M{"$sum": bson.M{"$cond": bson.A{bson.M{"$eq": bson.A{"$action", "dwell"}}, 1, 0}}},
				"likes":        bson.M{"$sum": bson.M{"$cond": bson.A{bson.M{"$eq": bson.A{"$action", "like"}}, 1, 0}}},
				"shares":       bson.M{"$sum": bson.M{"$cond": bson.A{bson.M{"$eq": bson.A{"$action", "share"}}, 1, 0}}},
				"comments":     bson.M{"$sum": bson.M{"$cond": bson.A{bson.M{"$eq": bson.A{"$action", "comment"}}, 1, 0}}},
				"totalDwellMs": bson.M{"$sum": bson.M{"$multiply": bson.A{"$duration", 1000}}},
				"avgDepth":     bson.M{"$avg": "$engagementDepth"},
				"uniqueUsers":  bson.M{"$addToSet": "$userId"},
			}}},
		}

		cursor, curErr := behaviorColl.Aggregate(ctx, pipeline)
		if curErr != nil {
			s.logger.Error("daily_metrics: aggregation failed",
				slog.String("error", curErr.Error()),
				slog.String("dimension", dim.name),
			)
			continue
		}

		var results []bson.M
		if decodeErr := cursor.All(ctx, &results); decodeErr != nil {
			s.logger.Error("daily_metrics: cursor decode failed", slog.String("error", decodeErr.Error()))
			continue
		}

		now := time.Now()
		for _, r := range results {
			dimKey := ""
			if v, ok := r["_id"]; ok && v != nil {
				dimKey = fmt.Sprintf("%v", v)
			}
			if dimKey == "" {
				continue
			}

			uniqueUsers := int64(0)
			if arr, ok := r["uniqueUsers"].(bson.A); ok {
				uniqueUsers = int64(len(arr))
			}

			metric := DailyMetric{
				Date:         date,
				Dimension:    dim.name,
				DimensionKey: dimKey,
				Impressions:  toInt64(r["impressions"]),
				Clicks:       toInt64(r["clicks"]),
				Dwells:       toInt64(r["dwells"]),
				Likes:        toInt64(r["likes"]),
				Shares:       toInt64(r["shares"]),
				Comments:     toInt64(r["comments"]),
				TotalDwellMs: toInt64(r["totalDwellMs"]),
				AvgDepth:     toFloat64(r["avgDepth"]),
				UniqueUsers:  uniqueUsers,
				CreatedAt:    now,
			}

			filter := bson.M{
				"date":         date,
				"dimension":    dim.name,
				"dimensionKey": dimKey,
			}
			update := bson.M{"$set": metric}
			opts := options.UpdateOne().SetUpsert(true)
			_, _ = s.coll.UpdateOne(ctx, filter, update, opts)
		}
	}

	return nil
}

func toInt64(v any) int64 {
	switch n := v.(type) {
	case int32:
		return int64(n)
	case int64:
		return n
	case float64:
		return int64(n)
	default:
		return 0
	}
}

func toFloat64(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case int32:
		return float64(n)
	case int64:
		return float64(n)
	default:
		return 0
	}
}

package persistence

import (
	"context"
	"log/slog"
	"time"

	"quwoquan_service/services/content-service/internal/content/post/application/ports"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	dailyMetricsCollection = "rm_daily_metrics"
	dailyMetricsTTLDays    = 90
)

// Daily-metric aggregation dimensions are the single source of truth for
// rm_daily_metrics. Per the analytics-metric-dictionary spec the only write path
// is the hot path (BehaviorService.ProcessBatch), so there is exactly one
// dimension set and it cannot drift. The earlier batch RunAggregation path that
// carried a divergent "referral" dimension was removed: it was never scheduled
// and violated the spec's single-source rule.
const (
	DailyMetricDimensionAction       = ports.DailyMetricDimensionAction
	DailyMetricDimensionContent      = ports.DailyMetricDimensionContent
	DailyMetricDimensionAuthor       = ports.DailyMetricDimensionAuthor
	DailyMetricDimensionIntersection = ports.DailyMetricDimensionIntersection
)

// DailyMetricDimensions is the ordered, exhaustive dimension set; consumers and
// the consistency gate enumerate it instead of hardcoding dimension strings.
var DailyMetricDimensions = ports.DailyMetricDimensions

// DailyMetric is a pre-aggregated daily metric row.
type DailyMetric = ports.DailyMetric

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

// IncrementMetric atomically increments a daily metric using upsert. The action
// -> counter mapping is aligned with the analytics-metric-dictionary behavior
// domain (impression/click/dwell/like/share/comment/dislike/report)
// plus the intersection conversion actions (follow/join_circle/add_contact);
// dimension must be one of DailyMetricDimensions. Actions outside the counted
// set still upsert the dimension row (createdAt) but increment nothing, avoiding
// an empty $inc.
func (s *DailyMetricsStore) IncrementMetric(ctx context.Context, date, dimension, dimensionKey, action string, dwellMs int64, depth int) error {
	_ = depth // reserved for future depth-bucketed metrics; kept for caller stability

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

	update := bson.M{
		"$setOnInsert": bson.M{"createdAt": time.Now()},
	}
	if len(incFields) > 0 {
		update["$inc"] = incFields
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

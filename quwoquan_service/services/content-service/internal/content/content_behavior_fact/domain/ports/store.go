package ports

import (
	"context"
	"time"

	behaviormodel "quwoquan_service/services/content-service/internal/content/content_behavior_fact/domain/model"
)

type FactStore interface {
	InsertBatch(context.Context, []behaviormodel.Fact) error
	ListUserFootprint(context.Context, string, []string, time.Time, int) ([]behaviormodel.Fact, error)
}

const (
	DailyMetricDimensionAction       = "action"
	DailyMetricDimensionContent      = "content"
	DailyMetricDimensionAuthor       = "author"
	DailyMetricDimensionIntersection = "intersection"
)

var DailyMetricDimensions = []string{
	DailyMetricDimensionAction,
	DailyMetricDimensionContent,
	DailyMetricDimensionAuthor,
	DailyMetricDimensionIntersection,
}

type DailyMetricsStore interface {
	IncrementMetric(
		ctx context.Context,
		date string,
		dimension string,
		dimensionKey string,
		action string,
		dwellMs int64,
		depth int,
	) error
}

type DailyMetric struct {
	Date                  string    `bson:"date"`
	Dimension             string    `bson:"dimension"`
	DimensionKey          string    `bson:"dimensionKey"`
	Impressions           int64     `bson:"impressions"`
	Clicks                int64     `bson:"clicks"`
	Dwells                int64     `bson:"dwells"`
	Likes                 int64     `bson:"likes"`
	Shares                int64     `bson:"shares"`
	Comments              int64     `bson:"comments"`
	Dislikes              int64     `bson:"dislikes"`
	Reports               int64     `bson:"reports"`
	FollowConversions     int64     `bson:"followConversions"`
	JoinCircleConversions int64     `bson:"joinCircleConversions"`
	AddContactConversions int64     `bson:"addContactConversions"`
	TotalDwellMs          int64     `bson:"totalDwellMs"`
	AvgDepth              float64   `bson:"avgDepth"`
	UniqueUsers           int64     `bson:"uniqueUsers"`
	CreatedAt             time.Time `bson:"createdAt"`
}

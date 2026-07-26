package persistence

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
)

// MongoCircleStore 是 Circle 聚合的具名读端口实现；写路径唯一入口是
// circle_management/circle/infrastructure/persistence.MongoAggregateStore。
type MongoCircleStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

var _ application.CircleRecordStore = (*MongoCircleStore)(nil)

func NewMongoCircleStore(coll *mongo.Collection) *MongoCircleStore {
	return &MongoCircleStore{coll: coll, logger: slog.Default()}
}

func (s *MongoCircleStore) FindByID(ctx context.Context, id string) (*model.Circle, bool) {
	circle, found, err := s.LoadForSearch(ctx, id)
	if err != nil {
		s.logger.Error(
			"circle FindByID storage failure",
			"circleId",
			id,
			"error",
			err,
		)
		return nil, false
	}
	return circle, found
}

// LoadForSearch preserves storage failures for durable search projection.
func (s *MongoCircleStore) LoadForSearch(
	ctx context.Context,
	id string,
) (*model.Circle, bool, error) {
	var c model.Circle
	err := s.coll.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(id)},
	).Decode(&c)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("load Circle %s: %w", id, err)
	}
	return &c, true, nil
}

// ListForSearch scans every Circle by stable _id keyset, including archived and
// private records so reconcile can actively delete stale search documents.
func (s *MongoCircleStore) ListForSearch(
	ctx context.Context,
	afterID string,
	limit int,
) ([]model.Circle, error) {
	if limit <= 0 {
		limit = 500
	}
	filter := bson.M{}
	if afterID = strings.TrimSpace(afterID); afterID != "" {
		filter["_id"] = bson.M{"$gt": afterID}
	}
	cursor, err := s.coll.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "_id", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("list Circles for search: %w", err)
	}
	defer cursor.Close(ctx)
	var circles []model.Circle
	if err := cursor.All(ctx, &circles); err != nil {
		return nil, fmt.Errorf("decode Circles for search: %w", err)
	}
	return circles, nil
}

func (s *MongoCircleStore) List(ctx context.Context, opts application.ListCirclesQuery) ([]model.Circle, string) {
	if opts.Limit <= 0 {
		opts.Limit = 20
	}

	filter := bson.M{"status": string(model.CircleStatusActive)}
	if opts.Category != "" {
		filter["category"] = opts.Category
	}
	if opts.DomainID != "" {
		filter["domainId"] = opts.DomainID
	}

	if opts.Cursor != "" {
		var cursorDoc model.Circle
		if err := s.coll.FindOne(ctx, bson.M{"_id": opts.Cursor}).Decode(&cursorDoc); err == nil {
			filter["createdAt"] = bson.M{"$lt": cursorDoc.CreatedAt}
		}
	}

	sortField := bson.D{{Key: "memberCount", Value: -1}, {Key: "createdAt", Value: -1}}
	if opts.Sort == "latest" {
		sortField = bson.D{{Key: "createdAt", Value: -1}}
	} else if opts.Sort == "active" {
		sortField = bson.D{{Key: "weeklyActiveCount", Value: -1}}
	}

	findOpts := options.Find().SetSort(sortField).SetLimit(int64(opts.Limit))
	cur, err := s.coll.Find(ctx, filter, findOpts)
	if err != nil {
		s.logger.Error("circle List storage failure", "error", err)
		return nil, ""
	}
	defer cur.Close(ctx)

	var circles []model.Circle
	if err := cur.All(ctx, &circles); err != nil {
		s.logger.Error("circle List decode failure", "error", err)
		return nil, ""
	}

	var nextCursor string
	if len(circles) == opts.Limit {
		nextCursor = circles[len(circles)-1].ID
	}
	return circles, nextCursor
}

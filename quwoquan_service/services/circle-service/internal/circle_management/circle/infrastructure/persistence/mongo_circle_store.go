package persistence

import (
	"context"
	"errors"
	"log/slog"

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
	var c model.Circle
	err := s.coll.FindOne(ctx, bson.M{"_id": id}).Decode(&c)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false
	}
	if err != nil {
		// 读端口签名保持 (value, bool)；存储故障与 not-found 在日志层面区分，
		// 避免把基础设施错误静默成业务空态却无观测痕迹。
		s.logger.Error("circle FindByID storage failure", "circleId", id, "error", err)
		return nil, false
	}
	return &c, true
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

package persistence

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

// MongoCircleStore implements CircleStore backed by MongoDB.
type MongoCircleStore struct {
	coll *mongo.Collection
}

func NewMongoCircleStore(coll *mongo.Collection) *MongoCircleStore {
	return &MongoCircleStore{coll: coll}
}

func (s *MongoCircleStore) Create(ctx context.Context, circle *model.Circle) error {
	_, err := s.coll.InsertOne(ctx, circle)
	return err
}

func (s *MongoCircleStore) Update(ctx context.Context, id string, circle *model.Circle) bool {
	circle.UpdatedAt = time.Now()
	result, err := s.coll.ReplaceOne(ctx, bson.M{"_id": id}, circle)
	if err != nil {
		return false
	}
	return result.MatchedCount > 0
}

func (s *MongoCircleStore) FindByID(ctx context.Context, id string) (*model.Circle, bool) {
	var c model.Circle
	err := s.coll.FindOne(ctx, bson.M{"_id": id}).Decode(&c)
	if err != nil {
		return nil, false
	}
	return &c, true
}

func (s *MongoCircleStore) List(ctx context.Context, opts ListCirclesOpts) ([]model.Circle, string) {
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
		return nil, ""
	}
	defer cur.Close(ctx)

	var circles []model.Circle
	if err := cur.All(ctx, &circles); err != nil {
		return nil, ""
	}

	var nextCursor string
	if len(circles) == opts.Limit {
		nextCursor = circles[len(circles)-1].ID
	}
	return circles, nextCursor
}

func (s *MongoCircleStore) Archive(ctx context.Context, id string) bool {
	result, err := s.coll.UpdateOne(ctx, bson.M{"_id": id}, bson.M{
		"$set": bson.M{"status": string(model.CircleStatusArchived), "updatedAt": time.Now()},
	})
	if err != nil {
		return false
	}
	return result.MatchedCount > 0
}

func (s *MongoCircleStore) IncrementMemberCount(ctx context.Context, id string, delta int64) error {
	_, err := s.coll.UpdateOne(ctx, bson.M{"_id": id}, bson.M{
		"$inc": bson.M{"memberCount": delta},
		"$set": bson.M{"updatedAt": time.Now()},
	})
	return err
}

func (s *MongoCircleStore) UpdateStorageUsed(ctx context.Context, id string, deltaBytes int64) error {
	_, err := s.coll.UpdateOne(ctx, bson.M{"_id": id}, bson.M{
		"$inc": bson.M{"storageUsedBytes": deltaBytes},
		"$set": bson.M{"updatedAt": time.Now()},
	})
	return err
}

func (s *MongoCircleStore) UpdateSections(ctx context.Context, id string, sections []model.CircleSectionConfig) error {
	_, err := s.coll.UpdateOne(ctx, bson.M{"_id": id}, bson.M{
		"$set": bson.M{"sectionConfig": sections, "updatedAt": time.Now()},
	})
	return err
}

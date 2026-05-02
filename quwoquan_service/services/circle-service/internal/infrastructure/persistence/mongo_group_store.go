package persistence

import (
	"context"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

// MongoGroupStore implements GroupStore backed by MongoDB.
type MongoGroupStore struct {
	coll *mongo.Collection
}

func NewMongoGroupStore(coll *mongo.Collection) *MongoGroupStore {
	return &MongoGroupStore{coll: coll}
}

func (s *MongoGroupStore) ListByCircle(ctx context.Context, circleID string, opts ListGroupsOpts) ([]model.CircleGroup, string) {
	if opts.Limit <= 0 {
		opts.Limit = 20
	}
	filter := bson.M{
		"circleId": circleID,
		"status":   string(model.CircleGroupStatusActive),
	}
	if opts.GroupType != "" {
		filter["groupType"] = opts.GroupType
	}
	if opts.Visibility != "" {
		filter["visibility"] = opts.Visibility
	}
	if opts.ParentGroupID != "" {
		filter["parentGroupId"] = opts.ParentGroupID
	}
	if opts.NodeType != "" {
		filter["nodeType"] = opts.NodeType
	}
	if opts.Cursor != "" {
		var cursorDoc model.CircleGroup
		if err := s.coll.FindOne(ctx, bson.M{"_id": opts.Cursor}).Decode(&cursorDoc); err == nil {
			filter["createdAt"] = bson.M{"$lt": cursorDoc.CreatedAt}
		}
	}

	cur, err := s.coll.Find(ctx, filter, options.Find().
		SetSort(bson.D{{Key: "isDefaultPublicGroup", Value: -1}, {Key: "createdAt", Value: -1}}).
		SetLimit(int64(opts.Limit)))
	if err != nil {
		return nil, ""
	}
	defer cur.Close(ctx)

	var groups []model.CircleGroup
	if err := cur.All(ctx, &groups); err != nil {
		return nil, ""
	}
	var nextCursor string
	if len(groups) == opts.Limit {
		nextCursor = groups[len(groups)-1].ID
	}
	return groups, nextCursor
}

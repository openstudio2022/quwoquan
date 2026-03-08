package persistence

import (
	"context"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// MongoFeedStore implements FeedStore backed by MongoDB.
type MongoFeedStore struct {
	coll *mongo.Collection
}

func NewMongoFeedStore(coll *mongo.Collection) *MongoFeedStore {
	return &MongoFeedStore{coll: coll}
}

func (s *MongoFeedStore) ListCirclePosts(ctx context.Context, circleID string, opts ListCirclePostsOpts) ([]map[string]any, string) {
	if opts.Limit <= 0 {
		opts.Limit = 20
	}

	filter := bson.M{"circleIds": circleID}
	if opts.Cursor != "" {
		filter["_id"] = bson.M{"$lt": opts.Cursor}
	}

	sortField := feedSortOrder(opts.Sort)

	findOpts := options.Find().SetSort(sortField).SetLimit(int64(opts.Limit))
	cur, err := s.coll.Find(ctx, filter, findOpts)
	if err != nil {
		return nil, ""
	}
	defer cur.Close(ctx)

	var docs []bson.M
	if err := cur.All(ctx, &docs); err != nil {
		return nil, ""
	}

	items := make([]map[string]any, len(docs))
	for i, doc := range docs {
		items[i] = map[string]any(doc)
	}

	var nextCursor string
	if len(items) == opts.Limit {
		if id, ok := items[len(items)-1]["_id"].(string); ok {
			nextCursor = id
		}
	}
	return items, nextCursor
}

func feedSortOrder(sort string) bson.D {
	switch sort {
	case "hot":
		return bson.D{{Key: "likeCount", Value: -1}, {Key: "_id", Value: -1}}
	case "featured":
		return bson.D{
			{Key: "pinnedAt", Value: -1},
			{Key: "featuredAt", Value: -1},
			{Key: "createdAt", Value: -1},
		}
	default: // "latest" or empty
		return bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}
	}
}

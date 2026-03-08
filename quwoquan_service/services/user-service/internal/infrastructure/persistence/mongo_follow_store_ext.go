package persistence

import (
	"context"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	followmodel "quwoquan_service/services/user-service/internal/domain/follow/model"
	followrepo "quwoquan_service/services/user-service/internal/domain/follow/repository"
)

// MongoFollowStore extends mongoFollowStoreBase with domain-specific methods.
type MongoFollowStore struct{ mongoFollowStoreBase }

var _ followrepo.FollowRepository = (*MongoFollowStore)(nil)

func NewMongoFollowStore(db *mongo.Database) *MongoFollowStore {
	return &MongoFollowStore{mongoFollowStoreBase{coll: db.Collection("follow_edges")}}
}

func (s *MongoFollowStore) Delete(ctx context.Context, followerID, followeeID string) (bool, error) {
	result, err := s.coll.DeleteOne(ctx, bson.M{"followerId": followerID, "followeeId": followeeID})
	if err != nil {
		return false, err
	}
	return result.DeletedCount > 0, nil
}

func (s *MongoFollowStore) Exists(ctx context.Context, followerID, followeeID string) (bool, error) {
	return s.ExistsByFilter(ctx, bson.M{"followerId": followerID, "followeeId": followeeID})
}

func (s *MongoFollowStore) ListByFollower(ctx context.Context, followerID string, cursor string, limit int) ([]followmodel.FollowEdge, string, error) {
	return s.listEdges(ctx, "followerId", followerID, cursor, limit)
}

func (s *MongoFollowStore) ListByFollowee(ctx context.Context, followeeID string, cursor string, limit int) ([]followmodel.FollowEdge, string, error) {
	return s.listEdges(ctx, "followeeId", followeeID, cursor, limit)
}

func (s *MongoFollowStore) CountByFollower(ctx context.Context, followerID string) (int64, error) {
	return s.CountByFilter(ctx, bson.M{"followerId": followerID})
}

func (s *MongoFollowStore) CountByFollowee(ctx context.Context, followeeID string) (int64, error) {
	return s.CountByFilter(ctx, bson.M{"followeeId": followeeID})
}

func (s *MongoFollowStore) listEdges(ctx context.Context, field, value string, cursor string, limit int) ([]followmodel.FollowEdge, string, error) {
	if limit <= 0 {
		limit = 20
	}
	filter := bson.M{field: value}
	if cursor != "" {
		var cursorDoc followmodel.FollowEdge
		if err := s.coll.FindOne(ctx, bson.M{
			"followerId": cursorFollowerID(cursor),
			"followeeId": cursorFolloweeID(cursor),
		}).Decode(&cursorDoc); err == nil {
			filter["createdAt"] = bson.M{"$lt": cursorDoc.CreatedAt}
		}
	}

	opts := options.Find().
		SetSort(bson.D{{Key: "createdAt", Value: -1}}).
		SetLimit(int64(limit + 1))

	cur, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil, "", err
	}
	defer cur.Close(ctx)

	var edges []followmodel.FollowEdge
	if err := cur.All(ctx, &edges); err != nil {
		return nil, "", err
	}

	var nextCursor string
	if len(edges) > limit {
		last := edges[limit]
		nextCursor = last.FollowerID + ":" + last.FolloweeID
		edges = edges[:limit]
	}
	return edges, nextCursor, nil
}

func cursorFollowerID(cursor string) string {
	for i, c := range cursor {
		if c == ':' {
			return cursor[:i]
		}
	}
	return cursor
}

func cursorFolloweeID(cursor string) string {
	for i, c := range cursor {
		if c == ':' {
			return cursor[i+1:]
		}
	}
	return ""
}

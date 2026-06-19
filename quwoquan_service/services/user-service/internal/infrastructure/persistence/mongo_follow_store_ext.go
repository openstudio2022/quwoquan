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
			// Keyset pagination over a deterministic compound key
			// (createdAt, followerId, followeeId). createdAt alone is NOT unique:
			// bulk follows land in the same millisecond, so a plain
			// `$lt createdAt` would exclude every same-timestamp edge after the
			// first page and silently truncate the list. The compound tiebreaker
			// keeps the page exact even under duplicate timestamps.
			filter["$or"] = bson.A{
				bson.M{"createdAt": bson.M{"$lt": cursorDoc.CreatedAt}},
				bson.M{
					"createdAt":  cursorDoc.CreatedAt,
					"followerId": bson.M{"$lt": cursorDoc.FollowerID},
				},
				bson.M{
					"createdAt":  cursorDoc.CreatedAt,
					"followerId": cursorDoc.FollowerID,
					"followeeId": bson.M{"$lt": cursorDoc.FolloweeID},
				},
			}
		}
	}

	opts := options.Find().
		SetSort(bson.D{
			{Key: "createdAt", Value: -1},
			{Key: "followerId", Value: -1},
			{Key: "followeeId", Value: -1},
		}).
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
		edges = edges[:limit]
		// Cursor is the LAST RETURNED edge; the next page filters strictly
		// "before" it (keyset exclusive), so it is not re-emitted. Using the
		// overfetched limit+1-th edge as the cursor would skip it entirely (it
		// becomes the cursor yet is excluded by the next `$lt`), silently
		// dropping one edge per page boundary.
		last := edges[len(edges)-1]
		nextCursor = last.FollowerID + ":" + last.FolloweeID
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

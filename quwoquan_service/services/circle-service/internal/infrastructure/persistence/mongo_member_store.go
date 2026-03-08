package persistence

import (
	"context"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

// MongoMemberStore implements MemberStore backed by MongoDB.
type MongoMemberStore struct {
	coll *mongo.Collection
}

func NewMongoMemberStore(coll *mongo.Collection) *MongoMemberStore {
	return &MongoMemberStore{coll: coll}
}

func (s *MongoMemberStore) Create(ctx context.Context, member *model.CircleMember) error {
	_, err := s.coll.InsertOne(ctx, member)
	return err
}

func (s *MongoMemberStore) FindByCircleAndUser(ctx context.Context, circleID, userID string) (*model.CircleMember, bool) {
	var m model.CircleMember
	err := s.coll.FindOne(ctx, bson.M{"circleId": circleID, "userId": userID}).Decode(&m)
	if err != nil {
		return nil, false
	}
	return &m, true
}

func (s *MongoMemberStore) Delete(ctx context.Context, circleID, userID string) bool {
	result, err := s.coll.DeleteOne(ctx, bson.M{"circleId": circleID, "userId": userID})
	if err != nil {
		return false
	}
	return result.DeletedCount > 0
}

func (s *MongoMemberStore) UpdateRole(ctx context.Context, circleID, userID string, role model.CircleMemberRole) bool {
	result, err := s.coll.UpdateOne(ctx,
		bson.M{"circleId": circleID, "userId": userID},
		bson.M{"$set": bson.M{"role": string(role)}},
	)
	if err != nil {
		return false
	}
	return result.MatchedCount > 0
}

func (s *MongoMemberStore) ListByCircle(ctx context.Context, circleID string, limit int, cursor string) ([]model.CircleMember, string) {
	if limit <= 0 {
		limit = 20
	}
	filter := bson.M{"circleId": circleID}
	if cursor != "" {
		var cursorDoc model.CircleMember
		if err := s.coll.FindOne(ctx, bson.M{"_id": cursor}).Decode(&cursorDoc); err == nil {
			filter["joinedAt"] = bson.M{"$gt": cursorDoc.JoinedAt}
		}
	}
	opts := options.Find().
		SetSort(bson.D{{Key: "joinedAt", Value: 1}}).
		SetLimit(int64(limit))
	cur, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil, ""
	}
	defer cur.Close(ctx)

	var members []model.CircleMember
	if err := cur.All(ctx, &members); err != nil {
		return nil, ""
	}

	var nextCursor string
	if len(members) == limit {
		nextCursor = members[len(members)-1].ID
	}
	return members, nextCursor
}

func (s *MongoMemberStore) ListByUser(ctx context.Context, userID string, limit int, cursor string) ([]model.CircleMember, string) {
	if limit <= 0 {
		limit = 20
	}
	filter := bson.M{"userId": userID}
	if cursor != "" {
		var cursorDoc model.CircleMember
		if err := s.coll.FindOne(ctx, bson.M{"_id": cursor}).Decode(&cursorDoc); err == nil {
			filter["joinedAt"] = bson.M{"$lt": cursorDoc.JoinedAt}
		}
	}
	opts := options.Find().
		SetSort(bson.D{{Key: "joinedAt", Value: -1}}).
		SetLimit(int64(limit))
	cur, err := s.coll.Find(ctx, filter, opts)
	if err != nil {
		return nil, ""
	}
	defer cur.Close(ctx)

	var members []model.CircleMember
	if err := cur.All(ctx, &members); err != nil {
		return nil, ""
	}

	var nextCursor string
	if len(members) == limit {
		nextCursor = members[len(members)-1].ID
	}
	return members, nextCursor
}

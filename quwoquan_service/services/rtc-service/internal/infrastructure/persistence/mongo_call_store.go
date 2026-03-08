package persistence

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
)

type MongoCallStore struct {
	calls *mongo.Collection
}

func NewMongoCallStore(db *mongo.Database) *MongoCallStore {
	return &MongoCallStore{
		calls: db.Collection("call_sessions"),
	}
}

func (s *MongoCallStore) CreateCall(ctx context.Context, session *model.CallSession) error {
	_, err := s.calls.InsertOne(ctx, session)
	return err
}

func (s *MongoCallStore) FindCallByID(ctx context.Context, id string) (*model.CallSession, error) {
	var session model.CallSession
	err := s.calls.FindOne(ctx, bson.M{"_id": id}).Decode(&session)
	if err != nil {
		return nil, fmt.Errorf("call session not found: %w", err)
	}
	return &session, nil
}

func (s *MongoCallStore) UpdateCall(ctx context.Context, session *model.CallSession) error {
	session.UpdatedAt = time.Now()
	_, err := s.calls.ReplaceOne(ctx, bson.M{"_id": session.ID}, session)
	return err
}

func (s *MongoCallStore) DeleteCall(ctx context.Context, id string) error {
	_, err := s.calls.DeleteOne(ctx, bson.M{"_id": id})
	return err
}

func (s *MongoCallStore) ListCallsByUserID(ctx context.Context, userID string, limit int, cursor string) ([]*model.CallSession, error) {
	if limit <= 0 {
		limit = 20
	}

	filter := bson.M{
		"participants.userId": userID,
	}
	if cursor != "" {
		filter["_id"] = bson.M{"$lt": cursor}
	}

	opts := options.Find().
		SetSort(bson.D{{Key: "createdAt", Value: -1}}).
		SetLimit(int64(limit))

	cur, err := s.calls.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)

	var sessions []*model.CallSession
	if err := cur.All(ctx, &sessions); err != nil {
		return nil, err
	}
	return sessions, nil
}

func (s *MongoCallStore) FindActiveCallByUserID(ctx context.Context, userID string) (*model.CallSession, error) {
	filter := bson.M{
		"participants.userId": userID,
		"status":              bson.M{"$nin": []string{model.StatusEnded}},
	}

	var session model.CallSession
	err := s.calls.FindOne(ctx, filter, options.FindOne().SetSort(bson.D{{Key: "createdAt", Value: -1}})).Decode(&session)
	if err != nil {
		return nil, fmt.Errorf("no active call: %w", err)
	}
	return &session, nil
}

package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	preferenceports "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/ports"
)

type MongoStore struct {
	preferences *mongo.Collection
}

func NewMongoStore(db *mongo.Database) *MongoStore {
	return &MongoStore{preferences: db.Collection("assistant_preferences")}
}

func (s *MongoStore) EnsureIndexes(ctx context.Context) error {
	indexes := []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "userId", Value: 1},
				{Key: "scope", Value: 1},
				{Key: "sessionId", Value: 1},
				{Key: "kind", Value: 1},
			},
			Options: options.Index().
				SetName("uq_assistant_preference_identity").
				SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "userId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "updatedAt", Value: -1},
			},
			Options: options.Index().SetName(
				"idx_assistant_preference_owner_status",
			),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "revocationDeadline", Value: 1},
			},
			Options: options.Index().
				SetName("idx_assistant_preference_revocation_deadline").
				SetSparse(true),
		},
	}
	if _, err := s.preferences.Indexes().CreateMany(ctx, indexes); err != nil {
		return fmt.Errorf("create assistant preference indexes: %w", err)
	}
	return nil
}

func (s *MongoStore) Upsert(
	ctx context.Context,
	input preferenceports.UpsertInput,
) (preferencemodel.AssistantPreference, error) {
	return s.upsert(ctx, input, true)
}

func (s *MongoStore) upsert(
	ctx context.Context,
	input preferenceports.UpsertInput,
	allowInsert bool,
) (preferencemodel.AssistantPreference, error) {
	filter := bson.M{
		"userId":    strings.TrimSpace(input.UserID),
		"scope":     input.Scope,
		"sessionId": strings.TrimSpace(input.SessionID),
		"kind":      input.Kind,
	}
	update := bson.M{
		"$set": bson.M{
			"value":           strings.TrimSpace(input.Value),
			"sourceType":      input.SourceType,
			"sourceSessionId": strings.TrimSpace(input.SourceSessionID),
			"confirmedAt":     input.ConfirmedAt,
			"status":          preferencemodel.StatusActive,
			"sessionId":       strings.TrimSpace(input.SessionID),
			"updatedAt":       input.Now.UTC(),
		},
		"$setOnInsert": bson.M{
			"_id":       strings.TrimSpace(input.PreferenceID),
			"userId":    strings.TrimSpace(input.UserID),
			"scope":     input.Scope,
			"kind":      input.Kind,
			"createdAt": input.Now.UTC(),
		},
		"$unset": bson.M{
			"revokedAt":          "",
			"revocationDeadline": "",
		},
		"$inc": bson.M{"version": int64(1)},
	}
	opts := options.FindOneAndUpdate().SetReturnDocument(options.After)
	if allowInsert {
		opts.SetUpsert(true)
	}
	var preference preferencemodel.AssistantPreference
	err := s.preferences.FindOneAndUpdate(ctx, filter, update, opts).Decode(&preference)
	if mongo.IsDuplicateKeyError(err) && allowInsert {
		return s.upsert(ctx, input, false)
	}
	if err != nil {
		return preferencemodel.AssistantPreference{}, err
	}
	return preference, nil
}

func (s *MongoStore) List(
	ctx context.Context,
	userID string,
	filter preferenceports.ListFilter,
) ([]preferencemodel.AssistantPreference, error) {
	query := bson.M{
		"userId": strings.TrimSpace(userID),
		"status": filter.Status,
	}
	if filter.Scope != "" {
		query["scope"] = filter.Scope
	}
	if strings.TrimSpace(filter.SessionID) != "" {
		query["sessionId"] = strings.TrimSpace(filter.SessionID)
	}
	limit := int64(filter.Limit)
	if limit <= 0 || limit > 100 {
		limit = 50
	}
	cursor, err := s.preferences.Find(
		ctx,
		query,
		options.Find().
			SetSort(bson.D{
				{Key: "updatedAt", Value: -1},
				{Key: "_id", Value: 1},
			}).
			SetLimit(limit),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	items := []preferencemodel.AssistantPreference{}
	if err := cursor.All(ctx, &items); err != nil {
		return nil, err
	}
	return items, nil
}

func (s *MongoStore) ListActiveForRun(
	ctx context.Context,
	userID string,
	sessionID string,
	limitPerScope int,
) ([]preferencemodel.AssistantPreference, error) {
	if limitPerScope <= 0 || limitPerScope > 16 {
		limitPerScope = 16
	}
	cursor, err := s.preferences.Find(
		ctx,
		bson.M{
			"userId": strings.TrimSpace(userID),
			"status": preferencemodel.StatusActive,
			"$or": bson.A{
				bson.M{"scope": preferencemodel.ScopeLongTerm},
				bson.M{
					"scope":     preferencemodel.ScopeSession,
					"sessionId": strings.TrimSpace(sessionID),
				},
			},
		},
		options.Find().
			SetSort(bson.D{
				{Key: "updatedAt", Value: -1},
				{Key: "_id", Value: 1},
			}).
			SetLimit(int64(limitPerScope*2)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	items := []preferencemodel.AssistantPreference{}
	if err := cursor.All(ctx, &items); err != nil {
		return nil, err
	}
	return items, nil
}

func (s *MongoStore) GetOwned(
	ctx context.Context,
	userID string,
	preferenceID string,
) (preferencemodel.AssistantPreference, bool, error) {
	var preference preferencemodel.AssistantPreference
	err := s.preferences.FindOne(ctx, bson.M{
		"_id":    strings.TrimSpace(preferenceID),
		"userId": strings.TrimSpace(userID),
	}).Decode(&preference)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return preferencemodel.AssistantPreference{}, false, nil
	}
	if err != nil {
		return preferencemodel.AssistantPreference{}, false, err
	}
	return preference, true, nil
}

func (s *MongoStore) UpdateStatus(
	ctx context.Context,
	userID string,
	preferenceID string,
	expectedVersion int64,
	update preferenceports.StatusUpdate,
) (preferencemodel.AssistantPreference, bool, error) {
	set := bson.M{
		"status":    update.Status,
		"updatedAt": update.UpdatedAt.UTC(),
	}
	mutation := bson.M{
		"$set": set,
		"$inc": bson.M{"version": int64(1)},
	}
	if update.Status == preferencemodel.StatusRevoked {
		set["revokedAt"] = update.RevokedAt
		set["revocationDeadline"] = update.RevocationDeadline
	} else {
		mutation["$unset"] = bson.M{
			"revokedAt":          "",
			"revocationDeadline": "",
		}
	}
	var preference preferencemodel.AssistantPreference
	err := s.preferences.FindOneAndUpdate(
		ctx,
		bson.M{
			"_id":     strings.TrimSpace(preferenceID),
			"userId":  strings.TrimSpace(userID),
			"version": expectedVersion,
		},
		mutation,
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&preference)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return preferencemodel.AssistantPreference{}, false, nil
	}
	if err != nil {
		return preferencemodel.AssistantPreference{}, false, err
	}
	return preference, true, nil
}

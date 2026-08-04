package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/domain/ports"
)

type visibilityDocument struct {
	ID           string    `bson:"_id"`
	AccountID    string    `bson:"accountId"`
	SkillID      string    `bson:"skillId"`
	HiddenBefore time.Time `bson:"hiddenBefore"`
	UpdatedAt    time.Time `bson:"updatedAt"`
}

type MongoVisibilityStore struct{ collection *mongo.Collection }

var _ ports.VisibilityStore = (*MongoVisibilityStore)(nil)

func NewMongoVisibilityStore(database *mongo.Database) *MongoVisibilityStore {
	return &MongoVisibilityStore{collection: database.Collection("skill_activity_visibility_controls")}
}

func (store *MongoVisibilityStore) EnsureIndexes(ctx context.Context) error {
	if store == nil || store.collection == nil {
		return model.ErrUnavailable
	}
	_, err := store.collection.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "accountId", Value: 1}, {Key: "skillId", Value: 1}},
		Options: options.Index().SetName("uq_skill_activity_visibility_owner_skill").SetUnique(true),
	})
	if err != nil {
		return fmt.Errorf("%w: ensure visibility index: %v", model.ErrUnavailable, err)
	}
	return nil
}

func (store *MongoVisibilityStore) HiddenBefore(
	ctx context.Context,
	accountID, skillID string,
) (*time.Time, error) {
	var document visibilityDocument
	err := store.collection.FindOne(ctx, bson.M{
		"accountId": strings.TrimSpace(accountID),
		"skillId":   strings.TrimSpace(skillID),
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("%w: read visibility watermark: %v", model.ErrUnavailable, err)
	}
	value := document.HiddenBefore.UTC()
	return &value, nil
}

func (store *MongoVisibilityStore) HideBefore(
	ctx context.Context,
	accountID, skillID string,
	before time.Time,
) error {
	accountID = strings.TrimSpace(accountID)
	skillID = strings.TrimSpace(skillID)
	if accountID == "" || skillID == "" || before.IsZero() {
		return model.ErrInvalidArgument
	}
	identity := accountID + "\x1f" + skillID
	_, err := store.collection.UpdateOne(
		ctx,
		bson.M{"_id": identity},
		bson.M{
			"$setOnInsert": bson.M{"accountId": accountID, "skillId": skillID},
			"$max":         bson.M{"hiddenBefore": before.UTC()},
			"$set":         bson.M{"updatedAt": before.UTC()},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		return fmt.Errorf("%w: write visibility watermark: %v", model.ErrUnavailable, err)
	}
	return nil
}

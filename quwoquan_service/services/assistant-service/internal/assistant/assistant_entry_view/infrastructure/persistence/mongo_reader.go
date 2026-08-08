package persistence

import (
	"context"
	"errors"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	entrymodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/domain/model"
)

type MongoReader struct{ collection *mongo.Collection }

func NewMongoReader(database *mongo.Database) *MongoReader {
	if database == nil {
		return &MongoReader{}
	}
	return &MongoReader{collection: database.Collection("rm_assistant_entry")}
}

func (r *MongoReader) EnsureIndexes(ctx context.Context) error {
	if r == nil || r.collection == nil {
		return errors.New("assistant entry projection store is unavailable")
	}
	_, err := r.collection.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "accountId", Value: 1}},
		Options: options.Index().
			SetName("uq_assistant_entry_account").
			SetUnique(true),
	})
	if err != nil {
		return fmt.Errorf("ensure assistant entry projection indexes: %w", err)
	}
	return nil
}

func (r *MongoReader) Get(ctx context.Context, accountID string) (*entrymodel.View, error) {
	if r == nil || r.collection == nil {
		return nil, errors.New("assistant entry projection store is unavailable")
	}
	var view entrymodel.View
	if err := r.collection.FindOne(ctx, bson.M{"accountId": accountID}).Decode(&view); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &view, nil
}

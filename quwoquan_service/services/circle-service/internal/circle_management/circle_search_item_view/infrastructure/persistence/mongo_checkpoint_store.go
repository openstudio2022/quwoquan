package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

type MongoCheckpointStore struct{ collection *mongo.Collection }

func NewMongoCheckpointStore(database *mongo.Database) *MongoCheckpointStore {
	if database == nil {
		panic("CircleSearchItemView checkpoint database is required")
	}
	return &MongoCheckpointStore{collection: database.Collection("circle_search_item_view_checkpoints")}
}

func (store *MongoCheckpointStore) Load(ctx context.Context, consumer string) (string, error) {
	var document struct {
		Checkpoint string `bson:"checkpoint"`
	}
	err := store.collection.FindOne(ctx, bson.M{"_id": strings.TrimSpace(consumer)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	return document.Checkpoint, err
}

func (store *MongoCheckpointStore) Save(ctx context.Context, consumer, checkpoint string) error {
	_, err := store.collection.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(consumer)},
		bson.M{"$set": bson.M{"checkpoint": strings.TrimSpace(checkpoint), "updatedAt": time.Now().UTC()}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

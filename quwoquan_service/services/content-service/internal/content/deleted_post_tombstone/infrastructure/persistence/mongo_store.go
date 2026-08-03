package persistence

import (
	"context"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	tombstonemodel "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/model"
	tombstoneports "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/domain/ports"
)

const collectionName = "deleted_post_tombstones"

type document struct {
	ID                       string `bson:"_id"`
	tombstonemodel.Tombstone `bson:",inline"`
}

type MongoStore struct {
	collection *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("DeletedPostTombstone Mongo store requires database")
	}
	return &MongoStore{collection: database.Collection(collectionName)}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	_, err := store.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "postId", Value: 1}},
			Options: options.Index().SetName("idx_tombstone_post").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "deletedAt", Value: -1}},
			Options: options.Index().SetName("idx_tombstone_deleted_at"),
		},
		{
			Keys:    bson.D{{Key: "expireAt", Value: 1}},
			Options: options.Index().SetName("idx_tombstone_expire").SetExpireAfterSeconds(0),
		},
	})
	return err
}

func (store *MongoStore) AppendIfAbsent(
	ctx context.Context,
	tombstone tombstonemodel.Tombstone,
) (bool, error) {
	if err := tombstone.Validate(); err != nil {
		return false, err
	}
	result, err := store.collection.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(tombstone.PostID)},
		bson.M{"$setOnInsert": document{
			ID:        strings.TrimSpace(tombstone.PostID),
			Tombstone: tombstone,
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		return false, err
	}
	return result.UpsertedCount == 1, nil
}

func (store *MongoStore) Find(
	ctx context.Context,
	postID string,
) (tombstonemodel.Tombstone, bool, error) {
	var stored document
	err := store.collection.FindOne(ctx, bson.M{"_id": strings.TrimSpace(postID)}).Decode(&stored)
	if err == mongo.ErrNoDocuments {
		return tombstonemodel.Tombstone{}, false, nil
	}
	if err != nil {
		return tombstonemodel.Tombstone{}, false, err
	}
	return stored.Tombstone, true, nil
}

var _ tombstoneports.Store = (*MongoStore)(nil)

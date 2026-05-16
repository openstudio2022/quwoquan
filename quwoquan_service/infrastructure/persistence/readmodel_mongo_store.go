package persistence

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/projector"
)

// Compile-time check.
var _ projector.ReadModelStore = (*MongoReadModelStore)(nil)

// MongoReadModelStore implements projector.ReadModelStore using MongoDB.
type MongoReadModelStore struct {
	db *mongo.Database
}

func NewMongoReadModelStore(db *mongo.Database) *MongoReadModelStore {
	return &MongoReadModelStore{db: db}
}

func (s *MongoReadModelStore) Upsert(ctx context.Context, collection, id string, setFields, setOnInsertFields map[string]any) error {
	coll := s.db.Collection(collection)
	setFields["updatedAt"] = time.Now().UTC()
	if setOnInsertFields == nil {
		setOnInsertFields = map[string]any{}
	}
	if _, ok := setOnInsertFields["createdAt"]; !ok {
		setOnInsertFields["createdAt"] = time.Now().UTC()
	}
	doc := bson.M{
		"$set":         bson.M(setFields),
		"$setOnInsert": bson.M(setOnInsertFields),
	}
	opts := options.UpdateOne().SetUpsert(true)
	_, err := coll.UpdateOne(ctx, bson.M{"_id": id}, doc, opts)
	return err
}

func (s *MongoReadModelStore) UpdateFields(ctx context.Context, collection, id string, setFields map[string]any) error {
	coll := s.db.Collection(collection)
	setFields["updatedAt"] = time.Now().UTC()
	_, err := coll.UpdateOne(ctx, bson.M{"_id": id}, bson.M{"$set": bson.M(setFields)})
	return err
}

func (s *MongoReadModelStore) IncrementField(ctx context.Context, collection, id, field string, delta int) error {
	coll := s.db.Collection(collection)
	_, err := coll.UpdateOne(ctx, bson.M{"_id": id}, bson.M{"$inc": bson.M{field: delta}})
	return err
}

func (s *MongoReadModelStore) IncrementFieldWithSet(ctx context.Context, collection, id, field string, delta int, setFields map[string]any) error {
	coll := s.db.Collection(collection)
	update := bson.M{"$inc": bson.M{field: delta}}
	if len(setFields) > 0 {
		setFields["lastEngagementAt"] = time.Now().UTC()
		update["$set"] = bson.M(setFields)
	} else {
		update["$set"] = bson.M{"lastEngagementAt": time.Now().UTC()}
	}
	_, err := coll.UpdateOne(ctx, bson.M{"_id": id}, update)
	return err
}

func (s *MongoReadModelStore) DeleteByID(ctx context.Context, collection, id string) error {
	coll := s.db.Collection(collection)
	_, err := coll.DeleteOne(ctx, bson.M{"_id": id})
	return err
}

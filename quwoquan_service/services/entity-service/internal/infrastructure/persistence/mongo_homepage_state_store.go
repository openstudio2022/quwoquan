package persistence

import (
	"context"
	"errors"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/entity-service/internal/application"
)

const homepageStateDocumentID = "homepage-state"

type MongoHomepageStateStore struct {
	collection *mongo.Collection
}

func NewMongoHomepageStateStore(collection *mongo.Collection) *MongoHomepageStateStore {
	return &MongoHomepageStateStore{collection: collection}
}

func (s *MongoHomepageStateStore) Load(ctx context.Context) (*application.HomepageStateSnapshot, error) {
	var doc struct {
		ID                                string `bson:"_id"`
		application.HomepageStateSnapshot `bson:",inline"`
	}
	err := s.collection.FindOne(ctx, bson.M{"_id": homepageStateDocumentID}).Decode(&doc)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &doc.HomepageStateSnapshot, nil
}

func (s *MongoHomepageStateStore) Save(ctx context.Context, snapshot application.HomepageStateSnapshot) error {
	_, err := s.collection.UpdateOne(
		ctx,
		bson.M{"_id": homepageStateDocumentID},
		bson.M{"$set": snapshot},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

package persistence

import (
	"context"
	"errors"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/ports"
)

const mapCollection = "trip_map_views"

type MongoStore struct{ maps *mongo.Collection }

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("TripMapView MongoStore requires database")
	}
	return &MongoStore{maps: database.Collection(mapCollection)}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	_, err := store.maps.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "currentRevisionId", Value: 1},
			{Key: "currentRevisionNumber", Value: 1},
		},
		Options: options.Index().SetName("idx_trip_map_source_revision"),
	})
	return err
}

func (store *MongoStore) GetMap(ctx context.Context, tripID string) (model.View, error) {
	var view model.View
	err := store.maps.FindOne(ctx, bson.M{"_id": strings.TrimSpace(tripID)}).Decode(&view)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.View{}, ports.ErrNotFound
	}
	return view, err
}

var _ ports.Store = (*MongoStore)(nil)

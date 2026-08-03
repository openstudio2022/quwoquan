package persistence

import (
	"context"
	"errors"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/ports"
)

const revisionCollection = "trip_plan_revisions"

type MongoStore struct {
	revisions *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("TripPlanRevision MongoStore requires database")
	}
	return &MongoStore{revisions: database.Collection(revisionCollection)}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	_, err := store.revisions.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "tripId", Value: 1}, {Key: "revisionNumber", Value: 1}}, Options: options.Index().SetName("uq_trip_plan_revision_number").SetUnique(true)},
		{Keys: bson.D{{Key: "tripId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_trip_plan_revision_created")},
	})
	return err
}

func (store *MongoStore) Get(ctx context.Context, tripID string, number int64) (model.Revision, error) {
	var revision model.Revision
	err := store.revisions.FindOne(ctx, bson.M{
		"tripId": strings.TrimSpace(tripID), "revisionNumber": number,
	}).Decode(&revision)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Revision{}, ports.ErrNotFound
	}
	return revision, err
}

func (store *MongoStore) AppendInTripPlanTransaction(ctx context.Context, revision model.Revision) error {
	if err := revision.Validate(); err != nil {
		return err
	}
	if _, err := store.revisions.InsertOne(ctx, revision); err != nil {
		if mongo.IsDuplicateKeyError(err) {
			return ports.ErrConflict
		}
		return err
	}
	return nil
}

var _ ports.Store = (*MongoStore)(nil)

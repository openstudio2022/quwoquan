package persistence

import (
	"context"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// MongoActiveSupplyReader is the production read side of data_release_state.
// The importer remains the sole writer; feed requests only verify that their
// environment has at least one canonical active release.
type MongoActiveSupplyReader struct {
	collection  *mongo.Collection
	environment string
}

func NewMongoActiveSupplyReader(db *mongo.Database, environment string) *MongoActiveSupplyReader {
	if db == nil {
		return nil
	}
	return &MongoActiveSupplyReader{
		collection:  db.Collection("data_release_state"),
		environment: strings.TrimSpace(environment),
	}
}

func (r *MongoActiveSupplyReader) HasActiveSupply(ctx context.Context) (bool, error) {
	if r == nil || r.collection == nil || r.environment == "" {
		return false, nil
	}
	var state struct {
		ActiveReleaseID string `bson:"activeReleaseId"`
	}
	err := r.collection.FindOne(
		ctx,
		bson.M{
			"environment":     r.environment,
			"status":          "active",
			"activeReleaseId": bson.M{"$type": "string", "$ne": ""},
		},
		options.FindOne().SetProjection(bson.M{"activeReleaseId": 1}),
	).Decode(&state)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return false, nil
		}
		return false, err
	}
	return strings.TrimSpace(state.ActiveReleaseID) != "", nil
}

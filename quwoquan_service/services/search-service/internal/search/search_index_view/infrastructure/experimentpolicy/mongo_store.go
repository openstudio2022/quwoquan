package experimentpolicy

import (
	"context"
	"errors"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

const CollectionName = "rm_search_experiment_policy"

type MongoStore struct {
	collection *mongo.Collection
}

func NewMongoStore(database *mongo.Database) (*MongoStore, error) {
	if database == nil {
		return nil, errors.New("search experiment policy store requires Mongo database")
	}
	return &MongoStore{collection: database.Collection(CollectionName)}, nil
}

func (s *MongoStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.collection.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "revision", Value: -1}, {Key: "updatedAt", Value: -1}},
		Options: options.Index().SetName("idx_search_experiment_policy_revision"),
	})
	return err
}

func (s *MongoStore) Load(ctx context.Context, id string) (application.ExperimentPolicy, bool, error) {
	var policy application.ExperimentPolicy
	err := s.collection.FindOne(ctx, bson.M{"_id": id}).Decode(&policy)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return application.ExperimentPolicy{}, false, nil
	}
	if err != nil {
		return application.ExperimentPolicy{}, false, err
	}
	return policy, true, nil
}

func (s *MongoStore) Apply(
	ctx context.Context,
	policy application.ExperimentPolicy,
) (application.ExperimentPolicy, bool, error) {
	canonical, err := application.CanonicalExperimentPolicy(policy)
	if err != nil {
		return application.ExperimentPolicy{}, false, err
	}
	result, err := s.collection.UpdateOne(
		ctx,
		bson.M{
			"_id": canonical.ID,
			"$or": bson.A{
				bson.M{"revision": bson.M{"$lt": canonical.Revision}},
				bson.M{"revision": canonical.Revision, "digest": canonical.Digest},
			},
		},
		bson.M{"$set": bson.M{
			"revision": canonical.Revision, "status": canonical.Status,
			"variants": canonical.Variants, "startsAt": canonical.StartsAt,
			"endsAt": canonical.EndsAt, "updatedAt": canonical.UpdatedAt,
			"digest": canonical.Digest,
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if err == nil {
		return canonical, result.ModifiedCount > 0 || result.UpsertedCount > 0, nil
	}
	if !mongo.IsDuplicateKeyError(err) {
		return application.ExperimentPolicy{}, false, err
	}
	current, found, loadErr := s.Load(ctx, canonical.ID)
	if loadErr != nil || !found {
		return application.ExperimentPolicy{}, false, errors.Join(err, loadErr)
	}
	if current.Revision > canonical.Revision || current.Revision == canonical.Revision && current.Digest == canonical.Digest {
		return current, false, nil
	}
	return application.ExperimentPolicy{}, false, fmt.Errorf("search Experiment policy revision %d has conflicting content", canonical.Revision)
}

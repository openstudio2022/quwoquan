package persistence

import (
	"context"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/domain"
)

const collectionName = "external_interaction_dead_letters"

type MongoRepository struct {
	collection *mongo.Collection
}

func NewMongoRepository(database *mongo.Database) *MongoRepository {
	return &MongoRepository{collection: database.Collection(collectionName)}
}

func (repository *MongoRepository) EnsureIndexes(ctx context.Context) error {
	_, err := repository.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "taskId", Value: 1}},
			Options: options.Index().SetName("uq_external_dead_letter_task").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "requestId", Value: 1}, {Key: "createdAt", Value: 1}},
			Options: options.Index().SetName("idx_external_dead_letter_request_created"),
		},
	})
	return err
}

func (repository *MongoRepository) AppendIfAbsent(
	ctx context.Context,
	fact domain.Fact,
) (bool, error) {
	canonical, err := domain.NewFact(fact)
	if err != nil {
		return false, err
	}
	if _, err := repository.collection.InsertOne(ctx, canonical); err == nil {
		return true, nil
	} else if !mongo.IsDuplicateKeyError(err) {
		return false, err
	}
	var existing domain.Fact
	if err := repository.collection.FindOne(ctx, bson.M{"_id": canonical.DeadLetterID}).Decode(&existing); err != nil {
		return false, err
	}
	if existing.TaskID != canonical.TaskID ||
		existing.RequestID != canonical.RequestID ||
		existing.Operation != canonical.Operation ||
		existing.Provider != canonical.Provider ||
		existing.FinalError != canonical.FinalError ||
		existing.Retryable != canonical.Retryable ||
		existing.RecoveryAction != canonical.RecoveryAction ||
		!existing.CreatedAt.Equal(canonical.CreatedAt) {
		return false, fmt.Errorf(
			"external interaction dead letter %s conflicts with immutable fact",
			canonical.DeadLetterID,
		)
	}
	return false, nil
}

func (repository *MongoRepository) ListByRequest(
	ctx context.Context,
	requestID string,
) ([]domain.Fact, error) {
	requestID = strings.TrimSpace(requestID)
	if requestID == "" {
		return nil, fmt.Errorf("requestId is required")
	}
	cursor, err := repository.collection.Find(
		ctx,
		bson.M{"requestId": requestID},
		options.Find().SetSort(bson.D{{Key: "createdAt", Value: 1}, {Key: "_id", Value: 1}}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var facts []domain.Fact
	if err := cursor.All(ctx, &facts); err != nil {
		return nil, err
	}
	if facts == nil {
		facts = []domain.Fact{}
	}
	return facts, nil
}

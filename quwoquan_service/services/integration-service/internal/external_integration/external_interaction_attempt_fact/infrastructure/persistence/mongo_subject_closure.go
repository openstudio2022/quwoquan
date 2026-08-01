package persistence

import (
	"context"
	"errors"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	interactionapplication "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

type MongoSubjectClosure struct {
	attempts *mongo.Collection
}

var _ interactionapplication.AttemptSubjectClosure = (*MongoSubjectClosure)(nil)

func NewMongoSubjectClosure(db *mongo.Database) (*MongoSubjectClosure, error) {
	if db == nil {
		return nil, errors.New("external interaction attempt closure requires MongoDB")
	}
	return &MongoSubjectClosure{
		attempts: db.Collection("external_provider_attempt_ledger"),
	}, nil
}

func (store *MongoSubjectClosure) EnsureIndexes(ctx context.Context) error {
	if store == nil || store.attempts == nil {
		return errors.New("external interaction attempt closure is not configured")
	}
	_, err := store.attempts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "subjectDigest", Value: 1}},
			Options: options.Index().SetName("idx_ext_attempt_subject_cleanup"),
		},
		{
			Keys:    bson.D{{Key: "taskId", Value: 1}},
			Options: options.Index().SetName("idx_ext_attempt_task_cleanup"),
		},
	})
	if err != nil {
		return fmt.Errorf("ensure external interaction attempt cleanup indexes: %w", err)
	}
	return nil
}

func (store *MongoSubjectClosure) DeleteByPrivacyLocators(
	ctx context.Context,
	subjectDigests []string,
	taskIDs []string,
	requestIDs []string,
) (int64, error) {
	if store == nil || store.attempts == nil {
		return 0, errors.New("external interaction attempt closure is not configured")
	}
	clauses := bson.A{}
	if len(subjectDigests) > 0 {
		clauses = append(clauses, bson.M{"subjectDigest": bson.M{"$in": subjectDigests}})
	}
	if len(taskIDs) > 0 {
		clauses = append(clauses, bson.M{"taskId": bson.M{"$in": taskIDs}})
	}
	if len(requestIDs) > 0 {
		clauses = append(clauses, bson.M{"requestId": bson.M{"$in": requestIDs}})
	}
	if len(clauses) == 0 {
		return 0, nil
	}
	result, err := store.attempts.DeleteMany(ctx, bson.M{"$or": clauses})
	if err != nil {
		return 0, fmt.Errorf("delete closed-subject provider attempts: %w", err)
	}
	return result.DeletedCount, nil
}

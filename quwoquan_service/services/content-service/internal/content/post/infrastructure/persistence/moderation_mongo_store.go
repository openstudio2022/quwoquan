package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// MongoPostModerationCaseStore is the sole production adapter for independent
// PostModerationCase state, reviewer audit, durable receipts, and its outbox.
// It has no process-memory fallback.
type MongoPostModerationCaseStore struct {
	cases       *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
	audit       *mongo.Collection
	checkpoints *mongo.Collection
}

func NewMongoPostModerationCaseStore(
	cases *mongo.Collection,
) *MongoPostModerationCaseStore {
	if cases == nil {
		panic("NewMongoPostModerationCaseStore requires post_moderation_cases collection")
	}
	db := cases.Database()
	return &MongoPostModerationCaseStore{
		cases:       cases,
		receipts:    db.Collection("post_moderation_case_command_receipts"),
		outbox:      db.Collection("post_moderation_case_outbox"),
		audit:       db.Collection("post_moderation_case_audit"),
		checkpoints: db.Collection("post_moderation_case_projection_checkpoints"),
	}
}

type moderationCheckpointDocument struct {
	ID         string    `bson:"_id"`
	Checkpoint string    `bson:"checkpoint"`
	UpdatedAt  time.Time `bson:"updatedAt"`
}

func (s *MongoPostModerationCaseStore) LoadModerationCheckpoint(
	ctx context.Context,
	consumer string,
) (string, error) {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return "", fmt.Errorf("moderation checkpoint consumer is required")
	}
	var document moderationCheckpointDocument
	err := s.checkpoints.FindOne(ctx, bson.M{"_id": consumer}).Decode(&document)
	if err == mongo.ErrNoDocuments {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(document.Checkpoint), nil
}

func (s *MongoPostModerationCaseStore) SaveModerationCheckpoint(
	ctx context.Context,
	consumer string,
	checkpoint string,
) error {
	consumer = strings.TrimSpace(consumer)
	checkpoint = strings.TrimSpace(checkpoint)
	if consumer == "" || checkpoint == "" {
		return fmt.Errorf("moderation checkpoint consumer and value are required")
	}
	if _, _, err := parseModerationOutboxCheckpoint(checkpoint); err != nil {
		return err
	}
	_, err := s.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": consumer},
		bson.M{"$set": bson.M{"checkpoint": checkpoint, "updatedAt": time.Now().UTC()}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

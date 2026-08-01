package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

type userAccountClosedFailureDocument struct {
	Attempts int64 `bson:"attempts"`
}

func (projection *MongoUserAccountClosedProjection) RecordUserAccountClosedFailure(
	ctx context.Context,
	stream string,
	messageID string,
	eventID string,
	errorClass string,
	cause error,
) (int64, error) {
	if projection == nil || projection.failures == nil || cause == nil {
		return 0, errors.New("integration UserAccountClosed failure state is unavailable")
	}
	errorClass = strings.TrimSpace(errorClass)
	if errorClass == "" {
		return 0, errors.New("integration UserAccountClosed error class is required")
	}
	now := time.Now().UTC()
	var document userAccountClosedFailureDocument
	err := projection.failures.FindOneAndUpdate(
		ctx,
		bson.M{
			"_id":            accountClosureFailureID(stream, messageID),
			"deadLetteredAt": bson.M{"$exists": false},
		},
		bson.M{
			"$inc": bson.M{"attempts": int64(1)},
			"$set": bson.M{
				"sourceStream":   strings.TrimSpace(stream),
				"sourceStreamId": strings.TrimSpace(messageID),
				"eventDigest":    accountClosureDigest(eventID),
				"errorClass":     errorClass,
				"errorDigest":    accountClosureDigest(cause.Error()),
				"updatedAt":      now,
				"expireAt":       now.Add(userAccountClosedFailureRetention),
			},
			"$setOnInsert": bson.M{"createdAt": now},
		},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		return 0, fmt.Errorf("persist integration account closure failure: %w", err)
	}
	return document.Attempts, nil
}

func (projection *MongoUserAccountClosedProjection) IsUserAccountClosedDeadLettered(
	ctx context.Context,
	stream string,
	messageID string,
) (bool, error) {
	var document struct {
		DeadLetteredAt *time.Time `bson:"deadLetteredAt"`
	}
	err := projection.failures.FindOne(
		ctx,
		bson.M{"_id": accountClosureFailureID(stream, messageID)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("read integration account closure failure: %w", err)
	}
	return document.DeadLetteredAt != nil && !document.DeadLetteredAt.IsZero(), nil
}

func (projection *MongoUserAccountClosedProjection) MarkUserAccountClosedDeadLettered(
	ctx context.Context,
	stream string,
	messageID string,
) error {
	now := time.Now().UTC()
	result, err := projection.failures.UpdateOne(
		ctx,
		bson.M{"_id": accountClosureFailureID(stream, messageID)},
		bson.M{
			"$set":   bson.M{"deadLetteredAt": now, "updatedAt": now},
			"$unset": bson.M{"expireAt": ""},
		},
	)
	if err != nil {
		return fmt.Errorf("mark integration account closure dead-lettered: %w", err)
	}
	if result.MatchedCount == 0 {
		return errors.New("integration account closure failure state is missing")
	}
	return nil
}

func (projection *MongoUserAccountClosedProjection) ClearUserAccountClosedFailure(
	ctx context.Context,
	stream string,
	messageID string,
) error {
	_, err := projection.failures.DeleteOne(
		ctx,
		bson.M{"_id": accountClosureFailureID(stream, messageID)},
	)
	if err != nil {
		return fmt.Errorf("clear integration account closure failure: %w", err)
	}
	return nil
}

func accountClosureFailureID(stream, messageID string) string {
	return accountClosureDigest(strings.TrimSpace(stream) + "\x00" + strings.TrimSpace(messageID))
}

func accountClosureDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}

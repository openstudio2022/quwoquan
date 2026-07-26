package accountclosure

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

func (projection *MongoProjection) RecordUserAccountClosedFailure(
	ctx context.Context,
	stream string,
	messageID string,
	eventID string,
	cause error,
) (int64, error) {
	if cause == nil {
		return 0, errors.New(
			"search UserAccountClosed failure cause is required",
		)
	}
	now := time.Now().UTC()
	var document failureDocument
	err := projection.failures.FindOneAndUpdate(
		ctx,
		bson.M{
			"_id":            failureDocumentID(stream, messageID),
			"deadLetteredAt": bson.M{"$exists": false},
		},
		bson.M{
			"$inc": bson.M{"attempts": int64(1)},
			"$set": bson.M{
				"sourceStream":   stream,
				"sourceStreamId": messageID,
				"eventDigest":    digestValue(eventID),
				"errorDigest":    digestValue(cause.Error()),
				"updatedAt":      now,
				"expireAt":       now.Add(failureRetention),
			},
			"$setOnInsert": bson.M{"createdAt": now},
		},
		options.FindOneAndUpdate().
			SetUpsert(true).
			SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		return 0, fmt.Errorf(
			"persist search UserAccountClosed failure: %w",
			err,
		)
	}
	return document.Attempts, nil
}

func (projection *MongoProjection) ClearUserAccountClosedFailure(
	ctx context.Context,
	stream string,
	messageID string,
) error {
	_, err := projection.failures.DeleteOne(
		ctx,
		bson.M{"_id": failureDocumentID(stream, messageID)},
	)
	if err != nil {
		return fmt.Errorf(
			"delete search UserAccountClosed failure: %w",
			err,
		)
	}
	return nil
}

func (projection *MongoProjection) IsUserAccountClosedDeadLettered(
	ctx context.Context,
	stream string,
	messageID string,
) (bool, error) {
	var document failureDocument
	err := projection.failures.FindOne(
		ctx,
		bson.M{"_id": failureDocumentID(stream, messageID)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf(
			"read search UserAccountClosed dead-letter state: %w",
			err,
		)
	}
	return document.DeadLetteredAt != nil, nil
}

func (projection *MongoProjection) MarkUserAccountClosedDeadLettered(
	ctx context.Context,
	stream string,
	messageID string,
) error {
	now := time.Now().UTC()
	result, err := projection.failures.UpdateOne(
		ctx,
		bson.M{"_id": failureDocumentID(stream, messageID)},
		bson.M{
			"$set": bson.M{
				"deadLetteredAt": now,
				"updatedAt":      now,
			},
			// The marker guards an unacknowledged source PEL and must not be
			// removed by the ordinary transient-failure TTL.
			"$unset": bson.M{"expireAt": ""},
		},
	)
	if err != nil {
		return fmt.Errorf(
			"mark search UserAccountClosed dead-letter state: %w",
			err,
		)
	}
	if result.MatchedCount != 1 {
		return errors.New("search UserAccountClosed failure state is missing")
	}
	return nil
}

func failureDocumentID(stream string, messageID string) string {
	return digestValue(
		strings.TrimSpace(stream) + "\x00" + strings.TrimSpace(messageID),
	)
}

func digestValue(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}

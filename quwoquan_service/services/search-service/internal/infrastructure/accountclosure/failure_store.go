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
		bson.M{"_id": failureDocumentID(stream, messageID)},
		bson.M{
			"$inc": bson.M{"attempts": int64(1)},
			"$set": bson.M{
				"eventDigest": digestValue(eventID),
				"errorDigest": digestValue(cause.Error()),
				"updatedAt":   now,
				"expireAt":    now.Add(failureRetention),
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

func failureDocumentID(stream string, messageID string) string {
	return digestValue(
		strings.TrimSpace(stream) + "\x00" + strings.TrimSpace(messageID),
	)
}

func digestValue(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}

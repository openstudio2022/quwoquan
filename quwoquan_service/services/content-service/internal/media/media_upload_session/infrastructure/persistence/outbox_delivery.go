package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/content-service/internal/media/media_upload_session/domain/ports"
)

var _ ports.TransactionalOutbox = (*MongoStore)(nil)

func (store *MongoStore) ClaimPendingOutbox(
	ctx context.Context,
	ownerID string,
	now time.Time,
	lease time.Duration,
) (ports.OutboxEvent, bool, error) {
	ownerID = strings.TrimSpace(ownerID)
	now = now.UTC()
	if store == nil || store.outbox == nil || ownerID == "" || now.IsZero() || lease <= 0 {
		return ports.OutboxEvent{}, false, errors.New("media upload session outbox claim is invalid")
	}
	// The oldest unpublished record remains the head while leased or backed off,
	// preserving aggregate lifecycle order across retries.
	var candidate struct {
		ID string `bson:"_id"`
	}
	err := store.outbox.FindOne(
		ctx,
		bson.M{"publishedAt": nil},
		options.FindOne().SetSort(bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}}),
	).Decode(&candidate)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.OutboxEvent{}, false, nil
	}
	if err != nil {
		return ports.OutboxEvent{}, false, fmt.Errorf("select media upload outbox head: %w", err)
	}
	var record outboxDocument
	err = store.outbox.FindOneAndUpdate(
		ctx,
		bson.M{
			"_id": candidate.ID, "publishedAt": nil,
			"$and": bson.A{
				bson.M{"$or": bson.A{
					bson.M{"nextAttemptAt": bson.M{"$exists": false}},
					bson.M{"nextAttemptAt": bson.M{"$lte": now}},
				}},
				bson.M{"$or": bson.A{
					bson.M{"leaseOwner": bson.M{"$exists": false}},
					bson.M{"leaseExpiresAt": bson.M{"$lte": now}},
				}},
			},
		},
		bson.M{
			"$set": bson.M{"leaseOwner": ownerID, "leaseExpiresAt": now.Add(lease)},
			"$inc": bson.M{"attemptCount": 1},
		},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&record)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.OutboxEvent{}, false, nil
	}
	if err != nil {
		return ports.OutboxEvent{}, false, fmt.Errorf("claim media upload outbox: %w", err)
	}
	return ports.OutboxEvent{
		EventID: record.ID, EventType: record.EventType,
		AggregateType: record.AggregateType, AggregateID: record.AggregateID,
		AggregateVersion: record.AggregateVersion,
		Payload:          append([]byte(nil), record.Payload...), OccurredAt: record.OccurredAt,
		AttemptCount: record.AttemptCount,
	}, true, nil
}

func (store *MongoStore) MarkOutboxPublished(
	ctx context.Context,
	eventID string,
	ownerID string,
	publishedAt time.Time,
) error {
	result, err := store.outbox.UpdateOne(ctx, bson.M{
		"_id": strings.TrimSpace(eventID), "leaseOwner": strings.TrimSpace(ownerID),
		"publishedAt": nil,
	}, bson.M{
		"$set": bson.M{"publishedAt": publishedAt.UTC()},
		"$unset": bson.M{
			"leaseOwner": "", "leaseExpiresAt": "", "nextAttemptAt": "", "lastErrorCode": "",
		},
	})
	if err != nil {
		return fmt.Errorf("mark media upload outbox published: %w", err)
	}
	if result.MatchedCount != 1 {
		return ports.ErrOutboxClaimLost
	}
	return nil
}

func (store *MongoStore) ScheduleOutboxRetry(
	ctx context.Context,
	eventID string,
	ownerID string,
	nextAttemptAt time.Time,
	failureCode string,
) error {
	result, err := store.outbox.UpdateOne(ctx, bson.M{
		"_id": strings.TrimSpace(eventID), "leaseOwner": strings.TrimSpace(ownerID),
		"publishedAt": nil,
	}, bson.M{
		"$set": bson.M{
			"nextAttemptAt": nextAttemptAt.UTC(),
			"lastErrorCode": boundedOutboxFailureCode(failureCode),
		},
		"$unset": bson.M{"leaseOwner": "", "leaseExpiresAt": ""},
	})
	if err != nil {
		return fmt.Errorf("schedule media upload outbox retry: %w", err)
	}
	if result.MatchedCount != 1 {
		return ports.ErrOutboxClaimLost
	}
	return nil
}

func boundedOutboxFailureCode(value string) string {
	value = strings.TrimSpace(value)
	if value == "" || len(value) > 64 {
		return "delivery_failed"
	}
	return value
}

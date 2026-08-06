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

	"quwoquan_service/runtime/reliabletask"
	deliveryapplication "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

type notificationDeliveryOutboxDocument struct {
	ID               string            `bson:"_id"`
	AggregateID      string            `bson:"aggregateId"`
	AggregateVersion int64             `bson:"aggregateVersion"`
	EventType        string            `bson:"eventType"`
	Payload          map[string]string `bson:"payload"`
	CreatedAt        time.Time         `bson:"createdAt"`
	RetryCount       int               `bson:"retryCount"`
}

func (store *MongoNotificationDeliveryJobStore) ClaimPendingOutbox(
	ctx context.Context,
	ownerID string,
	now time.Time,
	lease time.Duration,
) (deliveryapplication.OutboxEvent, bool, error) {
	ownerID = strings.TrimSpace(ownerID)
	now = now.UTC()
	if store == nil || store.outbox == nil || ownerID == "" || now.IsZero() || lease <= 0 {
		return deliveryapplication.OutboxEvent{}, false, errors.New("NotificationDeliveryJob outbox claim is invalid")
	}
	filter := bson.M{
		"publishedAt": nil,
		"$and": bson.A{
			bson.M{"$or": bson.A{
				bson.M{"status": bson.M{"$in": bson.A{
					reliabletask.TaskOutboxStatusPending,
					reliabletask.TaskOutboxStatusFailed,
				}}},
				bson.M{
					"status":     reliabletask.TaskOutboxStatusDispatching,
					"leaseUntil": bson.M{"$lte": now},
				},
			}},
			bson.M{"$or": bson.A{
				bson.M{"nextAttemptAt": bson.M{"$exists": false}},
				bson.M{"nextAttemptAt": nil},
				bson.M{"nextAttemptAt": bson.M{"$lte": now}},
			}},
		},
	}
	update := bson.M{
		"$set": bson.M{
			"status":     reliabletask.TaskOutboxStatusDispatching,
			"leaseOwner": ownerID,
			"leaseUntil": now.Add(lease),
			"updatedAt":  now,
		},
		"$inc": bson.M{"retryCount": 1},
	}
	var document notificationDeliveryOutboxDocument
	err := store.outbox.FindOneAndUpdate(
		ctx,
		filter,
		update,
		options.FindOneAndUpdate().
			SetSort(bson.D{{Key: "createdAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetReturnDocument(options.After),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return deliveryapplication.OutboxEvent{}, false, nil
	}
	if err != nil {
		return deliveryapplication.OutboxEvent{}, false, fmt.Errorf("claim NotificationDeliveryJob outbox: %w", err)
	}
	return deliveryapplication.OutboxEvent{
		EventID: document.ID, EventType: document.EventType,
		AggregateID: document.AggregateID, AggregateVersion: document.AggregateVersion,
		Payload: document.Payload, OccurredAt: document.CreatedAt,
		AttemptCount: document.RetryCount,
	}, true, nil
}

func (store *MongoNotificationDeliveryJobStore) MarkPublished(
	ctx context.Context,
	eventID string,
	ownerID string,
	publishedAt time.Time,
) error {
	result, err := store.outbox.UpdateOne(ctx, bson.M{
		"_id": strings.TrimSpace(eventID), "leaseOwner": strings.TrimSpace(ownerID),
		"status": reliabletask.TaskOutboxStatusDispatching, "publishedAt": nil,
	}, bson.M{
		"$set": bson.M{
			"status":      reliabletask.TaskOutboxStatusDispatched,
			"publishedAt": publishedAt.UTC(),
			"updatedAt":   publishedAt.UTC(),
		},
		"$unset": bson.M{
			"leaseOwner": "", "leaseUntil": "", "nextAttemptAt": "", "lastFailureDigest": "",
		},
	})
	if err != nil {
		return fmt.Errorf("mark NotificationDeliveryJob outbox published: %w", err)
	}
	if result.MatchedCount != 1 {
		return deliveryapplication.ErrOutboxClaimLost
	}
	return nil
}

func (store *MongoNotificationDeliveryJobStore) SchedulePublicationRetry(
	ctx context.Context,
	eventID string,
	ownerID string,
	nextAttemptAt time.Time,
	failureDigest string,
) error {
	result, err := store.outbox.UpdateOne(ctx, bson.M{
		"_id": strings.TrimSpace(eventID), "leaseOwner": strings.TrimSpace(ownerID),
		"status": reliabletask.TaskOutboxStatusDispatching, "publishedAt": nil,
	}, bson.M{
		"$set": bson.M{
			"status":            reliabletask.TaskOutboxStatusFailed,
			"nextAttemptAt":     nextAttemptAt.UTC(),
			"lastFailureDigest": strings.TrimSpace(failureDigest),
			"updatedAt":         time.Now().UTC(),
		},
		"$unset": bson.M{"leaseOwner": "", "leaseUntil": ""},
	})
	if err != nil {
		return fmt.Errorf("schedule NotificationDeliveryJob outbox retry: %w", err)
	}
	if result.MatchedCount != 1 {
		return deliveryapplication.ErrOutboxClaimLost
	}
	return nil
}

var _ deliveryapplication.PublicationOutbox = (*MongoNotificationDeliveryJobStore)(nil)

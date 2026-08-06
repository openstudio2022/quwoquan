package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/ports"
)

var _ ports.TransactionalOutbox = (*Store)(nil)

func (store *Store) ClaimPendingOutbox(
	ctx context.Context,
	ownerID string,
	now time.Time,
	lease time.Duration,
) (ports.OutboxEvent, bool, error) {
	ownerID = strings.TrimSpace(ownerID)
	now = now.UTC()
	if store == nil || store.outbox == nil || ownerID == "" || now.IsZero() || lease <= 0 {
		return ports.OutboxEvent{}, false, model.ErrStorageUnavailable
	}
	claimUntil := now.Add(lease)
	var document outboxDocument
	err := store.outbox.FindOneAndUpdate(
		ctx,
		bson.M{
			"publishedAt": bson.M{"$exists": false},
			"$and": bson.A{
				bson.M{"$or": bson.A{
					bson.M{"nextAttemptAt": bson.M{"$exists": false}},
					bson.M{"nextAttemptAt": bson.M{"$lte": now}},
				}},
				bson.M{"$or": bson.A{
					bson.M{"claimUntil": bson.M{"$exists": false}},
					bson.M{"claimUntil": bson.M{"$lte": now}},
				}},
			},
		},
		bson.M{
			"$set": bson.M{"claimOwner": ownerID, "claimUntil": claimUntil},
			"$inc": bson.M{"attemptCount": 1},
		},
		options.FindOneAndUpdate().
			SetSort(bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetReturnDocument(options.After),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.OutboxEvent{}, false, nil
	}
	if err != nil {
		return ports.OutboxEvent{}, false, unavailable("claim data control outbox", err)
	}
	payload, err := skillDataControlEventPayload(document)
	if err != nil {
		return ports.OutboxEvent{}, false, unavailable("encode data control outbox", err)
	}
	return ports.OutboxEvent{
		EventID: document.ID, EventType: document.EventType,
		AggregateID: document.RequestID, AggregateVersion: document.AggregateRevision,
		Payload: payload, OccurredAt: document.OccurredAt.UTC(),
		AttemptCount: document.AttemptCount,
	}, true, nil
}

func (store *Store) MarkOutboxPublished(
	ctx context.Context,
	eventID string,
	ownerID string,
	publishedAt time.Time,
) error {
	if store == nil || store.outbox == nil || strings.TrimSpace(eventID) == "" ||
		strings.TrimSpace(ownerID) == "" || publishedAt.IsZero() {
		return model.ErrStorageUnavailable
	}
	result, err := store.outbox.UpdateOne(
		ctx,
		bson.M{
			"_id": strings.TrimSpace(eventID), "claimOwner": strings.TrimSpace(ownerID),
			"claimUntil":  bson.M{"$gt": publishedAt.UTC()},
			"publishedAt": bson.M{"$exists": false},
		},
		bson.M{
			"$set": bson.M{"publishedAt": publishedAt.UTC()},
			"$unset": bson.M{
				"claimOwner": "", "claimUntil": "", "nextAttemptAt": "", "lastErrorCode": "",
			},
		},
	)
	if err != nil {
		return unavailable("mark data control outbox published", err)
	}
	if result.MatchedCount != 1 {
		return ports.ErrOutboxClaimLost
	}
	return nil
}

func (store *Store) ScheduleOutboxRetry(
	ctx context.Context,
	eventID string,
	ownerID string,
	failedAt time.Time,
	nextAttemptAt time.Time,
	failureCode string,
) error {
	if store == nil || store.outbox == nil || strings.TrimSpace(eventID) == "" ||
		strings.TrimSpace(ownerID) == "" || failedAt.IsZero() ||
		nextAttemptAt.IsZero() || nextAttemptAt.Before(failedAt) {
		return model.ErrStorageUnavailable
	}
	result, err := store.outbox.UpdateOne(
		ctx,
		bson.M{
			"_id": strings.TrimSpace(eventID), "claimOwner": strings.TrimSpace(ownerID),
			"claimUntil":  bson.M{"$gt": failedAt.UTC()},
			"publishedAt": bson.M{"$exists": false},
		},
		bson.M{
			"$set": bson.M{
				"nextAttemptAt": nextAttemptAt.UTC(),
				"lastErrorCode": boundedOutboxFailureCode(failureCode),
			},
			"$unset": bson.M{"claimOwner": "", "claimUntil": ""},
		},
	)
	if err != nil {
		return unavailable("schedule data control outbox retry", err)
	}
	if result.MatchedCount != 1 {
		return ports.ErrOutboxClaimLost
	}
	return nil
}

func skillDataControlEventPayload(document outboxDocument) ([]byte, error) {
	request := document.Payload
	payload := map[string]any{
		"requestId": request.RequestID,
		"accountId": request.AccountID,
		"skillId":   request.SkillID,
		"status":    request.Status,
		"revision":  request.Revision,
	}
	switch document.EventType {
	case model.EventRequested:
		payload["requestedActions"] = request.RequestedActions
		payload["createdAt"] = request.CreatedAt.UTC()
	case model.EventConfirmed:
		payload["confirmedAt"] = request.ConfirmedAt
		payload["updatedAt"] = request.UpdatedAt.UTC()
	case model.EventCompleted:
		payload["completedActions"] = request.CompletedActions
		payload["completedAt"] = request.CompletedAt
		payload["updatedAt"] = request.UpdatedAt.UTC()
	case model.EventCancelled:
		payload["completedAt"] = request.CompletedAt
		payload["updatedAt"] = request.UpdatedAt.UTC()
	case model.EventFailed:
		payload["completedActions"] = request.CompletedActions
		payload["failedAction"] = request.FailedAction
		payload["failureCode"] = request.FailureCode
		payload["updatedAt"] = request.UpdatedAt.UTC()
	default:
		return nil, model.ErrInvalidArgument
	}
	return json.Marshal(payload)
}

func boundedOutboxFailureCode(value string) string {
	value = strings.TrimSpace(value)
	if value == "" || len(value) > 64 {
		return "delivery_failed"
	}
	return value
}

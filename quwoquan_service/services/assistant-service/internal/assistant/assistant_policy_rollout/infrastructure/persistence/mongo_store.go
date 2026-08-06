package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/ports"
)

type MongoStore struct {
	rollouts *mongo.Collection
	receipts *mongo.Collection
	outbox   *mongo.Collection
}

type commandReceipt struct {
	ID            string        `bson:"_id"`
	CommandDigest string        `bson:"commandDigest"`
	PolicyID      string        `bson:"policyId"`
	Revision      int           `bson:"revision"`
	Rollout       model.Rollout `bson:"rollout"`
	CreatedAt     time.Time     `bson:"createdAt"`
}

type auditOutboxRecord struct {
	ID            string                   `bson:"_id"`
	EventType     string                   `bson:"eventType"`
	PolicyID      string                   `bson:"policyId"`
	Revision      int                      `bson:"revision"`
	Status        string                   `bson:"status"`
	Assignments   []model.CohortAssignment `bson:"assignments"`
	ActivatedAt   time.Time                `bson:"activatedAt"`
	OccurredAt    time.Time                `bson:"occurredAt"`
	PublishedAt   *time.Time               `bson:"publishedAt,omitempty"`
	PublishedRef  string                   `bson:"publishedRef,omitempty"`
	ClaimOwner    string                   `bson:"claimOwner,omitempty"`
	ClaimUntil    *time.Time               `bson:"claimUntil,omitempty"`
	NextAttemptAt *time.Time               `bson:"nextAttemptAt,omitempty"`
	AttemptCount  int                      `bson:"attemptCount,omitempty"`
	LastErrorCode string                   `bson:"lastErrorCode,omitempty"`
}

type auditOutboxPayload struct {
	PolicyID    string                   `json:"policyId"`
	Revision    int                      `json:"revision"`
	Status      string                   `json:"status"`
	Assignments []model.CohortAssignment `json:"assignments"`
	ActivatedAt time.Time                `json:"activatedAt"`
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		return &MongoStore{}
	}
	return &MongoStore{
		rollouts: database.Collection("assistant_policy_rollouts"),
		receipts: database.Collection("assistant_policy_rollout_receipts"),
		outbox:   database.Collection("assistant_policy_rollout_outbox"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if store == nil || store.rollouts == nil ||
		store.receipts == nil || store.outbox == nil {
		return model.ErrStorageUnavailable
	}
	for collection, indexes := range map[*mongo.Collection][]mongo.IndexModel{
		store.rollouts: {
			{
				Keys:    bson.D{{Key: "policyId", Value: 1}},
				Options: options.Index().SetName("uq_assistant_policy_rollout_policy").SetUnique(true),
			},
		},
		store.receipts: {
			{
				Keys:    bson.D{{Key: "policyId", Value: 1}, {Key: "revision", Value: -1}},
				Options: options.Index().SetName("idx_assistant_policy_rollout_receipt_policy"),
			},
		},
		store.outbox: {
			{
				Keys: bson.D{
					{Key: "publishedAt", Value: 1},
					{Key: "nextAttemptAt", Value: 1},
					{Key: "claimUntil", Value: 1},
					{Key: "occurredAt", Value: 1},
				},
				Options: options.Index().SetName("idx_assistant_policy_rollout_outbox_pending"),
			},
		},
	} {
		if _, err := collection.Indexes().CreateMany(ctx, indexes); err != nil {
			return fmt.Errorf("%w: ensure rollout indexes: %v", model.ErrStorageUnavailable, err)
		}
	}
	return nil
}

func (store *MongoStore) Get(
	ctx context.Context,
	policyID string,
) (model.Rollout, bool, error) {
	if store == nil || store.rollouts == nil {
		return model.Rollout{}, false, model.ErrStorageUnavailable
	}
	var rollout model.Rollout
	err := store.rollouts.FindOne(ctx, bson.M{
		"policyId": strings.TrimSpace(policyID),
	}).Decode(&rollout)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Rollout{}, false, nil
	}
	if err != nil {
		return model.Rollout{}, false, fmt.Errorf("%w: get rollout: %v", model.ErrStorageUnavailable, err)
	}
	return rollout, true, nil
}

// GetCommandResult returns the original result for an idempotent command
// before callers evaluate the current rollout revision. This ordering lets a
// retried activation replay successfully after its first commit advanced the
// revision, while still rejecting a reused command identity with different
// input.
func (store *MongoStore) GetCommandResult(
	ctx context.Context,
	commandID string,
	commandDigest string,
	policyID string,
) (model.Rollout, bool, error) {
	if store == nil || store.receipts == nil {
		return model.Rollout{}, false, model.ErrStorageUnavailable
	}
	commandID = strings.TrimSpace(commandID)
	commandDigest = strings.TrimSpace(commandDigest)
	policyID = strings.TrimSpace(policyID)
	if commandID == "" || commandDigest == "" || policyID == "" {
		return model.Rollout{}, false, model.ErrInvalidArgument
	}
	var receipt commandReceipt
	err := store.receipts.FindOne(ctx, bson.M{"_id": commandID}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Rollout{}, false, nil
	}
	if err != nil {
		return model.Rollout{}, false, fmt.Errorf(
			"%w: get rollout receipt: %v",
			model.ErrStorageUnavailable,
			err,
		)
	}
	if receipt.CommandDigest != commandDigest || receipt.PolicyID != policyID {
		return model.Rollout{}, false, model.ErrIdempotencyConflict
	}
	return receipt.Rollout, true, nil
}

func (store *MongoStore) ClaimPendingOutbox(
	ctx context.Context,
	ownerID string,
	now time.Time,
	lease time.Duration,
) (ports.OutboxEvent, bool, error) {
	if store == nil || store.outbox == nil {
		return ports.OutboxEvent{}, false, model.ErrStorageUnavailable
	}
	ownerID = strings.TrimSpace(ownerID)
	now = now.UTC()
	if ownerID == "" || now.IsZero() || lease <= 0 {
		return ports.OutboxEvent{}, false, model.ErrInvalidArgument
	}
	var record auditOutboxRecord
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
			"$set": bson.M{
				"claimOwner": ownerID,
				"claimUntil": now.Add(lease),
			},
			"$inc": bson.M{"attemptCount": 1},
		},
		options.FindOneAndUpdate().
			SetSort(bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetReturnDocument(options.After),
	).Decode(&record)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.OutboxEvent{}, false, nil
	}
	if err != nil {
		return ports.OutboxEvent{}, false, fmt.Errorf(
			"%w: claim policy rollout outbox: %v",
			model.ErrStorageUnavailable,
			err,
		)
	}
	payload, err := json.Marshal(auditOutboxPayload{
		PolicyID: record.PolicyID, Revision: record.Revision,
		Status: record.Status, Assignments: record.Assignments,
		ActivatedAt: record.ActivatedAt.UTC(),
	})
	if err != nil {
		return ports.OutboxEvent{}, false, fmt.Errorf(
			"%w: marshal policy rollout outbox payload: %v",
			model.ErrStorageUnavailable,
			err,
		)
	}
	return ports.OutboxEvent{
		EventID: record.ID, EventType: record.EventType,
		AggregateID: record.PolicyID, AggregateVersion: record.Revision,
		OccurredAt: record.OccurredAt.UTC(), Payload: payload,
		AttemptCount: record.AttemptCount,
	}, true, nil
}

func (store *MongoStore) MarkOutboxPublished(
	ctx context.Context,
	eventID string,
	ownerID string,
	publishedRef string,
	publishedAt time.Time,
) error {
	if store == nil || store.outbox == nil {
		return model.ErrStorageUnavailable
	}
	result, err := store.outbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         strings.TrimSpace(eventID),
			"claimOwner":  strings.TrimSpace(ownerID),
			"claimUntil":  bson.M{"$gt": publishedAt.UTC()},
			"publishedAt": bson.M{"$exists": false},
		},
		bson.M{
			"$set": bson.M{
				"publishedAt":  publishedAt.UTC(),
				"publishedRef": strings.TrimSpace(publishedRef),
			},
			"$unset": bson.M{
				"claimOwner": "", "claimUntil": "", "nextAttemptAt": "",
				"lastErrorCode": "",
			},
		},
	)
	if err != nil {
		return fmt.Errorf("%w: mark policy rollout outbox published: %v", model.ErrStorageUnavailable, err)
	}
	if result.MatchedCount == 0 {
		return ports.ErrOutboxClaimLost
	}
	return nil
}

func (store *MongoStore) ScheduleOutboxRetry(
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
			"_id":         strings.TrimSpace(eventID),
			"claimOwner":  strings.TrimSpace(ownerID),
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
		return fmt.Errorf(
			"%w: schedule policy rollout outbox retry: %v",
			model.ErrStorageUnavailable,
			err,
		)
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

func (store *MongoStore) Commit(
	ctx context.Context,
	commandID string,
	commandDigest string,
	expectedRevision int,
	next model.Rollout,
	eventType string,
) (model.Rollout, bool, error) {
	if store == nil || store.rollouts == nil ||
		store.receipts == nil || store.outbox == nil {
		return model.Rollout{}, false, model.ErrStorageUnavailable
	}
	commandID = strings.TrimSpace(commandID)
	commandDigest = strings.TrimSpace(commandDigest)
	if commandID == "" || commandDigest == "" ||
		next.PolicyID == "" || next.Revision != expectedRevision+1 {
		return model.Rollout{}, false, model.ErrInvalidArgument
	}
	session, err := store.rollouts.Database().Client().StartSession()
	if err != nil {
		return model.Rollout{}, false, fmt.Errorf("%w: start transaction: %v", model.ErrStorageUnavailable, err)
	}
	defer session.EndSession(ctx)

	result := model.Rollout{}
	replayed := false
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var receipt commandReceipt
		receiptErr := store.receipts.FindOne(txCtx, bson.M{"_id": commandID}).Decode(&receipt)
		if receiptErr == nil {
			if receipt.CommandDigest != commandDigest ||
				receipt.PolicyID != next.PolicyID {
				return nil, model.ErrIdempotencyConflict
			}
			result = receipt.Rollout
			replayed = true
			return nil, nil
		}
		if !errors.Is(receiptErr, mongo.ErrNoDocuments) {
			return nil, receiptErr
		}

		if expectedRevision == 0 {
			if _, insertErr := store.rollouts.InsertOne(txCtx, next); insertErr != nil {
				if mongo.IsDuplicateKeyError(insertErr) {
					return nil, model.ErrRevisionConflict
				}
				return nil, insertErr
			}
		} else {
			updateResult, replaceErr := store.rollouts.ReplaceOne(
				txCtx,
				bson.M{
					"policyId": next.PolicyID,
					"revision": expectedRevision,
				},
				next,
			)
			if replaceErr != nil {
				return nil, replaceErr
			}
			if updateResult.MatchedCount != 1 {
				return nil, model.ErrRevisionConflict
			}
		}
		now := time.Now().UTC()
		if _, receiptErr = store.receipts.InsertOne(txCtx, commandReceipt{
			ID:            commandID,
			CommandDigest: commandDigest,
			PolicyID:      next.PolicyID,
			Revision:      next.Revision,
			Rollout:       next,
			CreatedAt:     now,
		}); receiptErr != nil {
			return nil, receiptErr
		}
		if _, outboxErr := store.outbox.InsertOne(txCtx, auditOutboxRecord{
			ID:          commandID,
			EventType:   eventType,
			PolicyID:    next.PolicyID,
			Revision:    next.Revision,
			Status:      next.Status,
			Assignments: append([]model.CohortAssignment(nil), next.Assignments...),
			ActivatedAt: next.ActivatedAt,
			OccurredAt:  next.ActivatedAt,
		}); outboxErr != nil {
			return nil, outboxErr
		}
		result = next
		return nil, nil
	})
	if err != nil {
		switch {
		case errors.Is(err, model.ErrIdempotencyConflict),
			errors.Is(err, model.ErrRevisionConflict):
			return model.Rollout{}, false, err
		default:
			return model.Rollout{}, false, fmt.Errorf("%w: rollout transaction: %v", model.ErrStorageUnavailable, err)
		}
	}
	return result, replayed, nil
}

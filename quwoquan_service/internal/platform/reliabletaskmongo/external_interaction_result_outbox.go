package reliabletaskmongo

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
)

func (s *Store) RecordProviderAttemptWithResultOutbox(
	ctx context.Context,
	record reliabletask.ProviderAttemptRecord,
) (reliabletask.ProviderAttemptRecord, error) {
	if strings.TrimSpace(record.AttemptID) == "" {
		record.AttemptID = reliabletask.NewRecordID("attempt")
	}
	if record.CreatedAt.IsZero() {
		record.CreatedAt = time.Now().UTC()
	}
	if record.Attributes == nil {
		record.Attributes = map[string]string{}
	}
	if strings.TrimSpace(record.ProviderRequestDigest) == "" {
		record.ProviderRequestDigest = reliabletask.ProviderRequestDigest(
			record.ProviderRequestID,
		)
	}
	if strings.TrimSpace(record.RecoveryAction) == "" {
		record.RecoveryAction = "none"
	}
	if strings.TrimSpace(record.Status) == "" {
		return reliabletask.ProviderAttemptRecord{}, errors.New(
			"provider attempt result status is required",
		)
	}
	outbox := reliabletask.ExternalInteractionResultOutboxRecord{
		EventID:               record.AttemptID,
		RequestID:             record.RequestID,
		Operation:             record.Operation,
		ResultStatus:          record.Status,
		Provider:              record.Provider,
		ProviderRequestDigest: record.ProviderRequestDigest,
		NormalizedError:       record.NormalizedError,
		RecoveryAction:        record.RecoveryAction,
		OccurredAt:            record.CreatedAt.UTC(),
		DeliveryStatus:        reliabletask.ExternalInteractionResultOutboxPending,
		CreatedAt:             record.CreatedAt.UTC(),
		UpdatedAt:             record.CreatedAt.UTC(),
	}
	err := s.RunInTransaction(ctx, func(txCtx context.Context) error {
		if err := s.insertProviderAttemptOnce(txCtx, record); err != nil {
			return err
		}
		return s.insertResultOutboxOnce(txCtx, outbox)
	})
	if err != nil {
		return reliabletask.ProviderAttemptRecord{}, err
	}
	return record, nil
}

func (s *Store) insertProviderAttemptOnce(
	ctx context.Context,
	record reliabletask.ProviderAttemptRecord,
) error {
	if _, err := s.attempts.InsertOne(ctx, record); err == nil {
		return nil
	} else if !mongo.IsDuplicateKeyError(err) {
		return err
	}
	var existing reliabletask.ProviderAttemptRecord
	if err := s.attempts.FindOne(
		ctx,
		bson.M{"_id": record.AttemptID},
	).Decode(&existing); err != nil {
		return fmt.Errorf("read existing provider attempt: %w", err)
	}
	if existing.RequestID != record.RequestID ||
		existing.Operation != record.Operation ||
		existing.Provider != record.Provider ||
		existing.ProviderRequestDigest != record.ProviderRequestDigest ||
		existing.Status != record.Status ||
		existing.RecoveryAction != record.RecoveryAction {
		return fmt.Errorf(
			"provider attempt %s conflicts with its immutable audit record",
			record.AttemptID,
		)
	}
	return nil
}

func (s *Store) insertResultOutboxOnce(
	ctx context.Context,
	record reliabletask.ExternalInteractionResultOutboxRecord,
) error {
	if _, err := s.resultOutboxes.InsertOne(ctx, record); err == nil {
		return nil
	} else if !mongo.IsDuplicateKeyError(err) {
		return err
	}
	var existing reliabletask.ExternalInteractionResultOutboxRecord
	if err := s.resultOutboxes.FindOne(
		ctx,
		bson.M{"_id": record.EventID},
	).Decode(&existing); err != nil {
		return fmt.Errorf("read existing provider result outbox: %w", err)
	}
	if existing.RequestID != record.RequestID ||
		existing.Operation != record.Operation ||
		existing.ResultStatus != record.ResultStatus ||
		existing.Provider != record.Provider ||
		existing.ProviderRequestDigest != record.ProviderRequestDigest ||
		existing.RecoveryAction != record.RecoveryAction {
		return fmt.Errorf(
			"provider result outbox %s conflicts with immutable attempt",
			record.EventID,
		)
	}
	return nil
}

func (s *Store) LeaseNextExternalInteractionResultOutbox(
	ctx context.Context,
	leaseOwner string,
	leaseDuration time.Duration,
) (reliabletask.ExternalInteractionResultOutboxRecord, bool, error) {
	now := time.Now().UTC()
	var record reliabletask.ExternalInteractionResultOutboxRecord
	err := s.resultOutboxes.FindOneAndUpdate(
		ctx,
		bson.M{
			"$or": []bson.M{
				{
					"deliveryStatus": reliabletask.ExternalInteractionResultOutboxPending,
				},
				{
					"deliveryStatus": reliabletask.ExternalInteractionResultOutboxPublishing,
					"leaseExpiresAt": bson.M{"$lte": now},
				},
			},
		},
		bson.M{"$set": bson.M{
			"deliveryStatus": reliabletask.ExternalInteractionResultOutboxPublishing,
			"leaseOwner":     strings.TrimSpace(leaseOwner),
			"leaseExpiresAt": now.Add(leaseDuration),
			"updatedAt":      now,
		}},
		options.FindOneAndUpdate().
			SetSort(bson.D{
				{Key: "createdAt", Value: 1},
				{Key: "_id", Value: 1},
			}).
			SetReturnDocument(options.After),
	).Decode(&record)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return reliabletask.ExternalInteractionResultOutboxRecord{}, false, nil
	}
	if err != nil {
		return reliabletask.ExternalInteractionResultOutboxRecord{}, false, err
	}
	return record, true, nil
}

func (s *Store) AcknowledgeExternalInteractionResultOutbox(
	ctx context.Context,
	eventID string,
	leaseOwner string,
) (bool, error) {
	now := time.Now().UTC()
	result, err := s.resultOutboxes.UpdateOne(
		ctx,
		bson.M{
			"_id":            strings.TrimSpace(eventID),
			"deliveryStatus": reliabletask.ExternalInteractionResultOutboxPublishing,
			"leaseOwner":     strings.TrimSpace(leaseOwner),
		},
		bson.M{
			"$set": bson.M{
				"deliveryStatus": reliabletask.ExternalInteractionResultOutboxPublished,
				"publishedAt":    now,
				"updatedAt":      now,
			},
			"$unset": bson.M{
				"leaseOwner":     "",
				"leaseExpiresAt": "",
			},
		},
	)
	if err != nil {
		return false, err
	}
	return result.MatchedCount == 1, nil
}

func (s *Store) ReleaseExternalInteractionResultOutboxLease(
	ctx context.Context,
	eventID string,
	leaseOwner string,
) error {
	_, err := s.resultOutboxes.UpdateOne(
		ctx,
		bson.M{
			"_id":            strings.TrimSpace(eventID),
			"deliveryStatus": reliabletask.ExternalInteractionResultOutboxPublishing,
			"leaseOwner":     strings.TrimSpace(leaseOwner),
		},
		bson.M{
			"$set": bson.M{
				"deliveryStatus": reliabletask.ExternalInteractionResultOutboxPending,
				"updatedAt":      time.Now().UTC(),
			},
			"$unset": bson.M{
				"leaseOwner":     "",
				"leaseExpiresAt": "",
			},
		},
	)
	return err
}

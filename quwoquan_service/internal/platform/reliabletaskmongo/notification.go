package reliabletaskmongo

import (
	"context"
	"errors"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/reliabletask"
)

func (s *Store) CreateNotification(
	ctx context.Context,
	record reliabletask.NotificationOutboxRecord,
) (reliabletask.NotificationOutboxRecord, error) {
	now := time.Now().UTC()
	if strings.TrimSpace(record.DedupeKey) != "" {
		var existing reliabletask.NotificationOutboxRecord
		err := s.notifications.FindOne(
			ctx,
			bson.M{"dedupeKey": strings.TrimSpace(record.DedupeKey)},
		).Decode(&existing)
		if err == nil {
			return existing, nil
		}
		if !errors.Is(err, mongo.ErrNoDocuments) {
			return reliabletask.NotificationOutboxRecord{}, err
		}
	}
	if record.NotificationID == "" {
		record.NotificationID = reliabletask.NewRecordID("notification")
	}
	if record.Status == "" {
		record.Status = reliabletask.NotificationStatusPending
	}
	if record.CreatedAt.IsZero() {
		record.CreatedAt = now
	}
	record.UpdatedAt = now
	record.Payload = reliabletask.CloneStringMap(record.Payload)
	_, err := s.notifications.InsertOne(ctx, record)
	if mongo.IsDuplicateKeyError(err) && strings.TrimSpace(record.DedupeKey) != "" {
		var existing reliabletask.NotificationOutboxRecord
		if findErr := s.notifications.FindOne(
			ctx,
			bson.M{"dedupeKey": strings.TrimSpace(record.DedupeKey)},
		).Decode(&existing); findErr != nil {
			return reliabletask.NotificationOutboxRecord{}, err
		}
		return existing, nil
	}
	return record, err
}

func (s *Store) ClaimNotification(
	ctx context.Context,
	eventTypes []string,
	workerID string,
	leaseTTL time.Duration,
	now time.Time,
) (*reliabletask.NotificationOutboxRecord, error) {
	filter := bson.M{
		"nextAttemptAt": bson.M{"$lte": now.UTC()},
		"$or": bson.A{
			bson.M{"status": reliabletask.NotificationStatusPending},
			bson.M{"status": reliabletask.NotificationStatusRetryWait},
			bson.M{
				"status":     reliabletask.NotificationStatusProcessing,
				"leaseUntil": bson.M{"$lte": now.UTC()},
			},
		},
	}
	if len(eventTypes) > 0 {
		filter["eventType"] = bson.M{"$in": eventTypes}
	}
	token := reliabletask.NewRecordID("notification-lease")
	update := bson.M{
		"$set": bson.M{
			"status":     reliabletask.NotificationStatusProcessing,
			"leaseOwner": strings.TrimSpace(workerID),
			"leaseToken": token,
			"leaseUntil": now.Add(leaseTTL).UTC(),
			"updatedAt":  now.UTC(),
		},
	}
	opts := options.FindOneAndUpdate().
		SetSort(bson.D{{Key: "nextAttemptAt", Value: 1}}).
		SetReturnDocument(options.After)
	var notification reliabletask.NotificationOutboxRecord
	if err := s.notifications.FindOneAndUpdate(ctx, filter, update, opts).Decode(&notification); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &notification, nil
}

func (s *Store) EnsureRecipientLedgers(
	ctx context.Context,
	notificationID string,
	eventType string,
	recipientIDs []string,
) error {
	now := time.Now().UTC()
	for _, recipientID := range reliabletask.DedupeStrings(recipientIDs) {
		record := reliabletask.NotificationDeliveryLedgerRecord{
			LedgerID:       reliabletask.DeliveryLedgerID(notificationID, recipientID),
			NotificationID: notificationID,
			EventType:      eventType,
			RecipientID:    recipientID,
			Status:         reliabletask.RecipientStatusPending,
			UpdatedAt:      now,
		}
		_, err := s.ledgers.UpdateOne(ctx, bson.M{"_id": record.LedgerID}, bson.M{
			"$setOnInsert": record,
		}, options.UpdateOne().SetUpsert(true))
		if err != nil {
			return err
		}
	}
	return nil
}

func (s *Store) ListPendingRecipients(
	ctx context.Context,
	notificationID string,
) ([]reliabletask.NotificationDeliveryLedgerRecord, error) {
	cursor, err := s.ledgers.Find(ctx, bson.M{
		"notificationId": notificationID,
		"status":         bson.M{"$ne": reliabletask.RecipientStatusDelivered},
	})
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var records []reliabletask.NotificationDeliveryLedgerRecord
	if err := cursor.All(ctx, &records); err != nil {
		return nil, err
	}
	sort.Slice(records, func(i, j int) bool {
		return records[i].RecipientID < records[j].RecipientID
	})
	return records, nil
}

func (s *Store) MarkRecipientDelivered(
	ctx context.Context,
	notificationID string,
	recipientID string,
	syncSeq int64,
) error {
	_, err := s.ledgers.UpdateOne(
		ctx,
		bson.M{"_id": reliabletask.DeliveryLedgerID(notificationID, recipientID)},
		bson.M{
			"$set": bson.M{
				"status":       reliabletask.RecipientStatusDelivered,
				"deliveredSeq": syncSeq,
				"updatedAt":    time.Now().UTC(),
				"lastFailure":  nil,
			},
		},
	)
	return err
}

func (s *Store) MarkRecipientFailed(
	ctx context.Context,
	notificationID string,
	recipientID string,
	failure reliabletask.RuntimeFailure,
) error {
	_, err := s.ledgers.UpdateOne(ctx, bson.M{
		"_id":    reliabletask.DeliveryLedgerID(notificationID, recipientID),
		"status": bson.M{"$ne": reliabletask.RecipientStatusDelivered},
	}, bson.M{
		"$set": bson.M{
			"status":      reliabletask.RecipientStatusFailed,
			"updatedAt":   time.Now().UTC(),
			"lastFailure": failure,
		},
		"$inc": bson.M{"attempts": 1},
	})
	return err
}

func (s *Store) RecordProviderAttempt(
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
	_, err := s.attempts.InsertOne(ctx, record)
	return record, err
}

func (s *Store) ListProviderAttempts(
	ctx context.Context,
	requestID string,
) ([]reliabletask.ProviderAttemptRecord, error) {
	cursor, err := s.attempts.Find(
		ctx,
		bson.M{"requestId": strings.TrimSpace(requestID)},
		options.Find().SetSort(bson.D{{Key: "createdAt", Value: 1}}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var records []reliabletask.ProviderAttemptRecord
	for cursor.Next(ctx) {
		var record reliabletask.ProviderAttemptRecord
		if err := cursor.Decode(&record); err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	return records, cursor.Err()
}

func (s *Store) CompleteNotification(
	ctx context.Context,
	notificationID string,
	leaseToken string,
) error {
	res, err := s.notifications.UpdateOne(
		ctx,
		bson.M{"_id": notificationID, "leaseToken": leaseToken},
		bson.M{
			"$set": bson.M{
				"status":     reliabletask.NotificationStatusSucceeded,
				"leaseOwner": "",
				"leaseToken": "",
				"updatedAt":  time.Now().UTC(),
			},
		},
	)
	if err != nil {
		return err
	}
	if res.MatchedCount == 0 {
		return reliabletask.ErrLeaseMismatch
	}
	return nil
}

func (s *Store) RetryNotification(
	ctx context.Context,
	notificationID string,
	leaseToken string,
	failure reliabletask.RuntimeFailure,
	policy reliabletask.RetryPolicy,
	now time.Time,
) error {
	var notification reliabletask.NotificationOutboxRecord
	if err := s.notifications.FindOne(
		ctx,
		bson.M{"_id": notificationID, "leaseToken": leaseToken},
	).Decode(&notification); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return reliabletask.ErrLeaseMismatch
		}
		return err
	}
	notification.Attempts++
	notification.LastFailure = &failure
	notification.LeaseOwner = ""
	notification.LeaseToken = ""
	notification.UpdatedAt = now.UTC()
	if delay, retry := policy.NextDelay(notification.Attempts); retry {
		notification.Status = reliabletask.NotificationStatusRetryWait
		notification.NextAttemptAt = now.Add(delay).UTC()
	} else {
		notification.Status = reliabletask.NotificationStatusDead
	}
	_, err := s.notifications.ReplaceOne(ctx, bson.M{"_id": notificationID}, notification)
	return err
}

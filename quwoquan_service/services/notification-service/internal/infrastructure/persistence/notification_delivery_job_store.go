package persistence

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/internal/platform/reliabletaskmongo"
	rtid "quwoquan_service/runtime/id"
	"quwoquan_service/runtime/reliabletask"
	notification "quwoquan_service/services/notification-service/internal/domain/notification"
)

const (
	notificationDeliveryJobCollection        = "notification_delivery_jobs"
	notificationDeliveryJobReceiptCollection = "notification_delivery_jobs_command_receipts"
	notificationDeliveryJobOutboxCollection  = "notification_delivery_jobs_outbox"
)

type notificationDeliveryJobReceiptDocument struct {
	ID            string                                            `bson:"_id"`
	CommandName   string                                            `bson:"commandName"`
	CommandDigest string                                            `bson:"commandDigest"`
	Result        notification.RecoverNotificationDeliveryJobResult `bson:"result"`
	CreatedAt     time.Time                                         `bson:"createdAt"`
}

type notificationDeliveryJobEventDocument struct {
	ID               string            `bson:"_id"`
	AggregateID      string            `bson:"aggregateId"`
	AggregateVersion int64             `bson:"aggregateVersion"`
	EventType        string            `bson:"eventType"`
	Payload          map[string]string `bson:"payload"`
	Status           string            `bson:"status"`
	CreatedAt        time.Time         `bson:"createdAt"`
}

// MongoNotificationDeliveryJobStore 是 NotificationDeliveryJob 的对象专属
// aggregate store。可靠 worker 只复用租约算法，不再共享旧 notification_outbox
// 权威集合；state、command receipt 与 object outbox 始终在同一事务中提交。
type MongoNotificationDeliveryJobStore struct {
	*reliabletaskmongo.Store
	db       *mongo.Database
	jobs     *mongo.Collection
	receipts *mongo.Collection
	outbox   *mongo.Collection
}

func NewMongoNotificationDeliveryJobStore(db *mongo.Database) *MongoNotificationDeliveryJobStore {
	return &MongoNotificationDeliveryJobStore{
		Store:    reliabletaskmongo.NewNotificationDeliveryJobs(db),
		db:       db,
		jobs:     db.Collection(notificationDeliveryJobCollection),
		receipts: db.Collection(notificationDeliveryJobReceiptCollection),
		outbox:   db.Collection(notificationDeliveryJobOutboxCollection),
	}
}

func (s *MongoNotificationDeliveryJobStore) EnsureIndexes(ctx context.Context) error {
	if err := s.Store.EnsureIndexes(ctx); err != nil {
		return err
	}
	if _, err := s.jobs.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "deliveryKey", Value: 1},
				{Key: "destinationRef", Value: 1},
			},
			Options: options.Index().
				SetName("uq_notification_incoming_call_endpoint").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"deliveryKey":    bson.M{"$type": "string"},
					"destinationRef": bson.M{"$type": "string"},
				}),
		},
		{
			Keys: bson.D{
				{Key: "deliveryKey", Value: 1},
				{Key: "deviceId", Value: 1},
			},
			Options: options.Index().
				SetName("uq_notification_incoming_call_device").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"deliveryKey": bson.M{"$type": "string"},
					"deviceId":    bson.M{"$type": "string"},
				}),
		},
		{
			Keys: bson.D{
				{Key: "callId", Value: 1},
				{Key: "status", Value: 1},
				{Key: "updatedAt", Value: 1},
			},
			Options: options.Index().
				SetName("idx_notification_incoming_call_call_status").
				SetSparse(true),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "ackDeadlineAt", Value: 1},
			},
			Options: options.Index().
				SetName("idx_notification_incoming_call_ack_deadline").
				SetSparse(true),
		},
		{
			Keys: bson.D{
				{Key: "expiresAt", Value: 1},
				{Key: "status", Value: 1},
			},
			Options: options.Index().
				SetName("idx_notification_incoming_call_expiry").
				SetSparse(true),
		},
		{
			Keys: bson.D{
				{Key: "status", Value: 1},
				{Key: "cancellationPushRequired", Value: 1},
				{Key: "cancellationPushSubmittedAt", Value: 1},
			},
			Options: options.Index().
				SetName("idx_notification_incoming_call_cancel_push").
				SetSparse(true),
		},
	}); err != nil {
		return err
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "result.jobId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_notification_delivery_job_receipts_job"),
		},
	}); err != nil {
		return err
	}
	_, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}},
			Options: options.Index().SetName("idx_notification_delivery_job_outbox_version").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "status", Value: 1}, {Key: "createdAt", Value: 1}},
			Options: options.Index().SetName("idx_notification_delivery_job_outbox_pending"),
		},
	})
	return err
}

func (s *MongoNotificationDeliveryJobStore) CreateNotification(
	ctx context.Context,
	record reliabletask.NotificationOutboxRecord,
) (reliabletask.NotificationOutboxRecord, error) {
	if strings.TrimSpace(record.NotificationID) == "" {
		jobID, err := rtid.Generate(rtid.PrefixNotificationDeliveryJob)
		if err != nil {
			return reliabletask.NotificationOutboxRecord{}, err
		}
		record.NotificationID = jobID
	}
	if strings.TrimSpace(record.SubjectNotificationID) == "" {
		record.SubjectNotificationID = strings.TrimSpace(record.AggregateID)
	}
	if strings.TrimSpace(record.Channel) == "" {
		record.Channel = "push"
	}
	if strings.TrimSpace(record.DestinationRef) == "" && len(record.RecipientIDs) == 1 {
		record.DestinationRef = strings.TrimSpace(record.RecipientIDs[0])
	}
	if record.Version == 0 {
		record.Version = 1
	}
	if record.AttemptEpoch == 0 {
		record.AttemptEpoch = 1
	}

	var created reliabletask.NotificationOutboxRecord
	err := s.RunInTransaction(ctx, func(txCtx context.Context) error {
		var createErr error
		created, createErr = s.Store.CreateNotification(txCtx, record)
		if createErr != nil {
			return createErr
		}
		return s.appendEvent(txCtx, created, "NotificationDeliveryJobCreated", created.CreatedAt)
	})
	return created, err
}

func (s *MongoNotificationDeliveryJobStore) ClaimNotification(
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
	update := bson.M{
		"$set": bson.M{
			"status":     reliabletask.NotificationStatusProcessing,
			"leaseOwner": strings.TrimSpace(workerID),
			"leaseToken": reliabletask.NewRecordID("notification-lease"),
			"leaseUntil": now.Add(leaseTTL).UTC(),
			"updatedAt":  now.UTC(),
		},
		"$inc": bson.M{"version": 1},
	}
	opts := options.FindOneAndUpdate().
		SetSort(bson.D{{Key: "nextAttemptAt", Value: 1}}).
		SetReturnDocument(options.After)
	var job reliabletask.NotificationOutboxRecord
	if err := s.jobs.FindOneAndUpdate(ctx, filter, update, opts).Decode(&job); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &job, nil
}

func (s *MongoNotificationDeliveryJobStore) ReadDeliveryJobMetrics(
	ctx context.Context,
) (notification.NotificationDeliveryJobMetricsSnapshot, error) {
	snapshot := notification.NotificationDeliveryJobMetricsSnapshot{
		JobsByStatus: map[string]int64{},
		UpdatedAt:    time.Now().UTC(),
	}
	cursor, err := s.jobs.Aggregate(ctx, bson.A{
		bson.M{"$group": bson.M{"_id": "$status", "count": bson.M{"$sum": 1}}},
	})
	if err != nil {
		return snapshot, err
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var row struct {
			ID    string `bson:"_id"`
			Count int64  `bson:"count"`
		}
		if err := cursor.Decode(&row); err != nil {
			return snapshot, err
		}
		snapshot.JobsByStatus[row.ID] = row.Count
		if row.ID == reliabletask.NotificationStatusDead {
			snapshot.DeadJobs = row.Count
		}
	}
	return snapshot, cursor.Err()
}

func (s *MongoNotificationDeliveryJobStore) ListDeadDeliveryJobs(
	ctx context.Context,
	eventTypes []string,
	limit int,
) ([]reliabletask.DeadNotificationRecord, error) {
	return s.Store.ListDeadNotifications(ctx, eventTypes, limit)
}

func (s *MongoNotificationDeliveryJobStore) CompleteNotification(
	ctx context.Context,
	jobID string,
	leaseToken string,
) error {
	return s.RunInTransaction(ctx, func(txCtx context.Context) error {
		now := time.Now().UTC()
		var job reliabletask.NotificationOutboxRecord
		err := s.jobs.FindOneAndUpdate(
			txCtx,
			bson.M{"_id": strings.TrimSpace(jobID), "leaseToken": strings.TrimSpace(leaseToken)},
			bson.M{
				"$set": bson.M{
					"status":     reliabletask.NotificationStatusSucceeded,
					"leaseOwner": "",
					"leaseToken": "",
					"leaseUntil": time.Time{},
					"updatedAt":  now,
				},
				"$inc": bson.M{"version": 1},
			},
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&job)
		if errors.Is(err, mongo.ErrNoDocuments) {
			return reliabletask.ErrLeaseMismatch
		}
		if err != nil {
			return err
		}
		return s.appendEvent(txCtx, job, "NotificationDeliveryJobDispatched", now)
	})
}

func (s *MongoNotificationDeliveryJobStore) RetryNotification(
	ctx context.Context,
	jobID string,
	leaseToken string,
	failure reliabletask.RuntimeFailure,
	policy reliabletask.RetryPolicy,
	now time.Time,
) error {
	return s.RunInTransaction(ctx, func(txCtx context.Context) error {
		var job reliabletask.NotificationOutboxRecord
		if err := s.jobs.FindOne(
			txCtx,
			bson.M{"_id": strings.TrimSpace(jobID), "leaseToken": strings.TrimSpace(leaseToken)},
		).Decode(&job); err != nil {
			if errors.Is(err, mongo.ErrNoDocuments) {
				return reliabletask.ErrLeaseMismatch
			}
			return err
		}
		job.Attempts++
		job.Version++
		job.LastFailure = &failure
		job.LeaseOwner = ""
		job.LeaseToken = ""
		job.LeaseUntil = time.Time{}
		job.UpdatedAt = now.UTC()
		if delay, retry := policy.NextDelay(job.Attempts); retry {
			job.Status = reliabletask.NotificationStatusRetryWait
			job.NextAttemptAt = now.Add(delay).UTC()
		} else {
			job.Status = reliabletask.NotificationStatusDead
		}
		result, err := s.jobs.ReplaceOne(
			txCtx,
			bson.M{"_id": job.NotificationID, "leaseToken": strings.TrimSpace(leaseToken)},
			job,
		)
		if err != nil {
			return err
		}
		if result.MatchedCount != 1 {
			return reliabletask.ErrLeaseMismatch
		}
		if job.Status == reliabletask.NotificationStatusDead {
			return s.appendEvent(txCtx, job, "NotificationDeliveryJobDeadLettered", now.UTC())
		}
		return nil
	})
}

func (s *MongoNotificationDeliveryJobStore) RecoverDeliveryJob(
	ctx context.Context,
	jobID string,
	idempotencyKey string,
	now time.Time,
) (notification.RecoverNotificationDeliveryJobResult, error) {
	jobID = strings.TrimSpace(jobID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	digest := fmt.Sprintf("%x", sha256.Sum256([]byte("RecoverNotificationDeliveryJob\n"+jobID)))
	var result notification.RecoverNotificationDeliveryJobResult
	err := s.RunInTransaction(ctx, func(txCtx context.Context) error {
		var receipt notificationDeliveryJobReceiptDocument
		receiptErr := s.receipts.FindOne(txCtx, bson.M{"_id": idempotencyKey}).Decode(&receipt)
		if receiptErr == nil {
			if receipt.CommandDigest != digest {
				return notification.ErrDeliveryJobIdempotencyConflict
			}
			result = receipt.Result
			result.Replayed = true
			return nil
		}
		if !errors.Is(receiptErr, mongo.ErrNoDocuments) {
			return receiptErr
		}

		var job reliabletask.NotificationOutboxRecord
		updateErr := s.jobs.FindOneAndUpdate(
			txCtx,
			bson.M{"_id": jobID, "status": reliabletask.NotificationStatusDead},
			bson.M{
				"$set": bson.M{
					"status":        reliabletask.NotificationStatusPending,
					"nextAttemptAt": now.UTC(),
					"leaseOwner":    "",
					"leaseToken":    "",
					"leaseUntil":    time.Time{},
					"updatedAt":     now.UTC(),
				},
				"$inc": bson.M{"version": 1, "attemptEpoch": 1},
			},
			options.FindOneAndUpdate().SetReturnDocument(options.After),
		).Decode(&job)
		if errors.Is(updateErr, mongo.ErrNoDocuments) {
			return notification.ErrDeliveryJobNotFound
		}
		if updateErr != nil {
			return updateErr
		}
		result = notification.RecoverNotificationDeliveryJobResult{
			JobID:          job.NotificationID,
			NotificationID: job.SubjectNotificationID,
			Version:        job.Version,
			AttemptEpoch:   job.AttemptEpoch,
			RecoveredAt:    now.UTC(),
		}
		if err := s.appendEvent(txCtx, job, "NotificationDeliveryJobRecovered", now.UTC()); err != nil {
			return err
		}
		_, insertErr := s.receipts.InsertOne(txCtx, notificationDeliveryJobReceiptDocument{
			ID:            idempotencyKey,
			CommandName:   "RecoverNotificationDeliveryJob",
			CommandDigest: digest,
			Result:        result,
			CreatedAt:     now.UTC(),
		})
		if mongo.IsDuplicateKeyError(insertErr) {
			return notification.ErrDeliveryJobIdempotencyConflict
		}
		return insertErr
	})
	return result, err
}

func (s *MongoNotificationDeliveryJobStore) appendEvent(
	ctx context.Context,
	job reliabletask.NotificationOutboxRecord,
	eventType string,
	occurredAt time.Time,
) error {
	eventID := fmt.Sprintf("%s:%020d:%s", job.NotificationID, job.Version, eventType)
	_, err := s.outbox.UpdateOne(
		ctx,
		bson.M{"_id": eventID},
		bson.M{"$setOnInsert": notificationDeliveryJobEventDocument{
			ID:               eventID,
			AggregateID:      job.NotificationID,
			AggregateVersion: job.Version,
			EventType:        eventType,
			Payload: map[string]string{
				"jobId":          job.NotificationID,
				"notificationId": job.SubjectNotificationID,
				"channel":        job.Channel,
				"status":         job.Status,
			},
			Status:    reliabletask.TaskOutboxStatusPending,
			CreatedAt: occurredAt.UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

package reliabletask

import (
	"context"
	"errors"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

type MongoStore struct {
	db            *mongo.Database
	outboxes      *mongo.Collection
	tasks         *mongo.Collection
	notifications *mongo.Collection
	ledgers       *mongo.Collection
	attempts      *mongo.Collection
	leases        *mongo.Collection
}

func NewMongoStore(db *mongo.Database) *MongoStore {
	return &MongoStore{
		db:            db,
		outboxes:      db.Collection("reliable_task_outbox"),
		tasks:         db.Collection("reliable_async_task"),
		notifications: db.Collection("notification_outbox"),
		ledgers:       db.Collection("notification_delivery_ledger"),
		attempts:      db.Collection("external_provider_attempt_ledger"),
		leases:        db.Collection("reliable_task_leases"),
	}
}

func (s *MongoStore) RunInTransaction(ctx context.Context, fn func(context.Context) error) error {
	if mongo.SessionFromContext(ctx) != nil {
		return fn(ctx)
	}
	session, err := s.db.Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		return nil, fn(txCtx)
	})
	return err
}

func (s *MongoStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.outboxes.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "dedupeKey", Value: 1}, {Key: "status", Value: 1}},
			Options: options.Index().
				SetUnique(true).
				SetPartialFilterExpression(bson.M{"status": TaskOutboxStatusPending}),
		},
		{Keys: bson.D{{Key: "startAt", Value: 1}, {Key: "status", Value: 1}}},
		{Keys: bson.D{{Key: "shardId", Value: 1}, {Key: "startAt", Value: 1}, {Key: "status", Value: 1}}},
	})
	if err != nil {
		return err
	}
	_, err = s.tasks.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "dedupeKey", Value: 1}, {Key: "status", Value: 1}},
			Options: options.Index().
				SetUnique(true).
				SetPartialFilterExpression(bson.M{"status": bson.M{"$in": bson.A{TaskStatusReady, TaskStatusProcessing, TaskStatusRetryWait}}}),
		},
		{Keys: bson.D{{Key: "nextAttemptAt", Value: 1}, {Key: "status", Value: 1}}},
	})
	if err != nil {
		return err
	}
	_, err = s.notifications.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "dedupeKey", Value: 1}}, Options: options.Index().SetUnique(true)},
		{Keys: bson.D{{Key: "nextAttemptAt", Value: 1}, {Key: "status", Value: 1}}},
	})
	if err != nil {
		return err
	}
	_, err = s.ledgers.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "notificationId", Value: 1}, {Key: "recipientId", Value: 1}}, Options: options.Index().SetUnique(true)},
		{Keys: bson.D{{Key: "notificationId", Value: 1}, {Key: "status", Value: 1}}},
	})
	if err != nil {
		return err
	}
	_, err = s.attempts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "requestId", Value: 1}, {Key: "createdAt", Value: 1}}},
		{Keys: bson.D{{Key: "operation", Value: 1}, {Key: "provider", Value: 1}, {Key: "status", Value: 1}}},
	})
	if err != nil {
		return err
	}
	_, err = s.leases.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "env", Value: 1},
				{Key: "domain", Value: 1},
				{Key: "module", Value: 1},
				{Key: "shardId", Value: 1},
			},
			Options: options.Index().SetUnique(true),
		},
		{Keys: bson.D{{Key: "leaseUntil", Value: 1}}},
	})
	return err
}

func (s *MongoStore) DeclareTask(ctx context.Context, req DeclareTaskRequest) (TaskOutboxRecord, error) {
	if err := validatePayloadAllowlist(req.Payload, req.PayloadAllow); err != nil {
		return TaskOutboxRecord{}, err
	}
	now := time.Now().UTC()
	startAt, maxDelayUntil := normalizeStartAt(req, now)
	dedupeKey := strings.TrimSpace(req.DedupeKey)
	if dedupeKey == "" {
		dedupeKey = strings.TrimSpace(req.TaskType) + ":" + strings.TrimSpace(req.AggregateID)
	}

	var existing TaskOutboxRecord
	err := s.outboxes.FindOne(ctx, bson.M{
		"dedupeKey": dedupeKey,
		"status":    TaskOutboxStatusPending,
	}).Decode(&existing)
	if err == nil {
		existing.Payload = mergePayload(existing.Payload, req.Payload)
		existing.Trigger = mergeCSV(existing.Trigger, req.Trigger)
		existing.StartAt = extendStartAt(existing, req, now)
		if existing.MaxDelayUntil.IsZero() && !maxDelayUntil.IsZero() {
			existing.MaxDelayUntil = maxDelayUntil
		}
		existing.UpdatedAt = now
		_, err = s.outboxes.ReplaceOne(ctx, bson.M{"_id": existing.OutboxID}, existing)
		return existing, err
	}
	if !errors.Is(err, mongo.ErrNoDocuments) {
		return TaskOutboxRecord{}, err
	}

	record := TaskOutboxRecord{
		OutboxID:         newID("outbox"),
		TaskType:         strings.TrimSpace(req.TaskType),
		OwnerDomain:      strings.TrimSpace(req.OwnerDomain),
		AggregateType:    strings.TrimSpace(req.AggregateType),
		AggregateID:      strings.TrimSpace(req.AggregateID),
		DedupeKey:        dedupeKey,
		IdempotencyKey:   strings.TrimSpace(req.IdempotencyKey),
		PartitionKey:     strings.TrimSpace(req.PartitionKey),
		ShardID:          shardIDForRequest(req),
		Payload:          clonePayload(req.Payload),
		Trigger:          strings.TrimSpace(req.Trigger),
		Status:           TaskOutboxStatusPending,
		StartAt:          startAt,
		MaxDelayUntil:    maxDelayUntil,
		CreatedByModule:  strings.TrimSpace(req.CreatedByModule),
		CreatedAt:        now,
		UpdatedAt:        now,
		DispatchAttempts: 0,
	}
	_, err = s.outboxes.InsertOne(ctx, record)
	return record, err
}

func (s *MongoStore) DispatchDueTasks(ctx context.Context, now time.Time, limit int) ([]ReliableAsyncTask, error) {
	return s.DispatchDueTasksForShard(ctx, now, limit, -1)
}

func (s *MongoStore) DispatchDueTasksForShard(ctx context.Context, now time.Time, limit int, shardID int) ([]ReliableAsyncTask, error) {
	if limit <= 0 {
		limit = 100
	}
	filter := bson.M{
		"status":  bson.M{"$in": bson.A{TaskOutboxStatusPending, TaskOutboxStatusFailed}},
		"startAt": bson.M{"$lte": now.UTC()},
	}
	if shardID >= 0 {
		filter["shardId"] = shardID
	}
	cursor, err := s.outboxes.Find(
		ctx,
		filter,
		options.Find().SetSort(bson.D{{Key: "startAt", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var outboxes []TaskOutboxRecord
	if err := cursor.All(ctx, &outboxes); err != nil {
		return nil, err
	}
	tasks := make([]ReliableAsyncTask, 0, len(outboxes))
	for _, outbox := range outboxes {
		task, err := s.upsertReadyTask(ctx, outbox, now.UTC())
		if err != nil {
			return nil, err
		}
		outbox.Status = TaskOutboxStatusDispatched
		outbox.DispatchAttempts++
		outbox.UpdatedAt = now.UTC()
		if _, err := s.outboxes.ReplaceOne(ctx, bson.M{"_id": outbox.OutboxID}, outbox); err != nil {
			return nil, err
		}
		tasks = append(tasks, task)
	}
	return tasks, nil
}

func (s *MongoStore) upsertReadyTask(ctx context.Context, outbox TaskOutboxRecord, now time.Time) (ReliableAsyncTask, error) {
	var existing ReliableAsyncTask
	err := s.tasks.FindOne(ctx, bson.M{
		"dedupeKey": outbox.DedupeKey,
		"status":    bson.M{"$in": bson.A{TaskStatusReady, TaskStatusProcessing, TaskStatusRetryWait}},
	}).Decode(&existing)
	if err == nil {
		existing.Payload = mergePayload(existing.Payload, outbox.Payload)
		if existing.Status == TaskStatusRetryWait && !existing.NextAttemptAt.After(now) {
			existing.Status = TaskStatusReady
		}
		existing.UpdatedAt = now
		_, err = s.tasks.ReplaceOne(ctx, bson.M{"_id": existing.TaskID}, existing)
		return existing, err
	}
	if !errors.Is(err, mongo.ErrNoDocuments) {
		return ReliableAsyncTask{}, err
	}
	task := ReliableAsyncTask{
		TaskID:         newID("task"),
		OutboxID:       outbox.OutboxID,
		TaskType:       outbox.TaskType,
		OwnerDomain:    outbox.OwnerDomain,
		AggregateType:  outbox.AggregateType,
		AggregateID:    outbox.AggregateID,
		DedupeKey:      outbox.DedupeKey,
		IdempotencyKey: outbox.IdempotencyKey,
		PartitionKey:   outbox.PartitionKey,
		ShardID:        outbox.ShardID,
		Payload:        clonePayload(outbox.Payload),
		Status:         TaskStatusReady,
		NextAttemptAt:  now,
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	_, err = s.tasks.InsertOne(ctx, task)
	return task, err
}

func (s *MongoStore) ClaimReadyTask(ctx context.Context, taskTypes []string, workerID string, leaseTTL time.Duration, now time.Time) (*ReliableAsyncTask, error) {
	filter := bson.M{
		"nextAttemptAt": bson.M{"$lte": now.UTC()},
		"$or": bson.A{
			bson.M{"status": TaskStatusReady},
			bson.M{"status": TaskStatusRetryWait},
			bson.M{"status": TaskStatusProcessing, "leaseUntil": bson.M{"$lte": now.UTC()}},
		},
	}
	if len(taskTypes) > 0 {
		filter["taskType"] = bson.M{"$in": taskTypes}
	}
	token := newID("lease")
	update := bson.M{
		"$set": bson.M{
			"status":     TaskStatusProcessing,
			"leaseOwner": strings.TrimSpace(workerID),
			"leaseToken": token,
			"leaseUntil": now.Add(leaseTTL).UTC(),
			"updatedAt":  now.UTC(),
		},
	}
	opts := options.FindOneAndUpdate().SetSort(bson.D{{Key: "nextAttemptAt", Value: 1}}).SetReturnDocument(options.After)
	var task ReliableAsyncTask
	if err := s.tasks.FindOneAndUpdate(ctx, filter, update, opts).Decode(&task); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &task, nil
}

func (s *MongoStore) ClaimReadyTaskByID(ctx context.Context, taskID string, workerID string, leaseTTL time.Duration, now time.Time) (*ReliableAsyncTask, error) {
	filter := bson.M{
		"_id":           strings.TrimSpace(taskID),
		"nextAttemptAt": bson.M{"$lte": now.UTC()},
		"$or": bson.A{
			bson.M{"status": TaskStatusReady},
			bson.M{"status": TaskStatusRetryWait},
			bson.M{"status": TaskStatusProcessing, "leaseUntil": bson.M{"$lte": now.UTC()}},
		},
	}
	token := newID("lease")
	update := bson.M{
		"$set": bson.M{
			"status":     TaskStatusProcessing,
			"leaseOwner": strings.TrimSpace(workerID),
			"leaseToken": token,
			"leaseUntil": now.Add(leaseTTL).UTC(),
			"updatedAt":  now.UTC(),
		},
	}
	opts := options.FindOneAndUpdate().SetReturnDocument(options.After)
	var task ReliableAsyncTask
	if err := s.tasks.FindOneAndUpdate(ctx, filter, update, opts).Decode(&task); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &task, nil
}

func (s *MongoStore) CompleteTask(ctx context.Context, taskID string, leaseToken string) error {
	res, err := s.tasks.UpdateOne(ctx, bson.M{"_id": taskID, "leaseToken": leaseToken}, bson.M{
		"$set": bson.M{
			"status":     TaskStatusSucceeded,
			"leaseOwner": "",
			"leaseToken": "",
			"updatedAt":  time.Now().UTC(),
		},
	})
	if err != nil {
		return err
	}
	if res.MatchedCount == 0 {
		return ErrLeaseMismatch
	}
	return nil
}

func (s *MongoStore) FailTask(ctx context.Context, taskID string, leaseToken string, failure RuntimeFailure, policy RetryPolicy, now time.Time) error {
	var task ReliableAsyncTask
	if err := s.tasks.FindOne(ctx, bson.M{"_id": taskID, "leaseToken": leaseToken}).Decode(&task); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return ErrLeaseMismatch
		}
		return err
	}
	task.Attempts++
	task.LastFailure = &failure
	task.LeaseOwner = ""
	task.LeaseToken = ""
	task.UpdatedAt = now.UTC()
	if delay, retry := policy.NextDelay(task.Attempts); retry {
		task.Status = TaskStatusRetryWait
		task.NextAttemptAt = now.Add(delay).UTC()
	} else {
		task.Status = TaskStatusDead
	}
	_, err := s.tasks.ReplaceOne(ctx, bson.M{"_id": taskID}, task)
	return err
}

func (s *MongoStore) CreateNotification(ctx context.Context, record NotificationOutboxRecord) (NotificationOutboxRecord, error) {
	now := time.Now().UTC()
	if strings.TrimSpace(record.DedupeKey) != "" {
		var existing NotificationOutboxRecord
		err := s.notifications.FindOne(ctx, bson.M{"dedupeKey": strings.TrimSpace(record.DedupeKey)}).Decode(&existing)
		if err == nil {
			return existing, nil
		}
		if !errors.Is(err, mongo.ErrNoDocuments) {
			return NotificationOutboxRecord{}, err
		}
	}
	if record.NotificationID == "" {
		record.NotificationID = newID("notification")
	}
	if record.Status == "" {
		record.Status = NotificationStatusPending
	}
	if record.CreatedAt.IsZero() {
		record.CreatedAt = now
	}
	record.UpdatedAt = now
	record.Payload = clonePayload(record.Payload)
	_, err := s.notifications.InsertOne(ctx, record)
	if mongo.IsDuplicateKeyError(err) && strings.TrimSpace(record.DedupeKey) != "" {
		var existing NotificationOutboxRecord
		if findErr := s.notifications.FindOne(ctx, bson.M{"dedupeKey": strings.TrimSpace(record.DedupeKey)}).Decode(&existing); findErr != nil {
			return NotificationOutboxRecord{}, err
		}
		return existing, nil
	}
	return record, err
}

func (s *MongoStore) ClaimNotification(ctx context.Context, eventTypes []string, workerID string, leaseTTL time.Duration, now time.Time) (*NotificationOutboxRecord, error) {
	filter := bson.M{
		"nextAttemptAt": bson.M{"$lte": now.UTC()},
		"$or": bson.A{
			bson.M{"status": NotificationStatusPending},
			bson.M{"status": NotificationStatusRetryWait},
			bson.M{"status": NotificationStatusProcessing, "leaseUntil": bson.M{"$lte": now.UTC()}},
		},
	}
	if len(eventTypes) > 0 {
		filter["eventType"] = bson.M{"$in": eventTypes}
	}
	token := newID("notification-lease")
	update := bson.M{
		"$set": bson.M{
			"status":     NotificationStatusProcessing,
			"leaseOwner": strings.TrimSpace(workerID),
			"leaseToken": token,
			"leaseUntil": now.Add(leaseTTL).UTC(),
			"updatedAt":  now.UTC(),
		},
	}
	opts := options.FindOneAndUpdate().SetSort(bson.D{{Key: "nextAttemptAt", Value: 1}}).SetReturnDocument(options.After)
	var notification NotificationOutboxRecord
	if err := s.notifications.FindOneAndUpdate(ctx, filter, update, opts).Decode(&notification); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &notification, nil
}

func (s *MongoStore) EnsureRecipientLedgers(ctx context.Context, notificationID string, eventType string, recipientIDs []string) error {
	now := time.Now().UTC()
	for _, recipientID := range dedupeStrings(recipientIDs) {
		record := NotificationDeliveryLedgerRecord{
			LedgerID:       ledgerID(notificationID, recipientID),
			NotificationID: notificationID,
			EventType:      eventType,
			RecipientID:    recipientID,
			Status:         RecipientStatusPending,
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

func (s *MongoStore) ListPendingRecipients(ctx context.Context, notificationID string) ([]NotificationDeliveryLedgerRecord, error) {
	cursor, err := s.ledgers.Find(ctx, bson.M{
		"notificationId": notificationID,
		"status":         bson.M{"$ne": RecipientStatusDelivered},
	})
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var records []NotificationDeliveryLedgerRecord
	if err := cursor.All(ctx, &records); err != nil {
		return nil, err
	}
	sort.Slice(records, func(i, j int) bool {
		return records[i].RecipientID < records[j].RecipientID
	})
	return records, nil
}

func (s *MongoStore) MarkRecipientDelivered(ctx context.Context, notificationID string, recipientID string, syncSeq int64) error {
	_, err := s.ledgers.UpdateOne(ctx, bson.M{"_id": ledgerID(notificationID, recipientID)}, bson.M{
		"$set": bson.M{
			"status":       RecipientStatusDelivered,
			"deliveredSeq": syncSeq,
			"updatedAt":    time.Now().UTC(),
			"lastFailure":  nil,
		},
	})
	return err
}

func (s *MongoStore) MarkRecipientFailed(ctx context.Context, notificationID string, recipientID string, failure RuntimeFailure) error {
	_, err := s.ledgers.UpdateOne(ctx, bson.M{
		"_id":    ledgerID(notificationID, recipientID),
		"status": bson.M{"$ne": RecipientStatusDelivered},
	}, bson.M{
		"$set": bson.M{
			"status":      RecipientStatusFailed,
			"updatedAt":   time.Now().UTC(),
			"lastFailure": failure,
		},
		"$inc": bson.M{"attempts": 1},
	})
	return err
}

func (s *MongoStore) RecordProviderAttempt(ctx context.Context, record ProviderAttemptRecord) (ProviderAttemptRecord, error) {
	if strings.TrimSpace(record.AttemptID) == "" {
		record.AttemptID = newID("attempt")
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

func (s *MongoStore) ListProviderAttempts(ctx context.Context, requestID string) ([]ProviderAttemptRecord, error) {
	cursor, err := s.attempts.Find(
		ctx,
		bson.M{"requestId": strings.TrimSpace(requestID)},
		options.Find().SetSort(bson.D{{Key: "createdAt", Value: 1}}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var records []ProviderAttemptRecord
	for cursor.Next(ctx) {
		var record ProviderAttemptRecord
		if err := cursor.Decode(&record); err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	return records, cursor.Err()
}

func (s *MongoStore) ListDeadTasks(ctx context.Context, taskTypes []string, limit int) ([]DeadTaskRecord, error) {
	filter := bson.M{"status": TaskStatusDead}
	if len(taskTypes) > 0 {
		filter["taskType"] = bson.M{"$in": taskTypes}
	}
	opts := options.Find().SetSort(bson.D{{Key: "updatedAt", Value: 1}})
	if limit > 0 {
		opts.SetLimit(int64(limit))
	}
	cursor, err := s.tasks.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var out []DeadTaskRecord
	for cursor.Next(ctx) {
		var task ReliableAsyncTask
		if err := cursor.Decode(&task); err != nil {
			return nil, err
		}
		out = append(out, DeadTaskRecord{
			TaskID:      task.TaskID,
			TaskType:    task.TaskType,
			AggregateID: task.AggregateID,
			Attempts:    task.Attempts,
			LastFailure: task.LastFailure,
			Payload:     clonePayload(task.Payload),
			UpdatedAt:   task.UpdatedAt,
		})
	}
	return out, cursor.Err()
}

func (s *MongoStore) RecoverDeadTask(ctx context.Context, taskID string, now time.Time) error {
	res, err := s.tasks.UpdateOne(ctx, bson.M{"_id": strings.TrimSpace(taskID), "status": TaskStatusDead}, bson.M{
		"$set": bson.M{
			"status":        TaskStatusReady,
			"nextAttemptAt": now.UTC(),
			"leaseOwner":    "",
			"leaseToken":    "",
			"leaseUntil":    time.Time{},
			"updatedAt":     now.UTC(),
		},
	})
	if err != nil {
		return err
	}
	if res.MatchedCount == 0 {
		return ErrTaskNotFound
	}
	return nil
}

func (s *MongoStore) ListDeadNotifications(ctx context.Context, eventTypes []string, limit int) ([]DeadNotificationRecord, error) {
	filter := bson.M{"status": NotificationStatusDead}
	if len(eventTypes) > 0 {
		filter["eventType"] = bson.M{"$in": eventTypes}
	}
	opts := options.Find().SetSort(bson.D{{Key: "updatedAt", Value: 1}})
	if limit > 0 {
		opts.SetLimit(int64(limit))
	}
	cursor, err := s.notifications.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var out []DeadNotificationRecord
	for cursor.Next(ctx) {
		var notification NotificationOutboxRecord
		if err := cursor.Decode(&notification); err != nil {
			return nil, err
		}
		out = append(out, DeadNotificationRecord{
			NotificationID: notification.NotificationID,
			EventType:      notification.EventType,
			AggregateID:    notification.AggregateID,
			Attempts:       notification.Attempts,
			LastFailure:    notification.LastFailure,
			UpdatedAt:      notification.UpdatedAt,
		})
	}
	return out, cursor.Err()
}

func (s *MongoStore) RecoverDeadNotification(ctx context.Context, notificationID string, now time.Time) error {
	res, err := s.notifications.UpdateOne(ctx, bson.M{"_id": strings.TrimSpace(notificationID), "status": NotificationStatusDead}, bson.M{
		"$set": bson.M{
			"status":        NotificationStatusPending,
			"nextAttemptAt": now.UTC(),
			"leaseOwner":    "",
			"leaseToken":    "",
			"leaseUntil":    time.Time{},
			"updatedAt":     now.UTC(),
		},
	})
	if err != nil {
		return err
	}
	if res.MatchedCount == 0 {
		return ErrNotificationNotFound
	}
	return nil
}

func (s *MongoStore) CleanupReliableTaskRetention(ctx context.Context, policy RetentionPolicy, now time.Time) (RetentionCleanupResult, error) {
	var result RetentionCleanupResult
	if policy.Outbox.DispatchedTTL > 0 {
		res, err := s.outboxes.DeleteMany(ctx, bson.M{"status": TaskOutboxStatusDispatched, "updatedAt": bson.M{"$lt": now.Add(-policy.Outbox.DispatchedTTL)}})
		if err != nil {
			return result, err
		}
		result.OutboxesDeleted = res.DeletedCount
	}
	if policy.Task.DoneTTL > 0 || policy.Task.DeadTTL > 0 {
		filter := bson.M{"$or": bson.A{}}
		ors := bson.A{}
		if policy.Task.DoneTTL > 0 {
			ors = append(ors, bson.M{"status": TaskStatusSucceeded, "updatedAt": bson.M{"$lt": now.Add(-policy.Task.DoneTTL)}})
		}
		if policy.Task.DeadTTL > 0 {
			ors = append(ors, bson.M{"status": TaskStatusDead, "updatedAt": bson.M{"$lt": now.Add(-policy.Task.DeadTTL)}})
		}
		filter["$or"] = ors
		res, err := s.tasks.DeleteMany(ctx, filter)
		if err != nil {
			return result, err
		}
		result.TasksDeleted = res.DeletedCount
	}
	if policy.Notification.DoneTTL > 0 || policy.Notification.DeadTTL > 0 {
		ors := bson.A{}
		if policy.Notification.DoneTTL > 0 {
			ors = append(ors, bson.M{"status": NotificationStatusSucceeded, "updatedAt": bson.M{"$lt": now.Add(-policy.Notification.DoneTTL)}})
		}
		if policy.Notification.DeadTTL > 0 {
			ors = append(ors, bson.M{"status": NotificationStatusDead, "updatedAt": bson.M{"$lt": now.Add(-policy.Notification.DeadTTL)}})
		}
		res, err := s.notifications.DeleteMany(ctx, bson.M{"$or": ors})
		if err != nil {
			return result, err
		}
		result.NotificationsDeleted = res.DeletedCount
	}
	if policy.DeliveryLedger.DeliveredTTL > 0 {
		res, err := s.ledgers.DeleteMany(ctx, bson.M{"status": RecipientStatusDelivered, "updatedAt": bson.M{"$lt": now.Add(-policy.DeliveryLedger.DeliveredTTL)}})
		if err != nil {
			return result, err
		}
		result.LedgersDeleted = res.DeletedCount
		attemptRes, err := s.attempts.DeleteMany(ctx, bson.M{"createdAt": bson.M{"$lt": now.Add(-policy.DeliveryLedger.DeliveredTTL)}})
		if err != nil {
			return result, err
		}
		result.AttemptsDeleted = attemptRes.DeletedCount
	}
	return result, nil
}

func (s *MongoStore) ReliableTaskMetrics(ctx context.Context) (MetricsSnapshot, error) {
	snapshot := MetricsSnapshot{
		TasksByStatus:         map[string]int64{},
		NotificationsByStatus: map[string]int64{},
		ProviderAttempts:      map[string]int64{},
		UpdatedAt:             time.Now().UTC(),
	}
	taskCursor, err := s.tasks.Aggregate(ctx, bson.A{bson.M{"$group": bson.M{"_id": "$status", "count": bson.M{"$sum": 1}}}})
	if err != nil {
		return snapshot, err
	}
	defer taskCursor.Close(ctx)
	for taskCursor.Next(ctx) {
		var row struct {
			ID    string `bson:"_id"`
			Count int64  `bson:"count"`
		}
		if err := taskCursor.Decode(&row); err != nil {
			return snapshot, err
		}
		snapshot.TasksByStatus[row.ID] = row.Count
		if row.ID == TaskStatusDead {
			snapshot.DeadTasks = row.Count
		}
	}
	notificationCursor, err := s.notifications.Aggregate(ctx, bson.A{bson.M{"$group": bson.M{"_id": "$status", "count": bson.M{"$sum": 1}}}})
	if err != nil {
		return snapshot, err
	}
	defer notificationCursor.Close(ctx)
	for notificationCursor.Next(ctx) {
		var row struct {
			ID    string `bson:"_id"`
			Count int64  `bson:"count"`
		}
		if err := notificationCursor.Decode(&row); err != nil {
			return snapshot, err
		}
		snapshot.NotificationsByStatus[row.ID] = row.Count
		if row.ID == NotificationStatusDead {
			snapshot.DeadNotifications = row.Count
		}
	}
	attemptCursor, err := s.attempts.Aggregate(ctx, bson.A{bson.M{"$group": bson.M{"_id": bson.M{"operation": "$operation", "provider": "$provider", "status": "$status"}, "count": bson.M{"$sum": 1}}}})
	if err != nil {
		return snapshot, err
	}
	defer attemptCursor.Close(ctx)
	for attemptCursor.Next(ctx) {
		var row struct {
			ID struct {
				Operation string `bson:"operation"`
				Provider  string `bson:"provider"`
				Status    string `bson:"status"`
			} `bson:"_id"`
			Count int64 `bson:"count"`
		}
		if err := attemptCursor.Decode(&row); err != nil {
			return snapshot, err
		}
		snapshot.ProviderAttempts[row.ID.Operation+":"+row.ID.Provider+":"+row.ID.Status] = row.Count
	}
	return snapshot, nil
}

func (s *MongoStore) CompleteNotification(ctx context.Context, notificationID string, leaseToken string) error {
	res, err := s.notifications.UpdateOne(ctx, bson.M{"_id": notificationID, "leaseToken": leaseToken}, bson.M{
		"$set": bson.M{
			"status":     NotificationStatusSucceeded,
			"leaseOwner": "",
			"leaseToken": "",
			"updatedAt":  time.Now().UTC(),
		},
	})
	if err != nil {
		return err
	}
	if res.MatchedCount == 0 {
		return ErrLeaseMismatch
	}
	return nil
}

func (s *MongoStore) RetryNotification(ctx context.Context, notificationID string, leaseToken string, failure RuntimeFailure, policy RetryPolicy, now time.Time) error {
	var notification NotificationOutboxRecord
	if err := s.notifications.FindOne(ctx, bson.M{"_id": notificationID, "leaseToken": leaseToken}).Decode(&notification); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return ErrLeaseMismatch
		}
		return err
	}
	notification.Attempts++
	notification.LastFailure = &failure
	notification.LeaseOwner = ""
	notification.LeaseToken = ""
	notification.UpdatedAt = now.UTC()
	if delay, retry := policy.NextDelay(notification.Attempts); retry {
		notification.Status = NotificationStatusRetryWait
		notification.NextAttemptAt = now.Add(delay).UTC()
	} else {
		notification.Status = NotificationStatusDead
	}
	_, err := s.notifications.ReplaceOne(ctx, bson.M{"_id": notificationID}, notification)
	return err
}

func (s *MongoStore) ClaimShardLease(ctx context.Context, req ClaimShardLeaseRequest) (*TaskLease, error) {
	now := req.Now.UTC()
	if now.IsZero() {
		now = time.Now().UTC()
	}
	ttl := req.LeaseTTL
	if ttl <= 0 {
		ttl = 30 * time.Second
	}
	filter := bson.M{
		"env":     strings.TrimSpace(req.Env),
		"domain":  strings.TrimSpace(req.Domain),
		"module":  strings.TrimSpace(req.Module),
		"shardId": req.ShardID,
		"$or": bson.A{
			bson.M{"leaseUntil": bson.M{"$lte": now}},
			bson.M{"owner": strings.TrimSpace(req.Owner)},
			bson.M{"owner": bson.M{"$exists": false}},
		},
	}
	lease := TaskLease{
		Env:        strings.TrimSpace(req.Env),
		Domain:     strings.TrimSpace(req.Domain),
		Module:     strings.TrimSpace(req.Module),
		Owner:      strings.TrimSpace(req.Owner),
		Token:      newID("shard-lease"),
		ShardID:    req.ShardID,
		LeaseUntil: now.Add(ttl).UTC(),
		UpdatedAt:  now,
	}
	update := bson.M{
		"$set": lease,
		"$setOnInsert": bson.M{
			"_id": shardLeaseID(req.Env, req.Domain, req.Module, req.ShardID),
		},
	}
	opts := options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)
	var claimed TaskLease
	if err := s.leases.FindOneAndUpdate(ctx, filter, update, opts).Decode(&claimed); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &claimed, nil
}

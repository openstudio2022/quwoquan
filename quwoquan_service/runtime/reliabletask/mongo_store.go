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
	leases        *mongo.Collection
}

func NewMongoStore(db *mongo.Database) *MongoStore {
	return &MongoStore{
		db:            db,
		outboxes:      db.Collection("reliable_task_outbox"),
		tasks:         db.Collection("reliable_async_task"),
		notifications: db.Collection("notification_outbox"),
		ledgers:       db.Collection("notification_delivery_ledger"),
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

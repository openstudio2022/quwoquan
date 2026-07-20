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

func (s *Store) DeclareTask(
	ctx context.Context,
	req reliabletask.DeclareTaskRequest,
) (reliabletask.TaskOutboxRecord, error) {
	if err := reliabletask.ValidatePayloadAllowlist(req.Payload, req.PayloadAllow); err != nil {
		return reliabletask.TaskOutboxRecord{}, err
	}
	now := time.Now().UTC()
	startAt, maxDelayUntil := reliabletask.ResolveTaskSchedule(req, now)
	idempotencyKey := strings.TrimSpace(req.IdempotencyKey)
	if idempotencyKey != "" {
		var idempotent reliabletask.TaskOutboxRecord
		err := s.outboxes.FindOne(ctx, bson.M{"idempotencyKey": idempotencyKey}).Decode(&idempotent)
		if err == nil {
			return idempotent, nil
		}
		if !errors.Is(err, mongo.ErrNoDocuments) {
			return reliabletask.TaskOutboxRecord{}, err
		}
	}
	dedupeKey := strings.TrimSpace(req.DedupeKey)
	if dedupeKey == "" {
		dedupeKey = strings.TrimSpace(req.TaskType) + ":" + strings.TrimSpace(req.AggregateID)
	}

	var existing reliabletask.TaskOutboxRecord
	err := s.outboxes.FindOne(ctx, bson.M{
		"dedupeKey": dedupeKey,
		"status":    reliabletask.TaskOutboxStatusPending,
	}).Decode(&existing)
	if err == nil {
		existing.Payload = reliabletask.MergeTaskPayload(existing.Payload, req.Payload)
		existing.Trigger = reliabletask.MergeCSVValues(existing.Trigger, req.Trigger)
		existing.StartAt = reliabletask.ExtendTaskStartAt(existing, req, now)
		if existing.MaxDelayUntil.IsZero() && !maxDelayUntil.IsZero() {
			existing.MaxDelayUntil = maxDelayUntil
		}
		existing.UpdatedAt = now
		_, err = s.outboxes.ReplaceOne(ctx, bson.M{"_id": existing.OutboxID}, existing)
		return existing, err
	}
	if !errors.Is(err, mongo.ErrNoDocuments) {
		return reliabletask.TaskOutboxRecord{}, err
	}

	record := reliabletask.TaskOutboxRecord{
		OutboxID:         reliabletask.NewRecordID("outbox"),
		TaskType:         strings.TrimSpace(req.TaskType),
		OwnerDomain:      strings.TrimSpace(req.OwnerDomain),
		AggregateType:    strings.TrimSpace(req.AggregateType),
		AggregateID:      strings.TrimSpace(req.AggregateID),
		DedupeKey:        dedupeKey,
		IdempotencyKey:   strings.TrimSpace(req.IdempotencyKey),
		PartitionKey:     strings.TrimSpace(req.PartitionKey),
		ShardID:          reliabletask.ResolveTaskShardID(req),
		Payload:          reliabletask.CloneStringMap(req.Payload),
		Trigger:          strings.TrimSpace(req.Trigger),
		Status:           reliabletask.TaskOutboxStatusPending,
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

func (s *Store) DispatchDueTasks(
	ctx context.Context,
	now time.Time,
	limit int,
) ([]reliabletask.ReliableAsyncTask, error) {
	return s.DispatchDueTasksForShard(ctx, now, limit, -1)
}

// ListDueTaskShardIDs 返回当前实际存在到期任务的分片，避免 dispatcher 在每个
// tick 对全部分片执行空 lease 竞争。limit 只限制返回的不同分片数量。
func (s *Store) ListDueTaskShardIDs(ctx context.Context, now time.Time, limit int) ([]int, error) {
	if limit <= 0 || limit > reliabletask.DefaultShardCount {
		limit = reliabletask.DefaultShardCount
	}
	filter := bson.M{
		"status": bson.M{"$in": bson.A{
			reliabletask.TaskOutboxStatusPending,
			reliabletask.TaskOutboxStatusFailed,
		}},
		"startAt": bson.M{"$lte": now.UTC()},
	}
	var shardIDs []int
	if err := s.outboxes.Distinct(ctx, "shardId", filter).Decode(&shardIDs); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	sort.Ints(shardIDs)
	if len(shardIDs) > limit {
		shardIDs = shardIDs[:limit]
	}
	return shardIDs, nil
}

func (s *Store) DispatchDueTasksForShard(
	ctx context.Context,
	now time.Time,
	limit int,
	shardID int,
) ([]reliabletask.ReliableAsyncTask, error) {
	if limit <= 0 {
		limit = 100
	}
	filter := bson.M{
		"status": bson.M{"$in": bson.A{
			reliabletask.TaskOutboxStatusPending,
			reliabletask.TaskOutboxStatusFailed,
		}},
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
	var outboxes []reliabletask.TaskOutboxRecord
	if err := cursor.All(ctx, &outboxes); err != nil {
		return nil, err
	}
	tasks := make([]reliabletask.ReliableAsyncTask, 0, len(outboxes))
	for _, outbox := range outboxes {
		task, err := s.upsertReadyTask(ctx, outbox, now.UTC())
		if err != nil {
			return nil, err
		}
		outbox.Status = reliabletask.TaskOutboxStatusDispatched
		outbox.DispatchAttempts++
		outbox.UpdatedAt = now.UTC()
		if _, err := s.outboxes.ReplaceOne(ctx, bson.M{"_id": outbox.OutboxID}, outbox); err != nil {
			return nil, err
		}
		tasks = append(tasks, task)
	}
	return tasks, nil
}

func (s *Store) upsertReadyTask(
	ctx context.Context,
	outbox reliabletask.TaskOutboxRecord,
	now time.Time,
) (reliabletask.ReliableAsyncTask, error) {
	var existing reliabletask.ReliableAsyncTask
	err := s.tasks.FindOne(ctx, bson.M{
		"dedupeKey": outbox.DedupeKey,
		"status": bson.M{"$in": bson.A{
			reliabletask.TaskStatusReady,
			reliabletask.TaskStatusProcessing,
			reliabletask.TaskStatusRetryWait,
		}},
	}).Decode(&existing)
	if err == nil {
		existing.Payload = reliabletask.MergeTaskPayload(existing.Payload, outbox.Payload)
		if existing.Status == reliabletask.TaskStatusRetryWait && !existing.NextAttemptAt.After(now) {
			existing.Status = reliabletask.TaskStatusReady
		}
		existing.UpdatedAt = now
		_, err = s.tasks.ReplaceOne(ctx, bson.M{"_id": existing.TaskID}, existing)
		return existing, err
	}
	if !errors.Is(err, mongo.ErrNoDocuments) {
		return reliabletask.ReliableAsyncTask{}, err
	}
	task := reliabletask.ReliableAsyncTask{
		TaskID:         reliabletask.NewRecordID("task"),
		OutboxID:       outbox.OutboxID,
		TaskType:       outbox.TaskType,
		OwnerDomain:    outbox.OwnerDomain,
		AggregateType:  outbox.AggregateType,
		AggregateID:    outbox.AggregateID,
		DedupeKey:      outbox.DedupeKey,
		IdempotencyKey: outbox.IdempotencyKey,
		PartitionKey:   outbox.PartitionKey,
		ShardID:        outbox.ShardID,
		Payload:        reliabletask.CloneStringMap(outbox.Payload),
		Status:         reliabletask.TaskStatusReady,
		NextAttemptAt:  now,
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	_, err = s.tasks.InsertOne(ctx, task)
	return task, err
}

func (s *Store) ClaimReadyTask(
	ctx context.Context,
	taskTypes []string,
	workerID string,
	leaseTTL time.Duration,
	now time.Time,
) (*reliabletask.ReliableAsyncTask, error) {
	filter := readyTaskFilter(taskTypes, "", now)
	token := reliabletask.NewRecordID("lease")
	update := bson.M{
		"$set": bson.M{
			"status":     reliabletask.TaskStatusProcessing,
			"leaseOwner": strings.TrimSpace(workerID),
			"leaseToken": token,
			"leaseUntil": now.Add(leaseTTL).UTC(),
			"updatedAt":  now.UTC(),
		},
	}
	opts := options.FindOneAndUpdate().
		SetSort(bson.D{{Key: "nextAttemptAt", Value: 1}}).
		SetReturnDocument(options.After)
	var task reliabletask.ReliableAsyncTask
	if err := s.tasks.FindOneAndUpdate(ctx, filter, update, opts).Decode(&task); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &task, nil
}

func (s *Store) ClaimReadyTaskByID(
	ctx context.Context,
	taskID string,
	workerID string,
	leaseTTL time.Duration,
	now time.Time,
) (*reliabletask.ReliableAsyncTask, error) {
	filter := readyTaskFilter(nil, strings.TrimSpace(taskID), now)
	token := reliabletask.NewRecordID("lease")
	update := bson.M{
		"$set": bson.M{
			"status":     reliabletask.TaskStatusProcessing,
			"leaseOwner": strings.TrimSpace(workerID),
			"leaseToken": token,
			"leaseUntil": now.Add(leaseTTL).UTC(),
			"updatedAt":  now.UTC(),
		},
	}
	opts := options.FindOneAndUpdate().SetReturnDocument(options.After)
	var task reliabletask.ReliableAsyncTask
	if err := s.tasks.FindOneAndUpdate(ctx, filter, update, opts).Decode(&task); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &task, nil
}

func (s *Store) ListReadyTasks(
	ctx context.Context,
	taskTypes []string,
	limit int,
	now time.Time,
) ([]reliabletask.ReliableAsyncTask, error) {
	if limit <= 0 {
		limit = 100
	}
	cursor, err := s.tasks.Find(
		ctx,
		readyTaskFilter(taskTypes, "", now),
		options.Find().
			SetSort(bson.D{
				{Key: "nextAttemptAt", Value: 1},
				{Key: "_id", Value: 1},
			}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var tasks []reliabletask.ReliableAsyncTask
	if err := cursor.All(ctx, &tasks); err != nil {
		return nil, err
	}
	return tasks, nil
}

func readyTaskFilter(taskTypes []string, taskID string, now time.Time) bson.M {
	filter := bson.M{
		"nextAttemptAt": bson.M{"$lte": now.UTC()},
		"$or": bson.A{
			bson.M{"status": reliabletask.TaskStatusReady},
			bson.M{"status": reliabletask.TaskStatusRetryWait},
			bson.M{
				"status":     reliabletask.TaskStatusProcessing,
				"leaseUntil": bson.M{"$lte": now.UTC()},
			},
		},
	}
	if len(taskTypes) > 0 {
		filter["taskType"] = bson.M{"$in": taskTypes}
	}
	if taskID != "" {
		filter["_id"] = taskID
	}
	return filter
}

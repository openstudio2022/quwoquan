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
	return s.dispatchDueTaskFilter(ctx, now, limit, filter)
}

// DispatchDataContentExecution dispatches only the immutable execution named
// by the Data worker. Global due-task dispatch is unsafe here because two
// content executions may share the same Mongo outbox collection.
func (s *Store) DispatchDataContentExecution(
	ctx context.Context,
	executionID string,
	now time.Time,
	limit int,
) ([]reliabletask.ReliableAsyncTask, error) {
	if strings.TrimSpace(executionID) == "" {
		return nil, errors.New("data content executionId is required")
	}
	if limit <= 0 {
		limit = 100
	}
	return s.dispatchDueTaskFilter(ctx, now, limit, bson.M{
		"taskType":            reliabletask.DataContentTaskType,
		"payload.executionId": strings.TrimSpace(executionID),
		"status": bson.M{"$in": bson.A{
			reliabletask.TaskOutboxStatusPending,
			reliabletask.TaskOutboxStatusFailed,
		}},
		"startAt": bson.M{"$lte": now.UTC()},
	})
}

func (s *Store) dispatchDueTaskFilter(
	ctx context.Context,
	now time.Time,
	limit int,
	filter bson.M,
) ([]reliabletask.ReliableAsyncTask, error) {
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
	return s.listReadyTaskFilter(ctx, readyTaskFilter(taskTypes, "", now), limit)
}

// ListReadyDataContentExecution returns ready tasks for one immutable Data
// execution only; it is the Mongo truth used to rebuild its Redis stream.
func (s *Store) ListReadyDataContentExecution(
	ctx context.Context,
	executionID string,
	limit int,
	now time.Time,
) ([]reliabletask.ReliableAsyncTask, error) {
	if strings.TrimSpace(executionID) == "" {
		return nil, errors.New("data content executionId is required")
	}
	filter := readyTaskFilter([]string{reliabletask.DataContentTaskType}, "", now)
	filter["payload.executionId"] = strings.TrimSpace(executionID)
	return s.listReadyTaskFilter(ctx, filter, limit)
}

// PurgeDataContentExecution removes every task and outbox owned by a discarded
// Data execution. The caller must have already proved no worker owns it.
func (s *Store) PurgeDataContentExecution(
	ctx context.Context,
	executionID string,
) (reliabletask.DataContentExecutionPurgeResult, error) {
	executionID = strings.TrimSpace(executionID)
	if executionID == "" {
		return reliabletask.DataContentExecutionPurgeResult{}, errors.New("data content executionId is required")
	}
	filter := bson.M{
		"taskType":            reliabletask.DataContentTaskType,
		"payload.executionId": executionID,
	}
	cursor, err := s.tasks.Find(ctx, filter, options.Find().SetProjection(bson.M{"_id": 1}))
	if err != nil {
		return reliabletask.DataContentExecutionPurgeResult{}, err
	}
	defer cursor.Close(ctx)
	result := reliabletask.DataContentExecutionPurgeResult{}
	for cursor.Next(ctx) {
		var row struct {
			TaskID string `bson:"_id"`
		}
		if err := cursor.Decode(&row); err != nil {
			return result, err
		}
		result.TaskIDs = append(result.TaskIDs, row.TaskID)
	}
	if err := cursor.Err(); err != nil {
		return result, err
	}
	deletedTasks, err := s.tasks.DeleteMany(ctx, filter)
	if err != nil {
		return result, err
	}
	result.TasksDeleted = deletedTasks.DeletedCount
	deletedOutboxes, err := s.outboxes.DeleteMany(ctx, filter)
	if err != nil {
		return result, err
	}
	result.OutboxesDeleted = deletedOutboxes.DeletedCount
	return result, nil
}

// CountDataContentOutboxes returns the declared objects for one immutable
// execution stage without exposing the underlying Mongo collection to the
// Content composition root.
func (s *Store) CountDataContentOutboxes(
	ctx context.Context,
	executionID string,
	stage string,
) (int64, error) {
	executionID = strings.TrimSpace(executionID)
	stage = strings.TrimSpace(stage)
	if executionID == "" || (stage != "author" && stage != "publish") {
		return 0, errors.New("data content executionId and stage are required")
	}
	return s.outboxes.CountDocuments(ctx, bson.M{
		"taskType":            reliabletask.DataContentTaskType,
		"payload.executionId": executionID,
		"payload.stage":       stage,
	})
}

// ListDataContentExecutionTasks returns only tasks from one immutable
// execution in stable job order. Callers never receive a generic collection
// handle and therefore cannot scan another object's queue.
func (s *Store) ListDataContentExecutionTasks(
	ctx context.Context,
	executionID string,
) ([]reliabletask.ReliableAsyncTask, error) {
	executionID = strings.TrimSpace(executionID)
	if executionID == "" {
		return nil, errors.New("data content executionId is required")
	}
	cursor, err := s.tasks.Find(ctx, bson.M{
		"taskType":            reliabletask.DataContentTaskType,
		"payload.executionId": executionID,
	})
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var tasks []reliabletask.ReliableAsyncTask
	if err := cursor.All(ctx, &tasks); err != nil {
		return nil, err
	}
	sort.Slice(tasks, func(i, j int) bool {
		return tasks[i].Payload["jobId"] < tasks[j].Payload["jobId"]
	})
	return tasks, nil
}

func (s *Store) listReadyTaskFilter(
	ctx context.Context,
	filter bson.M,
	limit int,
) ([]reliabletask.ReliableAsyncTask, error) {
	if limit <= 0 {
		limit = 100
	}
	cursor, err := s.tasks.Find(
		ctx,
		filter,
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

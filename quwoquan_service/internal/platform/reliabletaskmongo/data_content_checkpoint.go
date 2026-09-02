package reliabletaskmongo

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/reliabletask"
)

// DataContentStore is the Post import task adapter. It intentionally exposes
// only the task state machine; notification, provider and shard-lease
// collections are not initialized in the content database.
type DataContentStore struct {
	*Store
	dataContentCheckpoints *mongo.Collection
}

// NewDataContentImport binds the reliable task state machine to collections
// owned by content.Post. Reusing Integration's generic queue names would make
// a Content worker a cross-service database writer.
func NewDataContentImport(db *mongo.Database) *DataContentStore {
	return &DataContentStore{
		Store: &Store{
			db:               db,
			outboxes:         db.Collection("post_import_task_outbox"),
			tasks:            db.Collection("post_import_task"),
			recoveryReceipts: db.Collection("post_import_task_recovery_receipt"),
		},
		dataContentCheckpoints: db.Collection("post_import_task_checkpoint"),
	}
}

func (s *DataContentStore) EnsureIndexes(ctx context.Context) error {
	if err := s.ensureTaskIndexes(ctx); err != nil {
		return err
	}
	if err := s.ensureRecoveryIndexes(ctx); err != nil {
		return err
	}
	_, err := s.dataContentCheckpoints.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "executionId", Value: 1},
			{Key: "stage", Value: 1},
			{Key: "partitionKey", Value: 1},
		},
		Options: options.Index().SetUnique(true),
	})
	return err
}

// DispatchDataContentExecution dispatches only the immutable execution named
// by the Data worker. Global due-task dispatch is unsafe here because two
// content executions may share the same Mongo outbox collection.
func (s *DataContentStore) DispatchDataContentExecution(
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

func (s *DataContentStore) AdvanceDataContentTaskFence(
	ctx context.Context,
	taskID string,
	fence reliabletask.DataContentWorkerFence,
	now time.Time,
) (bool, error) {
	if err := fence.Validate(); err != nil {
		return false, err
	}
	values := fence.PayloadForStore()
	exact := bson.M{
		"_id":                        strings.TrimSpace(taskID),
		"workerHostGenerationNumber": fence.Generation,
		"workerHostSetDigest":        values["workerHostSetDigest"],
		"workerFencingToken":         values["workerFencingToken"],
		"workerHostScopeId":          values["workerHostScopeId"],
	}
	if count, err := s.tasks.CountDocuments(ctx, exact, options.Count().SetLimit(1)); err != nil {
		return false, err
	} else if count == 1 {
		return true, nil
	}
	filter := bson.M{
		"_id":    strings.TrimSpace(taskID),
		"status": bson.M{"$nin": bson.A{reliabletask.TaskStatusSucceeded, reliabletask.TaskStatusDead}},
		"$or": bson.A{
			bson.M{"workerHostGenerationNumber": bson.M{"$lt": fence.Generation}},
			bson.M{"workerHostGenerationNumber": bson.M{"$exists": false}},
		},
	}
	set := bson.M{
		"workerHostGenerationNumber":   fence.Generation,
		"workerHostSetDigest":          values["workerHostSetDigest"],
		"workerHostGeneration":         values["workerHostGeneration"],
		"workerFencingToken":           values["workerFencingToken"],
		"workerHostScopeId":            values["workerHostScopeId"],
		"payload.workerHostSetDigest":  values["workerHostSetDigest"],
		"payload.workerHostGeneration": values["workerHostGeneration"],
		"payload.workerFencingToken":   values["workerFencingToken"],
		"payload.workerHostScopeId":    values["workerHostScopeId"],
		"status":                       reliabletask.TaskStatusReady,
		"nextAttemptAt":                now.UTC(),
		"updatedAt":                    now.UTC(),
	}
	update := bson.M{
		"$set":   set,
		"$unset": bson.M{"leaseOwner": "", "leaseToken": "", "leaseUntil": ""},
	}
	result, err := s.tasks.UpdateOne(ctx, filter, update)
	if err != nil {
		return false, err
	}
	return result.MatchedCount == 1, nil
}

// ListReadyDataContentExecution returns ready tasks for one immutable Data
// execution only; it is the Mongo truth used to rebuild its Redis stream.
func (s *DataContentStore) ListReadyDataContentExecution(
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
func (s *DataContentStore) PurgeDataContentExecution(
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

// CountDataContentOutboxesByIdempotencyKeys returns only the frozen task
// revisions requested by a worker, excluding superseded same-job revisions.
func (s *DataContentStore) CountDataContentOutboxesByIdempotencyKeys(
	ctx context.Context,
	executionID string,
	stage string,
	idempotencyKeys []string,
) (int64, error) {
	executionID = strings.TrimSpace(executionID)
	stage = strings.TrimSpace(stage)
	if executionID == "" || (stage != "author" && stage != "publish") {
		return 0, errors.New("data content executionId and stage are required")
	}
	keys := make([]string, 0, len(idempotencyKeys))
	seen := make(map[string]struct{}, len(idempotencyKeys))
	for _, raw := range idempotencyKeys {
		key := strings.TrimSpace(raw)
		if key == "" {
			continue
		}
		if _, exists := seen[key]; exists {
			continue
		}
		seen[key] = struct{}{}
		keys = append(keys, key)
	}
	if len(keys) == 0 {
		return 0, errors.New("data content idempotency keys are required")
	}
	return s.outboxes.CountDocuments(ctx, bson.M{
		"taskType":            reliabletask.DataContentTaskType,
		"payload.executionId": executionID,
		"payload.stage":       stage,
		"idempotencyKey":      bson.M{"$in": keys},
	})
}

// ListDataContentExecutionTasks returns only tasks from one immutable
// execution in stable job order. Callers never receive a generic collection
// handle and therefore cannot scan another object's queue.
func (s *DataContentStore) ListDataContentExecutionTasks(
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

type dataContentCheckpointDocument struct {
	ID             string `bson:"_id"`
	ExecutionID    string `bson:"executionId"`
	Stage          string `bson:"stage"`
	PartitionKey   string `bson:"partitionKey"`
	JobSetDigest   string `bson:"jobSetDigest"`
	CursorJobID    string `bson:"cursorJobId"`
	CompletedCount int    `bson:"completedCount"`
}

func dataContentCheckpointID(value reliabletask.DataContentPartitionCheckpoint) string {
	return strings.Join([]string{value.ExecutionID, value.Stage, value.PartitionKey}, "|")
}

func validateDataContentCheckpoint(value reliabletask.DataContentPartitionCheckpoint) error {
	if strings.TrimSpace(value.ExecutionID) == "" ||
		(value.Stage != "author" && value.Stage != "publish") ||
		strings.TrimSpace(value.PartitionKey) == "" ||
		!reliabletask.ValidSHA256Digest(value.JobSetDigest) ||
		strings.TrimSpace(value.CursorJobID) == "" ||
		value.CompletedCount < 1 || value.FlushedAt.IsZero() {
		return fmt.Errorf("data content partition checkpoint identity is invalid")
	}
	return nil
}

// FlushDataContentPartitionCheckpoint advances one Mongo watermark. The
// job-set digest is part of the update predicate, so a stale controller cannot
// overwrite a checkpoint after a new immutable attempt owns the partition.
func (s *DataContentStore) FlushDataContentPartitionCheckpoint(
	ctx context.Context,
	checkpoint reliabletask.DataContentPartitionCheckpoint,
) error {
	if err := validateDataContentCheckpoint(checkpoint); err != nil {
		return err
	}
	id := dataContentCheckpointID(checkpoint)
	filter := bson.M{
		"_id":            id,
		"jobSetDigest":   checkpoint.JobSetDigest,
		"completedCount": bson.M{"$lte": checkpoint.CompletedCount},
	}
	update := bson.M{"$set": bson.M{
		"cursorJobId":    checkpoint.CursorJobID,
		"completedCount": checkpoint.CompletedCount,
		"flushedAt":      checkpoint.FlushedAt.UTC(),
	}}
	result, err := s.dataContentCheckpoints.UpdateOne(ctx, filter, update)
	if err != nil {
		return fmt.Errorf("flush data content partition checkpoint: %w", err)
	}
	if result.MatchedCount == 1 {
		return nil
	}
	document := bson.M{
		"_id":            id,
		"executionId":    checkpoint.ExecutionID,
		"stage":          checkpoint.Stage,
		"partitionKey":   checkpoint.PartitionKey,
		"jobSetDigest":   checkpoint.JobSetDigest,
		"cursorJobId":    checkpoint.CursorJobID,
		"completedCount": checkpoint.CompletedCount,
		"flushedAt":      checkpoint.FlushedAt.UTC(),
	}
	if _, err := s.dataContentCheckpoints.InsertOne(ctx, document); err == nil {
		return nil
	} else if !mongo.IsDuplicateKeyError(err) {
		return fmt.Errorf("create data content partition checkpoint: %w", err)
	}
	var existing dataContentCheckpointDocument
	if err := s.dataContentCheckpoints.FindOne(ctx, bson.M{"_id": id}).Decode(&existing); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return fmt.Errorf("data content partition checkpoint collision disappeared")
		}
		return fmt.Errorf("load data content partition checkpoint collision: %w", err)
	}
	if existing.JobSetDigest != checkpoint.JobSetDigest {
		return fmt.Errorf("DATA.RELIABLETASK.STALE_FENCE: partition checkpoint jobSetDigest drift")
	}
	return fmt.Errorf("DATA.RELIABLETASK.STALE_CHECKPOINT: partition checkpoint cannot move backwards")
}

var _ reliabletask.DataContentCheckpointStore = (*DataContentStore)(nil)

var _ reliabletask.DataContentExecutionStore = (*DataContentStore)(nil)

func (s *DataContentStore) ClaimReadyTaskByIDWithFence(
	ctx context.Context,
	taskID string,
	workerID string,
	leaseTTL time.Duration,
	now time.Time,
	fence map[string]string,
) (*reliabletask.ReliableAsyncTask, error) {
	filter := readyTaskFilter(nil, strings.TrimSpace(taskID), now)
	filter["workerHostSetDigest"] = fence["workerHostSetDigest"]
	filter["workerHostGeneration"] = fence["workerHostGeneration"]
	filter["workerFencingToken"] = fence["workerFencingToken"]
	filter["workerHostScopeId"] = fence["workerHostScopeId"]
	token := reliabletask.NewRecordID("lease")
	update := bson.M{"$set": bson.M{
		"status": reliabletask.TaskStatusProcessing, "leaseOwner": strings.TrimSpace(workerID),
		"leaseToken": token, "leaseUntil": now.Add(leaseTTL).UTC(), "updatedAt": now.UTC(),
	}}
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

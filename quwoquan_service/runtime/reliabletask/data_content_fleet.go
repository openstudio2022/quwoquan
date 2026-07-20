package reliabletask

import (
	"context"
	"encoding/hex"
	"fmt"
	"strings"
	"time"
)

const (
	DataContentTaskType = "data.content_object.execute"
	DataContentQueue    = "reliabletask.data.content_supply"
)

// DataContentJob 是 quwoquan_data object_job 到 runtime/reliabletask 的强类型适配契约。
// 幂等身份由 entity + carrier + sourceRevision + stage 构成；同一内容对象的
// download/author/publish 是三个独立工作，批次与 worker 等易漂移字段仍不得进入。
type DataContentJob struct {
	EntityRef      string `json:"entityRef"`
	Carrier        string `json:"carrier"`
	SourceRevision string `json:"sourceRevision"`
	JobID          string `json:"jobId"`
	ExecutionID    string `json:"executionId"`
	Ref            string `json:"ref"`
	Stage          string `json:"stage"`
	PartitionKey   string `json:"partitionKey"`
}

func (j DataContentJob) IdempotencyKey() (string, error) {
	entity := strings.TrimSpace(j.EntityRef)
	carrier := strings.TrimSpace(j.Carrier)
	revision := strings.TrimSpace(j.SourceRevision)
	stage := strings.TrimSpace(j.Stage)
	if entity == "" || carrier == "" || revision == "" || stage == "" {
		return "", fmt.Errorf(
			"reliabletask data job requires entityRef + carrier + sourceRevision + stage",
		)
	}
	rawRevision := strings.TrimPrefix(revision, "sha256:")
	if !strings.HasPrefix(revision, "sha256:") || len(rawRevision) != 64 {
		return "", fmt.Errorf("reliabletask data job sourceRevision must be sha256")
	}
	if _, err := hex.DecodeString(rawRevision); err != nil {
		return "", fmt.Errorf("reliabletask data job sourceRevision must be sha256: %w", err)
	}
	for _, field := range []struct {
		name  string
		value string
	}{
		{name: "jobId", value: j.JobID},
		{name: "executionId", value: j.ExecutionID},
		{name: "ref", value: j.Ref},
	} {
		if strings.TrimSpace(field.value) == "" {
			return "", fmt.Errorf("reliabletask data job requires %s", field.name)
		}
	}
	return entity + "|" + carrier + "|" + revision + "|" + stage, nil
}

func (j DataContentJob) payload(idempotencyKey string) map[string]string {
	return map[string]string{
		"schema":         "quwoquan.object_job",
		"jobId":          strings.TrimSpace(j.JobID),
		"executionId":    strings.TrimSpace(j.ExecutionID),
		"ref":            strings.TrimSpace(j.Ref),
		"stage":          strings.TrimSpace(j.Stage),
		"partitionKey":   strings.TrimSpace(j.PartitionKey),
		"entityRef":      strings.TrimSpace(j.EntityRef),
		"carrier":        strings.TrimSpace(j.Carrier),
		"sourceRevision": strings.TrimSpace(j.SourceRevision),
		"idempotencyKey": idempotencyKey,
	}
}

// DataContentFleet 复用 runtime/reliabletask 的 Store/ReadyIndex/Worker，
// 不在 data 仓再实现 Mongo/Redis 状态机。
type DataContentFleet struct {
	Store          Store
	Ready          ReadyIndex
	WorkerID       string
	LeaseTTL       time.Duration
	PendingMinIdle time.Duration
	Retry          RetryPolicy
	ResultVerifier DataContentResultVerifier
	Now            func() time.Time
}

func (f DataContentFleet) Declare(ctx context.Context, job DataContentJob) (TaskOutboxRecord, error) {
	if f.Store == nil {
		return TaskOutboxRecord{}, ErrStoreRequired
	}
	key, err := job.IdempotencyKey()
	if err != nil {
		return TaskOutboxRecord{}, err
	}
	partitionKey := strings.TrimSpace(job.PartitionKey)
	if partitionKey == "" {
		partitionKey = strings.TrimSpace(job.EntityRef)
	}
	payload := job.payload(key)
	return f.Store.DeclareTask(ctx, DeclareTaskRequest{
		TaskType:        DataContentTaskType,
		OwnerDomain:     "data",
		AggregateType:   "content_object",
		AggregateID:     strings.TrimSpace(job.EntityRef),
		DedupeKey:       key,
		IdempotencyKey:  key,
		PartitionKey:    partitionKey,
		Payload:         payload,
		PayloadAllow:    []string{"schema", "jobId", "executionId", "ref", "stage", "partitionKey", "entityRef", "carrier", "sourceRevision", "idempotencyKey"},
		CreatedByModule: "data.task_outbox_dispatcher",
	})
}

func (f DataContentFleet) Dispatch(ctx context.Context, limit int) ([]ReliableAsyncTask, error) {
	dispatcher := Dispatcher{Store: f.Store, Ready: f.Ready, Now: f.Now}
	return dispatcher.DispatchDue(ctx, limit)
}

// ReconcileReadyIndex rebuilds the disposable Redis ready index from Mongo truth.
// Duplicate stream messages are harmless: ClaimReadyTaskByID fences them against
// the single task record and workers ACK stale messages.
func (f DataContentFleet) ReconcileReadyIndex(ctx context.Context, limit int) (int, error) {
	if f.Store == nil {
		return 0, ErrStoreRequired
	}
	if f.Ready == nil {
		return 0, nil
	}
	now := time.Now().UTC()
	if f.Now != nil {
		now = f.Now().UTC()
	}
	tasks, err := f.Store.ListReadyTasks(
		ctx,
		[]string{DataContentTaskType},
		limit,
		now,
	)
	if err != nil {
		return 0, err
	}
	enqueued := 0
	for _, task := range tasks {
		if err := f.Ready.EnqueueReadyOrMerge(ctx, task); err != nil {
			return enqueued, err
		}
		enqueued++
	}
	return enqueued, nil
}

func (f DataContentFleet) ProcessOne(ctx context.Context, handler TaskHandler) (bool, error) {
	workerID := strings.TrimSpace(f.WorkerID)
	if workerID == "" {
		workerID = "data-content-worker"
	}
	worker := Worker{
		Store:          f.Store,
		Ready:          f.Ready,
		TaskTypes:      []string{DataContentTaskType},
		WorkerID:       workerID,
		LeaseTTL:       f.LeaseTTL,
		PendingMinIdle: f.PendingMinIdle,
		Retry:          f.Retry,
		Now:            f.Now,
	}
	return worker.ProcessOne(ctx, handler)
}

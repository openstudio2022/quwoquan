package reliabletask

import (
	"context"
	"fmt"
	"strings"
	"time"
)

const (
	DataContentTaskType = "data.content_object.execute"
	DataContentQueue    = "reliabletask.data.content_supply"
)

// DataContentJob 是 quwoquan_data object_job 到 runtime/reliabletask 的强类型适配契约。
// 幂等身份只由 entity + carrier + sourceRevision 构成，不含批次/worker 等易漂移字段。
type DataContentJob struct {
	EntityRef      string
	Carrier        string
	SourceRevision string
	JobID          string
	TaskID         string
	BatchID        string
	Ref            string
	Stage          string
	PartitionKey   string
}

func (j DataContentJob) IdempotencyKey() (string, error) {
	entity := strings.TrimSpace(j.EntityRef)
	carrier := strings.TrimSpace(j.Carrier)
	revision := strings.TrimSpace(j.SourceRevision)
	if entity == "" || carrier == "" || revision == "" {
		return "", fmt.Errorf("reliabletask data job requires entityRef + carrier + sourceRevision")
	}
	return entity + "|" + carrier + "|" + revision, nil
}

func (j DataContentJob) payload(idempotencyKey string) map[string]string {
	return map[string]string{
		"schemaVersion":  "quwoquan.object_job",
		"jobId":          strings.TrimSpace(j.JobID),
		"taskId":         strings.TrimSpace(j.TaskID),
		"batchId":        strings.TrimSpace(j.BatchID),
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
		PayloadAllow:    []string{"schemaVersion", "jobId", "taskId", "batchId", "ref", "stage", "partitionKey", "entityRef", "carrier", "sourceRevision", "idempotencyKey"},
		CreatedByModule: "data.task_outbox_dispatcher",
	})
}

func (f DataContentFleet) Dispatch(ctx context.Context, limit int) ([]ReliableAsyncTask, error) {
	dispatcher := Dispatcher{Store: f.Store, Ready: f.Ready, Now: f.Now}
	return dispatcher.DispatchDue(ctx, limit)
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

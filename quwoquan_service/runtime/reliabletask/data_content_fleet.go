package reliabletask

import (
	"context"
	"encoding/hex"
	"fmt"
	"strconv"
	"strings"
	"time"
)

const (
	DataContentTaskType = "data.content_object.execute"
	DataContentQueue    = "reliabletask.data.content_supply"
)

// DataContentCampaignBinding is the immutable M100 campaign owner identity.
// It is copied into Mongo task payloads so live observation never relies on
// process environment variables as evidence.
type DataContentCampaignBinding struct {
	RootExecutionID     string `json:"rootExecutionId"`
	RunID               string `json:"campaignRunId"`
	Generation          int    `json:"campaignGeneration"`
	FencingToken        string `json:"campaignFencingToken"`
	PlanDigest          string `json:"campaignPlanDigest"`
	SourceRevision      string `json:"campaignSourceRevision"`
	SourceDigest        string `json:"campaignSourceDigest"`
	EntityCatalogDigest string `json:"campaignEntityCatalogDigest"`
}

// DataContentWorkerFence is the central Mongo claim authority for one host generation.
type DataContentWorkerFence struct {
	HostSetDigest string
	Generation    int
	FencingToken  string
	HostScopeID   string
}

func (f DataContentWorkerFence) Validate() error {
	if !validSHA256Digest(f.HostSetDigest) || f.Generation < 1 ||
		!validSHA256Digest(f.FencingToken) || strings.TrimSpace(f.HostScopeID) == "" {
		return fmt.Errorf("reliabletask data worker fence is invalid")
	}
	return nil
}

func (f DataContentWorkerFence) payload() map[string]string {
	return map[string]string{
		"workerHostSetDigest":  strings.TrimSpace(f.HostSetDigest),
		"workerHostGeneration": strconv.Itoa(f.Generation),
		"workerFencingToken":   strings.TrimSpace(f.FencingToken),
		"workerHostScopeId":    strings.TrimSpace(f.HostScopeID),
	}
}

func (f DataContentWorkerFence) PayloadForStore() map[string]string {
	return f.payload()
}

func (b DataContentCampaignBinding) empty() bool {
	return strings.TrimSpace(b.RootExecutionID) == "" &&
		strings.TrimSpace(b.RunID) == "" &&
		b.Generation == 0 &&
		strings.TrimSpace(b.FencingToken) == "" &&
		strings.TrimSpace(b.PlanDigest) == "" &&
		strings.TrimSpace(b.SourceRevision) == "" &&
		strings.TrimSpace(b.SourceDigest) == "" &&
		strings.TrimSpace(b.EntityCatalogDigest) == ""
}

func (b DataContentCampaignBinding) IsEmpty() bool {
	return b.empty()
}

func (b DataContentCampaignBinding) Validate() error {
	if strings.TrimSpace(b.RootExecutionID) == "" ||
		strings.TrimSpace(b.RunID) == "" ||
		b.Generation < 1 {
		return fmt.Errorf("reliabletask campaign binding requires rootExecutionId, runId and generation")
	}
	for _, field := range []struct {
		name  string
		value string
	}{
		{name: "fencingToken", value: b.FencingToken},
		{name: "planDigest", value: b.PlanDigest},
		{name: "sourceRevision", value: b.SourceRevision},
		{name: "sourceDigest", value: b.SourceDigest},
		{name: "entityCatalogDigest", value: b.EntityCatalogDigest},
	} {
		if !validSHA256Digest(field.value) {
			return fmt.Errorf("reliabletask campaign binding %s must be sha256", field.name)
		}
	}
	return nil
}

func (b DataContentCampaignBinding) payload() map[string]string {
	return map[string]string{
		"campaignRootExecutionId":     strings.TrimSpace(b.RootExecutionID),
		"campaignRunId":               strings.TrimSpace(b.RunID),
		"campaignGeneration":          strconv.Itoa(b.Generation),
		"campaignFencingToken":        strings.TrimSpace(b.FencingToken),
		"campaignPlanDigest":          strings.TrimSpace(b.PlanDigest),
		"campaignSourceRevision":      strings.TrimSpace(b.SourceRevision),
		"campaignSourceDigest":        strings.TrimSpace(b.SourceDigest),
		"campaignEntityCatalogDigest": strings.TrimSpace(b.EntityCatalogDigest),
	}
}

// DataContentJob 是 quwoquan_data object_job 到 runtime/reliabletask 的强类型适配契约。
// 幂等身份由 executionId + entity + carrier + sourceRevision + stage 构成。同一
// immutable execution 的重复声明必须合并；retryOf 创建的新 execution 即使复用相同
// 来源版本，也不得绑定旧 execution 的任务结果、死信或作者证据。
type DataContentJob struct {
	EntityRef               string                     `json:"entityRef"`
	Carrier                 string                     `json:"carrier"`
	SourceRevision          string                     `json:"sourceRevision"`
	JobID                   string                     `json:"jobId"`
	ExecutionID             string                     `json:"executionId"`
	Ref                     string                     `json:"ref"`
	Stage                   string                     `json:"stage"`
	PartitionKey            string                     `json:"partitionKey"`
	IdempotencyKey          string                     `json:"idempotencyKey"`
	MaxAttempts             int                        `json:"maxAttempts"`
	ExecutionEnvelopeDigest string                     `json:"executionEnvelopeDigest,omitempty"`
	JobSetEnvelopeDigest    string                     `json:"jobSetEnvelopeDigest,omitempty"`
	JobSetDigest            string                     `json:"jobSetDigest,omitempty"`
	ActualTaskDigest        string                     `json:"actualTaskDigest,omitempty"`
	Campaign                DataContentCampaignBinding `json:"campaignBinding,omitempty"`
	WorkerFence             *DataContentWorkerFence    `json:"-"`
}

func (j DataContentJob) ExpectedIdempotencyKey() (string, error) {
	executionID := strings.TrimSpace(j.ExecutionID)
	entity := strings.TrimSpace(j.EntityRef)
	carrier := strings.TrimSpace(j.Carrier)
	revision := strings.TrimSpace(j.SourceRevision)
	stage := strings.TrimSpace(j.Stage)
	if executionID == "" || entity == "" || carrier == "" || revision == "" || stage == "" {
		return "", fmt.Errorf(
			"reliabletask data job requires executionId + entityRef + carrier + sourceRevision + stage",
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
	return executionID + "|" + entity + "|" + carrier + "|" + revision + "|" + stage, nil
}

// ValidateIdentity rejects cross-boundary drift before a job reaches Mongo.
// The queue owns the declared key; Go verifies rather than silently rebuilding
// a second identity truth source.
func (j DataContentJob) ValidateIdentity() (string, error) {
	expected, err := j.ExpectedIdempotencyKey()
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(j.IdempotencyKey) == "" {
		return "", fmt.Errorf("reliabletask data job requires idempotencyKey")
	}
	if strings.TrimSpace(j.IdempotencyKey) != expected {
		return "", fmt.Errorf("reliabletask data job idempotencyKey does not match immutable job identity")
	}
	if j.MaxAttempts < 1 {
		return "", fmt.Errorf("reliabletask data job maxAttempts must be >= 1")
	}
	if !j.Campaign.empty() {
		if err := j.Campaign.Validate(); err != nil {
			return "", err
		}
		if !validSHA256Digest(j.ExecutionEnvelopeDigest) {
			return "", fmt.Errorf("reliabletask campaign job execution envelope digest must be sha256")
		}
	}
	if !validSHA256Digest(j.JobSetEnvelopeDigest) ||
		!validSHA256Digest(j.JobSetDigest) ||
		!validSHA256Digest(j.ActualTaskDigest) {
		return "", fmt.Errorf("reliabletask data job requires frozen job-set digests")
	}
	if j.WorkerFence != nil {
		if err := j.WorkerFence.Validate(); err != nil {
			return "", err
		}
	}
	return expected, nil
}

func (j DataContentJob) payload(idempotencyKey string) map[string]string {
	payload := map[string]string{
		"schema":               "quwoquan.object_job",
		"jobId":                strings.TrimSpace(j.JobID),
		"executionId":          strings.TrimSpace(j.ExecutionID),
		"ref":                  strings.TrimSpace(j.Ref),
		"stage":                strings.TrimSpace(j.Stage),
		"partitionKey":         strings.TrimSpace(j.PartitionKey),
		"entityRef":            strings.TrimSpace(j.EntityRef),
		"carrier":              strings.TrimSpace(j.Carrier),
		"sourceRevision":       strings.TrimSpace(j.SourceRevision),
		"idempotencyKey":       idempotencyKey,
		"maxAttempts":          strconv.Itoa(j.MaxAttempts),
		"jobSetEnvelopeDigest": strings.TrimSpace(j.JobSetEnvelopeDigest),
		"jobSetDigest":         strings.TrimSpace(j.JobSetDigest),
		"actualTaskDigest":     strings.TrimSpace(j.ActualTaskDigest),
	}
	if !j.Campaign.empty() {
		payload["executionEnvelopeDigest"] = strings.TrimSpace(j.ExecutionEnvelopeDigest)
		for key, value := range j.Campaign.payload() {
			payload[key] = value
		}
	}
	if j.WorkerFence != nil {
		for key, value := range j.WorkerFence.payload() {
			payload[key] = value
		}
	}
	return payload
}

// DataContentFleet 复用 runtime/reliabletask 的 Store/ReadyIndex/Worker，
// 不在 data 仓再实现 Mongo/Redis 状态机。
type DataContentFleet struct {
	Store             DataContentExecutionStore
	ExecutionID       string
	Ready             ReadyIndex
	WorkerID          string
	LeaseTTL          time.Duration
	PendingMinIdle    time.Duration
	Retry             RetryPolicy
	AllowedPartitions map[string]struct{}
	WorkerFence       *DataContentWorkerFence
	ResultVerifier    DataContentResultVerifier
	Now               func() time.Time
}

func (f DataContentFleet) ownsPartition(task ReliableAsyncTask) bool {
	if len(f.AllowedPartitions) == 0 {
		return true
	}
	_, ok := f.AllowedPartitions[strings.TrimSpace(task.PartitionKey)]
	return ok
}

// DataContentExecutionStore is the execution-scoped ReliableTask boundary for
// Data content work. A content worker must never dispatch or re-index another
// execution merely because its outbox happens to be due at the same time.
type DataContentExecutionStore interface {
	TaskStore
	DispatchDataContentExecution(
		ctx context.Context,
		executionID string,
		now time.Time,
		limit int,
	) ([]ReliableAsyncTask, error)
	ListReadyDataContentExecution(
		ctx context.Context,
		executionID string,
		limit int,
		now time.Time,
	) ([]ReliableAsyncTask, error)
	PurgeDataContentExecution(
		ctx context.Context,
		executionID string,
	) (DataContentExecutionPurgeResult, error)
	CountDataContentOutboxesByIdempotencyKeys(
		ctx context.Context,
		executionID string,
		stage string,
		idempotencyKeys []string,
	) (int64, error)
	ListDataContentExecutionTasks(
		ctx context.Context,
		executionID string,
	) ([]ReliableAsyncTask, error)
}

// DataContentExecutionPurgeResult reports only records owned by one discarded
// execution. It is intentionally not a retention policy or a global cleanup.
type DataContentExecutionPurgeResult struct {
	TaskIDs         []string
	TasksDeleted    int64
	OutboxesDeleted int64
}

// DataContentPartitionCheckpoint is a durable progress watermark for one
// immutable execution/stage/partition. JobSetDigest is the fencing identity;
// a replacement attempt cannot advance a checkpoint owned by another job set.
type DataContentPartitionCheckpoint struct {
	ExecutionID    string
	Stage          string
	PartitionKey   string
	JobSetDigest   string
	CursorJobID    string
	CompletedCount int
	FlushedAt      time.Time
}

type DataContentCheckpointStore interface {
	FlushDataContentPartitionCheckpoint(
		ctx context.Context,
		checkpoint DataContentPartitionCheckpoint,
	) error
}

type DataContentFenceStore interface {
	AdvanceDataContentTaskFence(
		ctx context.Context,
		taskID string,
		fence DataContentWorkerFence,
		now time.Time,
	) (bool, error)
}

func (f DataContentFleet) BindWorkerFence(
	ctx context.Context,
	tasks []ReliableAsyncTask,
) error {
	if f.WorkerFence == nil {
		return nil
	}
	if err := f.WorkerFence.Validate(); err != nil {
		return err
	}
	store, ok := f.Store.(DataContentFenceStore)
	if !ok {
		return fmt.Errorf("data content fleet requires durable worker fence store")
	}
	now := time.Now().UTC()
	if f.Now != nil {
		now = f.Now().UTC()
	}
	for _, task := range tasks {
		bound, err := store.AdvanceDataContentTaskFence(ctx, task.TaskID, *f.WorkerFence, now)
		if err != nil {
			return err
		}
		if !bound {
			return fmt.Errorf("stale data content worker generation rejected for task %s", task.TaskID)
		}
	}
	return nil
}

func (f DataContentFleet) executionID() (string, error) {
	executionID := strings.TrimSpace(f.ExecutionID)
	if executionID == "" {
		return "", fmt.Errorf("data content fleet executionId is required")
	}
	return executionID, nil
}

func (f DataContentFleet) Declare(ctx context.Context, job DataContentJob) (TaskOutboxRecord, error) {
	if f.Store == nil {
		return TaskOutboxRecord{}, ErrStoreRequired
	}
	executionID, err := f.executionID()
	if err != nil {
		return TaskOutboxRecord{}, err
	}
	if strings.TrimSpace(job.ExecutionID) != executionID {
		return TaskOutboxRecord{}, fmt.Errorf("data content job executionId does not match fleet execution")
	}
	key, err := job.ValidateIdentity()
	if err != nil {
		return TaskOutboxRecord{}, err
	}
	partitionKey := strings.TrimSpace(job.PartitionKey)
	if partitionKey == "" {
		partitionKey = strings.TrimSpace(job.EntityRef)
	}
	payload := job.payload(key)
	payloadAllow := []string{
		"schema", "jobId", "executionId", "ref", "stage", "partitionKey",
		"entityRef", "carrier", "sourceRevision", "idempotencyKey",
		"maxAttempts",
		"jobSetEnvelopeDigest", "jobSetDigest", "actualTaskDigest",
	}
	if job.WorkerFence != nil {
		payloadAllow = append(payloadAllow, "workerHostSetDigest", "workerHostGeneration", "workerFencingToken", "workerHostScopeId")
	}
	if !job.Campaign.empty() {
		payloadAllow = append(
			payloadAllow,
			"campaignRootExecutionId",
			"campaignRunId",
			"campaignGeneration",
			"campaignFencingToken",
			"campaignPlanDigest",
			"campaignSourceRevision",
			"campaignSourceDigest",
			"campaignEntityCatalogDigest",
			"executionEnvelopeDigest",
		)
	}
	return f.Store.DeclareTask(ctx, DeclareTaskRequest{
		TaskType:        DataContentTaskType,
		OwnerDomain:     "data",
		AggregateType:   "content_object",
		AggregateID:     strings.TrimSpace(job.EntityRef),
		DedupeKey:       key,
		IdempotencyKey:  key,
		PartitionKey:    partitionKey,
		Payload:         payload,
		PayloadAllow:    payloadAllow,
		CreatedByModule: "data.task_outbox_dispatcher",
	})
}

func (f DataContentFleet) Dispatch(ctx context.Context, limit int) ([]ReliableAsyncTask, error) {
	if f.Store == nil {
		return nil, ErrStoreRequired
	}
	executionID, err := f.executionID()
	if err != nil {
		return nil, err
	}
	now := time.Now().UTC()
	if f.Now != nil {
		now = f.Now().UTC()
	}
	tasks, err := f.Store.DispatchDataContentExecution(ctx, executionID, now, limit)
	if err != nil {
		return nil, err
	}
	owned := make([]ReliableAsyncTask, 0, len(tasks))
	for _, task := range tasks {
		if f.ownsPartition(task) {
			owned = append(owned, task)
		}
	}
	if f.Ready != nil {
		for _, task := range owned {
			if err := f.Ready.EnqueueReadyOrMerge(ctx, task); err != nil {
				return nil, err
			}
		}
	}
	return owned, nil
}

// RecoverAuditedDeadJobs revives only request-selected dead tasks. The
// controller records recovery before this method can be called; the retained
// logical idempotency key prevents duplicate content while the next claim gets
// a new runtime lease from Mongo truth.
func (f DataContentFleet) RecoverAuditedDeadJobs(
	ctx context.Context,
	jobs []DataContentJob,
) (int, error) {
	recovery, ok := f.Store.(DLQRecoveryStore)
	if !ok {
		return 0, fmt.Errorf("data content fleet store does not support DLQ recovery")
	}
	wanted := make(map[string]struct{}, len(jobs))
	for _, job := range jobs {
		key, err := job.ValidateIdentity()
		if err != nil {
			return 0, err
		}
		wanted[key] = struct{}{}
	}
	dead, err := recovery.ListDeadTasks(ctx, []string{DataContentTaskType}, 0)
	if err != nil {
		return 0, err
	}
	now := time.Now().UTC()
	if f.Now != nil {
		now = f.Now().UTC()
	}
	recovered := 0
	for _, task := range dead {
		if _, selected := wanted[strings.TrimSpace(task.Payload["idempotencyKey"])]; !selected {
			continue
		}
		if err := recovery.RecoverDeadTask(ctx, task.TaskID, now); err != nil {
			return recovered, err
		}
		recovered++
	}
	return recovered, nil
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
	executionID, err := f.executionID()
	if err != nil {
		return 0, err
	}
	now := time.Now().UTC()
	if f.Now != nil {
		now = f.Now().UTC()
	}
	tasks, err := f.Store.ListReadyDataContentExecution(
		ctx,
		executionID,
		limit,
		now,
	)
	if err != nil {
		return 0, err
	}
	enqueued := 0
	for _, task := range tasks {
		if !f.ownsPartition(task) {
			continue
		}
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
		RetryPolicyForTask: func(task ReliableAsyncTask) (RetryPolicy, error) {
			maxAttempts, err := strconv.Atoi(strings.TrimSpace(task.Payload["maxAttempts"]))
			if err != nil || maxAttempts < 1 {
				return RetryPolicy{}, fmt.Errorf(
					"reliabletask data task %s maxAttempts is invalid",
					task.TaskID,
				)
			}
			policy := f.Retry
			policy.MaxAttempts = maxAttempts
			return policy, nil
		},
		Now: f.Now,
		ClaimFence: func() map[string]string {
			if f.WorkerFence == nil {
				return nil
			}
			return f.WorkerFence.payload()
		}(),
	}
	return worker.ProcessOne(ctx, handler)
}

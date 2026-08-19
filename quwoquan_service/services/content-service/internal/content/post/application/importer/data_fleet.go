package importer

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/reliabletask"
)

// FleetRequestSchema is the immutable schema of one content release execution.
const FleetRequestSchema = "quwoquan.data_content_fleet_request"

const (
	dataContentOutboxTaskTypeField    = "taskType"
	dataContentOutboxExecutionIDField = "payload.executionId"
	dataContentOutboxStageField       = "payload.stage"
)

// FleetRequest binds every author/publish task to one frozen release execution.
// It is part of the Post importer application boundary; the worker command only
// supplies process and infrastructure composition.
// TargetObjectCount, FleetMaxConcurrentWorkers and RequiredQuota carry three
// different facts and none of them may stand in for another: the frozen
// work-unit count, the process concurrency ceiling, and the object floor this
// batch must reach. FleetWaveCount is the only value derived from two of them,
// and FleetBatchDeadlineEpochSeconds is absolute so no restart can widen it.
type FleetRequest struct {
	Schema                         string                                   `json:"schema"`
	ExecutionID                    string                                   `json:"executionId"`
	CampaignScale                  string                                   `json:"campaignScale"`
	ScaleClass                     string                                   `json:"scaleClass"`
	ExecutionEnvelopeDigest        string                                   `json:"executionEnvelopeDigest"`
	JobSetEnvelopeDigest           string                                   `json:"jobSetEnvelopeDigest"`
	JobSetDigest                   string                                   `json:"jobSetDigest"`
	ActualTaskDigest               string                                   `json:"actualTaskDigest"`
	CapacityPlanDigest             string                                   `json:"capacityPlanDigest"`
	CalibrationReceiptDigest       string                                   `json:"calibrationReceiptDigest"`
	TargetObjectCount              int                                      `json:"targetObjectCount"`
	FleetMaxConcurrentWorkers      int                                      `json:"fleetMaxConcurrentWorkers"`
	FleetWaveCount                 int                                      `json:"fleetWaveCount"`
	FleetBatchDeadlineEpochSeconds int64                                    `json:"fleetBatchDeadlineEpochSeconds"`
	PartitionCount                 int                                      `json:"partitionCount"`
	PartitionAlgorithm             string                                   `json:"partitionAlgorithm"`
	CheckpointPolicy               DataContentCheckpointPolicy              `json:"checkpointPolicy"`
	RequireCommercial              bool                                     `json:"requireCommercial"`
	RecoverDeadTasks               *bool                                    `json:"recoverDeadTasks"`
	ObjectTimeoutMS                int                                      `json:"objectTimeoutMilliseconds"`
	GlobalRequiredQuota            int                                      `json:"globalRequiredQuota"`
	RequiredQuota                  int                                      `json:"requiredQuota"`
	CampaignBinding                *reliabletask.DataContentCampaignBinding `json:"campaignBinding,omitempty"`
	WorkerHostBinding              *WorkerHostBinding                       `json:"workerHostBinding,omitempty"`
	Jobs                           []FleetRequestJob                        `json:"jobs"`
}

// FleetRequestJob is one frozen work unit exactly as
// quwoquan_data/schema/execution/data_content_fleet_request.schema.json declares
// it under jobs.items, which is closed with additionalProperties:false. The
// envelope digests, campaign binding and worker fence a running task also needs
// are owned by the request, not by the job, so they live on
// reliabletask.DataContentJob and are bound by ExecutionJobs.
type FleetRequestJob struct {
	EntityRef      string `json:"entityRef"`
	Carrier        string `json:"carrier"`
	SourceRevision string `json:"sourceRevision"`
	IdempotencyKey string `json:"idempotencyKey"`
	JobID          string `json:"jobId"`
	ExecutionID    string `json:"executionId"`
	Ref            string `json:"ref"`
	Stage          string `json:"stage"`
	PartitionKey   string `json:"partitionKey"`
	MaxAttempts    int    `json:"maxAttempts"`
}

// ExecutionJobs binds every frozen work unit to the request-level identity the
// runtime needs. It is a projection, not a second stored truth: a job cannot
// carry its own envelope digests, campaign binding or worker fence, so those
// can only come from the one request that froze them.
func (r FleetRequest) ExecutionJobs() []reliabletask.DataContentJob {
	jobs := make([]reliabletask.DataContentJob, 0, len(r.Jobs))
	for _, job := range r.Jobs {
		bound := reliabletask.DataContentJob{
			EntityRef:               job.EntityRef,
			Carrier:                 job.Carrier,
			SourceRevision:          job.SourceRevision,
			JobID:                   job.JobID,
			ExecutionID:             job.ExecutionID,
			Ref:                     job.Ref,
			Stage:                   job.Stage,
			PartitionKey:            job.PartitionKey,
			IdempotencyKey:          job.IdempotencyKey,
			MaxAttempts:             job.MaxAttempts,
			ExecutionEnvelopeDigest: r.ExecutionEnvelopeDigest,
			JobSetEnvelopeDigest:    r.JobSetEnvelopeDigest,
			JobSetDigest:            r.JobSetDigest,
			ActualTaskDigest:        r.ActualTaskDigest,
		}
		if r.CampaignBinding != nil {
			bound.Campaign = *r.CampaignBinding
		}
		if r.WorkerHostBinding != nil {
			bound.WorkerFence = &reliabletask.DataContentWorkerFence{
				HostSetDigest: r.WorkerHostBinding.HostSetDigest,
				Generation:    r.WorkerHostBinding.Generation,
				FencingToken:  r.WorkerHostBinding.FencingToken,
				HostScopeID:   r.WorkerHostBinding.HostScopeID,
			}
		}
		jobs = append(jobs, bound)
	}
	return jobs
}

type WorkerHostTransportBinding struct {
	MongoTransportDigest string `json:"mongoTransportDigest"`
	RedisTransportDigest string `json:"redisTransportDigest"`
}

// WorkerHostBinding is the exact host/generation/partition slice admitted by Data.
type WorkerHostBinding struct {
	HostSetID                string                     `json:"hostSetId"`
	Generation               int                        `json:"generation"`
	FencingToken             string                     `json:"fencingToken"`
	HostSetDigest            string                     `json:"hostSetDigest"`
	Transport                WorkerHostTransportBinding `json:"transportBinding"`
	HostScopeID              string                     `json:"hostScopeId"`
	WorkerCount              int                        `json:"workerCount"`
	PartitionKeys            []string                   `json:"partitionKeys"`
	RuntimeProfileDigest     string                     `json:"runtimeProfileDigest"`
	ExecutorBundleRef        string                     `json:"executorBundleRef"`
	ExecutorBundleDigest     string                     `json:"executorBundleDigest"`
	ExecutorBundleFileSHA256 string                     `json:"executorBundleFileSha256"`
	SourceCapsuleID          string                     `json:"sourceCapsuleId"`
	SourceCapsuleDigest      string                     `json:"sourceCapsuleDigest"`
}

// DataContentCheckpointPolicy freezes partition-local restart semantics.
// Runtime checkpoint persistence can evolve behind this create-once contract;
// a request cannot silently change cursor, store, or fence ownership.
type DataContentCheckpointPolicy struct {
	Mode                  string `json:"mode"`
	Scope                 string `json:"scope"`
	Cursor                string `json:"cursor"`
	Resume                string `json:"resume"`
	Store                 string `json:"store"`
	Fencing               string `json:"fencing"`
	EveryFinalizedObjects int    `json:"everyFinalizedObjects"`
	EverySeconds          int    `json:"everySeconds"`
	TriggerMode           string `json:"triggerMode"`
}

const (
	dataContentPartitionAlgorithm = "sha256_carrier_object_ref_mod_v1"
	dataContentMinPartitionCount  = 16
	dataContentMaxPartitionCount  = 256
)

// dataContentPartitionCount implements the partition topology bands declared by
// quwoquan_data/schema/execution/data_content_fleet_request.schema.json, which
// Data implements in
// quwoquan_data/scripts/content/execution/queue/partition.py#partition_count.
// Partitions isolate queue and checkpoint state, so the frozen work-unit count
// is the only admitted input; the concurrency ceiling and any per-worker
// resource ratio are deliberately absent.
func dataContentPartitionCount(workUnitCount int) int {
	requested := workUnitCount
	if requested < dataContentMinPartitionCount {
		requested = dataContentMinPartitionCount
	}
	if requested >= dataContentMaxPartitionCount {
		return dataContentMaxPartitionCount
	}
	count := dataContentMinPartitionCount
	for count < requested {
		count *= 2
	}
	return count
}

func dataContentPartitionKey(carrier string, objectRef string, partitionCount int) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(carrier) + strings.TrimSpace(objectRef)))
	remainder := 0
	for _, value := range digest {
		remainder = (remainder*256 + int(value)) % partitionCount
	}
	return strconv.Itoa(remainder)
}

func (p DataContentCheckpointPolicy) validate() error {
	if strings.TrimSpace(p.Mode) != "partition_watermark" ||
		strings.TrimSpace(p.Scope) != "execution_stage_partition" ||
		strings.TrimSpace(p.Cursor) != "last_succeeded_job_id" ||
		strings.TrimSpace(p.Resume) != "strictly_after_cursor" ||
		strings.TrimSpace(p.Store) != "MongoStore" ||
		strings.TrimSpace(p.Fencing) != "execution_job_set_digest" ||
		p.EveryFinalizedObjects != 100 ||
		p.EverySeconds != 900 ||
		strings.TrimSpace(p.TriggerMode) != "first_reached" {
		return errors.New("fleet request checkpointPolicy is invalid")
	}
	return nil
}

// validateFrozenCapacity keeps the three capacity semantics separate and fails
// closed on any missing one. None of them may be defaulted from another, and in
// particular the retired "worker count equals work-unit count" derivation must
// not reappear: scale only raises the wave count, never the number of processes
// running at the same time. The concurrency ceiling may legitimately exceed the
// work units still left in this attempt, because it is frozen once per
// execution while a replenishment round refreezes a smaller job set.
func (r FleetRequest) validateFrozenCapacity() error {
	if r.TargetObjectCount < 1 || r.TargetObjectCount < len(r.Jobs) {
		return fmt.Errorf(
			"fleet request targetObjectCount=%d must be positive and cover its %d frozen work units",
			r.TargetObjectCount,
			len(r.Jobs),
		)
	}
	if r.FleetMaxConcurrentWorkers < 1 {
		return fmt.Errorf(
			"fleet request fleetMaxConcurrentWorkers=%d must be a positive frozen ceiling",
			r.FleetMaxConcurrentWorkers,
		)
	}
	expectedWaveCount := (r.TargetObjectCount + r.FleetMaxConcurrentWorkers - 1) /
		r.FleetMaxConcurrentWorkers
	if r.FleetWaveCount != expectedWaveCount {
		return fmt.Errorf(
			"fleet request fleetWaveCount=%d does not match the %d work units at a ceiling of %d; want %d",
			r.FleetWaveCount,
			r.TargetObjectCount,
			r.FleetMaxConcurrentWorkers,
			expectedWaveCount,
		)
	}
	if r.FleetBatchDeadlineEpochSeconds < 1 {
		return fmt.Errorf(
			"fleet request fleetBatchDeadlineEpochSeconds=%d must be a frozen absolute epoch second",
			r.FleetBatchDeadlineEpochSeconds,
		)
	}
	if !reliabletask.ValidSHA256Digest(r.CapacityPlanDigest) {
		return errors.New("fleet request capacityPlanDigest must be sha256")
	}
	if !reliabletask.ValidSHA256Digest(r.CalibrationReceiptDigest) {
		return errors.New("fleet request calibrationReceiptDigest must be sha256")
	}
	return nil
}

// FleetConfig holds the runtime configuration required to execute a frozen
// content release. Secrets remain source-owned runtime values and are never
// persisted by this application service.
type FleetConfig struct {
	MongoURI        string
	MongoDatabase   string
	RedisAddr       string
	RedisPassword   string
	Python          string
	DataScriptsRoot string
	WorkDir         string
	PublishRoot     string
	EvidenceRoot    string
	LeaseTTL        time.Duration
	PendingMinIdle  time.Duration
}

// FleetStoreConfig is the minimum composition contract for an explicit
// execution discard. It intentionally excludes process, output and worker
// settings because a discard never runs content work.
type FleetStoreConfig struct {
	MongoURI      string
	MongoDatabase string
	RedisAddr     string
	RedisPassword string
}

// ReadFleetRequest decodes and validates one immutable data-content execution.
func ReadFleetRequest(path string) (FleetRequest, error) {
	handle, err := os.Open(filepath.Clean(path))
	if err != nil {
		return FleetRequest{}, fmt.Errorf("open fleet request: %w", err)
	}
	defer handle.Close()
	decoder := json.NewDecoder(handle)
	decoder.DisallowUnknownFields()
	var request FleetRequest
	if err := decoder.Decode(&request); err != nil {
		return FleetRequest{}, fmt.Errorf("decode fleet request: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err == nil {
		return FleetRequest{}, errors.New("fleet request contains multiple JSON values")
	} else if !errors.Is(err, io.EOF) {
		return FleetRequest{}, fmt.Errorf("decode fleet request trailing data: %w", err)
	}
	if request.Schema != FleetRequestSchema {
		return FleetRequest{}, fmt.Errorf("fleet request schema=%q", request.Schema)
	}
	request.ExecutionID = strings.TrimSpace(request.ExecutionID)
	request.CampaignScale = strings.TrimSpace(request.CampaignScale)
	request.ScaleClass = strings.TrimSpace(request.ScaleClass)
	request.ExecutionEnvelopeDigest = strings.TrimSpace(request.ExecutionEnvelopeDigest)
	request.JobSetEnvelopeDigest = strings.TrimSpace(request.JobSetEnvelopeDigest)
	request.JobSetDigest = strings.TrimSpace(request.JobSetDigest)
	request.ActualTaskDigest = strings.TrimSpace(request.ActualTaskDigest)
	request.CapacityPlanDigest = strings.TrimSpace(request.CapacityPlanDigest)
	request.CalibrationReceiptDigest = strings.TrimSpace(request.CalibrationReceiptDigest)
	request.PartitionAlgorithm = strings.TrimSpace(request.PartitionAlgorithm)
	if request.ExecutionID == "" || request.RecoverDeadTasks == nil ||
		request.ObjectTimeoutMS < 1 || len(request.Jobs) == 0 {
		return FleetRequest{}, errors.New(
			"fleet request requires executionId, recoverDeadTasks, objectTimeoutMilliseconds and at least one job",
		)
	}
	if !validCampaignScale(request.CampaignScale) ||
		(request.ScaleClass != "BELOW_M100" &&
			request.ScaleClass != "M100_PLUS" &&
			request.ScaleClass != "M10000_PLUS") ||
		!reliabletask.ValidSHA256Digest(request.ExecutionEnvelopeDigest) ||
		!reliabletask.ValidSHA256Digest(request.JobSetEnvelopeDigest) ||
		!reliabletask.ValidSHA256Digest(request.JobSetDigest) ||
		!reliabletask.ValidSHA256Digest(request.ActualTaskDigest) {
		return FleetRequest{}, errors.New(
			"fleet request requires scaleClass and execution/job-set digests",
		)
	}
	if err := request.validateFrozenCapacity(); err != nil {
		return FleetRequest{}, err
	}
	expectedPartitionCount := dataContentPartitionCount(request.TargetObjectCount)
	if request.PartitionCount != expectedPartitionCount ||
		request.PartitionAlgorithm != dataContentPartitionAlgorithm {
		return FleetRequest{}, fmt.Errorf(
			"fleet request partitionCount=%d partitionAlgorithm=%q does not match the %d frozen work units; want partitionCount=%d partitionAlgorithm=%q",
			request.PartitionCount,
			request.PartitionAlgorithm,
			request.TargetObjectCount,
			expectedPartitionCount,
			dataContentPartitionAlgorithm,
		)
	}
	if err := request.CheckpointPolicy.validate(); err != nil {
		return FleetRequest{}, err
	}
	if request.GlobalRequiredQuota < 1 ||
		request.RequiredQuota < 1 ||
		request.RequiredQuota > len(request.Jobs) ||
		request.RequiredQuota > request.GlobalRequiredQuota {
		return FleetRequest{}, fmt.Errorf(
			"fleet request requiredQuota=%d globalRequiredQuota=%d must fit the %d frozen jobs",
			request.RequiredQuota,
			request.GlobalRequiredQuota,
			len(request.Jobs),
		)
	}
	if request.CampaignBinding != nil {
		if err := request.CampaignBinding.Validate(); err != nil {
			return FleetRequest{}, err
		}
	}
	assignedPartitions := map[string]struct{}(nil)
	if request.WorkerHostBinding != nil {
		binding := request.WorkerHostBinding
		if strings.TrimSpace(binding.HostSetID) == "" ||
			binding.Generation < 1 ||
			strings.TrimSpace(binding.HostScopeID) == "" ||
			binding.WorkerCount != request.FleetMaxConcurrentWorkers ||
			!reliabletask.ValidSHA256Digest(binding.FencingToken) ||
			!reliabletask.ValidSHA256Digest(binding.HostSetDigest) ||
			!reliabletask.ValidSHA256Digest(binding.Transport.MongoTransportDigest) ||
			!reliabletask.ValidSHA256Digest(binding.Transport.RedisTransportDigest) ||
			!reliabletask.ValidSHA256Digest(binding.RuntimeProfileDigest) ||
			strings.TrimSpace(binding.ExecutorBundleRef) == "" ||
			!reliabletask.ValidSHA256Digest(binding.ExecutorBundleDigest) ||
			!reliabletask.ValidSHA256Digest(binding.ExecutorBundleFileSHA256) ||
			strings.TrimSpace(binding.SourceCapsuleID) == "" ||
			!reliabletask.ValidSHA256Digest(binding.SourceCapsuleDigest) ||
			len(binding.PartitionKeys) == 0 {
			return FleetRequest{}, errors.New("fleet request workerHostBinding is invalid")
		}
		assignedPartitions = make(map[string]struct{}, len(binding.PartitionKeys))
		for _, partition := range binding.PartitionKeys {
			value, err := strconv.Atoi(strings.TrimSpace(partition))
			if err != nil || value < 0 || value >= request.PartitionCount {
				return FleetRequest{}, errors.New("fleet request assigned partition is invalid")
			}
			if _, exists := assignedPartitions[strconv.Itoa(value)]; exists {
				return FleetRequest{}, errors.New("fleet request assigned partitions are duplicated")
			}
			assignedPartitions[strconv.Itoa(value)] = struct{}{}
		}
	}
	jobIDs := make(map[string]struct{}, len(request.Jobs))
	executionJobs := request.ExecutionJobs()
	for _, job := range executionJobs {
		if strings.TrimSpace(job.ExecutionID) != request.ExecutionID {
			return FleetRequest{}, fmt.Errorf(
				"fleet job %q execution binding mismatch",
				job.JobID,
			)
		}
		expectedPartitionKey := dataContentPartitionKey(
			job.Carrier,
			job.Ref,
			request.PartitionCount,
		)
		if strings.TrimSpace(job.PartitionKey) != expectedPartitionKey {
			return FleetRequest{}, fmt.Errorf(
				"fleet job %q partitionKey does not match carrier+objectRef partition",
				job.JobID,
			)
		}
		if assignedPartitions != nil {
			if _, assigned := assignedPartitions[strings.TrimSpace(job.PartitionKey)]; !assigned {
				return FleetRequest{}, fmt.Errorf(
					"fleet job %q partition is not assigned to hostScopeId=%q",
					job.JobID,
					request.WorkerHostBinding.HostScopeID,
				)
			}
		}
		if job.Stage != "author" && job.Stage != "publish" {
			return FleetRequest{}, fmt.Errorf(
				"fleet job %q stage=%q is not executable",
				job.JobID,
				job.Stage,
			)
		}
		if _, exists := jobIDs[job.JobID]; exists {
			return FleetRequest{}, fmt.Errorf(
				"fleet request duplicate jobId=%q",
				job.JobID,
			)
		}
		jobIDs[job.JobID] = struct{}{}
		if _, err := job.ValidateIdentity(); err != nil {
			return FleetRequest{}, err
		}
	}
	if _, err := request.Stage(); err != nil {
		return FleetRequest{}, err
	}
	actualTaskDigest, err := reliabletask.DataContentTaskDigest(executionJobs)
	if err != nil {
		return FleetRequest{}, err
	}
	if actualTaskDigest != request.ActualTaskDigest {
		return FleetRequest{}, errors.New(
			"fleet request actualTaskDigest does not match its exact host task set",
		)
	}
	return request, nil
}

func validCampaignScale(value string) bool {
	if !strings.HasPrefix(value, "M") || len(value) < 2 {
		return false
	}
	count, err := strconv.Atoi(value[1:])
	return err == nil && count >= 1 && count <= 100000 && strconv.Itoa(count) == value[1:]
}

// ObjectTimeout returns the frozen maximum runtime of one content object.
func (r FleetRequest) ObjectTimeout() time.Duration {
	return time.Duration(r.ObjectTimeoutMS) * time.Millisecond
}

// Stage returns the single stage represented by this immutable fleet request.
// A worker invocation never mixes author and publish tasks because their
// evidence and duplicate-detection scopes are intentionally independent.
func (r FleetRequest) Stage() (string, error) {
	if len(r.Jobs) == 0 {
		return "", errors.New("fleet request has no jobs")
	}
	stage := strings.TrimSpace(r.Jobs[0].Stage)
	if stage == "" {
		return "", errors.New("fleet request job stage is required")
	}
	for _, job := range r.Jobs[1:] {
		if strings.TrimSpace(job.Stage) != stage {
			return "", errors.New("fleet request must contain exactly one stage")
		}
	}
	return stage, nil
}

// DataContentOutboxFilter scopes duplicate detection to the frozen execution
// and its single work stage. The worker command only passes this application
// contract to Mongo infrastructure.
func DataContentOutboxFilter(request FleetRequest) (map[string]string, error) {
	stage, err := request.Stage()
	if err != nil {
		return nil, err
	}
	return map[string]string{
		dataContentOutboxTaskTypeField:    reliabletask.DataContentTaskType,
		dataContentOutboxExecutionIDField: request.ExecutionID,
		dataContentOutboxStageField:       stage,
	}, nil
}

// LoadFleetConfig reads the minimum composition inputs for the Post importer.
func LoadFleetConfig(
	provider runtimeconfig.RuntimeConfigProvider,
) (FleetConfig, error) {
	required := func(key string) (string, error) {
		value, ok := provider.GetString(key)
		if !ok {
			return "", fmt.Errorf("runtime config %s is required", key)
		}
		return value, nil
	}
	mongoURI, err := required("QWQ_DATA_FLEET_MONGO_URI")
	if err != nil {
		return FleetConfig{}, err
	}
	redisAddr, err := required("QWQ_DATA_FLEET_REDIS_ADDR")
	if err != nil {
		return FleetConfig{}, err
	}
	python, err := required("QWQ_DATA_FLEET_PYTHON")
	if err != nil {
		return FleetConfig{}, err
	}
	dataScriptsRoot, err := required("QWQ_DATA_FLEET_SCRIPTS_ROOT")
	if err != nil {
		return FleetConfig{}, err
	}
	workDir, err := required("QWQ_DATA_FLEET_WORK_DIR")
	if err != nil {
		return FleetConfig{}, err
	}
	publishRoot, err := required("QWQ_DATA_FLEET_PUBLISH_ROOT")
	if err != nil {
		return FleetConfig{}, err
	}
	evidenceRoot, err := required("QWQ_DATA_FLEET_EVIDENCE_ROOT")
	if err != nil {
		return FleetConfig{}, err
	}
	cfg := FleetConfig{
		MongoURI:        mongoURI,
		MongoDatabase:   "quwoquan_reliabletask_data",
		RedisAddr:       redisAddr,
		Python:          python,
		DataScriptsRoot: dataScriptsRoot,
		WorkDir:         workDir,
		PublishRoot:     publishRoot,
		EvidenceRoot:    evidenceRoot,
		LeaseTTL:        30 * time.Minute,
		PendingMinIdle:  time.Second,
	}
	if value, ok := provider.GetString("QWQ_DATA_FLEET_MONGO_DATABASE"); ok {
		cfg.MongoDatabase = value
	}
	if value, ok := provider.GetString("QWQ_DATA_FLEET_REDIS_PASSWORD"); ok {
		cfg.RedisPassword = value
	}
	if value, ok := provider.GetDurationMs("QWQ_DATA_FLEET_LEASE_TTL_MS"); ok {
		cfg.LeaseTTL = value
	}
	if value, ok := provider.GetDurationMs(
		"QWQ_DATA_FLEET_PENDING_MIN_IDLE_MS",
	); ok {
		cfg.PendingMinIdle = value
	}
	return cfg, nil
}

// LoadFleetStoreConfig reads only the transport required for an exact remote
// task cleanup. It shares the same runtime configuration boundary as workers.
func LoadFleetStoreConfig(
	provider runtimeconfig.RuntimeConfigProvider,
) (FleetStoreConfig, error) {
	required := func(key string) (string, error) {
		value, ok := provider.GetString(key)
		if !ok {
			return "", fmt.Errorf("runtime config %s is required", key)
		}
		return value, nil
	}
	mongoURI, err := required("QWQ_DATA_FLEET_MONGO_URI")
	if err != nil {
		return FleetStoreConfig{}, err
	}
	redisAddr, err := required("QWQ_DATA_FLEET_REDIS_ADDR")
	if err != nil {
		return FleetStoreConfig{}, err
	}
	cfg := FleetStoreConfig{
		MongoURI:      mongoURI,
		MongoDatabase: "quwoquan_reliabletask_data",
		RedisAddr:     redisAddr,
	}
	if value, ok := provider.GetString("QWQ_DATA_FLEET_MONGO_DATABASE"); ok {
		cfg.MongoDatabase = value
	}
	if value, ok := provider.GetString("QWQ_DATA_FLEET_REDIS_PASSWORD"); ok {
		cfg.RedisPassword = value
	}
	return cfg, nil
}

// DataWorkerEnvironment builds the process environment for the Python object
// worker. WorkDir is quwoquan_data, so PYTHONPATH must include both the data
// scripts root and the repository root (for quwoquan_ops and related packages).
func DataWorkerEnvironment(
	current []string,
	evidenceRoot string,
	publishRoot string,
	scriptsRoot string,
) []string {
	repoRoot := filepath.Clean(filepath.Join(scriptsRoot, "..", ".."))
	pythonPath := scriptsRoot
	if repoRoot != "" && repoRoot != "." && repoRoot != scriptsRoot {
		pythonPath = scriptsRoot + string(os.PathListSeparator) + repoRoot
	}
	overrides := map[string]string{
		"PYTHONDONTWRITEBYTECODE": "1",
		"QWQ_OUTPUT_ROOT":         evidenceRoot,
		"QWQ_PUBLISH_ROOT":        publishRoot,
		"PYTHONPATH":              pythonPath,
	}
	result := make([]string, 0, len(current)+len(overrides))
	for _, row := range current {
		key, _, found := strings.Cut(row, "=")
		if _, overridden := overrides[key]; found && overridden {
			continue
		}
		result = append(result, row)
	}
	for key, value := range overrides {
		result = append(result, key+"="+value)
	}
	return result
}

// SelectExecutionTasks returns only the exact frozen task identities named by
// request. jobId is stable across repair revisions, so it must not be used as
// the remote selection key.
func SelectExecutionTasks(
	executionTasks []reliabletask.ReliableAsyncTask,
	request FleetRequest,
) ([]reliabletask.ReliableAsyncTask, error) {
	byIdempotencyKey := make(
		map[string][]reliabletask.ReliableAsyncTask,
		len(executionTasks),
	)
	for _, task := range executionTasks {
		idempotencyKey := strings.TrimSpace(task.IdempotencyKey)
		if idempotencyKey != "" {
			byIdempotencyKey[idempotencyKey] = append(
				byIdempotencyKey[idempotencyKey],
				task,
			)
		}
	}
	selected := make([]reliabletask.ReliableAsyncTask, 0, len(request.Jobs))
	for _, job := range request.ExecutionJobs() {
		jobID := strings.TrimSpace(job.JobID)
		expectedKey, err := job.ValidateIdentity()
		if err != nil {
			return nil, err
		}
		matches := byIdempotencyKey[expectedKey]
		if len(matches) > 1 {
			return nil, fmt.Errorf(
				"data content request idempotency key for job %q has %d remote tasks; refusing ambiguous result projection",
				jobID,
				len(matches),
			)
		}
		if len(matches) == 0 {
			continue
		}
		task := matches[0]
		if task.IdempotencyKey != expectedKey ||
			task.DedupeKey != expectedKey ||
			task.PartitionKey != job.PartitionKey ||
			task.Payload["jobSetEnvelopeDigest"] != job.JobSetEnvelopeDigest ||
			task.Payload["jobSetDigest"] != job.JobSetDigest ||
			task.Payload["actualTaskDigest"] != job.ActualTaskDigest ||
			task.Payload["idempotencyKey"] != expectedKey ||
			task.Payload["executionId"] != request.ExecutionID ||
			task.Payload["jobId"] != jobID {
			return nil, fmt.Errorf(
				"data content request job %q remote identity does not match the frozen request",
				jobID,
			)
		}
		selected = append(selected, task)
	}
	return selected, nil
}

// SelectFenceTargets resolves stable logical jobs before a newer generation
// atomically replaces only their mutable worker-fence payload fields.
func SelectFenceTargets(
	executionTasks []reliabletask.ReliableAsyncTask,
	request FleetRequest,
) ([]reliabletask.ReliableAsyncTask, error) {
	wanted := make(map[string]reliabletask.DataContentJob, len(request.Jobs))
	for _, job := range request.ExecutionJobs() {
		key, err := job.ValidateIdentity()
		if err != nil {
			return nil, err
		}
		wanted[key] = job
	}
	selected := make([]reliabletask.ReliableAsyncTask, 0, len(wanted))
	for _, task := range executionTasks {
		job, ok := wanted[strings.TrimSpace(task.IdempotencyKey)]
		if !ok {
			continue
		}
		if task.DedupeKey != task.IdempotencyKey ||
			task.Payload["executionId"] != request.ExecutionID ||
			task.Payload["jobId"] != job.JobID ||
			task.PartitionKey != job.PartitionKey {
			return nil, fmt.Errorf("data content fence target %q stable identity drift", job.JobID)
		}
		selected = append(selected, task)
	}
	return selected, nil
}

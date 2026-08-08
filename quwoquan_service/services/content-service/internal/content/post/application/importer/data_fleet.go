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
type FleetRequest struct {
	Schema                  string                                   `json:"schema"`
	ExecutionID             string                                   `json:"executionId"`
	CampaignScale           string                                   `json:"campaignScale"`
	ScaleClass              string                                   `json:"scaleClass"`
	ExecutionEnvelopeDigest string                                   `json:"executionEnvelopeDigest"`
	JobSetEnvelopeDigest    string                                   `json:"jobSetEnvelopeDigest"`
	JobSetDigest            string                                   `json:"jobSetDigest"`
	ActualTaskDigest        string                                   `json:"actualTaskDigest"`
	RequiredWorkers         int                                      `json:"requiredWorkers"`
	PartitionCount          int                                      `json:"partitionCount"`
	PartitionAlgorithm      string                                   `json:"partitionAlgorithm"`
	CheckpointPolicy        DataContentCheckpointPolicy              `json:"checkpointPolicy"`
	RequireCommercial       bool                                     `json:"requireCommercial"`
	RecoverDeadTasks        *bool                                    `json:"recoverDeadTasks"`
	ObjectTimeoutMS         int                                      `json:"objectTimeoutMilliseconds"`
	RequiredQuota           int                                      `json:"requiredQuota"`
	CampaignBinding         *reliabletask.DataContentCampaignBinding `json:"campaignBinding,omitempty"`
	Jobs                    []reliabletask.DataContentJob            `json:"jobs"`
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

const dataContentPartitionAlgorithm = "sha256_carrier_object_ref_mod_v1"

func dataContentPartitionCount(requiredWorkers int) int {
	if requiredWorkers >= 64 {
		return 256
	}
	requested := 4 * requiredWorkers
	if requested < 16 {
		requested = 16
	}
	count := 16
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
	Workers         int
	BatchTimeout    time.Duration
	LeaseTTL        time.Duration
	PendingMinIdle  time.Duration
	MaxAttempts     int
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
	if request.RequiredWorkers < 1 ||
		request.PartitionCount != dataContentPartitionCount(request.RequiredWorkers) ||
		request.PartitionAlgorithm != dataContentPartitionAlgorithm {
		return FleetRequest{}, errors.New(
			"fleet request partition contract does not match requiredWorkers",
		)
	}
	if err := request.CheckpointPolicy.validate(); err != nil {
		return FleetRequest{}, err
	}
	if (request.ScaleClass == "M100_PLUS" || request.ScaleClass == "M10000_PLUS") &&
		request.CampaignBinding == nil {
		return FleetRequest{}, errors.New(
			request.ScaleClass + " fleet request requires campaign binding",
		)
	}
	if request.RequiredQuota < 1 || request.RequiredQuota > len(request.Jobs) {
		return FleetRequest{}, fmt.Errorf(
			"fleet request requiredQuota=%d must be between 1 and the %d frozen jobs",
			request.RequiredQuota,
			len(request.Jobs),
		)
	}
	if request.CampaignBinding != nil {
		if err := request.CampaignBinding.Validate(); err != nil {
			return FleetRequest{}, err
		}
	}
	jobIDs := make(map[string]struct{}, len(request.Jobs))
	for index := range request.Jobs {
		job := &request.Jobs[index]
		if !job.Campaign.IsEmpty() {
			return FleetRequest{}, fmt.Errorf(
				"fleet job %q cannot override campaign binding",
				job.JobID,
			)
		}
		if strings.TrimSpace(job.ExecutionEnvelopeDigest) != "" {
			return FleetRequest{}, fmt.Errorf(
				"fleet job %q cannot override execution envelope digest",
				job.JobID,
			)
		}
		if strings.TrimSpace(job.JobSetEnvelopeDigest) != "" ||
			strings.TrimSpace(job.JobSetDigest) != "" ||
			strings.TrimSpace(job.ActualTaskDigest) != "" {
			return FleetRequest{}, fmt.Errorf(
				"fleet job %q cannot override frozen job-set digests",
				job.JobID,
			)
		}
		job.ExecutionEnvelopeDigest = request.ExecutionEnvelopeDigest
		job.JobSetEnvelopeDigest = request.JobSetEnvelopeDigest
		job.JobSetDigest = request.JobSetDigest
		job.ActualTaskDigest = request.ActualTaskDigest
		if request.CampaignBinding != nil {
			job.Campaign = *request.CampaignBinding
		}
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
	actualTaskDigest, err := reliabletask.DataContentTaskDigest(request.Jobs)
	if err != nil {
		return FleetRequest{}, err
	}
	if actualTaskDigest != request.ActualTaskDigest ||
		request.ActualTaskDigest != request.JobSetDigest {
		return FleetRequest{}, errors.New(
			"fleet request actualTaskDigest does not match its exact job set",
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
		Workers:         1,
		LeaseTTL:        30 * time.Minute,
		PendingMinIdle:  time.Second,
		MaxAttempts:     3,
	}
	if value, ok := provider.GetString("QWQ_DATA_FLEET_MONGO_DATABASE"); ok {
		cfg.MongoDatabase = value
	}
	if value, ok := provider.GetString("QWQ_DATA_FLEET_REDIS_PASSWORD"); ok {
		cfg.RedisPassword = value
	}
	if value, ok := provider.GetInt("QWQ_DATA_FLEET_WORKERS"); ok {
		cfg.Workers = value
	}
	batchTimeout, ok := provider.GetDurationMs("QWQ_DATA_FLEET_BATCH_TIMEOUT_MS")
	if !ok || batchTimeout <= 0 {
		return FleetConfig{}, errors.New(
			"runtime config QWQ_DATA_FLEET_BATCH_TIMEOUT_MS is required and must be positive",
		)
	}
	cfg.BatchTimeout = batchTimeout
	if value, ok := provider.GetDurationMs("QWQ_DATA_FLEET_LEASE_TTL_MS"); ok {
		cfg.LeaseTTL = value
	}
	if value, ok := provider.GetDurationMs(
		"QWQ_DATA_FLEET_PENDING_MIN_IDLE_MS",
	); ok {
		cfg.PendingMinIdle = value
	}
	if value, ok := provider.GetInt("QWQ_DATA_FLEET_MAX_ATTEMPTS"); ok {
		cfg.MaxAttempts = value
	}
	if cfg.Workers < 1 || cfg.Workers > 4096 {
		return FleetConfig{}, errors.New(
			"QWQ_DATA_FLEET_WORKERS must be between 1 and 4096",
		)
	}
	if cfg.MaxAttempts < 1 {
		return FleetConfig{}, errors.New(
			"QWQ_DATA_FLEET_MAX_ATTEMPTS must be positive",
		)
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
	for _, job := range request.Jobs {
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

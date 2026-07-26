package importer

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
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
	Schema            string                        `json:"schema"`
	ExecutionID       string                        `json:"executionId"`
	RequireCommercial bool                          `json:"requireCommercial"`
	RecoverDeadTasks  *bool                         `json:"recoverDeadTasks"`
	ObjectTimeoutMS   int                           `json:"objectTimeoutMilliseconds"`
	Jobs              []reliabletask.DataContentJob `json:"jobs"`
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
	if request.ExecutionID == "" || request.RecoverDeadTasks == nil ||
		request.ObjectTimeoutMS < 1 || len(request.Jobs) == 0 {
		return FleetRequest{}, errors.New(
			"fleet request requires executionId, recoverDeadTasks, objectTimeoutMilliseconds and at least one job",
		)
	}
	jobIDs := make(map[string]struct{}, len(request.Jobs))
	for index := range request.Jobs {
		job := &request.Jobs[index]
		if strings.TrimSpace(job.ExecutionID) != request.ExecutionID {
			return FleetRequest{}, fmt.Errorf(
				"fleet job %q execution binding mismatch",
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
	return request, nil
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

// SelectExecutionTasks returns only the frozen jobs named by request. It
// rejects non-unique or mismatched remote tasks instead of guessing a result.
func SelectExecutionTasks(
	executionTasks []reliabletask.ReliableAsyncTask,
	request FleetRequest,
) ([]reliabletask.ReliableAsyncTask, error) {
	byJobID := make(map[string][]reliabletask.ReliableAsyncTask, len(executionTasks))
	for _, task := range executionTasks {
		jobID := strings.TrimSpace(task.Payload["jobId"])
		if jobID != "" {
			byJobID[jobID] = append(byJobID[jobID], task)
		}
	}
	selected := make([]reliabletask.ReliableAsyncTask, 0, len(request.Jobs))
	for _, job := range request.Jobs {
		jobID := strings.TrimSpace(job.JobID)
		matches := byJobID[jobID]
		if len(matches) > 1 {
			return nil, fmt.Errorf(
				"data content request job %q has %d remote tasks; refusing ambiguous result projection",
				jobID,
				len(matches),
			)
		}
		if len(matches) == 0 {
			continue
		}
		task := matches[0]
		expectedKey, err := job.ValidateIdentity()
		if err != nil {
			return nil, err
		}
		if task.IdempotencyKey != expectedKey ||
			task.DedupeKey != expectedKey ||
			task.PartitionKey != job.PartitionKey ||
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

// Command data-content-worker 将冻结的 Data 对象任务提交到 Mongo+Redis
// ReliableTask，并通过受控 Python worker 完成 author/publish 对象工作。
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"syscall"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	runtimeconfig "quwoquan_service/runtime/config"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
)

const fleetRequestSchema = "quwoquan.data_content_fleet_request"

// pythonWorkerModule is an internal adapter, not a public qwq-data command.
// The worker process imports its callable explicitly so the Python module has
// no second executable entrypoint alongside scripts/cli.py.
const pythonWorkerModule = "from content.execution.reliabletask_worker import run_process_worker; run_process_worker()"

type fleetRequest struct {
	Schema            string                        `json:"schema"`
	ExecutionID       string                        `json:"executionId"`
	RequireCommercial bool                          `json:"requireCommercial"`
	RecoverDeadTasks  *bool                         `json:"recoverDeadTasks"`
	Jobs              []reliabletask.DataContentJob `json:"jobs"`
}

type workerConfig struct {
	mongoURI        string
	mongoDatabase   string
	redisAddr       string
	redisPassword   string
	python          string
	dataScriptsRoot string
	workDir         string
	publishRoot     string
	evidenceRoot    string
	workers         int
	timeout         time.Duration
	leaseTTL        time.Duration
	pendingMinIdle  time.Duration
	maxAttempts     int
}

func main() {
	if err := run(); err != nil {
		log.Printf("data-content-worker failed: %v", err)
		os.Exit(1)
	}
}

func run() error {
	requestPath := flag.String(
		"request",
		"",
		"冻结的 quwoquan.data_content_fleet_request JSON（必填）",
	)
	reportPath := flag.String(
		"report",
		"",
		"reliabletask fleet report 输出路径（必填）",
	)
	flag.Parse()
	if strings.TrimSpace(*requestPath) == "" || strings.TrimSpace(*reportPath) == "" {
		return errors.New("--request and --report are required")
	}
	request, err := readFleetRequest(*requestPath)
	if err != nil {
		return err
	}
	cfg, err := loadWorkerConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return err
	}
	parent, stop := signal.NotifyContext(
		context.Background(),
		syscall.SIGINT,
		syscall.SIGTERM,
	)
	defer stop()
	ctx, cancel := context.WithTimeout(parent, cfg.timeout)
	defer cancel()

	client, err := mongo.Connect(options.Client().ApplyURI(cfg.mongoURI))
	if err != nil {
		return fmt.Errorf("connect reliabletask Mongo: %w", err)
	}
	defer client.Disconnect(context.Background())
	database := client.Database(cfg.mongoDatabase)
	store := reliabletaskmongo.New(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ensure reliabletask indexes: %w", err)
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"reliabletask": {
				Mode:     "standalone",
				Addr:     cfg.redisAddr,
				Password: cfg.redisPassword,
			},
		},
		DefaultScene: "reliabletask",
	})
	defer router.Close()
	executionHash := sha256.Sum256([]byte(request.ExecutionID))
	streamSuffix := hex.EncodeToString(executionHash[:6])
	ready, err := reliabletask.NewRedisReadyIndex(
		reliabletask.RedisReadyIndexConfig{
			Client: router.Scene("reliabletask"),
			Stream: "reliabletask:data:content:" + streamSuffix,
			Group:  "data.content_supply." + streamSuffix,
			Queue:  reliabletask.DataContentQueue,
		},
	)
	if err != nil {
		return fmt.Errorf("create reliabletask Redis ready index: %w", err)
	}
	if err := ready.Ensure(ctx); err != nil {
		return fmt.Errorf("ensure reliabletask Redis ready index: %w", err)
	}
	fleet := reliabletask.DataContentFleet{
		Store:          store,
		Ready:          ready,
		WorkerID:       "data-content-worker",
		LeaseTTL:       cfg.leaseTTL,
		PendingMinIdle: cfg.pendingMinIdle,
		Retry: reliabletask.RetryPolicy{
			MaxAttempts: cfg.maxAttempts,
		},
		ResultVerifier: reliabletask.DataContentFilesystemEvidenceVerifier{
			PublishRoot:  cfg.publishRoot,
			EvidenceRoot: cfg.evidenceRoot,
		},
	}
	startedAt := time.Now().UTC()
	for _, job := range request.Jobs {
		if _, err := fleet.Declare(ctx, job); err != nil {
			return fmt.Errorf("declare data content job %s: %w", job.JobID, err)
		}
	}
	if *request.RecoverDeadTasks {
		if _, err := fleet.RecoverAuditedDeadJobs(ctx, request.Jobs); err != nil {
			return fmt.Errorf("recover audited dead data content jobs: %w", err)
		}
		if _, err := fleet.ReconcileReadyIndex(ctx, len(request.Jobs)); err != nil {
			return fmt.Errorf("rebuild ready index after data content recovery: %w", err)
		}
	}
	if _, err := fleet.Dispatch(ctx, len(request.Jobs)); err != nil {
		return fmt.Errorf("dispatch data content jobs: %w", err)
	}
	executor := reliabletask.DataContentProcessExecutor{
		Command: []string{
			cfg.python,
			"-c",
			pythonWorkerModule,
		},
		WorkDir: cfg.workDir,
		Environment: dataWorkerEnvironment(
			os.Environ(),
			cfg.evidenceRoot,
			cfg.publishRoot,
			cfg.dataScriptsRoot,
		),
	}
	tasks, runErr := runWorkers(
		ctx,
		database,
		request,
		fleet,
		executor,
		cfg.workers,
	)
	completedAt := time.Now().UTC()
	outboxCount, countErr := database.Collection("reliable_task_outbox").
		CountDocuments(
			context.Background(),
			bson.M{
				"taskType":            reliabletask.DataContentTaskType,
				"payload.executionId": request.ExecutionID,
			},
		)
	if countErr != nil {
		return fmt.Errorf("count data content outboxes: %w", countErr)
	}
	report := reliabletask.BuildDataContentFleetReport(
		tasks,
		startedAt,
		completedAt,
		max(0, int(outboxCount)-len(request.Jobs)),
		max(0, len(request.Jobs)-len(tasks)),
	)
	if err := writeJSONAtomically(*reportPath, report); err != nil {
		return err
	}
	if runErr != nil {
		return runErr
	}
	for _, task := range tasks {
		if task.Status != reliabletask.TaskStatusSucceeded {
			return fmt.Errorf(
				"data content task %s ended as %s: %#v",
				task.Payload["jobId"],
				task.Status,
				task.LastFailure,
			)
		}
	}
	if request.RequireCommercial && !report.Passed {
		return fmt.Errorf(
			"commercial ReliableTask gate blocked: accepted=%d/%d status=%s",
			report.CommercialAcceptedCount,
			report.PublishTaskCount,
			report.AcceptedContentThroughputStatus,
		)
	}
	return nil
}

func readFleetRequest(path string) (fleetRequest, error) {
	handle, err := os.Open(filepath.Clean(path))
	if err != nil {
		return fleetRequest{}, fmt.Errorf("open fleet request: %w", err)
	}
	defer handle.Close()
	decoder := json.NewDecoder(handle)
	decoder.DisallowUnknownFields()
	var request fleetRequest
	if err := decoder.Decode(&request); err != nil {
		return fleetRequest{}, fmt.Errorf("decode fleet request: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err == nil {
		return fleetRequest{}, errors.New("fleet request contains multiple JSON values")
	} else if !errors.Is(err, io.EOF) {
		return fleetRequest{}, fmt.Errorf("decode fleet request trailing data: %w", err)
	}
	if request.Schema != fleetRequestSchema {
		return fleetRequest{}, fmt.Errorf("fleet request schema=%q", request.Schema)
	}
	request.ExecutionID = strings.TrimSpace(request.ExecutionID)
	if request.ExecutionID == "" || request.RecoverDeadTasks == nil || len(request.Jobs) == 0 {
		return fleetRequest{}, errors.New(
			"fleet request requires executionId, recoverDeadTasks and at least one job",
		)
	}
	jobIDs := make(map[string]struct{}, len(request.Jobs))
	for index := range request.Jobs {
		job := &request.Jobs[index]
		if strings.TrimSpace(job.ExecutionID) != request.ExecutionID {
			return fleetRequest{}, fmt.Errorf(
				"fleet job %q execution binding mismatch",
				job.JobID,
			)
		}
		if job.Stage != "author" && job.Stage != "publish" {
			return fleetRequest{}, fmt.Errorf(
				"fleet job %q stage=%q is not executable",
				job.JobID,
				job.Stage,
			)
		}
		if _, exists := jobIDs[job.JobID]; exists {
			return fleetRequest{}, fmt.Errorf(
				"fleet request duplicate jobId=%q",
				job.JobID,
			)
		}
		jobIDs[job.JobID] = struct{}{}
		if _, err := job.ValidateIdentity(); err != nil {
			return fleetRequest{}, err
		}
	}
	return request, nil
}

func loadWorkerConfig(
	provider runtimeconfig.RuntimeConfigProvider,
) (workerConfig, error) {
	required := func(key string) (string, error) {
		value, ok := provider.GetString(key)
		if !ok {
			return "", fmt.Errorf("runtime config %s is required", key)
		}
		return value, nil
	}
	mongoURI, err := required("QWQ_DATA_FLEET_MONGO_URI")
	if err != nil {
		return workerConfig{}, err
	}
	redisAddr, err := required("QWQ_DATA_FLEET_REDIS_ADDR")
	if err != nil {
		return workerConfig{}, err
	}
	python, err := required("QWQ_DATA_FLEET_PYTHON")
	if err != nil {
		return workerConfig{}, err
	}
	dataScriptsRoot, err := required("QWQ_DATA_FLEET_SCRIPTS_ROOT")
	if err != nil {
		return workerConfig{}, err
	}
	workDir, err := required("QWQ_DATA_FLEET_WORK_DIR")
	if err != nil {
		return workerConfig{}, err
	}
	publishRoot, err := required("QWQ_DATA_FLEET_PUBLISH_ROOT")
	if err != nil {
		return workerConfig{}, err
	}
	evidenceRoot, err := required("QWQ_DATA_FLEET_EVIDENCE_ROOT")
	if err != nil {
		return workerConfig{}, err
	}
	cfg := workerConfig{
		mongoURI:        mongoURI,
		mongoDatabase:   "quwoquan_reliabletask_data",
		redisAddr:       redisAddr,
		python:          python,
		dataScriptsRoot: dataScriptsRoot,
		workDir:         workDir,
		publishRoot:     publishRoot,
		evidenceRoot:    evidenceRoot,
		workers:         1,
		timeout:         24 * time.Hour,
		leaseTTL:        30 * time.Minute,
		pendingMinIdle:  time.Second,
		maxAttempts:     3,
	}
	if value, ok := provider.GetString("QWQ_DATA_FLEET_MONGO_DATABASE"); ok {
		cfg.mongoDatabase = value
	}
	if value, ok := provider.GetString("QWQ_DATA_FLEET_REDIS_PASSWORD"); ok {
		cfg.redisPassword = value
	}
	if value, ok := provider.GetInt("QWQ_DATA_FLEET_WORKERS"); ok {
		cfg.workers = value
	}
	if value, ok := provider.GetDurationMs("QWQ_DATA_FLEET_TIMEOUT_MS"); ok {
		cfg.timeout = value
	}
	if value, ok := provider.GetDurationMs("QWQ_DATA_FLEET_LEASE_TTL_MS"); ok {
		cfg.leaseTTL = value
	}
	if value, ok := provider.GetDurationMs(
		"QWQ_DATA_FLEET_PENDING_MIN_IDLE_MS",
	); ok {
		cfg.pendingMinIdle = value
	}
	if value, ok := provider.GetInt("QWQ_DATA_FLEET_MAX_ATTEMPTS"); ok {
		cfg.maxAttempts = value
	}
	if cfg.workers < 1 || cfg.workers > 4096 {
		return workerConfig{}, errors.New(
			"QWQ_DATA_FLEET_WORKERS must be between 1 and 4096",
		)
	}
	if cfg.maxAttempts < 1 {
		return workerConfig{}, errors.New(
			"QWQ_DATA_FLEET_MAX_ATTEMPTS must be positive",
		)
	}
	return cfg, nil
}

func runWorkers(
	ctx context.Context,
	database *mongo.Database,
	request fleetRequest,
	fleet reliabletask.DataContentFleet,
	executor reliabletask.DataContentExecutor,
	workers int,
) ([]reliabletask.ReliableAsyncTask, error) {
	workerCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	errorsCh := make(chan error, workers)
	var group sync.WaitGroup
	for index := 0; index < workers; index++ {
		group.Add(1)
		go func(workerIndex int) {
			defer group.Done()
			localFleet := fleet
			localFleet.WorkerID = fmt.Sprintf(
				"data-content-worker-%04d",
				workerIndex,
			)
			for workerCtx.Err() == nil {
				processed, err := localFleet.ProcessOneContent(
					workerCtx,
					executor,
				)
				if err != nil {
					select {
					case errorsCh <- err:
					default:
					}
					return
				}
				if !processed {
					time.Sleep(25 * time.Millisecond)
				}
			}
		}(index)
	}
	defer func() {
		cancel()
		group.Wait()
	}()
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for {
		executionTasks, err := loadExecutionTasks(
			ctx,
			database,
			request.ExecutionID,
		)
		if err != nil {
			return nil, err
		}
		tasks, err := requestedExecutionTasks(executionTasks, request)
		if err != nil {
			return nil, err
		}
		terminal := 0
		for _, task := range tasks {
			if task.Status == reliabletask.TaskStatusSucceeded ||
				task.Status == reliabletask.TaskStatusDead {
				terminal++
			}
		}
		if len(tasks) == len(request.Jobs) && terminal == len(tasks) {
			return tasks, nil
		}
		select {
		case err := <-errorsCh:
			return tasks, fmt.Errorf("data content worker: %w", err)
		case <-ctx.Done():
			return tasks, ctx.Err()
		case <-ticker.C:
			if _, err := fleet.Dispatch(ctx, len(request.Jobs)); err != nil {
				return tasks, err
			}
			if _, err := fleet.ReconcileReadyIndex(
				ctx,
				len(request.Jobs),
			); err != nil {
				return tasks, err
			}
		}
	}
}

func loadExecutionTasks(
	ctx context.Context,
	database *mongo.Database,
	executionID string,
) ([]reliabletask.ReliableAsyncTask, error) {
	cursor, err := database.Collection("reliable_async_task").Find(
		ctx,
		bson.M{
			"taskType":            reliabletask.DataContentTaskType,
			"payload.executionId": executionID,
		},
	)
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

// requestedExecutionTasks 只观察本次 fleet request 明确声明的任务。
// 同一 execution 允许 author 与 publish 分阶段独立运行；不能因已完成的
// author 任务被一并读出而让 publish worker 永久等待。
func requestedExecutionTasks(
	executionTasks []reliabletask.ReliableAsyncTask,
	request fleetRequest,
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

func dataWorkerEnvironment(
	current []string,
	evidenceRoot string,
	publishRoot string,
	scriptsRoot string,
) []string {
	overrides := map[string]string{
		"PYTHONDONTWRITEBYTECODE": "1",
		"QWQ_OUTPUT_ROOT":         evidenceRoot,
		"QWQ_PUBLISH_ROOT":        publishRoot,
		"PYTHONPATH":              scriptsRoot,
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

func writeJSONAtomically(path string, value any) error {
	target := filepath.Clean(path)
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		return err
	}
	payload, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	temporary, err := os.CreateTemp(filepath.Dir(target), ".fleet-report-*.json")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if _, err := temporary.Write(append(payload, '\n')); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	return os.Rename(temporaryPath, target)
}

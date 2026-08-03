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
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	runtimeconfig "quwoquan_service/runtime/config"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/content-service/internal/content/post/application/importer"
)

// pythonWorkerModule is an internal adapter, not a public qwq-data command.
// The worker process imports its callable explicitly so the Python module has
// no second executable entrypoint alongside scripts/cli.py.
const pythonWorkerModule = "from content.execution.reliabletask_worker import run_process_worker; run_process_worker()"

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
	discardExecutionID := flag.String(
		"discard-execution",
		"",
		"删除一个已停止 Data execution 的远端 ReliableTask 状态",
	)
	confirmDiscard := flag.Bool(
		"confirm-discard",
		false,
		"确认删除 --discard-execution 指定的远端状态",
	)
	flag.Parse()
	if strings.TrimSpace(*discardExecutionID) != "" {
		if strings.TrimSpace(*requestPath) != "" || strings.TrimSpace(*reportPath) != "" {
			return errors.New("--discard-execution cannot be combined with --request or --report")
		}
		if !*confirmDiscard {
			return errors.New("--discard-execution requires --confirm-discard")
		}
		return discardExecution(strings.TrimSpace(*discardExecutionID))
	}
	if strings.TrimSpace(*requestPath) == "" || strings.TrimSpace(*reportPath) == "" {
		return errors.New("--request and --report are required")
	}
	request, err := importer.ReadFleetRequest(*requestPath)
	if err != nil {
		return err
	}
	cfg, err := importer.LoadFleetConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return err
	}
	parent, stop := signal.NotifyContext(
		context.Background(),
		syscall.SIGINT,
		syscall.SIGTERM,
	)
	defer stop()
	ctx, cancel := context.WithTimeout(parent, cfg.BatchTimeout)
	defer cancel()

	client, err := mongo.Connect(options.Client().ApplyURI(cfg.MongoURI))
	if err != nil {
		return fmt.Errorf("connect reliabletask Mongo: %w", err)
	}
	defer client.Disconnect(context.Background())
	database := client.Database(cfg.MongoDatabase)
	store := reliabletaskmongo.NewDataContentImport(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ensure reliabletask indexes: %w", err)
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"reliabletask": {
				Mode:     "standalone",
				Addr:     cfg.RedisAddr,
				Password: cfg.RedisPassword,
			},
		},
		DefaultScene: "reliabletask",
	})
	defer router.Close()
	executionHash := sha256.Sum256([]byte(request.ExecutionID))
	streamSuffix := hex.EncodeToString(executionHash[:])
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
		ExecutionID:    request.ExecutionID,
		Ready:          ready,
		WorkerID:       "data-content-worker",
		LeaseTTL:       cfg.LeaseTTL,
		PendingMinIdle: cfg.PendingMinIdle,
		Retry: reliabletask.RetryPolicy{
			MaxAttempts: cfg.MaxAttempts,
		},
		ResultVerifier: reliabletask.DataContentFilesystemEvidenceVerifier{
			PublishRoot:  cfg.PublishRoot,
			EvidenceRoot: cfg.EvidenceRoot,
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
			cfg.Python,
			"-c",
			pythonWorkerModule,
		},
		WorkDir: cfg.WorkDir,
		Environment: importer.DataWorkerEnvironment(
			os.Environ(),
			cfg.EvidenceRoot,
			cfg.PublishRoot,
			cfg.DataScriptsRoot,
		),
	}
	tasks, runErr := runWorkers(
		ctx,
		request,
		fleet,
		executor,
		cfg.Workers,
		request.ObjectTimeout(),
	)
	completedAt := time.Now().UTC()
	stage, stageErr := request.Stage()
	if stageErr != nil {
		return stageErr
	}
	outboxCount, countErr := store.CountDataContentOutboxes(
		context.Background(),
		request.ExecutionID,
		stage,
	)
	if countErr != nil {
		return fmt.Errorf("count data content outboxes: %w", countErr)
	}
	executionCreatedAt, executionCreatedErr := reliabletask.ResolveDataContentExecutionCreatedAt(
		cfg.EvidenceRoot,
		request.ExecutionID,
	)
	if executionCreatedErr != nil {
		return fmt.Errorf("resolve data content execution creation time: %w", executionCreatedErr)
	}
	finalizedObjectCount, finalizedErr := reliabletask.CountFinalizedDataContentObjects(
		cfg.EvidenceRoot,
		request.ExecutionID,
		request.Jobs,
	)
	if finalizedErr != nil {
		return fmt.Errorf("count finalized data content objects: %w", finalizedErr)
	}
	report := reliabletask.BuildDataContentFleetReport(
		tasks,
		executionCreatedAt,
		startedAt,
		completedAt,
		max(0, int(outboxCount)-len(request.Jobs)),
		max(0, len(request.Jobs)-len(tasks)),
		request.RequiredQuota,
		finalizedObjectCount,
	)
	if err := writeJSONAtomically(*reportPath, report); err != nil {
		return err
	}
	if runErr != nil {
		return runErr
	}
	// 批次按配额准出：候选池已过采，未达标对象由 Data 侧记为 discarded 而不重试，
	// 因此单个 dead task 不再让整个 fleet 进程失败。批次是否合格只由配额门裁定。
	if !report.Passed {
		log.Printf(
			"data content batch below quota: succeeded=%d/%d requiredQuota=%d",
			report.Succeeded,
			report.Total,
			report.RequiredQuota,
		)
	}
	if request.RequireCommercial && !report.Passed {
		return fmt.Errorf(
			"commercial ReliableTask gate blocked: accepted=%d/quota=%d "+
				"succeeded=%d/total=%d publishTasks=%d finalizedObjects=%d "+
				"duplicatePublish=%d missingObjects=%d status=%s",
			report.CommercialAcceptedCount,
			report.RequiredQuota,
			report.Succeeded,
			report.Total,
			report.PublishTaskCount,
			report.FinalizedObjectCount,
			report.DuplicatePublishCount,
			report.MissingObjectCount,
			report.AcceptedContentThroughputStatus,
		)
	}
	return nil
}

func discardExecution(executionID string) error {
	cfg, err := importer.LoadFleetStoreConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	client, err := mongo.Connect(options.Client().ApplyURI(cfg.MongoURI))
	if err != nil {
		return fmt.Errorf("connect reliabletask Mongo for execution discard: %w", err)
	}
	defer client.Disconnect(context.Background())
	store := reliabletaskmongo.NewDataContentImport(client.Database(cfg.MongoDatabase))
	if err := store.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ensure reliabletask indexes for execution discard: %w", err)
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"reliabletask": {
				Mode:     "standalone",
				Addr:     cfg.RedisAddr,
				Password: cfg.RedisPassword,
			},
		},
		DefaultScene: "reliabletask",
	})
	defer router.Close()
	executionHash := sha256.Sum256([]byte(executionID))
	streamSuffix := hex.EncodeToString(executionHash[:])
	ready, err := reliabletask.NewRedisReadyIndex(reliabletask.RedisReadyIndexConfig{
		Client: router.Scene("reliabletask"),
		Stream: "reliabletask:data:content:" + streamSuffix,
		Group:  "data.content_supply." + streamSuffix,
		Queue:  reliabletask.DataContentQueue,
	})
	if err != nil {
		return fmt.Errorf("create reliabletask discard ready index: %w", err)
	}
	result, err := store.PurgeDataContentExecution(ctx, executionID)
	if err != nil {
		return fmt.Errorf("purge Data execution remote records: %w", err)
	}
	if err := ready.Purge(ctx, result.TaskIDs); err != nil {
		return fmt.Errorf("purge Data execution Redis stream: %w", err)
	}
	fmt.Printf(
		"discarded executionId=%s tasks=%d outboxes=%d\n",
		executionID,
		result.TasksDeleted,
		result.OutboxesDeleted,
	)
	return nil
}

func runWorkers(
	ctx context.Context,
	request importer.FleetRequest,
	fleet reliabletask.DataContentFleet,
	executor reliabletask.DataContentExecutor,
	workers int,
	objectTimeout time.Duration,
) ([]reliabletask.ReliableAsyncTask, error) {
	if objectTimeout <= 0 {
		return nil, errors.New("data content object timeout must be positive")
	}
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
				objectCtx, cancelObject := context.WithTimeout(
					workerCtx,
					objectTimeout,
				)
				processed, err := localFleet.ProcessOneContent(
					objectCtx,
					executor,
				)
				cancelObject()
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
			fleet.Store,
			request.ExecutionID,
		)
		if err != nil {
			return nil, err
		}
		tasks, err := importer.SelectExecutionTasks(executionTasks, request)
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
	store reliabletask.DataContentExecutionStore,
	executionID string,
) ([]reliabletask.ReliableAsyncTask, error) {
	if store == nil {
		return nil, reliabletask.ErrStoreRequired
	}
	return store.ListDataContentExecutionTasks(ctx, executionID)
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

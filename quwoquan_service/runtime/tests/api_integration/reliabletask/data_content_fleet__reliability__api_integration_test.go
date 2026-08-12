//go:build api_integration

package reliabletask_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
)

const (
	dataContentFleetIntegrationLeaseTTL      = 10 * time.Second
	dataContentFleetIntegrationObjectTimeout = 60 * time.Second
	dataContentFleetIntegrationBatchTimeout  = dataContentFleetIntegrationObjectTimeout + 30*time.Second
)

func dataJob(i int) reliabletask.DataContentJob {
	entity := fmt.Sprintf("entity/地点/景区/%03d", i)
	job := reliabletask.DataContentJob{
		EntityRef:      entity,
		Carrier:        "homepage",
		SourceRevision: fmt.Sprintf("sha256:%064d", i+1),
		JobID:          fmt.Sprintf("job-%03d", i),
		ExecutionID:    "20260719--travel-homepage-coverage--cn-zhejiang--canary-001",
		Ref:            entity,
		Stage:          "author",
		PartitionKey:   entity,
		MaxAttempts:    3,
	}
	key, err := job.ExpectedIdempotencyKey()
	if err != nil {
		panic(err)
	}
	job.IdempotencyKey = key
	job.JobSetEnvelopeDigest = "sha256:" + strings.Repeat("e", 64)
	job.JobSetDigest = "sha256:" + strings.Repeat("f", 64)
	job.ActualTaskDigest = job.JobSetDigest
	return job
}

func registerMongoCleanup(
	t *testing.T,
	client *mongo.Client,
	databaseName string,
) {
	t.Helper()
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		if err := client.Database(databaseName).Drop(ctx); err != nil {
			t.Errorf("drop ReliableTask integration database %s: %v", databaseName, err)
		}
		names, err := client.ListDatabaseNames(ctx, bson.M{"name": databaseName})
		if err != nil {
			t.Errorf("verify ReliableTask integration database cleanup %s: %v", databaseName, err)
		} else if len(names) != 0 {
			t.Errorf("ReliableTask integration database cleanup left %v", names)
		}
		if err := client.Disconnect(context.Background()); err != nil {
			t.Errorf("disconnect ReliableTask integration Mongo: %v", err)
		}
	})
}

func registerReliableTaskExecutionCleanup(
	t *testing.T,
	store *reliabletaskmongo.DataContentStore,
	router *rtredis.Router,
	ready *reliabletask.RedisReadyIndex,
	stream string,
	executionIDs ...string,
) {
	t.Helper()
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		taskIDs := make([]string, 0)
		for _, executionID := range executionIDs {
			result, err := store.PurgeDataContentExecution(ctx, executionID)
			if err != nil {
				t.Errorf("purge ReliableTask execution %s: %v", executionID, err)
				continue
			}
			taskIDs = append(taskIDs, result.TaskIDs...)
		}
		if err := ready.Purge(ctx, taskIDs); err != nil {
			t.Errorf("purge ReliableTask Redis stream %s: %v", stream, err)
		}
		redisClient := router.Scene("reliabletask")
		keys := []string{stream}
		for _, taskID := range taskIDs {
			keys = append(keys, stream+":queued:"+taskID)
		}
		for _, key := range keys {
			if _, err := redisClient.Get(ctx, key); !errors.Is(err, rtredis.ErrKeyNotFound) {
				t.Errorf("ReliableTask Redis cleanup left key %s: %v", key, err)
			}
		}
		if err := router.Close(); err != nil {
			t.Errorf("close ReliableTask integration Redis: %v", err)
		}
	})
}

func productionReadyStream(executionID string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(executionID)))
	return "reliabletask:data:content:" + hex.EncodeToString(digest[:])
}

func TestDataContentFleetMongoRedisEndToEnd(t *testing.T) {
	startedAt := time.Now()
	mongoURI := os.Getenv("TEST_MONGO_URI")
	redisAddr := os.Getenv("TEST_REDIS_ADDR")
	if mongoURI == "" || redisAddr == "" {
		t.Fatal("TEST_MONGO_URI and TEST_REDIS_ADDR are required for real Mongo+Redis ReliableTask E2E")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
	if err != nil {
		t.Fatal(err)
	}
	databaseName := fmt.Sprintf("reliabletask_data_%d", time.Now().UnixNano())
	registerMongoCleanup(t, client, databaseName)
	db := client.Database(databaseName)
	store := reliabletaskmongo.NewDataContentImport(db)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"reliabletask": {Mode: "standalone", Addr: redisAddr},
		},
		DefaultScene: "reliabletask",
	})
	stream := fmt.Sprintf("reliabletask:data:content:%d", time.Now().UnixNano())
	ready, err := reliabletask.NewRedisReadyIndex(reliabletask.RedisReadyIndexConfig{
		Client: router.Scene("reliabletask"),
		Stream: stream,
		Group:  "data.content_supply.integration",
		Queue:  reliabletask.DataContentQueue,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := ready.Ensure(ctx); err != nil {
		t.Fatal(err)
	}
	registerReliableTaskExecutionCleanup(
		t,
		store,
		router,
		ready,
		stream,
		dataJob(0).ExecutionID,
		"20260720--travel-homepage-coverage--cn-sichuan--scale-001",
		"20260720--travel-homepage-coverage--cn-zhejiang--canary-002",
	)
	fleet := reliabletask.DataContentFleet{
		Store:          store,
		ExecutionID:    dataJob(0).ExecutionID,
		Ready:          ready,
		WorkerID:       "data-integration-worker",
		LeaseTTL:       dataContentFleetIntegrationLeaseTTL,
		PendingMinIdle: 10 * time.Millisecond,
		Retry:          reliabletask.RetryPolicy{MaxAttempts: 3, Backoff: []time.Duration{10 * time.Millisecond}},
	}
	const total = 100
	foreign := dataJob(total + 1)
	foreign.ExecutionID = "20260720--travel-homepage-coverage--cn-sichuan--scale-001"
	foreign.JobID = "job-foreign"
	foreign.Ref = foreign.EntityRef
	foreignKey, err := foreign.ExpectedIdempotencyKey()
	if err != nil {
		t.Fatal(err)
	}
	foreign.IdempotencyKey = foreignKey
	foreignFleet := reliabletask.DataContentFleet{
		Store:       store,
		ExecutionID: foreign.ExecutionID,
	}
	if _, err := foreignFleet.Declare(ctx, foreign); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < total; i++ {
		if _, err := fleet.Declare(ctx, dataJob(i)); err != nil {
			t.Fatal(err)
		}
	}
	// completed 前重复声明不得制造第二 outbox。
	if _, err := fleet.Declare(ctx, dataJob(0)); err != nil {
		t.Fatal(err)
	}
	if tasks, err := fleet.Dispatch(ctx, total+10); err != nil || len(tasks) != total {
		t.Fatalf("dispatch got=%d err=%v", len(tasks), err)
	}
	if tasks, err := fleet.Dispatch(ctx, total+10); err != nil || len(tasks) != 0 {
		t.Fatalf("repeat execution dispatch got=%d err=%v", len(tasks), err)
	}
	foreignOutboxes, err := db.Collection("post_import_task_outbox").CountDocuments(
		ctx,
		bson.M{
			"taskType":            reliabletask.DataContentTaskType,
			"payload.executionId": foreign.ExecutionID,
			"status":              reliabletask.TaskOutboxStatusPending,
		},
	)
	if err != nil || foreignOutboxes != 1 {
		t.Fatalf("foreign execution was dispatched=%d err=%v", foreignOutboxes, err)
	}
	failOnce := map[string]bool{}
	completed := 0
	deadline := time.Now().Add(30 * time.Second)
	for completed < total && time.Now().Before(deadline) {
		processed, err := fleet.ProcessOneContent(
			ctx,
			reliabletask.DataContentExecutorFunc(
				func(_ context.Context, item reliabletask.DataContentWorkItem) (reliabletask.DataContentExecutionResult, error) {
					if item.EntityRef == dataJob(7).EntityRef && !failOnce[item.RuntimeTaskID] {
						failOnce[item.RuntimeTaskID] = true
						return reliabletask.DataContentExecutionResult{}, errors.New("transient integration failure")
					}
					completed++
					return reliabletask.DataContentExecutionResult{
						ExecutionID:         item.ExecutionID,
						JobID:               item.JobID,
						CanonicalObjectRef:  "publish/" + item.EntityRef,
						ObjectTransactionID: "object-transaction-" + item.JobID,
						ResultEnvelopeRef:   "results/" + item.JobID + ".json",
						AcceptanceClass:     reliabletask.DataContentAcceptanceContractFixture,
						CompletedAt:         time.Now().UTC(),
					}, nil
				},
			),
		)
		if err != nil {
			t.Fatal(err)
		}
		if !processed {
			time.Sleep(15 * time.Millisecond)
			_, _ = fleet.Dispatch(ctx, total)
		}
	}
	if completed != total {
		t.Fatalf("fleet did not finalize within budget: %d/%d", completed, total)
	}
	count, err := db.Collection("post_import_task").CountDocuments(
		ctx,
		bson.M{"status": reliabletask.TaskStatusSucceeded},
	)
	if err != nil {
		t.Fatal(err)
	}
	if count != total {
		t.Fatalf("succeeded task count=%d want=%d", count, total)
	}
	recorded, err := db.Collection("post_import_task").CountDocuments(
		ctx,
		bson.M{
			"result.schema": "quwoquan.data_content_object_result",
			"result.status": "contract_fixture",
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if recorded != total {
		t.Fatalf("contract fixture task result count=%d want=%d", recorded, total)
	}
	outboxes, err := db.Collection("post_import_task_outbox").CountDocuments(
		ctx,
		bson.M{"payload.executionId": dataJob(0).ExecutionID},
	)
	if err != nil {
		t.Fatal(err)
	}
	if outboxes != total {
		t.Fatalf("duplicate outbox publish: got=%d want=%d", outboxes, total)
	}
	// 终态后重放同一幂等身份仍返回原记录，且不再 dispatch。
	if _, err := fleet.Declare(ctx, dataJob(0)); err != nil {
		t.Fatal(err)
	}
	if tasks, err := fleet.Dispatch(ctx, 10); err != nil || len(tasks) != 0 {
		t.Fatalf("terminal replay dispatched duplicate tasks=%d err=%v", len(tasks), err)
	}
	if reportOut := os.Getenv("QWQ_RELIABLETASK_REPORT_OUT"); reportOut != "" {
		cursor, err := db.Collection("post_import_task").Find(
			ctx,
			bson.M{"taskType": reliabletask.DataContentTaskType},
		)
		if err != nil {
			t.Fatal(err)
		}
		defer cursor.Close(ctx)
		var taskRows []reliabletask.ReliableAsyncTask
		if err := cursor.All(ctx, &taskRows); err != nil {
			t.Fatal(err)
		}
		report := reliabletask.BuildDataContentFleetReport(
			taskRows,
			startedAt,
			startedAt,
			time.Now().UTC(),
			int(outboxes)-total,
			total-len(taskRows),
			total,
			0,
		)
		if report.CommercialAcceptedCount != 0 ||
			report.EndToEndAcceptedThroughputPerHour != 0 ||
			report.AcceptedContentThroughputStatus != "GATE_BLOCK_NO_COMMERCIAL_BATCH" {
			t.Fatalf(
				"control-plane fixture was misreported as commercial throughput: %#v",
				report,
			)
		}
		data, err := json.MarshalIndent(report, "", "  ")
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(reportOut, append(data, '\n'), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	// retryOf 的新 immutable execution 即使复用同一实体和来源版本，也必须有独立的
	// Mongo task/outbox，不能复用前一 execution 的终态或死信。
	retry := dataJob(0)
	retry.ExecutionID = "20260720--travel-homepage-coverage--cn-zhejiang--canary-002"
	retry.JobID = "job-000-retry"
	retryKey, err := retry.ExpectedIdempotencyKey()
	if err != nil {
		t.Fatal(err)
	}
	retry.IdempotencyKey = retryKey
	retryFleet := reliabletask.DataContentFleet{
		Store:       store,
		ExecutionID: retry.ExecutionID,
		Ready:       ready,
	}
	if _, err := retryFleet.Declare(ctx, retry); err != nil {
		t.Fatalf("declare retry execution task: %v", err)
	}
	retryTasks, err := retryFleet.Dispatch(ctx, 10)
	if err != nil {
		t.Fatalf("dispatch retry execution task: %v", err)
	}
	if len(retryTasks) != 1 {
		t.Fatalf("retry execution dispatched=%d want=1", len(retryTasks))
	}
	if retryTasks[0].Payload["executionId"] != retry.ExecutionID {
		t.Fatalf(
			"retry task executionId=%q want=%q",
			retryTasks[0].Payload["executionId"],
			retry.ExecutionID,
		)
	}
}

func TestDataContentFleetRunsRealPythonObjectTransaction(t *testing.T) {
	repoRoot := strings.TrimSpace(os.Getenv("TEST_REPO_ROOT"))
	python := strings.TrimSpace(os.Getenv("TEST_QWQ_DATA_PYTHON"))
	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	redisAddr := strings.TrimSpace(os.Getenv("TEST_REDIS_ADDR"))
	if repoRoot == "" || python == "" || mongoURI == "" || redisAddr == "" {
		t.Fatal(
			"TEST_REPO_ROOT, TEST_QWQ_DATA_PYTHON, TEST_MONGO_URI and " +
				"TEST_REDIS_ADDR are required for the real data worker E2E",
		)
	}
	tempRoot := t.TempDir()
	outputRoot := filepath.Join(tempRoot, "output")
	publishRoot := filepath.Join(tempRoot, "publish")
	fixtureCommand := exec.Command(
		python,
		filepath.Join(
			repoRoot,
			"quwoquan_data/tests/support/reliabletask_process_fixture.py",
		),
		"--output-root",
		outputRoot,
		"--publish-root",
		publishRoot,
	)
	fixtureCommand.Dir = repoRoot
	fixtureCommand.Env = dataContentTestEnvironment(
		os.Environ(),
		outputRoot,
		publishRoot,
	)
	fixtureOutput, err := fixtureCommand.CombinedOutput()
	if err != nil {
		t.Fatalf("prepare real Python worker fixture: %v\n%s", err, fixtureOutput)
	}
	var fixture struct {
		Schema               string                      `json:"schema"`
		SourceCapsuleRoot    string                      `json:"sourceCapsuleRoot"`
		Job                  reliabletask.DataContentJob `json:"job"`
		IdempotencyKey       string                      `json:"idempotencyKey"`
		ExpectedCanonicalRef string                      `json:"expectedCanonicalRef"`
	}
	if err := json.Unmarshal(fixtureOutput, &fixture); err != nil {
		t.Fatalf("decode real Python worker fixture: %v", err)
	}
	if fixture.Schema != "quwoquan.reliabletask_process_fixture" {
		t.Fatalf("fixture schema drift: %q", fixture.Schema)
	}
	if !filepath.IsAbs(fixture.SourceCapsuleRoot) {
		t.Fatalf("fixture source capsule root is not absolute: %q", fixture.SourceCapsuleRoot)
	}
	key, err := fixture.Job.ValidateIdentity()
	if err != nil {
		t.Fatal(err)
	}
	if key != fixture.IdempotencyKey {
		t.Fatalf("fixture idempotency drift: got=%q want=%q", key, fixture.IdempotencyKey)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
	if err != nil {
		t.Fatal(err)
	}
	databaseName := fmt.Sprintf("reliabletask_data_process_%d", time.Now().UnixNano())
	registerMongoCleanup(t, client, databaseName)
	db := client.Database(databaseName)
	store := reliabletaskmongo.NewDataContentImport(db)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"reliabletask": {Mode: "standalone", Addr: redisAddr},
		},
		DefaultScene: "reliabletask",
	})
	stream := fmt.Sprintf(
		"reliabletask:data:content:process:%d",
		time.Now().UnixNano(),
	)
	ready, err := reliabletask.NewRedisReadyIndex(reliabletask.RedisReadyIndexConfig{
		Client: router.Scene("reliabletask"),
		Stream: stream,
		Group:  "data.content_supply.process.integration",
		Queue:  reliabletask.DataContentQueue,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := ready.Ensure(ctx); err != nil {
		t.Fatal(err)
	}
	registerReliableTaskExecutionCleanup(
		t,
		store,
		router,
		ready,
		stream,
		fixture.Job.ExecutionID,
	)
	fleet := reliabletask.DataContentFleet{
		Store:          store,
		ExecutionID:    fixture.Job.ExecutionID,
		Ready:          ready,
		WorkerID:       "data-process-integration-worker",
		LeaseTTL:       10 * time.Second,
		PendingMinIdle: 10 * time.Millisecond,
		Retry: reliabletask.RetryPolicy{
			MaxAttempts: 2,
			Backoff:     []time.Duration{10 * time.Millisecond},
		},
		ResultVerifier: reliabletask.DataContentFilesystemEvidenceVerifier{
			PublishRoot:  publishRoot,
			EvidenceRoot: outputRoot,
		},
	}
	if _, err := fleet.Declare(ctx, fixture.Job); err != nil {
		t.Fatal(err)
	}
	if tasks, err := fleet.Dispatch(ctx, 10); err != nil || len(tasks) != 1 {
		t.Fatalf("dispatch real worker tasks=%d err=%v", len(tasks), err)
	}
	executor := reliabletask.DataContentProcessExecutor{
		Command: []string{
			python,
			"-c",
			"from content.execution.queue.reliabletask.worker import run_process_worker; run_process_worker()",
		},
		WorkDir: filepath.Join(fixture.SourceCapsuleRoot, "quwoquan_data"),
		Environment: dataContentCapsuleEnvironment(
			os.Environ(),
			outputRoot,
			publishRoot,
			fixture.SourceCapsuleRoot,
		),
	}
	deadline := time.Now().Add(60 * time.Second)
	var task reliabletask.ReliableAsyncTask
	for time.Now().Before(deadline) {
		processed, err := fleet.ProcessOneContent(ctx, executor)
		if err != nil {
			t.Fatal(err)
		}
		err = db.Collection("post_import_task").FindOne(
			ctx,
			bson.M{"payload.jobId": fixture.Job.JobID},
		).Decode(&task)
		if err != nil && !errors.Is(err, mongo.ErrNoDocuments) {
			t.Fatal(err)
		}
		if err == nil && (task.Status == reliabletask.TaskStatusSucceeded ||
			task.Status == reliabletask.TaskStatusDead) {
			break
		}
		if !processed {
			time.Sleep(15 * time.Millisecond)
		}
		_, _ = fleet.Dispatch(ctx, 10)
	}
	if task.Status != reliabletask.TaskStatusSucceeded {
		t.Fatalf(
			"real Python worker did not succeed: status=%s failure=%#v",
			task.Status,
			task.LastFailure,
		)
	}
	canonicalManifest := filepath.Join(
		publishRoot,
		filepath.FromSlash(fixture.ExpectedCanonicalRef),
		"manifest.json",
	)
	if _, err := os.Stat(canonicalManifest); err != nil {
		t.Fatalf("real canonical object missing: %v", err)
	}
	report := reliabletask.BuildDataContentFleetReport(
		[]reliabletask.ReliableAsyncTask{task},
		task.CreatedAt,
		task.CreatedAt,
		task.UpdatedAt,
		0,
		0,
		1,
		0,
	)
	if !report.Passed ||
		report.CommercialAcceptedCount != 1 ||
		report.EndToEndAcceptedThroughputPerHour <= 0 ||
		report.AcceptedContentThroughputStatus != "MEASURED" {
		t.Fatalf("real accepted throughput was not measured: %#v", report)
	}
}

func TestProductionDataContentWorkerUsesReliableTaskFleet(t *testing.T) {
	repoRoot := strings.TrimSpace(os.Getenv("TEST_REPO_ROOT"))
	python := strings.TrimSpace(os.Getenv("TEST_QWQ_DATA_PYTHON"))
	mongoURI := strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	redisAddr := strings.TrimSpace(os.Getenv("TEST_REDIS_ADDR"))
	if repoRoot == "" || python == "" || mongoURI == "" || redisAddr == "" {
		t.Fatal(
			"TEST_REPO_ROOT, TEST_QWQ_DATA_PYTHON, TEST_MONGO_URI and " +
				"TEST_REDIS_ADDR are required for the production fleet E2E",
		)
	}
	tempRoot := t.TempDir()
	outputRoot := filepath.Join(tempRoot, "output")
	publishRoot := filepath.Join(tempRoot, "publish")
	fixtureCommand := exec.Command(
		python,
		filepath.Join(
			repoRoot,
			"quwoquan_data/tests/support/reliabletask_process_fixture.py",
		),
		"--output-root",
		outputRoot,
		"--publish-root",
		publishRoot,
	)
	fixtureCommand.Dir = repoRoot
	fixtureCommand.Env = dataContentTestEnvironment(
		os.Environ(),
		outputRoot,
		publishRoot,
	)
	fixtureOutput, err := fixtureCommand.CombinedOutput()
	if err != nil {
		t.Fatalf("prepare production fleet fixture: %v\n%s", err, fixtureOutput)
	}
	var fixture struct {
		Job                  reliabletask.DataContentJob `json:"job"`
		ExpectedCanonicalRef string                      `json:"expectedCanonicalRef"`
		FleetRequest         json.RawMessage             `json:"fleetRequest"`
		SourceCapsuleRoot    string                      `json:"sourceCapsuleRoot"`
	}
	if err := json.Unmarshal(fixtureOutput, &fixture); err != nil {
		t.Fatalf("decode production fleet fixture: %v", err)
	}
	if !filepath.IsAbs(fixture.SourceCapsuleRoot) {
		t.Fatalf("production fixture source capsule root is not absolute: %q", fixture.SourceCapsuleRoot)
	}
	databaseName := fmt.Sprintf(
		"reliabletask_data_cli_%d",
		time.Now().UnixNano(),
	)
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
	if err != nil {
		t.Fatal(err)
	}
	registerMongoCleanup(t, client, databaseName)
	cleanupStore := reliabletaskmongo.NewDataContentImport(
		client.Database(databaseName),
	)
	cleanupRouter := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"reliabletask": {Mode: "standalone", Addr: redisAddr},
		},
		DefaultScene: "reliabletask",
	})
	cleanupStream := productionReadyStream(fixture.Job.ExecutionID)
	cleanupReady, err := reliabletask.NewRedisReadyIndex(
		reliabletask.RedisReadyIndexConfig{
			Client: cleanupRouter.Scene("reliabletask"),
			Stream: cleanupStream,
			Group: "data.content_supply." + strings.TrimPrefix(
				cleanupStream,
				"reliabletask:data:content:",
			),
			Queue: reliabletask.DataContentQueue,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	registerReliableTaskExecutionCleanup(
		t,
		cleanupStore,
		cleanupRouter,
		cleanupReady,
		cleanupStream,
		fixture.Job.ExecutionID,
	)
	requestPath := filepath.Join(tempRoot, "fleet_request.json")
	reportPath := filepath.Join(
		outputRoot,
		"data",
		"tasks",
		fixture.Job.ExecutionID,
		"evidence",
		"reliabletask",
		"publish_fleet_report.json",
	)
	if len(fixture.FleetRequest) == 0 {
		t.Fatal("fixture frozen fleet request is missing")
	}
	if err := os.WriteFile(requestPath, fixture.FleetRequest, 0o600); err != nil {
		t.Fatal(err)
	}
	command := exec.Command(
		"go",
		"run",
		"./services/content-service/cmd/data-content-worker",
		"--request",
		requestPath,
		"--report",
		reportPath,
	)
	command.Dir = filepath.Join(repoRoot, "quwoquan_service")
	command.Env = dataContentEnvironment(
		os.Environ(),
		map[string]string{
			"PYTHONDONTWRITEBYTECODE":            "1",
			"QWQ_OUTPUT_ROOT":                    outputRoot,
			"QWQ_PUBLISH_ROOT":                   publishRoot,
			"QWQ_DATA_FLEET_MONGO_URI":           mongoURI,
			"QWQ_DATA_FLEET_MONGO_DATABASE":      databaseName,
			"QWQ_DATA_FLEET_REDIS_ADDR":          redisAddr,
			"QWQ_DATA_FLEET_PENDING_MIN_IDLE_MS": "10",
			"QWQ_DATA_FLEET_PYTHON":              python,
			"QWQ_DATA_FLEET_SCRIPTS_ROOT":        filepath.Join(fixture.SourceCapsuleRoot, "quwoquan_data", "scripts"),
			"QWQ_DATA_FLEET_WORK_DIR":            filepath.Join(fixture.SourceCapsuleRoot, "quwoquan_data"),
			"QWQ_DATA_FLEET_PUBLISH_ROOT":        publishRoot,
			"QWQ_DATA_FLEET_EVIDENCE_ROOT":       outputRoot,
			"QWQ_DATA_FLEET_WORKERS":             "2",
			"QWQ_DATA_FLEET_BATCH_TIMEOUT_MS": strconv.FormatInt(
				dataContentFleetIntegrationBatchTimeout.Milliseconds(),
				10,
			),
		},
	)
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf(
			"production qwq-data ReliableTask fleet failed: %v\n%s",
			err,
			output,
		)
	}
	reportBytes, err := os.ReadFile(reportPath)
	if err != nil {
		t.Fatal(err)
	}
	var report reliabletask.DataContentFleetReport
	if err := json.Unmarshal(reportBytes, &report); err != nil {
		t.Fatal(err)
	}
	if reportOut := strings.TrimSpace(
		os.Getenv("QWQ_RELIABLETASK_COMMERCIAL_REPORT_OUT"),
	); reportOut != "" {
		if err := os.MkdirAll(filepath.Dir(reportOut), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(reportOut, reportBytes, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	if !report.Passed ||
		report.ResearchAcceptedCount != 1 ||
		report.CommercialAcceptedCount != 0 ||
		report.ObjectTransactionResultCount != 1 ||
		report.RequiredQuota != 1 ||
		report.EndToEndAcceptedThroughputPerHour <= 0 {
		tasks, taskErr := cleanupStore.ListDataContentExecutionTasks(
			context.Background(),
			fixture.Job.ExecutionID,
		)
		failures := make([]reliabletask.RuntimeFailure, 0, len(tasks))
		for _, task := range tasks {
			if task.LastFailure != nil {
				failures = append(failures, *task.LastFailure)
			}
		}
		t.Fatalf(
			"production fleet report is not research accepted: %#v failures=%#v taskErr=%v",
			report,
			failures,
			taskErr,
		)
	}
	if _, err := os.Stat(filepath.Join(
		publishRoot,
		filepath.FromSlash(fixture.ExpectedCanonicalRef),
		"manifest.json",
	)); err != nil {
		t.Fatalf("production fleet canonical object missing: %v", err)
	}
}

func dataContentTestEnvironment(
	current []string,
	outputRoot string,
	publishRoot string,
) []string {
	overrides := map[string]string{
		"PYTHONDONTWRITEBYTECODE": "1",
		"QWQ_OUTPUT_ROOT":         outputRoot,
		"QWQ_PUBLISH_ROOT":        publishRoot,
	}
	if repoRoot := strings.TrimSpace(os.Getenv("TEST_REPO_ROOT")); repoRoot != "" {
		scriptsRoot := filepath.Join(repoRoot, "quwoquan_data", "scripts")
		overrides["PYTHONPATH"] = scriptsRoot + string(os.PathListSeparator) + repoRoot
	}
	return dataContentEnvironment(current, overrides)
}

func dataContentCapsuleEnvironment(
	current []string,
	outputRoot string,
	publishRoot string,
	sourceCapsuleRoot string,
) []string {
	return dataContentEnvironment(
		current,
		map[string]string{
			"PYTHONDONTWRITEBYTECODE": "1",
			"PYTHONPATH": filepath.Join(
				sourceCapsuleRoot,
				"quwoquan_data",
				"scripts",
			),
			"QWQ_OUTPUT_ROOT":  outputRoot,
			"QWQ_PUBLISH_ROOT": publishRoot,
		},
	)
}

func dataContentEnvironment(
	current []string,
	overrides map[string]string,
) []string {
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

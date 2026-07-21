//go:build api_integration

package reliabletask_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
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

const dataContentFleetIntegrationLeaseTTL = 10 * time.Second

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
	}
	key, err := job.ExpectedIdempotencyKey()
	if err != nil {
		panic(err)
	}
	job.IdempotencyKey = key
	return job
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
	defer client.Disconnect(ctx)
	db := client.Database(fmt.Sprintf("reliabletask_data_%d", time.Now().UnixNano()))
	t.Cleanup(func() { _ = db.Drop(context.Background()) })
	store := reliabletaskmongo.New(db)
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
	fleet := reliabletask.DataContentFleet{
		Store:          store,
		Ready:          ready,
		WorkerID:       "data-integration-worker",
		LeaseTTL:       dataContentFleetIntegrationLeaseTTL,
		PendingMinIdle: 10 * time.Millisecond,
		Retry:          reliabletask.RetryPolicy{MaxAttempts: 3, Backoff: []time.Duration{10 * time.Millisecond}},
	}
	const total = 100
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
	count, err := db.Collection("reliable_async_task").CountDocuments(
		ctx,
		bson.M{"status": reliabletask.TaskStatusSucceeded},
	)
	if err != nil {
		t.Fatal(err)
	}
	if count != total {
		t.Fatalf("succeeded task count=%d want=%d", count, total)
	}
	recorded, err := db.Collection("reliable_async_task").CountDocuments(
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
	outboxes, err := db.Collection("reliable_task_outbox").CountDocuments(ctx, bson.M{})
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
		cursor, err := db.Collection("reliable_async_task").Find(
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
			time.Now().UTC(),
			int(outboxes)-total,
			total-len(taskRows),
		)
		if report.Passed ||
			report.CommercialAcceptedCount != 0 ||
			report.AcceptedContentThroughputPerHour != 0 ||
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
	if _, err := fleet.Declare(ctx, retry); err != nil {
		t.Fatalf("declare retry execution task: %v", err)
	}
	retryTasks, err := fleet.Dispatch(ctx, 10)
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
	fixtureOutput, err := fixtureCommand.Output()
	if err != nil {
		t.Fatalf("prepare real Python worker fixture: %v", err)
	}
	var fixture struct {
		Schema               string                      `json:"schema"`
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
	defer client.Disconnect(ctx)
	db := client.Database(fmt.Sprintf("reliabletask_data_process_%d", time.Now().UnixNano()))
	t.Cleanup(func() { _ = db.Drop(context.Background()) })
	store := reliabletaskmongo.New(db)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"reliabletask": {Mode: "standalone", Addr: redisAddr},
		},
		DefaultScene: "reliabletask",
	})
	t.Cleanup(func() { _ = router.Close() })
	ready, err := reliabletask.NewRedisReadyIndex(reliabletask.RedisReadyIndexConfig{
		Client: router.Scene("reliabletask"),
		Stream: fmt.Sprintf(
			"reliabletask:data:content:process:%d",
			time.Now().UnixNano(),
		),
		Group: "data.content_supply.process.integration",
		Queue: reliabletask.DataContentQueue,
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := ready.Ensure(ctx); err != nil {
		t.Fatal(err)
	}
	fleet := reliabletask.DataContentFleet{
		Store:          store,
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
			"from content.execution.reliabletask_worker import run_process_worker; run_process_worker()",
		},
		WorkDir: filepath.Join(repoRoot, "quwoquan_data"),
		Environment: dataContentTestEnvironment(
			os.Environ(),
			outputRoot,
			publishRoot,
		),
	}
	deadline := time.Now().Add(60 * time.Second)
	var task reliabletask.ReliableAsyncTask
	for time.Now().Before(deadline) {
		processed, err := fleet.ProcessOneContent(ctx, executor)
		if err != nil {
			t.Fatal(err)
		}
		err = db.Collection("reliable_async_task").FindOne(
			ctx,
			bson.M{"payload.jobId": fixture.Job.JobID},
		).Decode(&task)
		if err != nil && !errors.Is(err, mongo.ErrNoDocuments) {
			t.Fatal(err)
		}
		if err == nil && task.Status == reliabletask.TaskStatusSucceeded {
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
		task.UpdatedAt,
		0,
		0,
	)
	if !report.Passed ||
		report.CommercialAcceptedCount != 1 ||
		report.AcceptedContentThroughputPerHour <= 0 ||
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
	fixtureOutput, err := fixtureCommand.Output()
	if err != nil {
		t.Fatalf("prepare production fleet fixture: %v", err)
	}
	var fixture struct {
		Job                  reliabletask.DataContentJob `json:"job"`
		ExpectedCanonicalRef string                      `json:"expectedCanonicalRef"`
	}
	if err := json.Unmarshal(fixtureOutput, &fixture); err != nil {
		t.Fatalf("decode production fleet fixture: %v", err)
	}
	databaseName := fmt.Sprintf(
		"reliabletask_data_cli_%d",
		time.Now().UnixNano(),
	)
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(mongoURI))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_ = client.Database(databaseName).Drop(context.Background())
		_ = client.Disconnect(context.Background())
	})
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
	requestPayload, err := json.Marshal(map[string]any{
		"schema":            "quwoquan.data_content_fleet_request",
		"executionId":       fixture.Job.ExecutionID,
		"requireCommercial": true,
		"recoverDeadTasks":  false,
		"jobs":              []reliabletask.DataContentJob{fixture.Job},
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(requestPath, requestPayload, 0o600); err != nil {
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
			"QWQ_DATA_FLEET_SCRIPTS_ROOT":        filepath.Join(repoRoot, "quwoquan_data", "scripts"),
			"QWQ_DATA_FLEET_WORK_DIR":            filepath.Join(repoRoot, "quwoquan_data"),
			"QWQ_DATA_FLEET_PUBLISH_ROOT":        publishRoot,
			"QWQ_DATA_FLEET_EVIDENCE_ROOT":       outputRoot,
			"QWQ_DATA_FLEET_WORKERS":             "2",
			"QWQ_DATA_FLEET_TIMEOUT_MS":          "60000",
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
		report.CommercialAcceptedCount != 1 ||
		report.AcceptedContentThroughputPerHour <= 0 {
		t.Fatalf("production fleet report is not commercially accepted: %#v", report)
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
		overrides["PYTHONPATH"] = filepath.Join(repoRoot, "quwoquan_data", "scripts")
	}
	return dataContentEnvironment(current, overrides)
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

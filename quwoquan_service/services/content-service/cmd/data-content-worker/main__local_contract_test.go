package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/reliabletask"
)

func TestReadFleetRequestAcceptsBoundAuthorAndPublishJobs(t *testing.T) {
	path := filepath.Join(t.TempDir(), "request.json")
	executionID := "20260720--travel-image-publish--cn-zhejiang--canary-902"
	entityRef := "/entity/地点/景区/西湖"
	sourceRevision := "sha256:" + strings.Repeat("a", 64)
	idempotencyKey := executionID + "|" + entityRef + "|image|" + sourceRevision + "|publish"
	request := map[string]any{
		"schema":            fleetRequestSchema,
		"executionId":       executionID,
		"requireCommercial": true,
		"recoverDeadTasks":  false,
		"jobs": []map[string]string{
			{
				"entityRef":      entityRef,
				"carrier":        "image",
				"sourceRevision": sourceRevision,
				"idempotencyKey": idempotencyKey,
				"jobId":          "job-publish-001",
				"executionId":    executionID,
				"ref":            "image-source-001",
				"stage":          "publish",
				"partitionKey":   "canonical-publish",
			},
		},
	}
	payload, err := json.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, payload, 0o600); err != nil {
		t.Fatal(err)
	}

	decoded, err := readFleetRequest(path)

	if err != nil {
		t.Fatal(err)
	}
	if !decoded.RequireCommercial ||
		decoded.RecoverDeadTasks == nil ||
		*decoded.RecoverDeadTasks ||
		len(decoded.Jobs) != 1 ||
		decoded.Jobs[0].JobID != "job-publish-001" {
		t.Fatalf("fleet request drift: %#v", decoded)
	}
}

func TestReadFleetRequestRejectsUnknownFields(t *testing.T) {
	path := filepath.Join(t.TempDir(), "request.json")
	payload := `{
		"schema":"quwoquan.data_content_fleet_request",
		"executionId":"20260720--travel-image-publish--cn-zhejiang--canary-902",
		"requireCommercial":true,
		"recoverDeadTasks":false,
		"jobs":[],
		"fallback":"forbidden"
	}`
	if err := os.WriteFile(path, []byte(payload), 0o600); err != nil {
		t.Fatal(err)
	}

	_, err := readFleetRequest(path)

	if err == nil || !strings.Contains(err.Error(), "unknown field") {
		t.Fatalf("unknown fleet request field was not rejected: %v", err)
	}
}

func TestRequestedExecutionTasksIgnoresOtherStagesInSameExecution(t *testing.T) {
	executionID := "20260720--travel-image-publish--cn-zhejiang--canary-902"
	boundJob := func(jobID, ref string) reliabletask.DataContentJob {
		job := reliabletask.DataContentJob{
			EntityRef:      ref,
			Carrier:        "image",
			SourceRevision: "sha256:" + strings.Repeat("b", 64),
			JobID:          jobID,
			ExecutionID:    executionID,
			Ref:            ref,
			Stage:          "publish",
			PartitionKey:   "canonical-publish",
		}
		key, err := job.ExpectedIdempotencyKey()
		if err != nil {
			t.Fatal(err)
		}
		job.IdempotencyKey = key
		return job
	}
	putuo := boundJob("publish-putuo", "/entity/地点/景区/普陀山")
	dongqian := boundJob("publish-dongqian", "/entity/地点/自然景观/东钱湖")
	toTask := func(taskID string, job reliabletask.DataContentJob) reliabletask.ReliableAsyncTask {
		return reliabletask.ReliableAsyncTask{
			TaskID:         taskID,
			IdempotencyKey: job.IdempotencyKey,
			DedupeKey:      job.IdempotencyKey,
			PartitionKey:   job.PartitionKey,
			Payload: map[string]string{
				"jobId": job.JobID, "executionId": job.ExecutionID,
				"idempotencyKey": job.IdempotencyKey,
			},
		}
	}
	request := fleetRequest{
		ExecutionID: executionID,
		Jobs:        []reliabletask.DataContentJob{putuo, dongqian},
	}
	tasks := []reliabletask.ReliableAsyncTask{
		{
			TaskID: "author-putuo",
			Payload: map[string]string{
				"jobId": "author-putuo",
				"stage": "author",
			},
		},
		toTask("publish-dongqian", dongqian),
		toTask("publish-putuo", putuo),
	}

	selected, err := requestedExecutionTasks(tasks, request)
	if err != nil {
		t.Fatal(err)
	}

	if len(selected) != 2 ||
		selected[0].TaskID != "publish-putuo" ||
		selected[1].TaskID != "publish-dongqian" {
		t.Fatalf("request task selection drift: %#v", selected)
	}
}

func TestRequestedExecutionTasksRejectsAmbiguousRemoteIdentity(t *testing.T) {
	job := reliabletask.DataContentJob{
		EntityRef:      "/entity/地点/景区/普陀山",
		Carrier:        "homepage",
		SourceRevision: "sha256:" + strings.Repeat("c", 64),
		JobID:          "author-putuo",
		ExecutionID:    "20260720--travel-homepage-coverage--cn-zhejiang--canary-902",
		Ref:            "/entity/地点/景区/普陀山",
		Stage:          "author",
		PartitionKey:   "/entity/地点/景区/普陀山",
	}
	key, err := job.ExpectedIdempotencyKey()
	if err != nil {
		t.Fatal(err)
	}
	job.IdempotencyKey = key
	task := reliabletask.ReliableAsyncTask{
		IdempotencyKey: key,
		DedupeKey:      key,
		PartitionKey:   job.PartitionKey,
		Payload: map[string]string{
			"jobId": job.JobID, "executionId": job.ExecutionID, "idempotencyKey": key,
		},
	}
	_, err = requestedExecutionTasks(
		[]reliabletask.ReliableAsyncTask{task, task},
		fleetRequest{ExecutionID: job.ExecutionID, Jobs: []reliabletask.DataContentJob{job}},
	)
	if err == nil || !strings.Contains(err.Error(), "ambiguous") {
		t.Fatalf("ambiguous remote task was accepted: %v", err)
	}
}

func TestLoadWorkerConfigFailsClosedAndLoadsTypedValues(t *testing.T) {
	_, err := loadWorkerConfig(runtimeconfig.MapRuntimeConfigProvider{})
	if err == nil || !strings.Contains(err.Error(), "QWQ_DATA_FLEET_MONGO_URI") {
		t.Fatalf("missing runtime config was not rejected: %v", err)
	}
	provider := runtimeconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"QWQ_DATA_FLEET_MONGO_URI":           "mongodb://mongo:27017",
			"QWQ_DATA_FLEET_REDIS_ADDR":          "redis:6379",
			"QWQ_DATA_FLEET_PYTHON":              "/usr/bin/python3",
			"QWQ_DATA_FLEET_SCRIPTS_ROOT":        "/workspace/quwoquan_data/scripts",
			"QWQ_DATA_FLEET_WORK_DIR":            "/workspace/quwoquan_data",
			"QWQ_DATA_FLEET_PUBLISH_ROOT":        "/workspace/quwoquan_data/publish",
			"QWQ_DATA_FLEET_EVIDENCE_ROOT":       "/workspace/.qwq_output",
			"QWQ_DATA_FLEET_WORKERS":             "16",
			"QWQ_DATA_FLEET_TIMEOUT_MS":          "120000",
			"QWQ_DATA_FLEET_MAX_ATTEMPTS":        "4",
			"QWQ_DATA_FLEET_LEASE_TTL_MS":        "30000",
			"QWQ_DATA_FLEET_PENDING_MIN_IDLE_MS": "500",
		},
	}

	cfg, err := loadWorkerConfig(provider)

	if err != nil {
		t.Fatal(err)
	}
	if cfg.workers != 16 ||
		cfg.timeout.Milliseconds() != 120000 ||
		cfg.maxAttempts != 4 ||
		cfg.leaseTTL.Milliseconds() != 30000 ||
		cfg.pendingMinIdle.Milliseconds() != 500 {
		t.Fatalf("typed worker config drift: %#v", cfg)
	}
}

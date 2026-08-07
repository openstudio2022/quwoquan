package local_contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/content-service/internal/content/post/application/importer"
)

func TestDataFleetReadRequestAcceptsBoundAuthorAndPublishJobs(t *testing.T) {
	path := filepath.Join(t.TempDir(), "request.json")
	executionID := "20260720--travel-image-publish--cn-zhejiang--canary-902"
	entityRef := "/entity/地点/景区/西湖"
	sourceRevision := "sha256:" + strings.Repeat("a", 64)
	idempotencyKey := executionID + "|" + entityRef + "|image|" + sourceRevision + "|publish"
	request := map[string]any{
		"schema":                    importer.FleetRequestSchema,
		"executionId":               executionID,
		"scaleClass":                "BELOW_M100",
		"executionEnvelopeDigest":   "sha256:" + strings.Repeat("e", 64),
		"requireCommercial":         true,
		"recoverDeadTasks":          false,
		"objectTimeoutMilliseconds": 120000,
		"requiredQuota":             1,
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

	decoded, err := importer.ReadFleetRequest(path)

	if err != nil {
		t.Fatal(err)
	}
	if !decoded.RequireCommercial ||
		decoded.RecoverDeadTasks == nil ||
		*decoded.RecoverDeadTasks ||
		decoded.ObjectTimeout().Milliseconds() != 120000 ||
		decoded.RequiredQuota != 1 ||
		len(decoded.Jobs) != 1 ||
		decoded.Jobs[0].JobID != "job-publish-001" {
		t.Fatalf("fleet request drift: %#v", decoded)
	}
}

func TestDataFleetReadRequestCopiesCampaignBindingAndRejectsJobOverride(t *testing.T) {
	executionID := "20260720--travel-image-m100--cn-zhejiang--scale-902"
	entityRef := "/entity/地点/景区/西湖"
	sourceRevision := "sha256:" + strings.Repeat("a", 64)
	job := map[string]any{
		"entityRef":      entityRef,
		"carrier":        "image",
		"sourceRevision": sourceRevision,
		"idempotencyKey": executionID + "|" + entityRef + "|image|" + sourceRevision + "|publish",
		"jobId":          "job-publish-001",
		"executionId":    executionID,
		"ref":            "image-source-001",
		"stage":          "publish",
		"partitionKey":   "canonical-publish",
	}
	binding := map[string]any{
		"rootExecutionId":             "20260720--travel-homepage-m100--cn-zhejiang--scale-902",
		"campaignRunId":               "campaign-run-902",
		"campaignGeneration":          2,
		"campaignFencingToken":        "sha256:" + strings.Repeat("1", 64),
		"campaignPlanDigest":          "sha256:" + strings.Repeat("2", 64),
		"campaignSourceRevision":      "sha256:" + strings.Repeat("3", 64),
		"campaignSourceDigest":        "sha256:" + strings.Repeat("4", 64),
		"campaignEntityCatalogDigest": "sha256:" + strings.Repeat("5", 64),
	}
	write := func(request map[string]any) string {
		t.Helper()
		payload, err := json.Marshal(request)
		if err != nil {
			t.Fatal(err)
		}
		path := filepath.Join(t.TempDir(), "request.json")
		if err := os.WriteFile(path, payload, 0o600); err != nil {
			t.Fatal(err)
		}
		return path
	}
	request := map[string]any{
		"schema":                    importer.FleetRequestSchema,
		"executionId":               executionID,
		"scaleClass":                "M100_PLUS",
		"executionEnvelopeDigest":   "sha256:" + strings.Repeat("e", 64),
		"requireCommercial":         true,
		"recoverDeadTasks":          false,
		"objectTimeoutMilliseconds": 120000,
		"requiredQuota":             1,
		"campaignBinding":           binding,
		"jobs":                      []map[string]any{job},
	}
	decoded, err := importer.ReadFleetRequest(write(request))
	if err != nil {
		t.Fatal(err)
	}
	if decoded.CampaignBinding == nil ||
		decoded.Jobs[0].Campaign != *decoded.CampaignBinding ||
		decoded.Jobs[0].Campaign.Generation != 2 ||
		decoded.Jobs[0].ExecutionEnvelopeDigest != request["executionEnvelopeDigest"] {
		t.Fatalf("campaign binding was not copied into job: %#v", decoded)
	}

	delete(request, "campaignBinding")
	if _, err := importer.ReadFleetRequest(write(request)); err == nil ||
		!strings.Contains(err.Error(), "requires campaign binding") {
		t.Fatalf("M100 request without campaign binding was not rejected: %v", err)
	}
	request["campaignBinding"] = binding
	job["campaignBinding"] = binding
	if _, err := importer.ReadFleetRequest(write(request)); err == nil ||
		!strings.Contains(err.Error(), "cannot override campaign binding") {
		t.Fatalf("job-level campaign override was not rejected: %v", err)
	}
}

func TestDataFleetReadRequestBoundsRequiredQuotaToFrozenJobs(t *testing.T) {
	executionID := "20260720--travel-image-publish--cn-zhejiang--canary-902"
	entityRef := "/entity/地点/景区/西湖"
	sourceRevision := "sha256:" + strings.Repeat("a", 64)
	job := func(jobID string) map[string]string {
		return map[string]string{
			"entityRef":      entityRef,
			"carrier":        "image",
			"sourceRevision": sourceRevision,
			"idempotencyKey": executionID + "|" + entityRef + "|image|" + sourceRevision + "|publish",
			"jobId":          jobID,
			"executionId":    executionID,
			"ref":            "image-source-001",
			"stage":          "publish",
			"partitionKey":   "canonical-publish",
		}
	}
	writeRequest := func(t *testing.T, quota any) string {
		t.Helper()
		request := map[string]any{
			"schema":                    importer.FleetRequestSchema,
			"executionId":               executionID,
			"scaleClass":                "BELOW_M100",
			"executionEnvelopeDigest":   "sha256:" + strings.Repeat("e", 64),
			"requireCommercial":         true,
			"recoverDeadTasks":          false,
			"objectTimeoutMilliseconds": 120000,
			"jobs":                      []map[string]string{job("job-publish-001"), job("job-publish-002")},
		}
		if quota != nil {
			request["requiredQuota"] = quota
		}
		payload, err := json.Marshal(request)
		if err != nil {
			t.Fatal(err)
		}
		path := filepath.Join(t.TempDir(), "request.json")
		if err := os.WriteFile(path, payload, 0o600); err != nil {
			t.Fatal(err)
		}
		return path
	}
	for _, rejected := range []struct {
		name  string
		quota any
	}{
		{name: "missing", quota: nil},
		{name: "zero", quota: 0},
		{name: "above job count", quota: 3},
	} {
		t.Run(rejected.name, func(t *testing.T) {
			_, err := importer.ReadFleetRequest(writeRequest(t, rejected.quota))
			if err == nil || !strings.Contains(err.Error(), "requiredQuota") {
				t.Fatalf("requiredQuota %v was not rejected: %v", rejected.quota, err)
			}
		})
	}

	decoded, err := importer.ReadFleetRequest(writeRequest(t, 2))
	if err != nil {
		t.Fatal(err)
	}
	if decoded.RequiredQuota != 2 {
		t.Fatalf("requiredQuota=%d want=2", decoded.RequiredQuota)
	}
}

func TestDataFleetReadRequestRejectsUnknownFields(t *testing.T) {
	path := filepath.Join(t.TempDir(), "request.json")
	payload := `{
		"schema":"quwoquan.data_content_fleet_request",
		"executionId":"20260720--travel-image-publish--cn-zhejiang--canary-902",
		"scaleClass":"BELOW_M100",
		"executionEnvelopeDigest":"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
		"requireCommercial":true,
		"recoverDeadTasks":false,
		"objectTimeoutMilliseconds":120000,
		"jobs":[],
		"fallback":"forbidden"
	}`
	if err := os.WriteFile(path, []byte(payload), 0o600); err != nil {
		t.Fatal(err)
	}

	_, err := importer.ReadFleetRequest(path)

	if err == nil || !strings.Contains(err.Error(), "unknown field") {
		t.Fatalf("unknown fleet request field was not rejected: %v", err)
	}
}

func TestDataFleetOutboxFilterScopesDuplicateDetectionToOneStage(t *testing.T) {
	filter, err := importer.DataContentOutboxFilter(importer.FleetRequest{
		ExecutionID: "execution-a",
		Jobs: []reliabletask.DataContentJob{
			{Stage: "publish"},
			{Stage: "publish"},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if filter["taskType"] != reliabletask.DataContentTaskType ||
		filter["payload.executionId"] != "execution-a" ||
		filter["payload.stage"] != "publish" {
		t.Fatalf("outbox filter=%#v", filter)
	}
}

func TestDataFleetOutboxFilterRejectsMixedStages(t *testing.T) {
	_, err := importer.DataContentOutboxFilter(importer.FleetRequest{
		ExecutionID: "execution-a",
		Jobs: []reliabletask.DataContentJob{
			{Stage: "author"},
			{Stage: "publish"},
		},
	})
	if err == nil {
		t.Fatal("mixed stages must be rejected")
	}
}

func TestDataFleetSelectsOnlyFrozenExecutionTasks(t *testing.T) {
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
	request := importer.FleetRequest{
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

	selected, err := importer.SelectExecutionTasks(tasks, request)

	if err != nil {
		t.Fatal(err)
	}
	if len(selected) != 2 ||
		selected[0].TaskID != "publish-putuo" ||
		selected[1].TaskID != "publish-dongqian" {
		t.Fatalf("request task selection drift: %#v", selected)
	}
}

func TestDataFleetRejectsAmbiguousRemoteIdentity(t *testing.T) {
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

	_, err = importer.SelectExecutionTasks(
		[]reliabletask.ReliableAsyncTask{task, task},
		importer.FleetRequest{ExecutionID: job.ExecutionID, Jobs: []reliabletask.DataContentJob{job}},
	)

	if err == nil || !strings.Contains(err.Error(), "ambiguous") {
		t.Fatalf("ambiguous remote task was accepted: %v", err)
	}
}

func TestDataFleetConfigFailsClosedAndLoadsTypedValues(t *testing.T) {
	_, err := importer.LoadFleetConfig(runtimeconfig.MapRuntimeConfigProvider{})
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
			"QWQ_DATA_FLEET_BATCH_TIMEOUT_MS":    "120000",
			"QWQ_DATA_FLEET_MAX_ATTEMPTS":        "4",
			"QWQ_DATA_FLEET_LEASE_TTL_MS":        "30000",
			"QWQ_DATA_FLEET_PENDING_MIN_IDLE_MS": "500",
		},
	}

	cfg, err := importer.LoadFleetConfig(provider)

	if err != nil {
		t.Fatal(err)
	}
	if cfg.Workers != 16 ||
		cfg.BatchTimeout.Milliseconds() != 120000 ||
		cfg.MaxAttempts != 4 ||
		cfg.LeaseTTL.Milliseconds() != 30000 ||
		cfg.PendingMinIdle.Milliseconds() != 500 {
		t.Fatalf("typed worker config drift: %#v", cfg)
	}
}

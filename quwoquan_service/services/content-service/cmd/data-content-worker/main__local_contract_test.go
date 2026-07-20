package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
)

func TestReadFleetRequestAcceptsBoundAuthorAndPublishJobs(t *testing.T) {
	path := filepath.Join(t.TempDir(), "request.json")
	request := map[string]any{
		"schema":            fleetRequestSchema,
		"executionId":       "20260720--travel-image-publish--cn-zhejiang--canary-902",
		"requireCommercial": true,
		"jobs": []map[string]string{
			{
				"entityRef":      "/entity/地点/景区/西湖",
				"carrier":        "image",
				"sourceRevision": "sha256:" + strings.Repeat("a", 64),
				"jobId":          "job-publish-001",
				"executionId":    "20260720--travel-image-publish--cn-zhejiang--canary-902",
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
			"QWQ_DATA_FLEET_CLI":                 "/workspace/quwoquan_data/scripts/cli.py",
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

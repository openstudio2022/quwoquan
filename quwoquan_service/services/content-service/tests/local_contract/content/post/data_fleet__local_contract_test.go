package local_contract

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/content-service/internal/content/post/application/importer"
)

func testPartitionKey(carrier string, objectRef string, count int) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(carrier) + strings.TrimSpace(objectRef)))
	remainder := 0
	for _, value := range digest {
		remainder = (remainder*256 + int(value)) % count
	}
	return strconv.Itoa(remainder)
}

func testCheckpointPolicy() map[string]any {
	return map[string]any{
		"mode":                  "partition_watermark",
		"scope":                 "execution_stage_partition",
		"cursor":                "last_succeeded_job_id",
		"resume":                "strictly_after_cursor",
		"store":                 "MongoStore",
		"fencing":               "execution_job_set_digest",
		"everyFinalizedObjects": 100,
		"everySeconds":          900,
		"triggerMode":           "first_reached",
	}
}

func bindFrozenJobSet(job reliabletask.DataContentJob) reliabletask.DataContentJob {
	if job.MaxAttempts == 0 {
		job.MaxAttempts = 3
	}
	job.JobSetEnvelopeDigest = "sha256:" + strings.Repeat("d", 64)
	job.JobSetDigest = "sha256:" + strings.Repeat("c", 64)
	job.ActualTaskDigest = job.JobSetDigest
	return job
}

func bindFleetRequestTaskDigests(t *testing.T, request map[string]any) {
	t.Helper()
	payload, err := json.Marshal(request["jobs"])
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(payload)
	value := "sha256:" + hex.EncodeToString(digest[:])
	request["jobSetDigest"] = value
	request["actualTaskDigest"] = value
}

func TestDataFleetReadRequestAcceptsBoundAuthorAndPublishJobs(t *testing.T) {
	path := filepath.Join(t.TempDir(), "request.json")
	executionID := "20260720--travel-image-publish--cn-zhejiang--canary-902"
	entityRef := "/entity/地点/景区/西湖"
	sourceRevision := "sha256:" + strings.Repeat("a", 64)
	idempotencyKey := executionID + "|" + entityRef + "|image|" + sourceRevision + "|publish"
	request := map[string]any{
		"schema":                    importer.FleetRequestSchema,
		"executionId":               executionID,
		"campaignScale":             "M1",
		"scaleClass":                "BELOW_M100",
		"executionEnvelopeDigest":   "sha256:" + strings.Repeat("e", 64),
		"jobSetEnvelopeDigest":      "sha256:" + strings.Repeat("d", 64),
		"jobSetDigest":              "sha256:" + strings.Repeat("c", 64),
		"requiredWorkers":           1,
		"partitionCount":            16,
		"partitionAlgorithm":        "sha256_carrier_object_ref_mod_v1",
		"checkpointPolicy":          testCheckpointPolicy(),
		"recoverDeadTasks":          false,
		"objectTimeoutMilliseconds": 120000,
		"globalRequiredQuota":       1,
		"requiredQuota":             1,
		"jobs": []map[string]any{
			{
				"entityRef":      entityRef,
				"carrier":        "image",
				"sourceRevision": sourceRevision,
				"idempotencyKey": idempotencyKey,
				"jobId":          "job-publish-001",
				"executionId":    executionID,
				"ref":            "image-source-001",
				"stage":          "publish",
				"partitionKey":   testPartitionKey("image", "image-source-001", 16),
				"maxAttempts":    3,
			},
		},
	}
	bindFleetRequestTaskDigests(t, request)
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
	if decoded.RecoverDeadTasks == nil ||
		*decoded.RecoverDeadTasks ||
		decoded.ObjectTimeout().Milliseconds() != 120000 ||
		decoded.RequiredQuota != 1 ||
		len(decoded.Jobs) != 1 ||
		decoded.Jobs[0].JobID != "job-publish-001" ||
		decoded.Jobs[0].JobSetEnvelopeDigest != request["jobSetEnvelopeDigest"] ||
		decoded.Jobs[0].JobSetDigest != request["jobSetDigest"] {
		t.Fatalf("fleet request drift: %#v", decoded)
	}
}

func TestDataFleetReadRequestAcceptsOnlyExactHostPartitionSlice(t *testing.T) {
	executionID := "20260720--travel-image-m1000--cn-zhejiang--scale-990"
	entityRef := "/entity/地点/景区/西湖"
	sourceRevision := "sha256:" + strings.Repeat("a", 64)
	partition := testPartitionKey("image", "image-source-host-001", 16)
	job := map[string]any{
		"entityRef": entityRef, "carrier": "image", "sourceRevision": sourceRevision,
		"idempotencyKey": executionID + "|" + entityRef + "|image|" + sourceRevision + "|author",
		"jobId":          "job-author-host-001", "executionId": executionID,
		"ref": "image-source-host-001", "stage": "author", "partitionKey": partition,
		"maxAttempts": 3,
	}
	request := map[string]any{
		"schema": importer.FleetRequestSchema, "executionId": executionID,
		"campaignScale": "M1000", "scaleClass": "M100_PLUS",
		"executionEnvelopeDigest": "sha256:" + strings.Repeat("e", 64),
		"jobSetEnvelopeDigest":    "sha256:" + strings.Repeat("d", 64),
		"jobSetDigest":            "sha256:" + strings.Repeat("c", 64),
		"requiredWorkers":         1, "partitionCount": 16,
		"partitionAlgorithm": "sha256_carrier_object_ref_mod_v1",
		"checkpointPolicy": testCheckpointPolicy(),
		"recoverDeadTasks": false, "objectTimeoutMilliseconds": 120000,
		"globalRequiredQuota": 1, "requiredQuota": 1,
		"campaignBinding": map[string]any{
			"rootExecutionId": "20260720--travel-homepage-m1000--cn-zhejiang--scale-990",
			"campaignRunId":   "campaign-run-990", "campaignGeneration": 1,
			"campaignFencingToken":        "sha256:" + strings.Repeat("1", 64),
			"campaignPlanDigest":          "sha256:" + strings.Repeat("2", 64),
			"campaignSourceRevision":      "sha256:" + strings.Repeat("3", 64),
			"campaignSourceDigest":        "sha256:" + strings.Repeat("4", 64),
			"campaignEntityCatalogDigest": "sha256:" + strings.Repeat("5", 64),
		},
		"workerHostBinding": map[string]any{
			"hostSetId": "m1000-workers", "generation": 2,
			"fencingToken":  "sha256:" + strings.Repeat("6", 64),
			"hostSetDigest": "sha256:" + strings.Repeat("7", 64),
			"transportBinding": map[string]any{
				"mongoTransportDigest": "sha256:" + strings.Repeat("8", 64),
				"redisTransportDigest": "sha256:" + strings.Repeat("9", 64),
			},
			"hostScopeId": "worker-alpha", "workerCount": 1,
			"partitionKeys":            []string{partition},
			"runtimeProfileDigest":     "sha256:" + strings.Repeat("a", 64),
			"executorBundleRef":        "data/executor-bundles/worker",
			"executorBundleDigest":     "sha256:" + strings.Repeat("b", 64),
			"executorBundleFileSha256": "sha256:" + strings.Repeat("c", 64),
			"sourceCapsuleId":          "source-snapshot-m1000",
			"sourceCapsuleDigest":      "sha256:" + strings.Repeat("d", 64),
		},
		"jobs": []map[string]any{job},
	}
	bindFleetRequestTaskDigests(t, request)
	request["jobSetDigest"] = "sha256:" + strings.Repeat("f", 64)
	write := func() string {
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
	decoded, err := importer.ReadFleetRequest(write())
	if err != nil {
		t.Fatal(err)
	}
	if decoded.WorkerHostBinding == nil || decoded.WorkerHostBinding.HostScopeID != "worker-alpha" || decoded.ActualTaskDigest == decoded.JobSetDigest {
		t.Fatalf("host-specific fleet binding drift: %#v", decoded)
	}
	request["workerHostBinding"].(map[string]any)["partitionKeys"] = []string{"15"}
	if _, err := importer.ReadFleetRequest(write()); err == nil || !strings.Contains(err.Error(), "not assigned") {
		t.Fatalf("unassigned partition was not rejected: %v", err)
	}
}

func TestDataFleetReadRequestCopiesCampaignBindingAndAcceptsStandaloneDispatch(t *testing.T) {
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
		"partitionKey":   testPartitionKey("image", "image-source-001", 16),
		"maxAttempts":    3,
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
		bindFleetRequestTaskDigests(t, request)
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
		"campaignScale":             "M100",
		"scaleClass":                "M100_PLUS",
		"executionEnvelopeDigest":   "sha256:" + strings.Repeat("e", 64),
		"jobSetEnvelopeDigest":      "sha256:" + strings.Repeat("d", 64),
		"jobSetDigest":              "sha256:" + strings.Repeat("c", 64),
		"requiredWorkers":           1,
		"partitionCount":            16,
		"partitionAlgorithm":        "sha256_carrier_object_ref_mod_v1",
		"checkpointPolicy":          testCheckpointPolicy(),
		"recoverDeadTasks":          false,
		"objectTimeoutMilliseconds": 120000,
		"globalRequiredQuota":       1,
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
		decoded.Jobs[0].ExecutionEnvelopeDigest != request["executionEnvelopeDigest"] ||
		decoded.Jobs[0].JobSetEnvelopeDigest != request["jobSetEnvelopeDigest"] ||
		decoded.Jobs[0].JobSetDigest != request["jobSetDigest"] {
		t.Fatalf("campaign binding was not copied into job: %#v", decoded)
	}

	delete(request, "campaignBinding")
	standalone, err := importer.ReadFleetRequest(write(request))
	if err != nil {
		t.Fatalf("standalone M100 dispatch was rejected: %v", err)
	}
	if standalone.CampaignBinding != nil || !standalone.Jobs[0].Campaign.IsEmpty() {
		t.Fatalf("standalone dispatch invented a campaign binding: %#v", standalone)
	}
	request["campaignBinding"] = binding
	job["campaignBinding"] = binding
	if _, err := importer.ReadFleetRequest(write(request)); err == nil ||
		!strings.Contains(err.Error(), "cannot override campaign binding") {
		t.Fatalf("job-level campaign override was not rejected: %v", err)
	}
}

func TestDataFleetReadRequestAcceptsM10000AndRejectsPartitionDrift(t *testing.T) {
	executionID := "20260720--travel-video-m10000--china--scale-903"
	jobs := fleetWorkUnits(executionID, "video", "author", 129, 256)
	job := jobs[0]
	request := map[string]any{
		"schema":                  importer.FleetRequestSchema,
		"executionId":             executionID,
		"campaignScale":           "M10000",
		"scaleClass":              "M10000_PLUS",
		"executionEnvelopeDigest": "sha256:" + strings.Repeat("e", 64),
		"jobSetEnvelopeDigest":    "sha256:" + strings.Repeat("d", 64),
		"jobSetDigest":            "sha256:" + strings.Repeat("c", 64),
		// requiredWorkers is deliberately unrelated to the partition topology:
		// partitions isolate queue state, they are not worker capacity.
		"requiredWorkers":           1000,
		"partitionCount":            256,
		"partitionAlgorithm":        "sha256_carrier_object_ref_mod_v1",
		"checkpointPolicy":          testCheckpointPolicy(),
		"recoverDeadTasks":          false,
		"objectTimeoutMilliseconds": 120000,
		"globalRequiredQuota":       129,
		"requiredQuota":             129,
		"campaignBinding": map[string]any{
			"rootExecutionId":             "20260720--travel-homepage-m10000--china--scale-903",
			"campaignRunId":               "campaign-run-903",
			"campaignGeneration":          3,
			"campaignFencingToken":        "sha256:" + strings.Repeat("1", 64),
			"campaignPlanDigest":          "sha256:" + strings.Repeat("2", 64),
			"campaignSourceRevision":      "sha256:" + strings.Repeat("3", 64),
			"campaignSourceDigest":        "sha256:" + strings.Repeat("4", 64),
			"campaignEntityCatalogDigest": "sha256:" + strings.Repeat("5", 64),
		},
		"jobs": jobs,
	}
	write := func() string {
		t.Helper()
		bindFleetRequestTaskDigests(t, request)
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

	decoded, err := importer.ReadFleetRequest(write())
	if err != nil {
		t.Fatal(err)
	}
	if decoded.ScaleClass != "M10000_PLUS" || decoded.PartitionCount != 256 ||
		decoded.RequiredWorkers != 1000 || len(decoded.Jobs) != 129 {
		t.Fatalf("M10000 partition contract drift: %#v", decoded)
	}

	request["partitionCount"] = 128
	if _, err := importer.ReadFleetRequest(write()); err == nil ||
		!strings.Contains(err.Error(), "partitionCount") {
		t.Fatalf("partitionCount drift was not rejected: %v", err)
	}
	request["partitionCount"] = 256
	expectedKey, _ := strconv.Atoi(job["partitionKey"].(string))
	job["partitionKey"] = strconv.Itoa((expectedKey + 1) % 256)
	if _, err := importer.ReadFleetRequest(write()); err == nil ||
		!strings.Contains(err.Error(), "partitionKey") {
		t.Fatalf("partitionKey drift was not rejected: %v", err)
	}
}

// fleetWorkUnits builds jobCount frozen work units ordered by jobId, which is
// the order DataContentTaskDigest hashes them in.
func fleetWorkUnits(
	executionID string,
	carrier string,
	stage string,
	jobCount int,
	partitionCount int,
) []map[string]any {
	sourceRevision := "sha256:" + strings.Repeat("a", 64)
	jobs := make([]map[string]any, 0, jobCount)
	for index := 0; index < jobCount; index++ {
		suffix := fmt.Sprintf("%04d", index)
		entityRef := "/entity/地点/景区/西湖-" + suffix
		objectRef := "west-lake-" + suffix
		jobs = append(jobs, map[string]any{
			"entityRef":      entityRef,
			"carrier":        carrier,
			"sourceRevision": sourceRevision,
			"idempotencyKey": executionID + "|" + entityRef + "|" + carrier +
				"|" + sourceRevision + "|" + stage,
			"jobId":        "job-" + stage + "-" + suffix,
			"executionId":  executionID,
			"ref":          objectRef,
			"stage":        stage,
			"partitionKey": testPartitionKey(carrier, objectRef, partitionCount),
			"maxAttempts":  3,
		})
	}
	return jobs
}

// declaredPartitionBand is one governed band of the partition topology declared
// by quwoquan_data/schema/execution/data_content_fleet_request.schema.json.
// maxItems == 0 means the band is unbounded above.
type declaredPartitionBand struct {
	minItems       int
	maxItems       int
	partitionCount int
}

func fleetContractRepoRoot(t *testing.T) string {
	t.Helper()
	directory, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(fleetRequestSchemaPath(directory)); err == nil {
			return directory
		}
		parent := filepath.Dir(directory)
		if parent == directory {
			t.Fatal("data content fleet request schema not found above test directory")
		}
		directory = parent
	}
}

func fleetRequestSchemaPath(repoRoot string) string {
	return filepath.Join(
		repoRoot, "quwoquan_data", "schema", "execution",
		"data_content_fleet_request.schema.json",
	)
}

// declaredPartitionBands reads the governed topology straight from the declared
// contract so this side cannot drift away from it silently.
func declaredPartitionBands(t *testing.T) []declaredPartitionBand {
	t.Helper()
	raw, err := os.ReadFile(fleetRequestSchemaPath(fleetContractRepoRoot(t)))
	if err != nil {
		t.Fatal(err)
	}
	var contract struct {
		AllOf []struct {
			If struct {
				Properties struct {
					Jobs struct {
						MinItems int `json:"minItems"`
						MaxItems int `json:"maxItems"`
					} `json:"jobs"`
				} `json:"properties"`
			} `json:"if"`
			Then struct {
				Properties struct {
					PartitionCount struct {
						Const int `json:"const"`
					} `json:"partitionCount"`
				} `json:"properties"`
			} `json:"then"`
		} `json:"allOf"`
	}
	if err := json.Unmarshal(raw, &contract); err != nil {
		t.Fatal(err)
	}
	bands := make([]declaredPartitionBand, 0, len(contract.AllOf))
	for _, row := range contract.AllOf {
		band := declaredPartitionBand{
			minItems:       row.If.Properties.Jobs.MinItems,
			maxItems:       row.If.Properties.Jobs.MaxItems,
			partitionCount: row.Then.Properties.PartitionCount.Const,
		}
		if band.minItems < 1 || band.partitionCount < 1 {
			t.Fatalf("declared partition band is incomplete: %#v", row)
		}
		bands = append(bands, band)
	}
	if len(bands) == 0 {
		t.Fatal("declared partition topology bands are missing from the contract")
	}
	return bands
}

// writeFleetPartitionRequest freezes one dispatch whose approved quota, worker
// count and work-unit count all coincide, which is the production shape of a
// content execution: requiredWorkers carries the quota and must never reach the
// partition topology.
func writeFleetPartitionRequest(t *testing.T, jobCount int, partitionCount int) string {
	t.Helper()
	executionID := "20260720--travel-image-m1000--cn-zhejiang--scale-990"
	request := map[string]any{
		"schema":                    importer.FleetRequestSchema,
		"executionId":               executionID,
		"campaignScale":             "M1000",
		"scaleClass":                "M100_PLUS",
		"executionEnvelopeDigest":   "sha256:" + strings.Repeat("e", 64),
		"jobSetEnvelopeDigest":      "sha256:" + strings.Repeat("d", 64),
		"jobSetDigest":              "sha256:" + strings.Repeat("c", 64),
		"requiredWorkers":           jobCount,
		"partitionCount":            partitionCount,
		"partitionAlgorithm":        "sha256_carrier_object_ref_mod_v1",
		"checkpointPolicy":          testCheckpointPolicy(),
		"recoverDeadTasks":          false,
		"objectTimeoutMilliseconds": 120000,
		"globalRequiredQuota":       jobCount,
		"requiredQuota":             jobCount,
		"jobs": fleetWorkUnits(
			executionID, "image", "author", jobCount, partitionCount,
		),
	}
	bindFleetRequestTaskDigests(t, request)
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

// declaredPartitionCount resolves one work-unit count through the declared
// bands so tests never restate the derivation themselves.
func declaredPartitionCount(t *testing.T, workUnitCount int) int {
	t.Helper()
	for _, band := range declaredPartitionBands(t) {
		if workUnitCount < band.minItems {
			continue
		}
		if band.maxItems == 0 || workUnitCount <= band.maxItems {
			return band.partitionCount
		}
	}
	t.Fatalf("no declared partition band covers %d work units", workUnitCount)
	return 0
}

// TestDataFleetPartitionCountFollowsDeclaredTopologyBands pins this side to the
// declared contract: partitionCount is derived from the frozen work-unit count
// carried by jobs, never from requiredWorkers.
func TestDataFleetPartitionCountFollowsDeclaredTopologyBands(t *testing.T) {
	governed := []int{16, 32, 64, 128, 256}
	for _, band := range declaredPartitionBands(t) {
		jobCounts := []int{band.minItems}
		if band.maxItems > band.minItems {
			jobCounts = append(jobCounts, band.maxItems)
		}
		for _, jobCount := range jobCounts {
			t.Run(fmt.Sprintf("jobs=%d", jobCount), func(t *testing.T) {
				decoded, err := importer.ReadFleetRequest(
					writeFleetPartitionRequest(t, jobCount, band.partitionCount),
				)
				if err != nil {
					t.Fatalf(
						"declared partitionCount=%d for %d work units was rejected: %v",
						band.partitionCount, jobCount, err,
					)
				}
				if decoded.PartitionCount != band.partitionCount ||
					len(decoded.Jobs) != jobCount {
					t.Fatalf("declared partition band drift: %#v", decoded)
				}
				for _, other := range governed {
					if other == band.partitionCount {
						continue
					}
					_, err := importer.ReadFleetRequest(
						writeFleetPartitionRequest(t, jobCount, other),
					)
					if err == nil || !strings.Contains(err.Error(), "partitionCount") {
						t.Fatalf(
							"partitionCount=%d for %d work units was not rejected: %v",
							other, jobCount, err,
						)
					}
				}
			})
		}
	}
}

// TestDataFleetAcceptsPlannedQuotaTiers covers the exact work-unit counts the
// G1/G2/G3 rollout dispatches, including the oversampled first round and the
// smaller quota-pursuit replenishment rounds that refreeze a job set from only
// the newly added work units.
func TestDataFleetAcceptsPlannedQuotaTiers(t *testing.T) {
	for _, tier := range []struct {
		name     string
		jobCount int
	}{
		{name: "G1_quota10", jobCount: 10},
		{name: "G1_quota10_oversampled", jobCount: 18},
		{name: "G2_video_lane", jobCount: 10},
		{name: "G2_quota100", jobCount: 100},
		{name: "G2_quota100_oversampled", jobCount: 180},
		{name: "G3_quota1000", jobCount: 1000},
		{name: "replenishment_round", jobCount: 3},
		{name: "replenishment_round_tail", jobCount: 7},
	} {
		t.Run(tier.name, func(t *testing.T) {
			expected := declaredPartitionCount(t, tier.jobCount)
			decoded, err := importer.ReadFleetRequest(
				writeFleetPartitionRequest(t, tier.jobCount, expected),
			)
			if err != nil {
				t.Fatalf(
					"quota tier with %d work units was rejected: %v",
					tier.jobCount, err,
				)
			}
			if decoded.PartitionCount != expected ||
				decoded.RequiredWorkers != tier.jobCount ||
				len(decoded.Jobs) != tier.jobCount {
				t.Fatalf("quota tier partition contract drift: %#v", decoded)
			}
		})
	}
}

func TestDataFleetReadRequestBoundsRequiredQuotaToFrozenJobs(t *testing.T) {
	executionID := "20260720--travel-image-publish--cn-zhejiang--canary-902"
	entityRef := "/entity/地点/景区/西湖"
	sourceRevision := "sha256:" + strings.Repeat("a", 64)
	job := func(jobID string) map[string]any {
		return map[string]any{
			"entityRef":      entityRef,
			"carrier":        "image",
			"sourceRevision": sourceRevision,
			"idempotencyKey": executionID + "|" + entityRef + "|image|" + sourceRevision + "|publish",
			"jobId":          jobID,
			"executionId":    executionID,
			"ref":            "image-source-001",
			"stage":          "publish",
			"partitionKey":   testPartitionKey("image", "image-source-001", 16),
			"maxAttempts":    3,
		}
	}
	writeRequest := func(t *testing.T, quota any) string {
		t.Helper()
		request := map[string]any{
			"schema":                    importer.FleetRequestSchema,
			"executionId":               executionID,
			"campaignScale":             "M1",
			"scaleClass":                "BELOW_M100",
			"executionEnvelopeDigest":   "sha256:" + strings.Repeat("e", 64),
			"jobSetEnvelopeDigest":      "sha256:" + strings.Repeat("d", 64),
			"jobSetDigest":              "sha256:" + strings.Repeat("c", 64),
			"requiredWorkers":           1,
			"partitionCount":            16,
			"partitionAlgorithm":        "sha256_carrier_object_ref_mod_v1",
			"checkpointPolicy":          testCheckpointPolicy(),
			"recoverDeadTasks":          false,
			"objectTimeoutMilliseconds": 120000,
			"globalRequiredQuota":       2,
			"jobs":                      []map[string]any{job("job-publish-001"), job("job-publish-002")},
		}
		if quota != nil {
			request["requiredQuota"] = quota
		}
		bindFleetRequestTaskDigests(t, request)
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
		return bindFrozenJobSet(job)
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
				"idempotencyKey":       job.IdempotencyKey,
				"jobSetEnvelopeDigest": job.JobSetEnvelopeDigest,
				"jobSetDigest":         job.JobSetDigest,
				"actualTaskDigest":     job.ActualTaskDigest,
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

func TestDataFleetSelectsCurrentRevisionWhenStableJobIDHasSupersededRemoteTask(t *testing.T) {
	executionID := "20260720--travel-article-publish--cn-zhejiang--canary-903"
	boundJob := func(sourceRevision string) reliabletask.DataContentJob {
		job := reliabletask.DataContentJob{
			EntityRef:      "/entity/地点/景区/普陀山",
			Carrier:        "article",
			SourceRevision: sourceRevision,
			JobID:          "publish-putuo",
			ExecutionID:    executionID,
			Ref:            "/entity/地点/景区/普陀山",
			Stage:          "publish",
			PartitionKey:   "canonical-publish",
		}
		key, err := job.ExpectedIdempotencyKey()
		if err != nil {
			t.Fatal(err)
		}
		job.IdempotencyKey = key
		return bindFrozenJobSet(job)
	}
	toTask := func(taskID string, job reliabletask.DataContentJob) reliabletask.ReliableAsyncTask {
		return reliabletask.ReliableAsyncTask{
			TaskID:         taskID,
			IdempotencyKey: job.IdempotencyKey,
			DedupeKey:      job.IdempotencyKey,
			PartitionKey:   job.PartitionKey,
			Payload: map[string]string{
				"jobId": job.JobID, "executionId": job.ExecutionID,
				"idempotencyKey":       job.IdempotencyKey,
				"jobSetEnvelopeDigest": job.JobSetEnvelopeDigest,
				"jobSetDigest":         job.JobSetDigest,
				"actualTaskDigest":     job.ActualTaskDigest,
			},
		}
	}
	superseded := boundJob("sha256:" + strings.Repeat("d", 64))
	current := boundJob("sha256:" + strings.Repeat("e", 64))

	selected, err := importer.SelectExecutionTasks(
		[]reliabletask.ReliableAsyncTask{
			toTask("publish-putuo-superseded", superseded),
			toTask("publish-putuo-current", current),
		},
		importer.FleetRequest{
			ExecutionID: executionID,
			Jobs:        []reliabletask.DataContentJob{current},
		},
	)

	if err != nil {
		t.Fatal(err)
	}
	if len(selected) != 1 || selected[0].TaskID != "publish-putuo-current" {
		t.Fatalf("current source revision was not selected: %#v", selected)
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
	job = bindFrozenJobSet(job)
	task := reliabletask.ReliableAsyncTask{
		IdempotencyKey: key,
		DedupeKey:      key,
		PartitionKey:   job.PartitionKey,
		Payload: map[string]string{
			"jobId": job.JobID, "executionId": job.ExecutionID,
			"idempotencyKey":       key,
			"jobSetEnvelopeDigest": job.JobSetEnvelopeDigest,
			"jobSetDigest":         job.JobSetDigest,
			"actualTaskDigest":     job.ActualTaskDigest,
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
		cfg.LeaseTTL.Milliseconds() != 30000 ||
		cfg.PendingMinIdle.Milliseconds() != 500 {
		t.Fatalf("typed worker config drift: %#v", cfg)
	}
}

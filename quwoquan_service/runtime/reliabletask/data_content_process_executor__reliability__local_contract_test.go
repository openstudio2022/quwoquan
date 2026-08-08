package reliabletask

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"
	"testing"
	"time"
)

const (
	processJobSetEnvelopeDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	processJobSetDigest         = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
	processActualTaskDigest     = "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
)

func TestMain(m *testing.M) {
	if mode := os.Getenv("QWQ_DATA_PROCESS_HELPER"); mode != "" {
		os.Exit(runDataContentProcessExecutorHelper(mode))
	}
	os.Exit(m.Run())
}

func TestDataContentProcessExecutorRunsTypedWorkerBoundary(t *testing.T) {
	item := DataContentWorkItem{
		RuntimeTaskID:        "runtime-task-1",
		LeaseToken:           "must-not-cross-process-boundary",
		JobID:                "job-1",
		ExecutionID:          "20260711--travel-article-cold-start--cn-test--canary-001",
		Ref:                  "posts/article/真实文章",
		Stage:                "author",
		PartitionKey:         "entity/真实地点",
		EntityRef:            "entity/真实地点",
		Carrier:              "article",
		SourceRevision:       "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		IdempotencyKey:       "entity/真实地点|article|sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|author",
		JobSetEnvelopeDigest: processJobSetEnvelopeDigest,
		JobSetDigest:         processJobSetDigest,
		ActualTaskDigest:     processActualTaskDigest,
	}
	result, err := (DataContentProcessExecutor{
		Command:     []string{os.Args[0], "-test.run=^TestDataContentProcessExecutorHelper$"},
		Environment: append(os.Environ(), "QWQ_DATA_PROCESS_HELPER=valid"),
	}).ExecuteDataContentObject(context.Background(), item)
	if err != nil {
		t.Fatal(err)
	}
	if result.ExecutionID != item.ExecutionID ||
		result.JobID != item.JobID ||
		result.AcceptanceClass != DataContentAcceptanceStageCompleted {
		t.Fatalf("typed process result drift: %#v", result)
	}
}

func TestDataContentProcessExecutorRejectsMultipleJSONValues(t *testing.T) {
	_, err := (DataContentProcessExecutor{
		Command:     []string{os.Args[0], "-test.run=^TestDataContentProcessExecutorHelper$"},
		Environment: append(os.Environ(), "QWQ_DATA_PROCESS_HELPER=multiple"),
	}).ExecuteDataContentObject(context.Background(), DataContentWorkItem{})
	if err == nil || !strings.Contains(err.Error(), "multiple values") {
		t.Fatalf("multiple worker responses were not rejected: %v", err)
	}
}

func TestDataContentProcessExecutorIncludesOnlyProtocolWorkerDiagnostic(t *testing.T) {
	_, err := (DataContentProcessExecutor{
		Command:     []string{os.Args[0], "-test.run=^TestDataContentProcessExecutorHelper$"},
		Environment: append(os.Environ(), "QWQ_DATA_PROCESS_HELPER=failed"),
	}).ExecuteDataContentObject(context.Background(), DataContentWorkItem{})
	if err == nil {
		t.Fatal("expected worker failure")
	}
	message := err.Error()
	if !strings.Contains(
		message,
		"[data-content-worker] ValueError: typed failure",
	) {
		t.Fatalf("protocol diagnostic missing from error: %q", message)
	}
	if strings.Contains(message, "untrusted diagnostic") {
		t.Fatalf("untrusted stderr leaked into error: %q", message)
	}
}

func TestDataContentProcessExecutorHelper(t *testing.T) {
	t.Helper()
}

func runDataContentProcessExecutorHelper(mode string) int {
	input, err := io.ReadAll(os.Stdin)
	if err != nil {
		return 2
	}
	var request map[string]any
	if err := json.Unmarshal(input, &request); err != nil {
		return 3
	}
	item, ok := request["item"].(map[string]any)
	if !ok {
		return 4
	}
	if _, leaked := item["leaseToken"]; leaked {
		return 5
	}
	if mode == "valid" &&
		(fmt.Sprint(item["jobSetEnvelopeDigest"]) != processJobSetEnvelopeDigest ||
			fmt.Sprint(item["jobSetDigest"]) != processJobSetDigest ||
			fmt.Sprint(item["actualTaskDigest"]) != processActualTaskDigest) {
		return 8
	}
	response := map[string]any{
		"schema": "quwoquan.data_content_worker_response",
		"result": map[string]any{
			"executionId":       fmt.Sprint(item["executionId"]),
			"jobId":             fmt.Sprint(item["jobId"]),
			"resultEnvelopeRef": "evidence/agent-result.json",
			"acceptanceClass":   DataContentAcceptanceStageCompleted,
			"completedAt":       time.Now().UTC().Format(time.RFC3339Nano),
		},
	}
	data, err := json.Marshal(response)
	if err != nil {
		return 6
	}
	_, _ = os.Stdout.Write(append(data, '\n'))
	if mode == "multiple" {
		_, _ = os.Stdout.Write(append(data, '\n'))
	}
	if mode == "failed" {
		_, _ = fmt.Fprintln(os.Stderr, "untrusted diagnostic")
		_, _ = fmt.Fprintln(
			os.Stderr,
			"[data-content-worker] ValueError: typed failure",
		)
		return 7
	}
	return 0
}

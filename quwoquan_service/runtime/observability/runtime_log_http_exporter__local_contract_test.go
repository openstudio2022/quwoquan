package runtimeobservability

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"
)

func TestHTTPRuntimeLogExporterRejectsPartialConfiguration(t *testing.T) {
	if _, err := NewHTTPRuntimeLogFieldExporter("https://logs.example", "", t.TempDir()); err == nil {
		t.Fatal("partial runtime log exporter configuration must fail closed")
	}
	if _, err := NewHTTPRuntimeLogFieldExporter("", "", ""); err != nil {
		t.Fatalf("all-empty local configuration should disable exporter: %v", err)
	}
}

func TestHTTPRuntimeLogExporterDeliversSpooledBatch(t *testing.T) {
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests.Add(1)
		if r.Header.Get("X-Runtime-Log-Ingest-Token") != "machine-token" {
			t.Errorf("missing machine token")
		}
		if len(r.Header.Get("Idempotency-Key")) != 64 {
			t.Errorf("idempotency digest is invalid")
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	exporter := newTestHTTPRuntimeLogExporter(t, server.URL)
	exporter.Export(testRuntimeLogBatch("ERROR"))
	if err := exporter.FlushOnce(context.Background()); err != nil {
		t.Fatalf("flush: %v", err)
	}
	files, _ := runtimeLogJSONFiles(exporter.spoolDir)
	if len(files) != 0 || requests.Load() != 1 {
		t.Fatalf("delivered batch must leave spool: files=%v requests=%d", files, requests.Load())
	}
}

func TestHTTPRuntimeLogExporterRetriesTransientFailureAcrossRestart(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	spoolDir := t.TempDir()
	exporter := newTestHTTPRuntimeLogExporterAt(t, server.URL, spoolDir)
	exporter.Export(testRuntimeLogBatch("WARN"))
	if err := exporter.FlushOnce(context.Background()); err != nil {
		t.Fatalf("first flush: %v", err)
	}
	server.Close()

	files, _ := runtimeLogJSONFiles(spoolDir)
	if len(files) != 1 {
		t.Fatalf("transient failure must preserve one spool file: %v", files)
	}
	batch, err := readRuntimeLogBatch(files[0])
	if err != nil || batch.Attempts != 1 || !batch.NextAttemptAt.After(time.Now().UTC()) {
		t.Fatalf("retry metadata missing: batch=%+v err=%v", batch, err)
	}

	var requests atomic.Int32
	recovered := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		requests.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	defer recovered.Close()
	batch.NextAttemptAt = time.Now().UTC().Add(-time.Second)
	if err := writeRuntimeLogBatchAtomic(files[0], batch); err != nil {
		t.Fatalf("prepare restart retry: %v", err)
	}
	restarted := newTestHTTPRuntimeLogExporterAt(t, recovered.URL, spoolDir)
	if err := restarted.FlushOnce(context.Background()); err != nil {
		t.Fatalf("restart flush: %v", err)
	}
	files, _ = runtimeLogJSONFiles(spoolDir)
	if len(files) != 0 || requests.Load() != 1 {
		t.Fatalf("restarted exporter must drain spool: files=%v requests=%d", files, requests.Load())
	}
}

func TestHTTPRuntimeLogExporterDeadLettersPermanentAndExpiredBatches(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnprocessableEntity)
	}))
	defer server.Close()
	exporter := newTestHTTPRuntimeLogExporter(t, server.URL)
	exporter.Export(testRuntimeLogBatch("ERROR"))
	if err := exporter.FlushOnce(context.Background()); err != nil {
		t.Fatalf("permanent flush: %v", err)
	}
	pending, _ := runtimeLogJSONFiles(exporter.spoolDir)
	dead, _ := runtimeLogJSONFiles(exporter.deadDir)
	if len(pending) != 0 || len(dead) != 1 {
		t.Fatalf("422 must unblock spool into DLQ: pending=%v dead=%v", pending, dead)
	}
	permanent, err := readRuntimeLogBatch(dead[0])
	if err != nil || permanent.LastFailure != "http_422" {
		t.Fatalf("permanent DLQ reason mismatch: %+v err=%v", permanent, err)
	}

	expired := spooledRuntimeLogBatch{
		ID:            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		Service:       "content-service",
		CreatedAt:     time.Now().UTC().Add(-96 * time.Hour),
		ExpiresAt:     time.Now().UTC().Add(-24 * time.Hour),
		NextAttemptAt: time.Now().UTC().Add(-96 * time.Hour),
		Records:       testRuntimeLogBatch("WARN"),
	}
	if err := writeRuntimeLogBatchAtomic(exporter.batchPath(expired.ID), expired); err != nil {
		t.Fatalf("write expired spool: %v", err)
	}
	if err := exporter.FlushOnce(context.Background()); err != nil {
		t.Fatalf("expire flush: %v", err)
	}
	dead, _ = runtimeLogJSONFiles(exporter.deadDir)
	if len(dead) != 2 {
		t.Fatalf("expired batch must enter DLQ: %v", dead)
	}
}

func newTestHTTPRuntimeLogExporter(t *testing.T, endpoint string) *HTTPRuntimeLogExporter {
	t.Helper()
	return newTestHTTPRuntimeLogExporterAt(t, endpoint, t.TempDir())
}

func newTestHTTPRuntimeLogExporterAt(
	t *testing.T,
	endpoint string,
	spoolDir string,
) *HTTPRuntimeLogExporter {
	t.Helper()
	deadDir := filepath.Join(spoolDir, "dead-letter")
	if err := os.MkdirAll(deadDir, 0o700); err != nil {
		t.Fatal(err)
	}
	return &HTTPRuntimeLogExporter{
		endpoint: endpoint,
		token:    "machine-token",
		spoolDir: spoolDir,
		deadDir:  deadDir,
		service:  "content-service",
		client:   &http.Client{Timeout: time.Second},
		enabled:  true,
		wake:     make(chan struct{}, 1),
		stop:     make(chan struct{}),
		done:     make(chan struct{}),
	}
}

func testRuntimeLogBatch(severity string) []map[string]string {
	return []map[string]string{{
		"schema":             "observability.slim",
		"recordId":           "r.test",
		"occurredAt":         time.Now().UTC().Format(time.RFC3339Nano),
		"observedAt":         time.Now().UTC().Format(time.RFC3339Nano),
		"logKind":            "exception",
		"severity":           severity,
		"signal":             "service.exception.runtime",
		"message":            "test",
		"resourceSourceType": "service",
		"resourceService":    "content-service",
		"errorCode":          "SERVICE.RUNTIME.test",
	}}
}

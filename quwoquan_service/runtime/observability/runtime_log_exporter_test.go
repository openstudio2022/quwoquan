package runtimeobservability

import (
	"bytes"
	"testing"
	"time"
)

func TestRuntimeLogExportWriter_MirrorsOnlyCanonicalRecords(t *testing.T) {
	var primary bytes.Buffer
	exported := make(chan map[string]string, 1)
	writer := NewRuntimeLogExportWriter(&primary, 4, func(batch []map[string]string) {
		for _, fields := range batch {
			exported <- fields
		}
	})
	defer writer.Close()

	line := formatCanonicalRuntimeLog("runtime", map[string]any{
		"signal":  "service.runtime.process",
		"event":   "worker_started",
		"result":  "ok",
		"message": "worker started",
		"resource": map[string]any{
			"sourceType": "service",
			"service":    "content-service",
		},
	})
	if _, err := writer.Write([]byte(line + "\nnot-json\n")); err != nil {
		t.Fatalf("write log lines: %v", err)
	}
	if primary.String() != line+"\nnot-json\n" {
		t.Fatalf("primary stdout was not preserved: %q", primary.String())
	}
	select {
	case fields := <-exported:
		if fields["schema"] != ObservabilitySchema ||
			fields["signal"] != "service.runtime.process" ||
			fields["resourceService"] != "content-service" ||
			fields["recordId"] == "" {
			t.Fatalf("unexpected exported fields: %+v", fields)
		}
	case <-time.After(time.Second):
		t.Fatal("canonical runtime record was not exported")
	}
	select {
	case fields := <-exported:
		t.Fatalf("noncanonical line must not be exported: %+v", fields)
	default:
	}
}

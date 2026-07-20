package runtimeobservability

import (
	"encoding/json"
	"testing"
)

func TestRuntimeLogRecord_EnforcesSignalKindAndStringOnlyAttributes(t *testing.T) {
	record, err := newRuntimeLogRecord("runtime", map[string]any{
		"event":  "worker_started",
		"result": "ok",
		"signal": "service.runtime.process",
		"attrs": map[string]any{
			"authorization":   "Bearer token",
			"protocolVersion": "must-not-appear",
			"releaseVersion":  "must-not-appear",
			"releaseId":       "must-not-appear",
			"inputKv":         "kept",
			"outputKv":        map[string]any{"value": "kept"},
			"unregistered":    "must-not-appear",
		},
	})
	if err != nil {
		t.Fatalf("create runtime log record: %v", err)
	}
	if record.RecordID == "" {
		t.Fatalf("service runtime record must always receive a generated ID: %+v", record)
	}
	if record.Attributes["inputKv"] != "kept" {
		t.Fatalf("registered attribute was not retained: %+v", record.Attributes)
	}
	if record.Attributes["outputKv"] != `{"value":"kept"}` {
		t.Fatalf("structured attribute must be encoded as a string: %+v", record.Attributes)
	}
	if _, found := record.Attributes["authorization"]; found {
		t.Fatalf("secret attribute key must be dropped: %+v", record.Attributes)
	}
	if _, found := record.Attributes["releaseId"]; found {
		t.Fatalf("forbidden version/release attribute key must be dropped: %+v", record.Attributes)
	}
	if _, found := record.Attributes["protocolVersion"]; found {
		t.Fatalf("forbidden protocol version attribute key must be dropped: %+v", record.Attributes)
	}
	if _, found := record.Attributes["releaseVersion"]; found {
		t.Fatalf("forbidden release version attribute key must be dropped: %+v", record.Attributes)
	}
	if _, found := record.Attributes["unregistered"]; found {
		t.Fatalf("unregistered attribute key must be dropped: %+v", record.Attributes)
	}
	if record.DurationMS != nil {
		t.Fatalf("non-access record must not serialize durationMs")
	}

	_, err = newRuntimeLogRecord("runtime", map[string]any{
		"event":  "worker_started",
		"result": "ok",
		"signal": "service.access.http",
	})
	if err == nil {
		t.Fatal("signal/log kind mismatch must be rejected")
	}
}

func TestRuntimeLogRecord_EmergencyFallbackRemainsCanonical(t *testing.T) {
	var record map[string]any
	if err := json.Unmarshal(
		[]byte(formatCanonicalRuntimeLog("unsupported", map[string]any{})),
		&record,
	); err != nil {
		t.Fatalf("decode emergency log: %v", err)
	}
	for _, field := range CatalogEnvelopeRequiredFields {
		if record[field] == nil || record[field] == "" {
			t.Fatalf("emergency log misses required %s: %+v", field, record)
		}
	}
	if record["schema"] != ObservabilitySchema ||
		record["logKind"] != "exception" ||
		record["signal"] != "service.exception.runtime" {
		t.Fatalf("unexpected emergency log: %+v", record)
	}
	if record["recordId"] == nil || record["recordId"] == "" {
		t.Fatalf("emergency log must receive a record ID: %+v", record)
	}
	if _, found := record["releaseId"]; found {
		t.Fatalf("emergency log must not include releaseId: %+v", record)
	}
}

func TestCanonicalRuntimeLogFields_RejectsBranchesAndUnknownAttributes(t *testing.T) {
	payload := map[string]any{
		"schema":     ObservabilitySchema,
		"recordId":   "r.test.1",
		"occurredAt": "2026-07-19T00:00:00Z",
		"observedAt": "2026-07-19T00:00:01Z",
		"logKind":    "exception",
		"severity":   "ERROR",
		"signal":     "app.exception.flutter",
		"message":    "uncaught exception",
		"resource": map[string]any{
			"sourceType": "app",
			"service":    "quwoquan_app",
			"appVersion": "1.2.3",
		},
		"errorCode": "APP.RUNTIME.uncaught_exception",
		"attributes": map[string]any{
			"source":        "flutter",
			"exceptionType": "StateError",
		},
	}
	fields, err := CanonicalRuntimeLogFields(payload)
	if err != nil {
		t.Fatalf("canonical runtime log: %v", err)
	}
	if fields["recordId"] != "r.test.1" ||
		fields["resourceAppVersion"] != "1.2.3" ||
		fields["errorCode"] != "APP.RUNTIME.uncaught_exception" {
		t.Fatalf("unexpected flattened fields: %+v", fields)
	}
	payload["schemaVersion"] = "1"
	if _, err := CanonicalRuntimeLogFields(payload); err == nil {
		t.Fatal("schema branch must be rejected")
	}
	delete(payload, "schemaVersion")
	payload["protocolVersion"] = "1"
	if _, err := CanonicalRuntimeLogFields(payload); err == nil {
		t.Fatal("protocol branch must be rejected")
	}
	delete(payload, "protocolVersion")
	payload["releaseVersion"] = "1"
	if _, err := CanonicalRuntimeLogFields(payload); err == nil {
		t.Fatal("release branch must be rejected")
	}
	delete(payload, "releaseVersion")
	payload["attributes"] = map[string]any{"unregistered": "value"}
	if _, err := CanonicalRuntimeLogFields(payload); err == nil {
		t.Fatal("unregistered attribute must be rejected")
	}
}

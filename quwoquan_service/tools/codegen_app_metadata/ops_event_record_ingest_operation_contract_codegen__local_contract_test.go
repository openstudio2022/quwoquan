package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestOpsEventRecordIngestSourceGeneratesTypedItemsAndOneReceiptOwner(
	t *testing.T,
) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	graphSourceOperations := activeMetadataSource.Graph().Operations
	payload, err := json.Marshal(graphSourceOperations)
	if err != nil {
		t.Fatal(err)
	}
	var graphOperations []appExposedOperation
	if err := json.Unmarshal(payload, &graphOperations); err != nil {
		t.Fatal(err)
	}
	wanted := map[string]bool{
		"ops.event_record.ReportEventBatch":      false,
		"ops.event_record.ReportRuntimeLogBatch": false,
	}
	lock := appContractLock{}
	for index, operation := range graphOperations {
		operation.CanonicalOperationID = graphSourceOperations[index].ID
		operation.LocalOperationID = graphSourceOperations[index].LocalID
		if _, ok := wanted[operation.CanonicalOperationID]; !ok || operation.ClientContract == nil {
			continue
		}
		wanted[operation.CanonicalOperationID] = true
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	for operationID, found := range wanted {
		if !found {
			t.Fatalf("%s has no App-generated client contract", operationID)
		}
	}
	if got := len(lock.AppExposedOperations); got != len(wanted) {
		t.Fatalf("EventRecord ingest App operation matches = %d, want %d", got, len(wanted))
	}
	assertCanonicalRequestInputs(t, lock.AppExposedOperations)

	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	owner := generatedDomainOperationOwnerImport("ops")
	if len(provided[owner]) == 0 {
		t.Fatal("Ops owner did not provide EventRecordBatchReceipt")
	}
	artifacts, err := writeGeneratedOperationRequests(appDir, lock, provided)
	if err != nil {
		t.Fatal(err)
	}
	if got := len(artifacts); got != 2 {
		t.Fatalf("Ops EventRecord ingest typed request artifacts = %d, want 2", got)
	}

	ownerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/ops/ops_operation_contracts.g.dart",
	))
	requestPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/ops/ops_operation_contracts.g.requests.g.dart",
	))
	for _, expected := range []string{
		"final class EventRecordBatchReceipt {",
		"EventRecordBatchReceipt decodeEventRecordBatchReceipt(Object? response)",
	} {
		if !strings.Contains(ownerPayload, expected) {
			t.Fatalf("Ops EventRecord generated owner is missing %q", expected)
		}
	}
	if got := strings.Count(ownerPayload, "final class EventRecordBatchReceipt {"); got != 1 {
		t.Fatalf("EventRecordBatchReceipt generated owner count = %d, want 1", got)
	}
	for _, expected := range []string{
		"// Derived from product_ops/event_record/event_catalog.yaml; source SHA256:",
		"final class EventRecord {",
		"final String eventType;",
		"final String? devicePlatform;",
		"unknown canonical event",
		"event contains forbidden extension",
		"final class EventRecordBatchRequest {",
		"final List<EventRecord> events;",
		"encodeOpsEventRecordReportEventBatchGeneratedRequest",
		`"events": request.events.map((value) => value.toWire()).toList(growable: false)`,
		"// Derived from _shared/runtime_observability.yaml#envelope; source SHA256:",
		"final class RuntimeLogRecordWire {",
		"final RuntimeLogResourceWire resource;",
		"final RuntimeLogAttributesWire? attributes;",
		"unknown runtime log signal",
		"contains fields outside signal policy",
		"final class RuntimeLogBatchRequest {",
		"final List<RuntimeLogRecordWire> records;",
		"encodeOpsEventRecordReportRuntimeLogBatchGeneratedRequest",
		`"records": request.records.map((value) => value.toWire()).toList(growable: false)`,
	} {
		if !strings.Contains(requestPayload, expected) {
			t.Fatalf("Ops EventRecord generated request is missing %q:\n%s", expected, requestPayload)
		}
	}
	for _, forbidden := range []string{
		"final List<Object?> events;",
		"final List<Object?> records;",
		"final Map<String, Object?> extensions;",
		"final Map<String, Object?> attributes;",
	} {
		if strings.Contains(requestPayload, forbidden) {
			t.Fatalf("Ops EventRecord generated request retained raw payload %q", forbidden)
		}
	}
}

func TestOpsRuntimeLogDerivedTypeRejectsAnUnboundEmptyMarker(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	operation := findGraphOperationForTest(
		t,
		"ops.event_record.ReportRuntimeLogBatch",
	)
	fieldsPath := filepath.Join(
		metadataDir,
		"ops",
		"product_ops",
		"event_record",
		"fields.yaml",
	)
	payload, err := os.ReadFile(fieldsPath)
	if err != nil {
		t.Fatal(err)
	}
	withoutSource := strings.Replace(
		string(payload),
		"    derived_from: _shared/runtime_observability.yaml#envelope\n",
		"",
		1,
	)
	if withoutSource == string(payload) {
		t.Fatal("RuntimeLogRecordWire derived_from marker was not present")
	}
	// The compiler view deliberately uses symlinks back to the service-owned
	// contract sources.  Break this file's symlink before the negative mutation;
	// writing through it would corrupt the repository truth source and make the
	// test outcome depend on execution order.
	if err := os.Remove(fieldsPath); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(fieldsPath, []byte(withoutSource), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	_, _, err = loadOperationRequestModel(operation, "RuntimeLogBatchRequest")
	if err == nil || !strings.Contains(err.Error(), "explicit empty derived marker") {
		t.Fatalf("unbound empty RuntimeLogRecordWire error = %v", err)
	}
}

func findGraphOperationForTest(
	t *testing.T,
	operationID string,
) appExposedOperation {
	t.Helper()
	operations := activeMetadataSource.Graph().Operations
	payload, err := json.Marshal(operations)
	if err != nil {
		t.Fatal(err)
	}
	var decoded []appExposedOperation
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatal(err)
	}
	for index, operation := range decoded {
		if operations[index].ID != operationID {
			continue
		}
		operation.CanonicalOperationID = operations[index].ID
		operation.LocalOperationID = operations[index].LocalID
		return operation
	}
	t.Fatalf("operation %s was not found", operationID)
	return appExposedOperation{}
}

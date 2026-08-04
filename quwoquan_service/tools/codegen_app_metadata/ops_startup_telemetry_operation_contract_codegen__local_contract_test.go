package main

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestOpsStartupTelemetrySurfaceGeneratesOneTypedRequestReceiptAndProofHeader(
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
	lock := appContractLock{}
	for index, operation := range graphOperations {
		operation.CanonicalOperationID = graphSourceOperations[index].ID
		operation.LocalOperationID = graphSourceOperations[index].LocalID
		if operation.CanonicalOperationID != "ops.event_record.ReportStartupEventBatch" ||
			operation.ClientContract == nil {
			continue
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if got := len(lock.AppExposedOperations); got != 1 {
		t.Fatalf("ReportStartupEventBatch App operation matches = %d, want 1", got)
	}
	assertCanonicalRequestInputs(t, lock.AppExposedOperations)

	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	owner := generatedDomainOperationOwnerImport("ops")
	if len(provided[owner]) == 0 {
		t.Fatal("Ops owner did not provide StartupTelemetryBatchReceipt")
	}
	artifacts, err := writeGeneratedOperationRequests(appDir, lock, provided)
	if err != nil {
		t.Fatal(err)
	}
	if got := len(artifacts); got != 1 {
		t.Fatalf("Ops startup typed request artifacts = %d, want 1", got)
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
		"final class StartupTelemetryBatchReceipt {",
		"StartupTelemetryBatchReceipt decodeStartupTelemetryBatchReceipt(Object? response)",
	} {
		if !strings.Contains(ownerPayload, expected) {
			t.Fatalf("Ops startup generated owner is missing %q", expected)
		}
	}
	for _, expected := range []string{
		"final class StartupTelemetryEventWire {",
		"final class ReportStartupEventBatchCommand {",
		"final List<StartupTelemetryEventWire> events;",
		"encodeOpsEventRecordReportStartupEventBatchGeneratedRequest",
		`"events": request.events.map((value) => value.toWire()).toList(growable: false)`,
		`"X-Qwq-Startup-Proof": request.proof`,
	} {
		if !strings.Contains(requestPayload, expected) {
			t.Fatalf("Ops startup generated request is missing %q:\n%s", expected, requestPayload)
		}
	}
	encoderStart := strings.Index(
		requestPayload,
		"CloudOperationRequestPayload encodeOpsEventRecordReportStartupEventBatchGeneratedRequest",
	)
	if encoderStart < 0 {
		t.Fatal("startup request encoder was not generated")
	}
	encoderPayload := requestPayload[encoderStart:]
	if strings.Contains(encoderPayload, `"proof": request.proof`) ||
		strings.Contains(encoderPayload, `"proof": this.proof`) {
		t.Fatal("startup proof leaked into the JSON body")
	}
}

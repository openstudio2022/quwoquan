package main

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestOpsVisitAppSurfaceGeneratesTypedRequestReceiptAndHeaderIdentity(t *testing.T) {
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
		if operation.CanonicalOperationID != "ops.visit_record.RecordVisit" ||
			operation.ClientContract == nil {
			continue
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if got := len(lock.AppExposedOperations); got != 1 {
		t.Fatalf("RecordVisit App operation matches = %d, want 1", got)
	}
	operation := lock.AppExposedOperations[0]
	if operation.CanonicalOperationID != "ops.visit_record.RecordVisit" {
		t.Fatalf("Ops App operation = %s, want RecordVisit", operation.CanonicalOperationID)
	}
	assertCanonicalRequestInputs(t, lock.AppExposedOperations)

	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	owner := generatedDomainOperationOwnerImport("ops")
	if len(provided[owner]) == 0 {
		t.Fatal("Ops owner did not provide RecordVisitReceipt")
	}
	artifacts, err := writeGeneratedOperationRequests(appDir, lock, provided)
	if err != nil {
		t.Fatal(err)
	}
	if got := len(artifacts); got != 1 {
		t.Fatalf("Ops typed request artifacts = %d, want 1", got)
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
		"enum VisitTargetType {",
		"final class RecordVisitReceipt {",
		"RecordVisitReceipt decodeRecordVisitReceipt(Object? response)",
	} {
		if !strings.Contains(ownerPayload, expected) {
			t.Fatalf("Ops generated owner is missing %q", expected)
		}
	}
	for _, expected := range []string{
		"final class RecordVisitRequest {",
		"final VisitTargetType targetType;",
		"encodeOpsVisitRecordRecordVisitGeneratedRequest",
		`"targetType": request.targetType.wireName`,
		`"targetKey": request.targetKey`,
	} {
		if !strings.Contains(requestPayload, expected) {
			t.Fatalf("Ops generated request is missing %q", expected)
		}
	}
	if strings.Contains(requestPayload, `"idempotencyKey": request.idempotencyKey`) {
		t.Fatal("Idempotency-Key leaked into the RecordVisit JSON body")
	}
}

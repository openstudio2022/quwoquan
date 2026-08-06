package main

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestOpsRecoveryAppShellGeneratesTypedRequestsResponsesAndCanonicalOperations(
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
		"ops.app_release.GetAppRecoveryVersion":      false,
		"ops.recovery_failure.ReportRecoveryFailure": false,
	}
	lock := appContractLock{}
	var feedOperation *appExposedOperation
	for index, operation := range graphOperations {
		operation.CanonicalOperationID = graphSourceOperations[index].ID
		operation.LocalOperationID = graphSourceOperations[index].LocalID
		if operation.CanonicalOperationID == "content.post.GetFeed" &&
			operation.ClientContract != nil {
			operation.SurfaceIDs = []string{"home"}
			candidate := operation
			feedOperation = &candidate
		}
		if _, selected := wanted[operation.CanonicalOperationID]; !selected || operation.ClientContract == nil {
			continue
		}
		wanted[operation.CanonicalOperationID] = true
		operation.SurfaceIDs = []string{"appShell"}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	for operationID, found := range wanted {
		if !found {
			t.Fatalf("%s has no App-generated client contract", operationID)
		}
	}
	if got := len(lock.AppExposedOperations); got != len(wanted) {
		t.Fatalf("Ops recovery App operation matches = %d, want %d", got, len(wanted))
	}
	if feedOperation == nil {
		t.Fatal("content.post.GetFeed support operation is unavailable")
	}
	// The operation-contract emitter owns the global GetFeed budget policy, so
	// include that canonical operation as generator support. Recovery assertions
	// below remain scoped to the two Product Ops operations.
	lock.AppExposedOperations = append(lock.AppExposedOperations, *feedOperation)
	assertCanonicalRequestInputs(t, lock.AppExposedOperations)

	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	owner := generatedDomainOperationOwnerImport("ops")
	if len(provided[owner]) == 0 {
		t.Fatal("Ops owner did not provide the recovery response contract")
	}
	artifacts, err := writeGeneratedOperationRequests(appDir, lock, provided)
	if err != nil {
		t.Fatal(err)
	}
	if got := len(artifacts); got != len(wanted)+1 {
		t.Fatalf("typed request artifacts = %d, want %d", got, len(wanted)+1)
	}
	if err := writeGeneratedOperationContracts(appDir, lock, artifacts); err != nil {
		t.Fatal(err)
	}

	ownerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/ops/ops_operation_contracts.g.dart",
	))
	requestPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/ops/ops_operation_contracts.g.requests.g.dart",
	))
	operationPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/operation_contracts.g.dart",
	))

	for _, expected := range []string{
		"final class AppReleaseRecoveryView {",
		"AppReleaseRecoveryView decodeAppReleaseRecoveryView(Object? response)",
		"void decodeEmptyResponse(Object? response)",
	} {
		if !strings.Contains(ownerPayload, expected) {
			t.Fatalf("Ops recovery generated owner is missing %q", expected)
		}
	}
	for _, expected := range []string{
		"final class GetAppRecoveryVersionQuery {",
		"final int buildNumber;",
		"encodeOpsAppReleaseGetAppRecoveryVersionGeneratedRequest",
		`"platform": request.platform`,
		`"appVersion": request.appVersion`,
		`"buildNumber": request.buildNumber`,
		"final class ReportRecoveryFailureRequest {",
		"final DateTime occurredAt;",
		"encodeOpsRecoveryFailureReportRecoveryFailureGeneratedRequest",
		`"errorMessage": request.errorMessage`,
		`"stackTrace": request.stackTrace`,
	} {
		if !strings.Contains(requestPayload, expected) {
			t.Fatalf("Ops recovery generated request is missing %q:\n%s", expected, requestPayload)
		}
	}
	for _, expected := range []string{
		`static const String opsAppReleaseGetAppRecoveryVersion = "ops.app_release.GetAppRecoveryVersion";`,
		`static const String opsRecoveryFailureReportRecoveryFailure = "ops.recovery_failure.ReportRecoveryFailure";`,
		`pathTemplate: "/ops/app-recovery/version"`,
		`pathTemplate: "/ops/recovery-failures"`,
		`responseBodyKind: "ack"`,
		`"appShell"`,
	} {
		if !strings.Contains(operationPayload, expected) {
			t.Fatalf("Ops recovery generated operation contract is missing %q", expected)
		}
	}
}

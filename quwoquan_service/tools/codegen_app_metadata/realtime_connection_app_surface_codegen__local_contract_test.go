package main

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestRealtimeConnectionAppSurfaceGeneratesTicketAndLongPollTypedOwners(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	sourceOperations := activeMetadataSource.Graph().Operations
	payload, err := json.Marshal(sourceOperations)
	if err != nil {
		t.Fatal(err)
	}
	var operations []appExposedOperation
	if err := json.Unmarshal(payload, &operations); err != nil {
		t.Fatal(err)
	}
	wanted := map[string]struct{}{
		"realtime.connection.IssueConnectionTicket": {},
		"realtime.connection.LongPoll":              {},
	}
	lock := appContractLock{}
	for index, operation := range operations {
		operation.CanonicalOperationID = sourceOperations[index].ID
		operation.LocalOperationID = sourceOperations[index].LocalID
		if _, selected := wanted[operation.CanonicalOperationID]; selected && operation.ClientContract != nil {
			lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
		}
	}
	if got := len(lock.AppExposedOperations); got != len(wanted) {
		t.Fatalf("Realtime connection App-exposed operations = %d, want %d", got, len(wanted))
	}
	assertCanonicalRequestInputs(t, lock.AppExposedOperations)

	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	artifacts, err := writeGeneratedOperationRequests(appDir, lock, provided)
	if err != nil {
		t.Fatal(err)
	}
	if got := len(artifacts); got != len(wanted) {
		t.Fatalf("Realtime connection typed request artifacts = %d, want %d", got, len(wanted))
	}
	owner := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/realtime/realtime_operation_contracts.g.dart",
	))
	requests := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/realtime/realtime_operation_contracts.g.requests.g.dart",
	))
	for _, expected := range []string{
		"import \"../generated/realtime/realtime_event_catalog.g.dart\";",
		"export \"../generated/realtime/realtime_event_catalog.g.dart\";",
		"final class ConnectionTicket",
		"final class LongPollResponse",
		"final class IssueConnectionTicketRequest",
		"const IssueConnectionTicketRequest();",
		"final class LongPollRequest",
		"encodeRealtimeConnectionIssueConnectionTicketGeneratedRequest",
		"encodeRealtimeConnectionLongPollGeneratedRequest",
	} {
		if !strings.Contains(owner, expected) && !strings.Contains(requests, expected) {
			t.Fatalf("Realtime generated ABI is missing %q", expected)
		}
	}
	if strings.Contains(owner, "final class RealtimeEventEnvelope") ||
		strings.Contains(owner, "final Map<String, Object?> payload") {
		t.Fatal("Realtime operation owner regenerated the shared tagged union as an opaque object")
	}
	if strings.Contains(requests, "final String accountId") ||
		strings.Contains(requests, "final String personaId") ||
		strings.Contains(requests, "final String deviceId") {
		t.Fatal("IssueConnectionTicket request exposed trusted injected identity")
	}
}

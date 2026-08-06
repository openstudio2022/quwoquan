package main

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestOperationContractsGenerateTypedStreamAndUpgradeSurfaces(t *testing.T) {
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

	wanted := map[string]struct{}{
		"assistant.assistant_run.StartAssistantRun":        {},
		"assistant.assistant_run.StreamAssistantRunEvents": {},
		"content.post.GetFeed":                             {},
		"realtime.connection.WebSocketUpgrade":             {},
	}
	lock := appContractLock{}
	requestArtifacts := map[string]operationRequestArtifact{}
	for index, operation := range graphOperations {
		operation.CanonicalOperationID = graphSourceOperations[index].ID
		operation.LocalOperationID = graphSourceOperations[index].LocalID
		if _, selected := wanted[operation.CanonicalOperationID]; !selected {
			continue
		}
		if operation.ClientContract == nil {
			t.Fatalf("%s has no generated client contract", operation.CanonicalOperationID)
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
		requestArtifacts[operation.CanonicalOperationID] = operationRequestArtifact{
			RequestType: operation.RequestEntity,
			Encoder: generatedOperationRequestEncoder(
				operation.CanonicalOperationID,
			),
		}
	}
	if got := len(lock.AppExposedOperations); got != len(wanted) {
		t.Fatalf("selected operations = %d, want %d", got, len(wanted))
	}

	appDir := t.TempDir()
	if err := writeGeneratedOperationContracts(
		appDir,
		lock,
		requestArtifacts,
	); err != nil {
		t.Fatal(err)
	}
	generated := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/operation_contracts.g.dart",
	))
	for _, expected := range []string{
		"abstract interface class CloudOperationStreamExecutor",
		"final class CloudOperationStreamBudget",
		"final CloudOperationStreamBudget? streamBudget;",
		"Stream<assistantContracts.AssistantStreamEventWire> assistantAssistantRunStreamAssistantRunEvents(",
		"return streamExecutor.stream<assistantContracts.AssistantStreamEventWire>(",
		"responseDecoder: assistantContracts.decodeAssistantStreamEventWire,",
		"handshakeMilliseconds: 5000,",
		"idleMilliseconds: 60000,",
		"maxDurationMilliseconds: 600000,",
		"final int? successStatus;",
		"successStatus: 201,",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("SSE generated client is missing %q", expected)
		}
	}
	if strings.Contains(
		generated,
		"Future<assistantContracts.AssistantStreamEventWire> assistantAssistantRunStreamAssistantRunEvents(",
	) {
		t.Fatal("SSE operation was downgraded to a Future response")
	}
	for _, expected := range []string{
		"final class CloudOperationUpgradeDescriptor<TRequest>",
		"abstract final class AppCloudOperationUpgradeDescriptors",
		"static final CloudOperationUpgradeDescriptor<realtimeContracts.WebSocketUpgradeRequest> realtimeConnectionWebSocketUpgrade =",
		"operation: appCloudOperationContracts[AppCloudOperationIds.realtimeConnectionWebSocketUpgrade]!",
		"requestEncoder: realtimeContracts.encodeRealtimeConnectionWebSocketUpgradeGeneratedRequest,",
		"idleMilliseconds: 90000,",
		"maxDurationMilliseconds: 1800000,",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("upgrade descriptor is missing %q", expected)
		}
	}
	if strings.Contains(
		generated,
		"Future<void> realtimeConnectionWebSocketUpgrade(",
	) {
		t.Fatal("WebSocket upgrade was emitted as a JSON Future method")
	}
	if strings.Contains(
		generated,
		`_executor.send<void>(\n      appCloudOperationContracts["realtime.connection.WebSocketUpgrade"]!`,
	) {
		t.Fatal("WebSocket upgrade was routed through CloudOperationExecutor.send")
	}

	malformedLock := lock
	malformedLock.AppExposedOperations = append(
		[]appExposedOperation(nil),
		lock.AppExposedOperations...,
	)
	for index := range malformedLock.AppExposedOperations {
		operation := &malformedLock.AppExposedOperations[index]
		if operation.CanonicalOperationID == "realtime.connection.WebSocketUpgrade" {
			operation.Method = "POST"
		}
	}
	err = writeGeneratedOperationContracts(
		t.TempDir(),
		malformedLock,
		requestArtifacts,
	)
	if err == nil || !strings.Contains(err.Error(), "upgrade ABI must be GET/body-none") {
		t.Fatalf("malformed upgrade ABI was not rejected: %v", err)
	}
}

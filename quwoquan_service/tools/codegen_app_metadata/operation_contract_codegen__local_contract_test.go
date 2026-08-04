package main

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestSSEOperationGeneratesTypedStreamClient(t *testing.T) {
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
		"assistant.assistant_run.StreamAssistantRunEvents": {},
		"content.post.GetFeed":                             {},
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
		"Stream<assistantContracts.AssistantStreamEventWire> assistantAssistantRunStreamAssistantRunEvents(",
		"return streamExecutor.stream<assistantContracts.AssistantStreamEventWire>(",
		"responseDecoder: assistantContracts.decodeAssistantStreamEventWire,",
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
}

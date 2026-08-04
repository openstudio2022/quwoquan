package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestContentMediaDiscardResultGeneratesDeletedOnlyStatus(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}

	graphOperations := activeMetadataSource.Graph().Operations
	payload, err := json.Marshal(graphOperations)
	if err != nil {
		t.Fatal(err)
	}
	var operations []appExposedOperation
	if err := json.Unmarshal(payload, &operations); err != nil {
		t.Fatal(err)
	}

	const operationID = "content.media_asset.DiscardMediaAsset"
	lock := appContractLock{}
	for index, operation := range operations {
		if graphOperations[index].ID != operationID {
			continue
		}
		operation.CanonicalOperationID = graphOperations[index].ID
		operation.LocalOperationID = graphOperations[index].LocalID
		if operation.ClientContract == nil {
			t.Fatalf("%s is not App-exposed", operationID)
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if len(lock.AppExposedOperations) != 1 {
		t.Fatalf("%s operation count = %d, want 1", operationID, len(lock.AppExposedOperations))
	}

	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := writeGeneratedOperationRequests(appDir, lock, provided); err != nil {
		t.Fatal(err)
	}
	generatedPath := filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/content/content_operation_contracts.g.dart",
	)
	generated, err := os.ReadFile(generatedPath)
	if err != nil {
		t.Fatal(err)
	}
	content := string(generated)
	for _, expected := range []string{
		"enum MediaAssetDiscardStatus {",
		`deleted("deleted");`,
		"final MediaAssetDiscardStatus status;",
		`status: MediaAssetDiscardStatus.fromWire(map["status"], '$path.status'),`,
		`_ => throw FormatException('$path has an invalid enum value'),`,
	} {
		if !strings.Contains(content, expected) {
			t.Fatalf("generated Content media discard contract is missing %q", expected)
		}
	}
	if strings.Contains(content, `ready("ready")`) {
		t.Fatal("MediaAssetDiscardStatus generator accepted the non-terminal ready status")
	}
}

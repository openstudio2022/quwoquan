package main

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestCrossDomainSharedValueHasOneGeneratedOwner(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(activeMetadataSource.Graph().Operations)
	if err != nil {
		t.Fatal(err)
	}
	var operations []appExposedOperation
	if err := json.Unmarshal(payload, &operations); err != nil {
		t.Fatal(err)
	}
	lock := appContractLock{}
	for index, operation := range operations {
		operation.CanonicalOperationID = activeMetadataSource.Graph().Operations[index].ID
		operation.LocalOperationID = activeMetadataSource.Graph().Operations[index].LocalID
		if operation.ClientContract == nil ||
			(operation.Domain != "chat" && operation.Domain != "user") {
			continue
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if len(lock.AppExposedOperations) == 0 {
		t.Fatal("Chat/User App-exposed operations are missing")
	}

	appDir := t.TempDir()
	if _, err := generateDomainOperationContracts(metadataDir, appDir, lock); err != nil {
		t.Fatal(err)
	}
	shared := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/shared_operation_types.g.dart",
	))
	if got := strings.Count(shared, "final class GreetingIntersectionSnapshot {"); got != 1 {
		t.Fatalf("shared GreetingIntersectionSnapshot declarations = %d, want 1", got)
	}
	for _, expected := range []string{
		"final String intersectionId;",
		"final String primaryText;",
		"final DateTime resolvedAt;",
		"GreetingIntersectionSnapshot.fromWire",
		"Map<String, Object?> toWire()",
	} {
		if !strings.Contains(shared, expected) {
			t.Fatalf("shared GreetingIntersectionSnapshot is missing %q", expected)
		}
	}

	for _, domain := range []string{"chat", "user"} {
		owner := readGeneratedTestFile(t, filepath.Join(
			appDir,
			"packages/quwoquan_cloud_contracts/lib/src",
			domain,
			domain+"_operation_contracts.g.dart",
		))
		if strings.Contains(owner, "final class GreetingIntersectionSnapshot {") {
			t.Fatalf("%s retained a duplicate GreetingIntersectionSnapshot", domain)
		}
		for _, directive := range []string{
			`import "../generated/shared_operation_types.g.dart";`,
			`export "../generated/shared_operation_types.g.dart";`,
		} {
			if strings.Count(owner, directive) != 1 {
				t.Fatalf("%s owner does not reference the shared value owner once: %s", domain, directive)
			}
		}
	}
}

func TestCrossDomainValueWithoutSharedCanonicalOwnerFailsClosed(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	newSpec := func(domain string) *domainOperationContractSpec {
		return &domainOperationContractSpec{
			Domain: domain,
			Models: map[string]requestModelSpec{
				"CoincidentallyNamedValue": {
					Name: "CoincidentallyNamedValue",
					Fields: []fieldDef{
						{Name: "id", Type: "string", Constraints: []string{"NOT_BLANK"}},
					},
				},
			},
			ResponseEntities:         map[string]struct{}{},
			ExternalResponseEntities: map[string]struct{}{},
			ExternalImports:          map[string]struct{}{},
			ExternalExports:          map[string]struct{}{},
			EnumMembers:              map[string][]canonicalRequestEnumMember{},
		}
	}
	err := externalizeSharedDomainModels(map[string]*domainOperationContractSpec{
		generatedDomainOperationOwnerImport("chat"): newSpec("chat"),
		generatedDomainOperationOwnerImport("user"): newSpec("user"),
	})
	if err == nil || !strings.Contains(
		err.Error(),
		"has no canonical _shared/types.yaml owner",
	) {
		t.Fatalf("non-canonical cross-domain value error = %v", err)
	}
}

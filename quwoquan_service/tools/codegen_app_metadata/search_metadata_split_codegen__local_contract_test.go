package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestCanonicalSearchMetadataHasLayeredGeneratedOwners(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatalf("initialize metadata source: %v", err)
	}
	contract, err := readSearchContract(filepath.Join(
		metadataDir,
		"_shared",
		"search_contract.yaml",
	))
	if err != nil {
		t.Fatalf("read Search contract: %v", err)
	}
	objects, err := readSearchObjects(filepath.Join(
		metadataDir,
		"_shared",
		"search_objects.yaml",
	))
	if err != nil {
		t.Fatalf("read Search objects: %v", err)
	}

	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, "canonical-search-graph")
	if err := writeCanonicalSearchMetadata(appDir, contract, objects); err != nil {
		t.Fatalf("write canonical Search metadata: %v", err)
	}

	vocabulary := readSearchGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/search/"+
			"search_contract_vocabulary.g.dart",
	))
	for _, symbol := range []string{
		"enum SearchObjectType",
		"enum RetrieveTarget",
		"enum SearchConversationType",
		"final class RetrieveToolContract",
		"static const List<String> forbiddenFields",
	} {
		if !strings.Contains(vocabulary, symbol) {
			t.Fatalf("shared Search vocabulary misses %q", symbol)
		}
	}
	for _, duplicate := range []string{
		"enum SearchMode",
		"enum CanonicalSearchMode",
		"SearchExecutionStrategy",
		"SearchRegistry",
	} {
		if strings.Contains(vocabulary, duplicate) {
			t.Fatalf("shared Search vocabulary duplicates %q", duplicate)
		}
	}

	execution := readSearchGeneratedTestFile(t, filepath.Join(
		appDir,
		"lib/service/search_service/search/search_index_view/application/generated/"+
			"search_execution_policy.g.dart",
	))
	for _, symbol := range []string{
		"final class SearchContractDefaults",
		"enum SearchExecutionStrategy",
		"final class SearchObjectExecutionPolicy",
		"final class SearchRetrieveTargetPolicy",
		"static const int suggestLimit = 12",
		"static const int resultLimit = 20",
		"static const int assistantLimit = 8",
		"SearchObjectType.contentPost",
		"RetrieveTarget.article",
	} {
		if !strings.Contains(execution, symbol) {
			t.Fatalf("Search execution policy misses %q", symbol)
		}
	}
	if strings.Contains(execution, "label:") ||
		strings.Contains(execution, "title:") {
		t.Fatal("Search execution policy owns presentation copy")
	}

	display := readSearchGeneratedTestFile(t, filepath.Join(
		appDir,
		"lib/service/search_service/search/search_index_view/presentation/generated/"+
			"search_display_metadata.g.dart",
	))
	for _, symbol := range []string{
		"final class SearchObjectDisplayMetadata",
		"final class SearchSectionDisplayMetadata",
		"final class SearchRetrieveTargetDisplayMetadata",
		"title: '联系人'",
		"label: '内容'",
	} {
		if !strings.Contains(display, symbol) {
			t.Fatalf("Search display metadata misses %q", symbol)
		}
	}
	for _, privateExecutionDetail := range []string{
		"SearchExecutionStrategy",
		"provider:",
		"domain:",
	} {
		if strings.Contains(display, privateExecutionDetail) {
			t.Fatalf(
				"Search display metadata leaks execution detail %q",
				privateExecutionDetail,
			)
		}
	}

	for _, relative := range []string{
		"packages/quwoquan_cloud_contracts/lib/src/generated/search/" +
			"search_contract_vocabulary.g.dart",
		"lib/service/search_service/search/search_index_view/application/generated/" +
			"search_execution_policy.g.dart",
		"lib/service/search_service/search/search_index_view/presentation/generated/" +
			"search_display_metadata.g.dart",
	} {
		if _, ok := generatedManifestOutputs[relative]; !ok {
			t.Fatalf("generated manifest did not record %s", relative)
		}
	}

	spec := domainOperationContractSpec{
		Domain:                   "search",
		Models:                   map[string]requestModelSpec{},
		ExternalImports:          map[string]struct{}{},
		ExternalExports:          map[string]struct{}{},
		EnumMembers:              map[string][]canonicalRequestEnumMember{},
		ResponseEntities:         map[string]struct{}{},
		ExternalResponseEntities: map[string]struct{}{},
	}
	if err := finalizeDomainOperationContractSpec(&spec); err != nil {
		t.Fatalf("finalize Search operation owner: %v", err)
	}
	if _, ok := spec.ExternalExports[searchContractVocabularyImport]; !ok {
		t.Fatal("Search operation owner does not re-export canonical vocabulary")
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestCanonicalSearchMetadataRejectsUnknownObjectPolicyReferences(t *testing.T) {
	contract := &searchContractFile{
		ExecutionStrategies: []searchNamedValueDef{{ID: "remote_only"}},
		ConversationTypes:   []searchNamedValueDef{{ID: "direct"}},
		Defaults: searchContractDefaultsDef{
			SuggestLimit:   1,
			ResultLimit:    1,
			AssistantLimit: 1,
		},
		RetrieveContract: retrieveContractDef{
			ForbiddenFields: []string{"type"},
		},
	}
	objects := &searchObjectsFile{
		ObjectTypes: []searchObjectTypeDef{{
			ID:                "content.post",
			Label:             "Content",
			Domain:            "content",
			ExecutionStrategy: "missing_strategy",
			Provider:          "content_remote",
		}},
		AITargets: []aiTargetDef{{
			ID:         "article",
			Label:      "Article",
			ObjectType: "content.post",
		}},
		SectionKinds: []searchSectionKindDef{{
			ID:                 "content",
			Title:              "Content",
			DefaultObjectTypes: []string{"content.post"},
		}},
	}
	if err := validateCanonicalSearchMetadata(contract, objects); err == nil ||
		!strings.Contains(err.Error(), "unknown execution strategy") {
		t.Fatalf("unknown Search execution strategy must fail closed, got %v", err)
	}

	objects.ObjectTypes[0].ExecutionStrategy = "remote_only"
	objects.AITargets[0].ObjectType = "missing.object"
	if err := validateCanonicalSearchMetadata(contract, objects); err == nil ||
		!strings.Contains(err.Error(), "unknown object type") {
		t.Fatalf("unknown Search target object must fail closed, got %v", err)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestSearchOperationOwnersExportCanonicalVocabulary(t *testing.T) {
	oldSHA := activeContractSHA256
	t.Cleanup(func() { activeContractSHA256 = oldSHA })
	activeContractSHA256 = strings.Repeat("a", 64)

	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, activeContractSHA256)
	lock := appContractLock{AppExposedOperations: []appExposedOperation{{
		CanonicalOperationID: "search.search_index_view.Search",
		Domain:               "search",
		ClientContract: &appClientContract{
			DartImport: generatedDomainOperationOwnerImport("search"),
		},
	}}}
	if err := generateDomainOperationPublicBarrels(appDir, lock); err != nil {
		t.Fatalf("generate Search public owner: %v", err)
	}
	barrel := readSearchGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/generated/search_contracts.dart",
	))
	if !strings.Contains(
		barrel,
		"export '../src/generated/search/search_contract_vocabulary.g.dart';",
	) {
		t.Fatal("Search public package owner does not export canonical vocabulary")
	}
}

func readSearchGeneratedTestFile(t *testing.T, path string) string {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated Search artifact %s: %v", path, err)
	}
	return string(payload)
}

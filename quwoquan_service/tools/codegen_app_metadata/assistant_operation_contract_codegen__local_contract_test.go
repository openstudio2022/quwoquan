package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestAssistantOperationResponsesAreDerivedFromCanonicalEntities(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	fields, service, enumCatalog, err := loadAssistantCloudAPISource(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	objectSchemas, schemaTypes, err := loadAssistantOperationObjectSchemas(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	responseFields := assistantFieldsWithSchemaTypes(fields, schemaTypes)
	direct := assistantDirectResponseEntities(responseFields, service)
	models := collectAssistantWireEntityClosure(
		responseFields,
		append(
			append([]string(nil), direct...),
			"AssistantDeviceActionExecutionReceipt",
		),
	)
	models = assistantExcludeSchemaModels(models, schemaTypes)
	rendered := renderAssistantOperationResponsesDart(
		responseFields,
		models,
		direct,
		enumCatalog,
		assistantResponseSchemaImports(responseFields, models, objectSchemas),
	)
	for _, expected := range []string{
		"class AssistantEntryResponse",
		"class AssistantDeviceActionExecutionReceipt",
		"AssistantEntryResponse decodeAssistantEntryResponse(Object? response)",
		"class GrantSkillConsentReceipt",
		"GrantSkillConsentReceipt decodeGrantSkillConsentReceipt(Object? response)",
		"class RevokeSkillConsentReceipt",
		"class SkillConsentListSlice",
		"class AssistantPreferenceListView",
		"class AssistantTaskSlice",
		"class AssistantTurnListView",
		"class SkillPackageRelease",
		"class SkillSurfacePlacement",
		"class SkillUserSetting",
		"AssistantLearningFactReceipt response contains unknown fields",
		"AssistantLearningFactReceipt field eventId has an invalid wire value",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("generated Assistant operation response is missing %q", expected)
		}
	}
	for _, forbidden := range []string{
		"AssistantSessionProjection",
		"AssistantSkillCatalogListProjection",
		"AssistantSkillSubscriptionProjection",
		"class AssistantSession {",
		"class SkillSubscription {",
	} {
		if strings.Contains(rendered, forbidden) {
			t.Fatalf("generated Assistant response retained legacy alias %q", forbidden)
		}
	}
	for _, expected := range []string{
		"import 'assistant_session.g.dart';",
		"import 'skill_subscription.g.dart';",
		"List<AssistantSessionWire> items",
		"List<SkillSubscriptionWire> items",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("generated Assistant response is missing schema mapping %q", expected)
		}
	}
}

func TestAssistantOperationDiscoveryUsesContractGraphDocuments(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	// App-only rebuild receives an arbitrary empty metadata root. Discovery must
	// therefore enumerate the fixed ContractGraph documents rather than glob the
	// host filesystem behind that root.
	activeMetadataRoot = t.TempDir()
	activeMetadataSource = contractcodegen.NewSourceFromGraph(
		activeMetadataRoot,
		activeMetadataSource.Graph(),
	)
	fields, service, _, err := loadAssistantCloudAPISource(activeMetadataRoot)
	if err != nil {
		t.Fatal(err)
	}
	if len(fields.Entities) == 0 || len(service.APIRoutes) == 0 {
		t.Fatal("fixed ContractGraph did not provide Assistant fields and operations")
	}
	schemas, _, err := loadAssistantOperationObjectSchemas(activeMetadataRoot)
	if err != nil {
		t.Fatal(err)
	}
	if len(schemas) == 0 {
		t.Fatal("fixed ContractGraph did not provide Assistant object schemas")
	}
}

func TestAssistantOperationOwnerIsTheOnlyRequestAndResponseLibrary(t *testing.T) {
	rendered := renderAssistantOperationOwnerLibrary([]string{
		"assistant_session.g.dart",
		"skill_subscription.g.dart",
	}, []string{"skill_subscription.g.dart"})
	for _, expected := range []string{
		"import '../generated/assistant/assistant_runtime_enums.g.dart';",
		"assistant_api_responses.g.dart",
		"assistant_runtime_failure.g.dart",
		"assistant_run_envelope.g.dart",
		"assistant_stream_event.g.dart",
		"assistant_session.g.dart",
		"skill_subscription.g.dart",
		"assistant_operation_contracts.g.requests.g.dart",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("Assistant operation owner is missing %q", expected)
		}
	}
	if strings.Contains(rendered, "assistant_contracts.dart") {
		t.Fatal("Assistant operation owner retained the handwritten wire library")
	}
}

func TestAssistantOperationPackageOutputsDoNotDependOnAppLocalWireTypes(
	t *testing.T,
) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	appDir := t.TempDir()
	if err := generateAssistantOperationContracts(metadataDir, appDir); err != nil {
		t.Fatal(err)
	}
	generatedDir := filepath.Join(
		appDir,
		"packages",
		"quwoquan_cloud_contracts",
		"lib",
		"src",
		"generated",
		"assistant",
	)
	paths, err := filepath.Glob(filepath.Join(generatedDir, "*.dart"))
	if err != nil {
		t.Fatal(err)
	}
	if len(paths) == 0 {
		t.Fatal("Assistant operation package generator emitted no Dart files")
	}
	var generated strings.Builder
	for _, path := range paths {
		payload, readErr := os.ReadFile(path)
		if readErr != nil {
			t.Fatal(readErr)
		}
		if strings.Contains(string(payload), "package:quwoquan_app/") {
			t.Fatalf("%s depends on an App-local wire type", path)
		}
		generated.Write(payload)
	}
	for _, expected := range []string{
		"AssistantSessionWire response contains unknown fields",
		"AssistantSessionWire field sessionId has an invalid wire value",
		"SkillSubscriptionWire field subscriptionId has an invalid wire value",
	} {
		if !strings.Contains(generated.String(), expected) {
			t.Fatalf("generated Assistant package is missing strict decoder guard %q", expected)
		}
	}
	clientCount := 0
	var surfaces struct {
		Surfaces []struct {
			Owner        string   `yaml:"owner"`
			OperationIDs []string `yaml:"operation_ids"`
		} `yaml:"surfaces"`
	}
	if err := activeMetadataSource.Decode("_shared/ui_surfaces.yaml", &surfaces); err != nil {
		t.Fatal(err)
	}
	assistantExposed := map[string]struct{}{}
	for _, surface := range surfaces.Surfaces {
		if surface.Owner != "assistant" {
			continue
		}
		for _, operationID := range surface.OperationIDs {
			assistantExposed[operationID] = struct{}{}
		}
	}
	for _, operation := range activeMetadataSource.Graph().Operations {
		if operation.Domain != "assistant" {
			continue
		}
		if _, exposed := assistantExposed[operation.LocalID]; !exposed {
			continue
		}
		if operation.ClientContract == nil {
			t.Fatalf("%s App exposure has no generated client contract", operation.ID)
		}
		clientCount++
		client := operation.ClientContract
		if client.DartImport != assistantOperationOwnerImport {
			t.Fatalf(
				"%s client owner = %q, want %q",
				operation.ID,
				client.DartImport,
				assistantOperationOwnerImport,
			)
		}
		if !strings.Contains(
			generated.String(),
			client.ResponseDecoder+"(Object? response)",
		) {
			t.Fatalf(
				"%s generated decoder %s is missing",
				operation.ID,
				client.ResponseDecoder,
			)
		}
	}
	if clientCount == 0 {
		t.Fatal("Assistant source graph has no generated client contracts")
	}
}

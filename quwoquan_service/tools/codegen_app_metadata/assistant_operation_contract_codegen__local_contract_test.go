package main

import (
	"encoding/json"
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
	direct := assistantDirectResponseEntities(
		responseFields,
		service,
		schemaTypes,
	)
	models := collectAssistantWireEntityClosure(
		responseFields,
		append(append(
			append([]string(nil), direct...),
			"AssistantDeviceActionExecutionReceipt",
		), assistantObjectSchemaResponseRoots(
			responseFields,
			objectSchemas,
		)...),
	)
	models = assistantExcludeSchemaModels(models, schemaTypes)
	requestSchemaImports := assistantRequestSchemaImports(
		fields,
		service,
		objectSchemas,
	)
	requestSchemaOutputs := make(map[string]struct{}, len(requestSchemaImports))
	for _, output := range requestSchemaImports {
		requestSchemaOutputs[output] = struct{}{}
	}
	rendered := renderAssistantOperationResponsesDart(
		responseFields,
		models,
		direct,
		enumCatalog,
		assistantResponseSchemaImports(responseFields, models, objectSchemas),
		assistantSchemaTypesForOutputs(objectSchemas, requestSchemaOutputs),
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
		"class AssistantRunTerminalSnapshotView",
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
		"decodeAssistantRunEnvelopeWire(Object? response)",
		"decodeAssistantSessionWire(Object? response)",
		"decodeSkillSubscriptionWire(Object? response)",
	} {
		if strings.Contains(rendered, forbidden) {
			t.Fatalf("generated Assistant response retained legacy alias %q", forbidden)
		}
	}
	activityClass := assistantGeneratedClassBlock(
		t,
		rendered,
		"SkillActivityView",
	)
	for _, forbidden := range []string{
		"accountId",
		"runId",
		"consentId",
		"subscriptionId",
	} {
		if strings.Contains(activityClass, forbidden) {
			t.Fatalf("SkillActivityView exposed private field %q", forbidden)
		}
	}
	if !strings.Contains(
		activityClass,
		"final String? dataControlRequestId;",
	) {
		t.Fatal("SkillActivityView omitted typed data-control recovery target")
	}
	dataControlClass := assistantGeneratedClassBlock(
		t,
		rendered,
		"SkillDataControlRequest",
	)
	for _, forbidden := range []string{
		"accountId",
		"leaseOwner",
		"leaseToken",
		"leaseExpiresAt",
		"leaseHeartbeatAt",
	} {
		if strings.Contains(dataControlClass, forbidden) {
			t.Fatalf("SkillDataControlRequest exposed private field %q", forbidden)
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

func assistantGeneratedClassBlock(
	t *testing.T,
	generated string,
	className string,
) string {
	t.Helper()
	start := strings.Index(generated, "class "+className+" {")
	if start < 0 {
		t.Fatalf("generated Assistant response is missing class %s", className)
	}
	remainder := generated[start:]
	if next := strings.Index(remainder[1:], "\nclass "); next >= 0 {
		return remainder[:next+1]
	}
	return remainder
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
		"assistant_run.g.dart",
		"assistant_session.g.dart",
		"skill_subscription.g.dart",
	}, []string{"skill_subscription.g.dart"}, []string{
		"assistant_presentation_document.g.dart",
		"assistant_trace_event.g.dart",
	})
	for _, expected := range []string{
		"import '../generated/assistant/assistant_runtime_enums.g.dart';",
		"assistant_api_responses.g.dart",
		"assistant_runtime_failure.g.dart",
		"assistant_run.g.dart",
		"assistant_stream_event.g.dart",
		"assistant_session.g.dart",
		"skill_subscription.g.dart",
		"assistant_presentation_document.g.dart",
		"assistant_trace_event.g.dart",
		"assistant_operation_contracts.g.requests.g.dart",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("Assistant operation owner is missing %q", expected)
		}
	}
	if strings.Contains(rendered, "assistant_contracts.dart") {
		t.Fatal("Assistant operation owner retained the handwritten wire library")
	}
	if strings.Contains(rendered, "assistant_run_envelope.g.dart") {
		t.Fatal("Assistant operation owner retained the duplicate run envelope output")
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-001
func TestAssistantPackageSharedWireOutputsExcludeReplayFixtures(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	outputs, err := assistantPackageSharedWireOutputs(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if len(outputs) != 14 {
		t.Fatalf("Assistant package shared wire output count = %d, want 14: %v", len(outputs), outputs)
	}
	joined := strings.Join(outputs, "\n")
	for _, expected := range []string{
		"assistant_presentation_document.g.dart",
		"assistant_trace_event.g.dart",
		"device_context.g.dart",
		"tool_use.g.dart",
	} {
		if !strings.Contains(joined, expected) {
			t.Fatalf("Assistant package output list misses %q: %v", expected, outputs)
		}
	}
	for _, retired := range []string{
		"assistant_replay_case.g.dart",
		"assistant_run_response.g.dart",
	} {
		if strings.Contains(joined, retired) {
			t.Fatalf("Assistant package output list retained %q: %v", retired, outputs)
		}
	}
}

func TestAssistantObjectSchemaDependenciesRejectUnownedWireReferences(
	t *testing.T,
) {
	_, _, err := assistantObjectSchemaDependencies(
		&assistantContractSchema{
			DartClass:   "ExampleWire",
			LibraryPath: "example.g.dart",
			Fields: []assistantContractField{
				{Name: "unknown", Ref: "UnownedWire"},
			},
		},
		&fieldsFile{Entities: map[string]entityDef{}},
		nil,
	)
	if err == nil || !strings.Contains(err.Error(), "UnownedWire") {
		t.Fatalf("unowned Assistant schema ref was not rejected: %v", err)
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
	if _, err := os.Stat(filepath.Join(
		generatedDir,
		"assistant_run_envelope.g.dart",
	)); !os.IsNotExist(err) {
		t.Fatal("Assistant generator retained duplicate assistant_run_envelope.g.dart")
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
	for _, decoder := range []string{
		"decodeAssistantRunEnvelopeWire(Object? response)",
		"decodeAssistantSessionWire(Object? response)",
		"decodeSkillSubscriptionWire(Object? response)",
	} {
		if count := strings.Count(generated.String(), decoder); count != 1 {
			t.Fatalf("generated Assistant package owns %s %d times, want 1", decoder, count)
		}
	}
	runPayload, err := os.ReadFile(filepath.Join(generatedDir, "assistant_run.g.dart"))
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		"import 'assistant_api_responses.g.dart';",
		"final AssistantRunTerminalSnapshotView? terminalSnapshot;",
	} {
		if !strings.Contains(string(runPayload), expected) {
			t.Fatalf("generated Assistant run owner is missing %q", expected)
		}
	}
	skillSubscriptionPayload, err := os.ReadFile(filepath.Join(
		generatedDir,
		"skill_subscription.g.dart",
	))
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		"factory SkillSubscriptionSearchQueryPlanWire.fromWire(",
		"factory SkillSubscriptionTriggerWire.fromWire(",
		"factory SkillSubscriptionDestinationWire.fromWire(",
		"factory SkillSubscriptionWire.fromWire(",
		"Map<String, Object?> toWire()",
		"return SkillSubscriptionWire.fromWire(response.cast<String, Object?>())",
	} {
		if !strings.Contains(string(skillSubscriptionPayload), expected) {
			t.Fatalf("generated SkillSubscription wire owner is missing %q", expected)
		}
	}
	for _, forbidden := range []string{"toJson()", ".fromJson("} {
		if strings.Contains(string(skillSubscriptionPayload), forbidden) {
			t.Fatalf("generated SkillSubscription wire owner retained JSON codec %q", forbidden)
		}
	}
	responsePayload, err := os.ReadFile(filepath.Join(
		generatedDir,
		"assistant_api_responses.g.dart",
	))
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		"SkillSubscriptionWire.fromWire(item.cast<String, dynamic>())",
		"items.map((item) => item.toWire()).toList(growable: false)",
	} {
		if !strings.Contains(string(responsePayload), expected) {
			t.Fatalf("Assistant response wrapper is missing wire-owned nested codec %q", expected)
		}
	}
	if strings.Contains(string(responsePayload), "SkillSubscriptionWire.fromJson(") {
		t.Fatal("Assistant response wrapper retained SkillSubscriptionWire.fromJson")
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

func TestAssistantSkillSubscriptionRequestUsesOnlyPackageOwnedWireTypes(
	t *testing.T,
) {
	initializeTestContractGraph(t)
	graphOperations := activeMetadataSource.Graph().Operations
	payload, err := json.Marshal(graphOperations)
	if err != nil {
		t.Fatal(err)
	}
	var operations []appExposedOperation
	if err := json.Unmarshal(payload, &operations); err != nil {
		t.Fatal(err)
	}
	const operationID = "assistant.skill_subscription.CreateSkillSubscription"
	var operation appExposedOperation
	found := false
	for index := range operations {
		operations[index].CanonicalOperationID = graphOperations[index].ID
		operations[index].LocalOperationID = graphOperations[index].LocalID
		if operations[index].CanonicalOperationID == operationID {
			operation = operations[index]
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("fresh ContractGraph is missing %s", operationID)
	}
	model, dependencies, err := loadOperationRequestModel(
		operation,
		operation.RequestEntity,
	)
	if err != nil {
		t.Fatal(err)
	}
	models := make(map[string]requestModelSpec, len(dependencies)+1)
	models[model.Name] = model
	for name, dependency := range dependencies {
		models[name] = dependency
	}
	bindings := appRequestBindings{}
	if operation.RequestBindings != nil {
		bindings = *operation.RequestBindings
	}
	constants := appRequestConstants{}
	if operation.RequestConstants != nil {
		constants = *operation.RequestConstants
	}
	rendered, err := renderOperationRequestPart(
		requestLibrarySpec{
			OwnerImport: assistantOperationOwnerImport,
			Models:      models,
			Operations: []requestOperationSpec{
				{
					CanonicalOperationID: operationID,
					RequestType:          model.Name,
					RequestBodyKind:      operation.RequestBodyKind,
					RequestBindings:      bindings,
					RequestConstants:     constants,
				},
			},
		},
		"../../../assistant/assistant_operation_contracts.g.dart",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		"factory CreateAssistantSkillSubscriptionCommand.fromWire(",
		"final SkillSubscriptionSearchQueryPlanWire searchQueryPlan;",
		"final SkillSubscriptionTriggerWire trigger;",
		"final SkillSubscriptionDestinationWire destination;",
		`"searchQueryPlan": request.searchQueryPlan.toWire()`,
		`"trigger": request.trigger.toWire()`,
		`"destination": request.destination.toWire()`,
		"SkillSubscriptionSearchQueryPlanWire.fromWire(",
		"SkillSubscriptionTriggerWire.fromWire(",
		"SkillSubscriptionDestinationWire.fromWire(",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("generated SkillSubscription request misses %q:\n%s", expected, rendered)
		}
	}
	for _, ghost := range []string{
		"final class SkillSubscriptionSearchQueryPlan {",
		"final class SkillSubscriptionTrigger {",
		"final class SkillSubscriptionDestination {",
	} {
		if strings.Contains(rendered, ghost) {
			t.Fatalf("generated SkillSubscription request retained ghost model %q", ghost)
		}
	}
}

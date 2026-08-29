package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

func TestNormalizeRequestEnumUnknownMemberKeepsAbsenceDistinct(t *testing.T) {
	for name, input := range map[string]any{
		"array declaration":          []any{"active"},
		"object without declaration": map[string]any{"values": []any{"active"}},
		"explicit null": map[string]any{
			"values":                []any{"active"},
			"client_unknown_member": nil,
		},
	} {
		t.Run(name, func(t *testing.T) {
			if got := normalizeRequestEnumUnknownMember(input); got != "" {
				t.Fatalf("unknown member = %q, want absent", got)
			}
		})
	}
	if got := normalizeRequestEnumUnknownMember(map[string]any{
		"values":                []any{"active"},
		"client_unknown_member": "unknown",
	}); got != "unknown" {
		t.Fatalf("explicit unknown member = %q, want unknown", got)
	}
}

func TestRenderDomainWireEnumHonorsExplicitClientUnknownMember(t *testing.T) {
	members := []canonicalRequestEnumMember{
		{WireValue: "agenda", DartMember: "agenda"},
		{WireValue: "note", DartMember: "note"},
	}
	var output strings.Builder
	renderDomainWireEnum(&output, "PlanItemKind", members, "unknown")
	payload := output.String()
	for _, expected := range []string{
		`unknown("")`,
		`String() => PlanItemKind.unknown`,
		`_ => throw FormatException('$path has an invalid enum value')`,
		`PlanItemKind.unknown => throw StateError`,
	} {
		if !strings.Contains(payload, expected) {
			t.Fatalf("opt-in enum output missing %q:\n%s", expected, payload)
		}
	}
	if strings.Contains(payload, `_ => PlanItemKind.unknown`) {
		t.Fatalf("opt-in enum accepts malformed non-string wire values:\n%s", payload)
	}

	output.Reset()
	renderDomainWireEnum(&output, "PlanAcknowledgementMode", members, "")
	strictPayload := output.String()
	if !strings.Contains(
		strictPayload,
		`_ => throw FormatException('$path has an invalid enum value')`,
	) {
		t.Fatalf("non-opt-in enum does not reject unknown wire values:\n%s", strictPayload)
	}
	if strings.Contains(strictPayload, `unknown("")`) {
		t.Fatalf("non-opt-in enum gained an implicit unknown member:\n%s", strictPayload)
	}
}

func TestCrossDomainCanonicalEnumHasOneGeneratedOwner(t *testing.T) {
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
		"circle.circle_behavior_fact.ReportCircleBehavior": {},
		"content.content_behavior_fact.ReportBehaviors":    {},
	}
	lock := appContractLock{}
	for index, operation := range graphOperations {
		operation.CanonicalOperationID = graphSourceOperations[index].ID
		operation.LocalOperationID = graphSourceOperations[index].LocalID
		if _, selected := wanted[operation.CanonicalOperationID]; !selected {
			continue
		}
		if operation.ClientContract == nil {
			t.Fatalf("%s is not App-exposed", operation.CanonicalOperationID)
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if len(lock.AppExposedOperations) != len(wanted) {
		t.Fatalf(
			"cross-domain behavior operations = %d, want %d",
			len(lock.AppExposedOperations),
			len(wanted),
		)
	}
	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	artifacts, err := writeGeneratedOperationRequests(appDir, lock, provided)
	if err != nil {
		t.Fatal(err)
	}
	if len(artifacts) != len(wanted) {
		t.Fatalf("behavior request artifacts = %d, want %d", len(artifacts), len(wanted))
	}
	sharedPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/shared_operation_enums.g.dart",
	))
	if got := strings.Count(sharedPayload, "enum BehaviorEventType {"); got != 1 {
		t.Fatalf("shared BehaviorEventType declarations = %d, want 1", got)
	}
	if !strings.Contains(sharedPayload, `onboardingInterest("onboarding_interest");`) {
		t.Fatal("shared BehaviorEventType does not contain the canonical final member")
	}

	for domain, field := range map[string]string{
		"circle":  "final BehaviorEventType eventType;",
		"content": "final BehaviorEventType action;",
	} {
		ownerPayload := readGeneratedTestFile(t, filepath.Join(
			appDir,
			"packages/quwoquan_cloud_contracts/lib/src",
			domain,
			domain+"_operation_contracts.g.dart",
		))
		if strings.Contains(ownerPayload, "enum BehaviorEventType {") {
			t.Fatalf("%s retained a duplicate BehaviorEventType declaration", domain)
		}
		for _, directive := range []string{
			`import "../generated/shared_operation_enums.g.dart";`,
			`export "../generated/shared_operation_enums.g.dart";`,
		} {
			if strings.Count(ownerPayload, directive) != 1 {
				t.Fatalf("%s owner does not reference canonical shared enum once: %s", domain, directive)
			}
		}
		requestPayload := readGeneratedTestFile(t, filepath.Join(
			appDir,
			"packages/quwoquan_cloud_contracts/lib/src/generated/requests",
			domain,
			domain+"_operation_contracts.g.requests.g.dart",
		))
		if !strings.Contains(requestPayload, field) {
			t.Fatalf("%s request does not use shared BehaviorEventType: %s", domain, field)
		}
	}
}

func TestHomepageTypeUsesTheCrossDomainGeneratedEnumOwner(t *testing.T) {
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
		"circle.circle.GetCircle":         {},
		"entity.homepage.SearchHomepages": {},
	}
	lock := appContractLock{}
	for index, operation := range graphOperations {
		operation.CanonicalOperationID = graphSourceOperations[index].ID
		operation.LocalOperationID = graphSourceOperations[index].LocalID
		if _, selected := wanted[operation.CanonicalOperationID]; !selected {
			continue
		}
		if operation.ClientContract == nil {
			t.Fatalf("%s is not App-exposed", operation.CanonicalOperationID)
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if len(lock.AppExposedOperations) != len(wanted) {
		t.Fatalf(
			"HomepageType owner operations = %d, want %d",
			len(lock.AppExposedOperations),
			len(wanted),
		)
	}
	appDir := t.TempDir()
	if _, err := generateDomainOperationContracts(metadataDir, appDir, lock); err != nil {
		t.Fatal(err)
	}
	sharedPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/shared_operation_enums.g.dart",
	))
	if got := strings.Count(sharedPayload, "enum HomepageType {"); got != 1 {
		t.Fatalf("shared HomepageType declarations = %d, want 1", got)
	}
	for _, domain := range []string{"circle", "entity"} {
		ownerPayload := readGeneratedTestFile(t, filepath.Join(
			appDir,
			"packages/quwoquan_cloud_contracts/lib/src",
			domain,
			domain+"_operation_contracts.g.dart",
		))
		if strings.Contains(ownerPayload, "enum HomepageType {") {
			t.Fatalf("%s retained a duplicate HomepageType declaration", domain)
		}
		for _, directive := range []string{
			`import "../generated/shared_operation_enums.g.dart";`,
			`export "../generated/shared_operation_enums.g.dart";`,
		} {
			if strings.Count(ownerPayload, directive) != 1 {
				t.Fatalf("%s owner does not reference canonical HomepageType once: %s", domain, directive)
			}
		}
	}
	if _, err := os.Stat(filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/homepage_type.g.dart",
	)); !os.IsNotExist(err) {
		t.Fatalf("retired HomepageType owner was generated: %v", err)
	}
}

func TestCrossDomainEnumWithoutSharedCanonicalOwnerFailsClosed(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	members := []canonicalRequestEnumMember{{WireValue: "same", DartMember: "same"}}
	newSpec := func(domain string) *domainOperationContractSpec {
		return &domainOperationContractSpec{
			Domain:          domain,
			ExternalImports: map[string]struct{}{},
			ExternalExports: map[string]struct{}{},
			EnumMembers: map[string][]canonicalRequestEnumMember{
				"CoincidentallyNamedEnum": members,
			},
		}
	}
	err := externalizeSharedDomainEnums(map[string]*domainOperationContractSpec{
		generatedDomainOperationOwnerImport("circle"):  newSpec("circle"),
		generatedDomainOperationOwnerImport("content"): newSpec("content"),
	}, t.TempDir())
	if err == nil || !strings.Contains(err.Error(), "has no canonical _shared/types.yaml owner") {
		t.Fatalf("non-canonical cross-domain enum error = %v", err)
	}
}

func TestRetiredTravelDomainCannotRegenerateAppContracts(t *testing.T) {
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	for _, operation := range activeMetadataSource.Graph().Operations {
		if operation.Domain == "travel" {
			t.Fatalf(
				"retired travel domain operation %q can regenerate App contracts",
				operation.ID,
			)
		}
	}
}

func TestTagAppSurfaceUsesCanonicalResponseEntityNames(t *testing.T) {
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
		if operation.Domain == "tag" && operation.ClientContract != nil {
			lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
		}
	}
	if got := len(lock.AppExposedOperations); got != 4 {
		t.Fatalf("Tag App-exposed operations = %d, want 4", got)
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
	if got := len(artifacts); got != 4 {
		t.Fatalf("Tag typed request artifacts = %d, want 4", got)
	}
	ownerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/tag/tag_operation_contracts.g.dart",
	))
	requestPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/tag/tag_operation_contracts.g.requests.g.dart",
	))
	for _, expected := range []string{
		"final class TagResolveView",
		"final class TagChildrenSlice",
		"final class TagValidationResultView",
		"final class TagFeedbackResultView",
		"decodeTagFeedbackResultView",
	} {
		if !strings.Contains(ownerPayload, expected) {
			t.Fatalf("Tag owner is missing %q", expected)
		}
	}
	for _, expected := range []string{
		"final class ReportTagFeedbackCommand",
		"final class ResolveTagQuery",
		"final class ListTagChildrenQuery",
		"final class ValidateTagRefsQuery",
	} {
		if !strings.Contains(requestPayload, expected) {
			t.Fatalf("Tag request part is missing %q", expected)
		}
	}
	for _, legacy := range []string{
		"TagFeedbackAck",
		"TagResolve {",
		"TagValidationResult {",
		"tag_catalog_contracts.dart",
		"tag_feedback_fact_contracts.dart",
	} {
		if strings.Contains(ownerPayload, legacy) ||
			strings.Contains(requestPayload, legacy) {
			t.Fatalf("Tag generated ABI retained legacy type %q", legacy)
		}
	}
}

func TestDomainResponseBooleanWireTypeIsPrimitive(t *testing.T) {
	t.Parallel()

	if got := responseFieldReference(fieldDef{Name: "replayed", Type: "boolean"}); got != "" {
		t.Fatalf("boolean response field resolved as object reference %q", got)
	}
}

func TestCircleAppSurfaceUsesCanonicalResponseEntitiesAndOneGeneratedOwner(t *testing.T) {
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
		if operation.Domain != "circle" || operation.ClientContract == nil {
			continue
		}
		client := operation.ClientContract
		if got, want := client.DartImport, "../circle/circle_operation_contracts.g.dart"; got != want {
			t.Fatalf("Circle operation %s owner import = %q, want %q", operation.CanonicalOperationID, got, want)
		}
		if client.ResponseType != "void" && client.ResponseType != operation.ResponseEntity {
			t.Fatalf(
				"Circle operation %s response alias = %q, want response_entity %q",
				operation.CanonicalOperationID,
				client.ResponseType,
				operation.ResponseEntity,
			)
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if got := len(lock.AppExposedOperations); got != 64 {
		t.Fatalf("Circle App-exposed operations = %d, want 64", got)
	}

	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	artifacts, err := writeGeneratedOperationRequests(appDir, lock, provided)
	if err != nil {
		t.Fatal(err)
	}
	if got := len(artifacts); got != 64 {
		t.Fatalf("Circle typed request artifacts = %d, want 64", got)
	}
	ownerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/circle/circle_operation_contracts.g.dart",
	))
	for _, expected := range []string{
		"final class Circle {",
		"final class CirclePageSlice {",
		"final class CircleSearchResultView {",
		"final class CircleStatsWire {",
		"final class CircleImpactSummary {",
		"final class CircleGroupPageSlice {",
		"final class CircleMembershipPageSlice {",
		"CircleStatsWire decodeCircleStatsWire(Object? response)",
		`unknown("")`,
		`String() => PlanItemKind.unknown`,
		`PlanItemKind.unknown => throw StateError`,
		`String() => PlanTravelMode.unknown`,
		`PlanTravelMode.unknown => throw StateError`,
		`_ => throw FormatException('$path has an invalid enum value')`,
	} {
		if !strings.Contains(ownerPayload, expected) {
			t.Fatalf("Circle owner is missing %q", expected)
		}
	}
	for _, legacy := range []string{
		"CircleProjection",
		"CircleStatsSlice",
		"CircleImpactSlice",
		"decodeEmptyResponse",
		"circle_query_contracts.dart",
		"circle_contracts.dart",
	} {
		if strings.Contains(ownerPayload, legacy) {
			t.Fatalf("Circle generated ABI retained legacy owner/type %q", legacy)
		}
	}
}

func TestChatAppSurfaceUsesObjectLocalCanonicalResponsesAndOneGeneratedOwner(t *testing.T) {
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
		if operation.Domain != "chat" || operation.ClientContract == nil {
			continue
		}
		client := operation.ClientContract
		if got, want := client.DartImport, "../chat/chat_operation_contracts.g.dart"; got != want {
			t.Fatalf("Chat operation %s owner import = %q, want %q", operation.CanonicalOperationID, got, want)
		}
		if client.ResponseType != operation.ResponseEntity {
			t.Fatalf(
				"Chat operation %s response alias = %q, want response_entity %q",
				operation.CanonicalOperationID,
				client.ResponseType,
				operation.ResponseEntity,
			)
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if got := len(lock.AppExposedOperations); got != 33 {
		t.Fatalf("Chat App-exposed operations = %d, want 33", got)
	}

	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	artifacts, err := writeGeneratedOperationRequests(appDir, lock, provided)
	if err != nil {
		t.Fatal(err)
	}
	if got := len(artifacts); got != 33 {
		t.Fatalf("Chat typed request artifacts = %d, want 33", got)
	}
	ownerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/chat/chat_operation_contracts.g.dart",
	))
	for _, expected := range []string{
		"final class ChatConversation {",
		"final class ChatInboxPageSlice {",
		"final class ChatMessageView {",
		"final class ConversationPageSlice {",
		"final class ConversationMembershipCommandAck {",
		"final class MessagePageSlice {",
		"final class MessageReceiptPageSlice {",
		"final class GroupHome {",
	} {
		if !strings.Contains(ownerPayload, expected) {
			t.Fatalf("Chat owner is missing %q", expected)
		}
	}
	for _, legacy := range []string{
		"ChatCommandAck",
		"ChatConversationPageSlice",
		"ChatMessagePageSlice",
		"ChatMessageReceiptPageSlice",
		"conversation_contracts.dart",
		"message_contracts.dart",
		"contact_contracts.dart",
	} {
		if strings.Contains(ownerPayload, legacy) {
			t.Fatalf("Chat generated ABI retained legacy owner/type %q", legacy)
		}
	}
}

func TestContentAppSurfaceUsesCanonicalResponseEntitiesAndOneGeneratedOwner(t *testing.T) {
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
		if operation.Domain != "content" || operation.ClientContract == nil {
			continue
		}
		client := operation.ClientContract
		if got, want := client.DartImport, "../content/content_operation_contracts.g.dart"; got != want {
			t.Fatalf("Content operation %s owner import = %q, want %q", operation.CanonicalOperationID, got, want)
		}
		if client.ResponseType != "void" && client.ResponseType != operation.ResponseEntity {
			t.Fatalf(
				"Content operation %s response alias = %q, want response_entity %q",
				operation.CanonicalOperationID,
				client.ResponseType,
				operation.ResponseEntity,
			)
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if got := len(lock.AppExposedOperations); got != 44 {
		ids := make([]string, 0, len(lock.AppExposedOperations))
		for _, operation := range lock.AppExposedOperations {
			ids = append(ids, operation.CanonicalOperationID)
		}
		t.Fatalf("Content App-exposed operations = %d, want 44: %s", got, strings.Join(ids, ", "))
	}

	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	artifacts, err := writeGeneratedOperationRequests(appDir, lock, provided)
	if err != nil {
		t.Fatal(err)
	}
	if got := len(artifacts); got != 44 {
		t.Fatalf("Content typed request artifacts = %d, want 44", got)
	}
	ownerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/content/content_operation_contracts.g.dart",
	))
	recommendationOwnerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/recommendation/recommendation_operation_contracts.g.dart",
	))
	for _, expected := range []string{
		"final class AppConfigSlice {",
		"final class AppConfigActivationPolicy {",
		"final class ContentAppConfig {",
		"final class ContentAppConfigFeatureFlags {",
		"final class ContentAppConfigGrayRelease {",
		"decodeAppConfigSlice",
		`map["feature_flags"]`,
		`map["gray_release"]`,
		"final class ContentDiscoveryFeedPageSlice {",
		"final class PostPublicationReceipt {",
		"final class AuthorPostPageSlice {",
		"final class ContentPostDetailSlice {",
		"final class CommentPageSlice {",
		"final class ContentReactionCommandResult {",
		"final class MediaUploadSessionCommandResult {",
		"final class MyReportPageSlice {",
	} {
		if !strings.Contains(ownerPayload, expected) {
			t.Fatalf("Content owner is missing %q", expected)
		}
	}
	for _, legacy := range []string{
		"ContentCommentPageSlice",
		"ContentAuthorCommentPageSlice",
		"ContentPostPublicationReceipt",
		"ContentMediaAssetSlice",
		"ContentMyReportPage",
		"post_reader_queries.dart",
		"comment_contracts.dart",
		"media_contracts.dart",
		"final class IntersectionReason {",
	} {
		if strings.Contains(ownerPayload, legacy) {
			t.Fatalf("Content generated ABI retained legacy owner/type %q", legacy)
		}
	}
	if !strings.Contains(ownerPayload, "import \"../recommendation/recommendation_operation_contracts.g.dart\";") {
		t.Fatal("Content owner does not import the canonical Recommendation value-object owner")
	}
	if !strings.Contains(ownerPayload, "export \"../recommendation/recommendation_operation_contracts.g.dart\";") {
		t.Fatal("Content owner does not re-export the canonical Recommendation value-object ABI")
	}
	if !strings.Contains(recommendationOwnerPayload, "final class IntersectionReason {") ||
		!strings.Contains(recommendationOwnerPayload, "factory IntersectionReason.fromWire(") {
		t.Fatal("Recommendation owner is missing its public canonical IntersectionReason decoder")
	}
}

func TestUserAppSurfaceUsesCanonicalResponseEntitiesAndOneGeneratedOwner(t *testing.T) {
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
		if operation.Domain != "user" || operation.ClientContract == nil {
			continue
		}
		client := operation.ClientContract
		if got, want := client.DartImport, "../user/user_operation_contracts.g.dart"; got != want {
			t.Fatalf("User operation %s owner import = %q, want %q", operation.CanonicalOperationID, got, want)
		}
		if client.ResponseType != "void" && client.ResponseType != operation.ResponseEntity {
			t.Fatalf(
				"User operation %s response alias = %q, want response_entity %q",
				operation.CanonicalOperationID,
				client.ResponseType,
				operation.ResponseEntity,
			)
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if got := len(lock.AppExposedOperations); got != 73 {
		ids := make([]string, 0, len(lock.AppExposedOperations))
		for _, operation := range lock.AppExposedOperations {
			ids = append(ids, operation.CanonicalOperationID)
		}
		t.Fatalf("User App-exposed operations = %d, want 73: %s", got, strings.Join(ids, ", "))
	}

	appDir := t.TempDir()
	provided, err := generateDomainOperationContracts(metadataDir, appDir, lock)
	if err != nil {
		t.Fatal(err)
	}
	artifacts, err := writeGeneratedOperationRequests(appDir, lock, provided)
	if err != nil {
		t.Fatal(err)
	}
	if got := len(artifacts); got != 73 {
		t.Fatalf("User typed request artifacts = %d, want 73", got)
	}
	ownerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/user/user_operation_contracts.g.dart",
	))
	for _, expected := range []string{
		"final class AuthSessionGrant {",
		"final class FederatedLoginOutcome {",
		"final class ListCredentialsSlice {",
		"final class FollowingSubjectSlice {",
		"final class GreetingRequestSlice {",
		"final class FollowingRelationshipPageSlice {",
		"final class PersonaManagementSummaryView {",
		"enum ProposalStatus {",
		"final ProposalSource source;",
		"final ProposalStatus status;",
		"final class SearchSocialRelationsResult {",
		"enum UserSyncPatchKind {",
		"final class UserAvatarSyncPatchPayload {",
		"final class ConversationAvatarSyncPatchPayload {",
		"final class UserSyncPatch {",
		"final class PullUserSyncSlice {",
		"decodePullUserSyncSlice",
	} {
		if !strings.Contains(ownerPayload, expected) {
			t.Fatalf("User owner is missing %q", expected)
		}
	}
	for _, legacy := range []string{
		"AuthLoginResultDto",
		"DevicePushEndpointCommandResultDto",
		"PersonaManagementSummaryProjection",
		"PersonaRelationshipPage",
		"RelationshipCapabilityResult",
		"public_profile_query_contracts.dart",
		"persona_relationship_contracts.dart",
	} {
		if strings.Contains(ownerPayload, legacy) {
			t.Fatalf("User generated ABI retained legacy owner/type %q", legacy)
		}
	}
}

func TestSearchAppSurfaceUsesOneGeneratedDomainOwner(t *testing.T) {
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
		if operation.Domain != "search" || operation.ClientContract == nil {
			continue
		}
		if got, want := operation.ClientContract.DartImport, "../search/search_operation_contracts.g.dart"; got != want {
			t.Fatalf("Search operation %s owner import = %q, want %q", operation.CanonicalOperationID, got, want)
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if got := len(lock.AppExposedOperations); got != 7 {
		t.Fatalf("Search App-exposed operations = %d, want 7", got)
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
	if got := len(artifacts); got != 7 {
		t.Fatalf("Search typed request artifacts = %d, want 7", got)
	}
	ownerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/search/search_operation_contracts.g.dart",
	))
	requestPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/search/search_operation_contracts.g.requests.g.dart",
	))
	for _, expected := range []string{
		"final class RecentSearchCommandAck",
		"final class RecentSearchEntrySlice",
		"final class RecentSearchEntryWire",
		"final class SearchFeedbackAck",
		"final class SearchTermHeatSlice",
		"export \"../generated/search/search_response_view.g.dart\";",
	} {
		if !strings.Contains(ownerPayload, expected) {
			t.Fatalf("Search owner is missing %q", expected)
		}
	}
	if strings.Contains(ownerPayload, "import \"../generated/search/search_response_view.g.dart\";") {
		t.Fatal("Search owner imported an external response that it only re-exports")
	}
	for _, expected := range []string{
		"final class UpsertRecentSearchCommand",
		"final class ReportSearchFeedbackCommand",
		"final class CanonicalSearchQuery",
		"final class ListHotQueriesQuery",
		"encodeSearchSearchIndexViewSearchGeneratedRequest",
	} {
		if !strings.Contains(requestPayload, expected) {
			t.Fatalf("Search request part is missing %q", expected)
		}
	}
	for _, legacy := range []string{
		"HotQuerySlice",
		"RecentSearchEntryWireDto",
		"hot_query_contracts.dart",
		"recent_search_contracts.dart",
		"search_feedback_contracts.dart",
		"search_query_contracts.dart",
	} {
		if strings.Contains(ownerPayload, legacy) ||
			strings.Contains(requestPayload, legacy) {
			t.Fatalf("Search generated ABI retained legacy type/path %q", legacy)
		}
	}
}

func TestEntityAppSurfaceUsesCanonicalProjectionDependencies(t *testing.T) {
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
		if operation.Domain != "entity" || operation.ClientContract == nil {
			continue
		}
		lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
	}
	if got := len(lock.AppExposedOperations); got != 17 {
		t.Fatalf("Entity App-exposed operations = %d, want 17", got)
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
	if got := len(artifacts); got != 17 {
		t.Fatalf("Entity typed request artifacts = %d, want 17", got)
	}
	ownerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/entity/entity_operation_contracts.g.dart",
	))
	recommendationOwnerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/recommendation/recommendation_operation_contracts.g.dart",
	))
	requestPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/entity/entity_operation_contracts.g.requests.g.dart",
	))
	for _, expected := range []string{
		"final class ObjectPageBundle",
		"final class EntityImpactSummary",
		"final class HomepageSearchSlice",
		"decodeObjectPageBundle",
	} {
		if !strings.Contains(ownerPayload, expected) {
			t.Fatalf("Entity owner is missing %q", expected)
		}
	}
	for _, forbidden := range []string{
		"final class IntersectionReason",
		"final class IntersectionTextSpan",
	} {
		if strings.Contains(ownerPayload, forbidden) {
			t.Fatalf("Entity owner duplicated Recommendation type %q", forbidden)
		}
	}
	if !strings.Contains(recommendationOwnerPayload, "final class IntersectionReason") ||
		!strings.Contains(recommendationOwnerPayload, "final class IntersectionTextSpan") {
		t.Fatal("Recommendation owner is missing Entity response dependencies")
	}
	if !strings.Contains(ownerPayload, "export \"../recommendation/recommendation_operation_contracts.g.dart\";") {
		t.Fatal("Entity owner does not re-export the canonical Recommendation value-object ABI")
	}
	for _, expected := range []string{
		"final class HomepageSearchQuery",
		"encodeEntityHomepageSearchHomepagesGeneratedRequest",
	} {
		if !strings.Contains(requestPayload, expected) {
			t.Fatalf("Entity request part is missing %q", expected)
		}
	}
	for _, legacy := range []string{
		"HomepageDetailProjection",
		"homepage_models.dart",
		"homepage_queries.dart",
		"homepage_review_contracts.dart",
	} {
		if strings.Contains(ownerPayload, legacy) || strings.Contains(requestPayload, legacy) {
			t.Fatalf("Entity generated ABI retained legacy type/path %q", legacy)
		}
	}
}

func TestIntegrationLocationAppSurfaceUsesGeneratedSliceOwner(t *testing.T) {
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
		if operation.Domain == "integration" &&
			operation.ObjectID == "integration.location" &&
			operation.ClientContract != nil {
			lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
		}
	}
	if got := len(lock.AppExposedOperations); got != 2 {
		t.Fatalf("Integration location App-exposed operations = %d, want 2", got)
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
	if got := len(artifacts); got != 2 {
		t.Fatalf("Integration location typed request artifacts = %d, want 2", got)
	}
	ownerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/integration/integration_operation_contracts.g.dart",
	))
	requestPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/integration/integration_operation_contracts.g.requests.g.dart",
	))
	for _, expected := range []string{
		"final class LocationPoi",
		"final class LocationPoiListSlice",
		"LocationPoiListSlice decodeLocationPoiListSlice(Object? response)",
		"final class NearbyLocationQueryParams",
		"final class LocationSearchQueryParams",
	} {
		if !strings.Contains(ownerPayload, expected) &&
			!strings.Contains(requestPayload, expected) {
			t.Fatalf("Integration generated ABI is missing %q", expected)
		}
	}
	for _, legacy := range []string{
		"LocationPoiDto",
		"location_queries.dart",
		"factory LocationPoi.fromMap",
	} {
		if strings.Contains(ownerPayload, legacy) ||
			strings.Contains(requestPayload, legacy) {
			t.Fatalf("Integration generated ABI retained legacy type/path %q", legacy)
		}
	}
}

func TestNotificationAppSurfacesUseOneGeneratedDomainOwner(t *testing.T) {
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
		if operation.Domain == "notification" && operation.ClientContract != nil {
			lock.AppExposedOperations = append(lock.AppExposedOperations, operation)
		}
	}
	if got := len(lock.AppExposedOperations); got != 6 {
		t.Fatalf("Notification App-exposed operations = %d, want 6", got)
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
	if got := len(artifacts); got != 6 {
		t.Fatalf("Notification typed request artifacts = %d, want 6", got)
	}
	ownerPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/notification/notification_operation_contracts.g.dart",
	))
	requestPayload := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/requests/notification/notification_operation_contracts.g.requests.g.dart",
	))
	for _, expected := range []string{
		"final class AppMessage",
		"final class AppMessageInboxSlice",
		"final class AppMessageUnreadCountSlice",
		"final class AckIncomingCallPresentationResult",
		"enum NotificationType",
		"_requiredNonBlankString(",
		"_requiredNonNegativeInt(",
		"final class AckIncomingCallPresentationCommand",
		"final class ListAppMessagesQuery",
	} {
		if !strings.Contains(ownerPayload, expected) &&
			!strings.Contains(requestPayload, expected) {
			t.Fatalf("Notification generated ABI is missing %q", expected)
		}
	}
	for _, legacy := range []string{
		"AckIncomingCallPresentationResultDto",
		"app_message_contracts.dart",
		"incoming_call_delivery_contracts.dart",
		"factory AppMessage.fromMap",
	} {
		if strings.Contains(ownerPayload, legacy) ||
			strings.Contains(requestPayload, legacy) {
			t.Fatalf("Notification generated ABI retained legacy type/path %q", legacy)
		}
	}
}

func TestResponseDecoderPreservesConstraintsAfterNullable(t *testing.T) {
	expression, err := responseFieldDecodeExpression(
		fieldDef{
			Name:        "label",
			Type:        "string",
			Constraints: []string{"NULLABLE", "NOT_BLANK"},
		},
		"map['label']",
		"'$path.label'",
	)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(expression, "_requiredNonBlankString") {
		t.Fatalf("nullable response constraint was discarded: %s", expression)
	}
}

func TestResponseDecoderEnforcesCanonicalIntegerBounds(t *testing.T) {
	expression, err := responseFieldDecodeExpression(
		fieldDef{
			Name:        "rating",
			Type:        "int",
			Constraints: []string{"NOT_NULL", "MIN_1", "MAX_5"},
		},
		"map['rating']",
		"'$path.rating'",
	)
	if err != nil {
		t.Fatal(err)
	}
	want := "_requiredBoundedInt(map['rating'], '$path.rating', min: 1, max: 5)"
	if expression != want {
		t.Fatalf("bounded integer decoder = %q, want %q", expression, want)
	}
}

func assertCanonicalRequestInputs(
	t *testing.T,
	operations []appExposedOperation,
) {
	t.Helper()
	enumValues, err := loadCanonicalRequestEnumValues()
	if err != nil {
		t.Fatal(err)
	}
	var failures []string
	for _, operation := range operations {
		model, _, loadErr := loadOperationRequestModel(
			operation,
			operation.RequestEntity,
		)
		if loadErr != nil {
			failures = append(failures, loadErr.Error())
			continue
		}
		bindings := appRequestBindings{}
		if operation.RequestBindings != nil {
			bindings = *operation.RequestBindings
		}
		for _, validate := range []func() error{
			func() error {
				return validateRequestModelCanonicalEnums(
					operation.CanonicalOperationID,
					model,
					enumValues,
				)
			},
			func() error {
				return validateRequestModelDefaults(
					operation.CanonicalOperationID,
					model,
				)
			},
			func() error {
				return validateRequestModelBindings(
					operation.CanonicalOperationID,
					model,
					operation.RequestBodyKind,
					bindings,
					operation.RequestConstants,
				)
			},
		} {
			if validateErr := validate(); validateErr != nil {
				failures = append(failures, validateErr.Error())
			}
		}
	}
	if len(failures) != 0 {
		t.Fatalf("Travel canonical request gaps:\n%s", strings.Join(failures, "\n"))
	}
}

func readGeneratedTestFile(t *testing.T, path string) string {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(payload)
}

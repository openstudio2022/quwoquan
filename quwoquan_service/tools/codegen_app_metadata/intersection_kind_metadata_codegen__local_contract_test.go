package main

import (
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
	"quwoquan_service/tools/recintersectionmeta"
)

func loadIntersectionGeneratedTestRegistry(
	t *testing.T,
) (string, *recintersectionmeta.Registry, []string) {
	t.Helper()
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataDocumentSource(metadataDir, []string{
		"_shared/types.yaml",
		intersectionKindRegistryMetadataPath,
	}); err != nil {
		t.Fatalf("initialize metadata source: %v", err)
	}
	sourcePath, registry, err := readIntersectionGeneratedMetadata(metadataDir)
	if err != nil {
		t.Fatalf("read intersection generated metadata: %v", err)
	}
	canonicalEnums, err := loadCanonicalSharedEnumValues()
	if err != nil {
		t.Fatalf("load canonical shared enums: %v", err)
	}
	return sourcePath, registry, canonicalEnums["IntersectionDimension"]
}

func readIntersectionGeneratedTestFile(t *testing.T, path string) string {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read generated file %s: %v", path, err)
	}
	return string(payload)
}

// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-001
func TestCanonicalIntersectionMetadataHasLayeredOwnersWithoutLegacyOutput(
	t *testing.T,
) {
	sourcePath, registry, _ := loadIntersectionGeneratedTestRegistry(t)
	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, "canonical-intersection-graph")
	writeIntersectionFeedbackContracts(appDir, sourcePath, registry)
	writeCanonicalIntersectionMetadata(appDir, sourcePath, registry)

	paths := map[string]string{
		"feedback": filepath.Join(
			appDir,
			"packages/quwoquan_cloud_contracts/lib/src/generated/recommendation/"+
				"intersection_feedback_contracts.g.dart",
		),
		"vocabulary": filepath.Join(
			appDir,
			"packages/quwoquan_cloud_contracts/lib/src/generated/recommendation/"+
				"intersection_contract_vocabulary.g.dart",
		),
		"application": recommendationFeatureProfileApplicationOutputPath(
			appDir,
			"intersection_client_policy.g.dart",
		),
		"presentation": recommendationFeatureProfilePresentationOutputPath(
			appDir,
			"intersection_display_metadata.g.dart",
		),
		"actionKeyMeta": recommendationFeatureProfilePresentationOutputPath(
			appDir,
			"intersection_kind_metadata.g.dart",
		),
	}
	outputs := map[string]string{}
	for name, path := range paths {
		outputs[name] = readIntersectionGeneratedTestFile(t, path)
		relative, err := filepath.Rel(appDir, path)
		if err != nil {
			t.Fatalf("relative generated path: %v", err)
		}
		if _, ok := generatedManifestOutputs[filepath.ToSlash(relative)]; !ok {
			t.Fatalf("generated manifest did not record %s", relative)
		}
	}
	if got, want := len(generatedManifestOutputs), len(paths); got != want {
		t.Fatalf("intersection manifest outputs = %d, want %d", got, want)
	}

	for _, symbol := range []string{
		"enum IntersectionDimension",
		"enum IntersectionLifecycleState",
		"enum IntersectionVertical",
		"enum IntersectionMoment",
		"enum IntersectionGateKey",
		"enum IntersectionActionDispatch",
		"enum IntersectionActionKey",
		"enum IntersectionActionTier",
		"enum IntersectionObjectKind",
	} {
		if !strings.Contains(outputs["vocabulary"], symbol) {
			t.Fatalf("package vocabulary misses %q", symbol)
		}
	}
	for _, forbidden := range []string{
		"routeId",
		"assetKind",
		"iconKey",
		"visualTone",
		"intersectionFeedback",
	} {
		if strings.Contains(outputs["vocabulary"], forbidden) {
			t.Fatalf("package vocabulary leaks %q", forbidden)
		}
	}

	for _, symbol := range []string{
		"final class IntersectionActionPolicy",
		"intersectionActionPolicies",
		"intersectionRouteIdByObjectKind",
		"intersectionObjectKindForObjectType",
	} {
		if !strings.Contains(outputs["application"], symbol) {
			t.Fatalf("application policy misses %q", symbol)
		}
	}
	for _, forbidden := range []string{
		"iconKey",
		"visualTone",
		"assetKind",
		"presentation/",
		"adapters/",
		"package:flutter/",
		"runtime/",
	} {
		if strings.Contains(outputs["application"], forbidden) {
			t.Fatalf("application policy leaks %q", forbidden)
		}
	}

	for _, symbol := range []string{
		"final class IntersectionKindDisplayMetadata",
		"intersectionKindDisplayMetadata",
		"intersectionVisualToneByIconKey",
		"intersectionFallbackIconKeyByDimension",
		"intersectionAssetKindByObjectKind",
	} {
		if !strings.Contains(outputs["presentation"], symbol) {
			t.Fatalf("presentation metadata misses %q", symbol)
		}
	}
	for _, forbidden := range []string{
		"routeId",
		"objectType",
		"requiredGates",
		"IntersectionActionTier",
		"IntersectionActionDispatch",
		"adapters/",
		"runtime/",
	} {
		if strings.Contains(outputs["presentation"], forbidden) {
			t.Fatalf("presentation metadata leaks %q", forbidden)
		}
	}
	if strings.Contains(outputs["presentation"], "required this.kind") ||
		strings.Contains(outputs["presentation"], "required this.tone") {
		t.Fatal("presentation metadata regenerates dead kind/tone fields")
	}

	for _, symbol := range []string{
		"class IntersectionActionKeyMeta",
		"intersectionActionKeyMeta",
		"intersectionActionKeys",
	} {
		if !strings.Contains(outputs["actionKeyMeta"], symbol) {
			t.Fatalf("action key metadata misses %q", symbol)
		}
	}
	for _, forbidden := range []string{
		"iconKey",
		"visualTone",
		"IntersectionKindDisplayMetadata",
	} {
		if strings.Contains(outputs["actionKeyMeta"], forbidden) {
			t.Fatalf("action key metadata leaks %q", forbidden)
		}
	}

	for _, symbol := range []string{
		"intersectionFeedbackKinds",
		"intersectionFeedbackKindNotInterested",
		"intersectionFeedbackKindDismiss",
		"intersectionFeedbackKindRejectGreeting",
		"intersectionFeedbackKindLeaveCircle",
	} {
		if !strings.Contains(outputs["feedback"], symbol) {
			t.Fatalf("shared feedback contract missing %s", symbol)
		}
		for name, payload := range outputs {
			if name != "feedback" && strings.Contains(payload, symbol) {
				t.Fatalf("%s output duplicates feedback symbol %s", name, symbol)
			}
		}
	}
}

// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-001
func TestIntersectionMetadataMatchesEveryCanonicalRegistryEntry(t *testing.T) {
	sourcePath, registry, _ := loadIntersectionGeneratedTestRegistry(t)
	vocabulary := renderIntersectionContractVocabularyDart(sourcePath, registry)
	application := renderIntersectionClientPolicyDart(sourcePath, registry)
	presentation := renderIntersectionDisplayMetadataDart(sourcePath, registry)
	feedback := renderIntersectionFeedbackContractsDart(sourcePath, registry)

	enums := []struct {
		name   string
		values []string
	}{
		{"IntersectionDimension", registry.Dimensions},
		{"IntersectionLifecycleState", registry.LifecycleStates},
		{"IntersectionVertical", registry.Verticals},
		{"IntersectionMoment", registry.Moments},
		{"IntersectionGateKey", registry.GateKeys},
		{"IntersectionActionDispatch", registry.ActionDispatch},
	}
	actionKeys := make([]string, 0, len(registry.ActionHintLegend))
	for key := range registry.ActionHintLegend {
		actionKeys = append(actionKeys, key)
	}
	sort.Strings(actionKeys)
	enums = append(enums, struct {
		name   string
		values []string
	}{"IntersectionActionKey", actionKeys})
	objectKinds := make([]string, 0, len(registry.ObjectKinds))
	for _, item := range registry.ObjectKinds {
		objectKinds = append(objectKinds, item.Kind)
	}
	enums = append(enums, struct {
		name   string
		values []string
	}{"IntersectionObjectKind", objectKinds})
	for _, enum := range enums {
		for _, value := range enum.values {
			mapping := "      " + `"` + value + `"` + " => " + enum.name + "." +
				intersectionDartEnumMemberName(value)
			if !strings.Contains(vocabulary, mapping) {
				t.Fatalf("%s misses canonical value %q", enum.name, value)
			}
		}
	}

	if got, want := len(registry.ActionKeyMeta), 13; got != want {
		t.Fatalf("action policy count = %d, want %d", got, want)
	}
	for key := range registry.ActionKeyMeta {
		needle := "IntersectionActionKey." + intersectionDartEnumMemberName(key) +
			": IntersectionActionPolicy("
		if !strings.Contains(application, needle) {
			t.Fatalf("application policy misses action %q", key)
		}
	}
	if got, want := len(registry.ObjectKinds), 12; got != want {
		t.Fatalf("object kind count = %d, want %d", got, want)
	}
	if got, want := len(registry.ObjectTypeBindings), 30; got != want {
		t.Fatalf("object type binding count = %d, want %d", got, want)
	}
	if got := strings.Count(application, " => IntersectionObjectKind."); got != 30 {
		t.Fatalf("generated object type binding count = %d, want 30", got)
	}
	routeCount := 0
	assetCount := 0
	for _, item := range registry.ObjectKinds {
		if strings.TrimSpace(item.RouteID) != "" {
			routeCount++
			needle := "IntersectionObjectKind." +
				intersectionDartEnumMemberName(item.Kind) + ": " +
				`"` + item.RouteID + `"`
			if !strings.Contains(application, needle) {
				t.Fatalf("application route policy misses %q", item.Kind)
			}
		}
		if strings.TrimSpace(item.AssetKind) != "" {
			assetCount++
			needle := "IntersectionObjectKind." +
				intersectionDartEnumMemberName(item.Kind) + ": " +
				`"` + item.AssetKind + `"`
			if !strings.Contains(presentation, needle) {
				t.Fatalf("presentation asset policy misses %q", item.Kind)
			}
		}
	}
	if routeCount != 11 {
		t.Fatalf("route parity = %d, want 11", routeCount)
	}
	if got, want := len(registry.Kinds), 16; got != want {
		t.Fatalf("display kind count = %d, want %d", got, want)
	}
	if got := strings.Count(presentation, "IntersectionKindDisplayMetadata(iconKey:"); got != 16 {
		t.Fatalf("generated display kind count = %d, want 16", got)
	}
	if got, want := len(registry.VisualToneByIcon), 13; got != want {
		t.Fatalf("visual tone count = %d, want %d", got, want)
	}
	if got, want := len(registry.IconKeyByDimension), 5; got != want {
		t.Fatalf("dimension fallback count = %d, want %d", got, want)
	}
	if got, want := assetCount, 10; got != want {
		t.Fatalf("asset kind mapping count = %d, want %d", got, want)
	}
	if got, want := len(registry.FeedbackKinds), 4; got != want {
		t.Fatalf("feedback count = %d, want %d", got, want)
	}
	for _, kind := range registry.FeedbackKinds {
		if !strings.Contains(feedback, `"`+kind+`"`) {
			t.Fatalf("feedback output misses %q", kind)
		}
	}
}

// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-001
func TestIntersectionFeedbackWriterHasIndependentLifecycle(t *testing.T) {
	sourcePath, registry, _ := loadIntersectionGeneratedTestRegistry(t)
	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, "feedback-only-graph")
	writeIntersectionFeedbackContracts(appDir, sourcePath, registry)
	if got := len(generatedManifestOutputs); got != 1 {
		t.Fatalf("feedback-only writer recorded %d outputs, want 1", got)
	}
	legacy := filepath.Join(
		appDir,
		"lib/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart",
	)
	if _, err := os.Stat(legacy); !os.IsNotExist(err) {
		t.Fatalf("feedback writer must not create legacy output, stat err=%v", err)
	}
}

// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-001
func TestIntersectionMetadataRejectsAmbiguousOrCrossOwnerVocabulary(t *testing.T) {
	_, registry, canonicalDimensions := loadIntersectionGeneratedTestRegistry(t)

	t.Run("duplicate feedback", func(t *testing.T) {
		copy := *registry
		copy.FeedbackKinds = append(
			append([]string(nil), registry.FeedbackKinds...),
			registry.FeedbackKinds[0],
		)
		err := validateIntersectionGeneratedMetadata(&copy, canonicalDimensions)
		if err == nil || !strings.Contains(err.Error(), "duplicate") {
			t.Fatalf("duplicate feedback must fail closed, got %v", err)
		}
	})

	t.Run("Dart member collision", func(t *testing.T) {
		copy := *registry
		copy.FeedbackKinds = []string{"same-value", "same_value"}
		err := validateIntersectionGeneratedMetadata(&copy, canonicalDimensions)
		if err == nil || !strings.Contains(err.Error(), "map to Dart member") {
			t.Fatalf("Dart member collision must fail closed, got %v", err)
		}
	})

	t.Run("dimension owner drift", func(t *testing.T) {
		copy := *registry
		copy.Dimensions = append([]string(nil), registry.Dimensions...)
		copy.Dimensions[0] = "drifted"
		err := validateIntersectionGeneratedMetadata(&copy, canonicalDimensions)
		if err == nil || !strings.Contains(err.Error(), "canonical IntersectionDimension") {
			t.Fatalf("dimension owner drift must fail closed, got %v", err)
		}
	})

	t.Run("duplicate object kind", func(t *testing.T) {
		copy := *registry
		copy.ObjectKinds = append(
			append([]recintersectionmeta.ObjectKindDef(nil), registry.ObjectKinds...),
			registry.ObjectKinds[0],
		)
		err := validateIntersectionGeneratedMetadata(&copy, canonicalDimensions)
		if err == nil || !strings.Contains(err.Error(), "duplicate kind") {
			t.Fatalf("duplicate object kind must fail closed, got %v", err)
		}
	})

	t.Run("duplicate required gate", func(t *testing.T) {
		copy := *registry
		copy.ActionKeyMeta = cloneIntersectionActionMeta(registry.ActionKeyMeta)
		keys := make([]string, 0, len(copy.ActionKeyMeta))
		for key := range copy.ActionKeyMeta {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		key := keys[0]
		meta := copy.ActionKeyMeta[key]
		meta.RequiredGates = []string{"login", "login"}
		copy.ActionKeyMeta[key] = meta
		err := validateIntersectionGeneratedMetadata(&copy, canonicalDimensions)
		if err == nil || !strings.Contains(err.Error(), "duplicate") {
			t.Fatalf("duplicate required gate must fail closed, got %v", err)
		}
	})

	t.Run("missing kind tone", func(t *testing.T) {
		copy := *registry
		copy.VisualToneByIcon = cloneIntersectionStringMap(registry.VisualToneByIcon)
		delete(copy.VisualToneByIcon, registry.Kinds[0].IconKey)
		err := validateIntersectionGeneratedMetadata(&copy, canonicalDimensions)
		if err == nil || !strings.Contains(err.Error(), "has no visual tone") {
			t.Fatalf("missing visual tone must fail closed, got %v", err)
		}
	})
}

// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-001
func TestIntersectionMetadataRenderingIsMapOrderIndependent(t *testing.T) {
	sourcePath, registry, _ := loadIntersectionGeneratedTestRegistry(t)
	copy := *registry
	copy.ActionHintLegend = reverseIntersectionStringMap(registry.ActionHintLegend)
	copy.ActionKeyMeta = reverseIntersectionActionMeta(registry.ActionKeyMeta)
	copy.VisualToneByIcon = reverseIntersectionStringMap(registry.VisualToneByIcon)
	copy.IconKeyByDimension = reverseIntersectionStringMap(registry.IconKeyByDimension)

	renderers := []struct {
		name string
		run  func(*recintersectionmeta.Registry) string
	}{
		{"feedback", func(value *recintersectionmeta.Registry) string {
			return renderIntersectionFeedbackContractsDart(sourcePath, value)
		}},
		{"vocabulary", func(value *recintersectionmeta.Registry) string {
			return renderIntersectionContractVocabularyDart(sourcePath, value)
		}},
		{"application", func(value *recintersectionmeta.Registry) string {
			return renderIntersectionClientPolicyDart(sourcePath, value)
		}},
		{"presentation", func(value *recintersectionmeta.Registry) string {
			return renderIntersectionDisplayMetadataDart(sourcePath, value)
		}},
		{"actionKeyMeta", func(value *recintersectionmeta.Registry) string {
			return renderIntersectionActionKeyMetadataDart(sourcePath, value)
		}},
	}
	for _, renderer := range renderers {
		if got, want := renderer.run(&copy), renderer.run(registry); got != want {
			t.Fatalf("%s rendering depends on Go map insertion order", renderer.name)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestIntersectionDimensionHasOnePackageOwner(t *testing.T) {
	_, _, canonicalDimensions := loadIntersectionGeneratedTestRegistry(t)
	members := make([]canonicalRequestEnumMember, 0, len(canonicalDimensions))
	for _, value := range canonicalDimensions {
		members = append(members, canonicalRequestEnumMember{
			WireValue:  value,
			DartMember: intersectionDartEnumMemberName(value),
		})
	}
	spec := domainOperationContractSpec{
		Domain:                   "content",
		Models:                   map[string]requestModelSpec{},
		ResponseEntities:         map[string]struct{}{},
		ExternalResponseEntities: map[string]struct{}{},
		ExternalImports:          map[string]struct{}{},
		ExternalExports:          map[string]struct{}{},
		EnumMembers: map[string][]canonicalRequestEnumMember{
			"IntersectionDimension": members,
		},
	}
	if err := finalizeDomainOperationContractSpec(&spec); err != nil {
		t.Fatalf("externalize IntersectionDimension: %v", err)
	}
	if _, duplicate := spec.EnumMembers["IntersectionDimension"]; duplicate {
		t.Fatal("content operation owner still declares IntersectionDimension")
	}
	if _, ok := spec.ExternalImports[packageInternalIntersectionContractVocabularyImport]; !ok {
		t.Fatal("content operation owner does not import canonical vocabulary")
	}
	if _, ok := spec.ExternalExports[packageInternalIntersectionContractVocabularyImport]; !ok {
		t.Fatal("content operation owner does not export canonical vocabulary")
	}
	rendered, err := renderDomainOperationContract(spec)
	if err != nil {
		t.Fatalf("render content owner: %v", err)
	}
	if strings.Contains(rendered, "enum IntersectionDimension") {
		t.Fatal("content operation owner duplicates IntersectionDimension")
	}
	if strings.Count(rendered, packageInternalIntersectionContractVocabularyImport) != 2 {
		t.Fatalf("content owner must import and export canonical vocabulary:\n%s", rendered)
	}
	if strings.Contains(rendered, "package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart") {
		t.Fatal("package-internal operation owner imports its own public barrel")
	}

	broken := spec
	broken.EnumMembers = map[string][]canonicalRequestEnumMember{
		"IntersectionDimension": append(
			[]canonicalRequestEnumMember(nil),
			members...,
		),
	}
	broken.EnumMembers["IntersectionDimension"][0].DartMember = "drifted"
	delete(broken.ExternalImports, packageInternalIntersectionContractVocabularyImport)
	delete(broken.ExternalExports, packageInternalIntersectionContractVocabularyImport)
	if err := finalizeDomainOperationContractSpec(&broken); err == nil ||
		!strings.Contains(err.Error(), "want") {
		t.Fatalf("drifted operation enum mapping must fail closed, got %v", err)
	}

	oldSHA := activeContractSHA256
	t.Cleanup(func() { activeContractSHA256 = oldSHA })
	activeContractSHA256 = strings.Repeat("a", 64)
	appDir := t.TempDir()
	beginGeneratedManifestForTest(t, appDir, activeContractSHA256)
	lock := appContractLock{AppExposedOperations: []appExposedOperation{{
		CanonicalOperationID: "recommendation.recommendation_feature_profile_view.List",
		Domain:               "recommendation",
		ClientContract: &appClientContract{
			DartImport: generatedDomainOperationOwnerImport("recommendation"),
		},
	}}}
	if err := generateDomainOperationPublicBarrels(appDir, lock); err != nil {
		t.Fatalf("generate recommendation public barrel: %v", err)
	}
	barrel := readIntersectionGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/generated/"+
			"recommendation_contracts.dart",
	))
	if !strings.Contains(
		barrel,
		"export '../src/generated/recommendation/"+
			"intersection_contract_vocabulary.g.dart';",
	) {
		t.Fatal("recommendation public barrel does not export intersection vocabulary")
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestIntersectionGeneratedTargetsOwnCanonicalOutputsAndRetireLegacy(t *testing.T) {
	appDir := t.TempDir()
	application := recommendationFeatureProfileApplicationOutputPath(
		appDir,
		"intersection_client_policy.g.dart",
	)
	presentation := recommendationFeatureProfilePresentationOutputPath(
		appDir,
		"intersection_display_metadata.g.dart",
	)
	for label, target := range map[string]string{
		"application":  application,
		"presentation": presentation,
	} {
		if relative, err := filepath.Rel(appDir, target); err != nil {
			t.Fatalf("%s target relative path: %v", label, err)
		} else if !strings.HasPrefix(
			filepath.ToSlash(relative),
			"lib/service/recommendation_service/recommendation/"+
				"recommendation_feature_profile_view/"+label+"/generated/",
		) {
			t.Fatalf("%s target = %q", label, target)
		}
	}

	activeRoots := map[string]struct{}{}
	for _, root := range appGeneratedOutputRoots {
		activeRoots[root] = struct{}{}
	}
	for _, root := range []string{
		"lib/service/recommendation_service/recommendation/" +
			"recommendation_feature_profile_view/application/generated",
		"lib/service/recommendation_service/recommendation/" +
			"recommendation_feature_profile_view/presentation/generated",
		"packages/quwoquan_cloud_contracts/lib/src/generated",
	} {
		if _, ok := activeRoots[root]; !ok {
			t.Fatalf("intersection generated root is not active: %s", root)
		}
	}

	legacy := "lib/cloud/runtime/generated/recommendation/" +
		"intersection_kind_metadata.g.dart"
	activeExact := map[string]struct{}{}
	for _, path := range appGeneratedExactOutputs {
		activeExact[path] = struct{}{}
	}
	retiredExact := map[string]struct{}{}
	for _, path := range appRetiredGeneratedExactOutputs {
		retiredExact[path] = struct{}{}
	}
	if _, ok := activeExact[legacy]; ok {
		t.Fatal("legacy intersection exact output remains active after App cutover")
	}
	if _, retired := retiredExact[legacy]; !retired {
		t.Fatal("legacy intersection exact output is not retired after App cutover")
	}
}

func cloneIntersectionStringMap(source map[string]string) map[string]string {
	result := make(map[string]string, len(source))
	for key, value := range source {
		result[key] = value
	}
	return result
}

func reverseIntersectionStringMap(source map[string]string) map[string]string {
	keys := make([]string, 0, len(source))
	for key := range source {
		keys = append(keys, key)
	}
	sort.Sort(sort.Reverse(sort.StringSlice(keys)))
	result := make(map[string]string, len(source))
	for _, key := range keys {
		result[key] = source[key]
	}
	return result
}

func cloneIntersectionActionMeta(
	source map[string]recintersectionmeta.ActionKeyMeta,
) map[string]recintersectionmeta.ActionKeyMeta {
	result := make(map[string]recintersectionmeta.ActionKeyMeta, len(source))
	for key, value := range source {
		value.RequiredGates = append([]string(nil), value.RequiredGates...)
		result[key] = value
	}
	return result
}

func reverseIntersectionActionMeta(
	source map[string]recintersectionmeta.ActionKeyMeta,
) map[string]recintersectionmeta.ActionKeyMeta {
	keys := make([]string, 0, len(source))
	for key := range source {
		keys = append(keys, key)
	}
	sort.Sort(sort.Reverse(sort.StringSlice(keys)))
	result := make(map[string]recintersectionmeta.ActionKeyMeta, len(source))
	for _, key := range keys {
		value := source[key]
		value.RequiredGates = append([]string(nil), value.RequiredGates...)
		result[key] = value
	}
	return result
}

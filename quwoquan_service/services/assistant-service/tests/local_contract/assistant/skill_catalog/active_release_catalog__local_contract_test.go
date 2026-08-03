// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
package local_contract

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	presentation "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	catalogmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	activerelease "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/activerelease"
	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

type activeReleaseResolverStub struct {
	resolved   packageapplication.ResolvedRelease
	releases   map[string]packageapplication.ResolvedRelease
	calls      int
	exactCalls int
}

func TestBuildTimeCatalogDecodesPlatformPresentationTemplate(t *testing.T) {
	for _, templateID := range []string{
		"assistant.answer.default",
		"assistant.tool_confirmation",
	} {
		raw, found, err := (skillfixture.Loader{}).ResolvePresentationTemplate(
			t.Context(),
			templateID,
			"calendar_task",
		)
		if err != nil || !found {
			t.Fatalf("resolve platform presentation template %s found=%v err=%v", templateID, found, err)
		}
		template, err := presentation.DecodeTemplate(raw)
		if err != nil || template.SkillID != presentation.PlatformTemplateSkillID {
			t.Fatalf("decode platform presentation template %s=%+v err=%v", templateID, template, err)
		}
	}
}

func (resolver *activeReleaseResolverStub) ResolveRelease(
	ctx context.Context,
	packageID string,
	releaseDigest string,
) (packageapplication.ResolvedRelease, error) {
	if err := ctx.Err(); err != nil {
		return packageapplication.ResolvedRelease{}, err
	}
	if packageID != activerelease.OfficialPackageID {
		return packageapplication.ResolvedRelease{}, fmt.Errorf("unexpected package %q", packageID)
	}
	resolver.exactCalls++
	resolved, found := resolver.releases[releaseDigest]
	if !found {
		return packageapplication.ResolvedRelease{}, fmt.Errorf("release %q not found", releaseDigest)
	}
	return resolved, nil
}

func (resolver *activeReleaseResolverStub) ResolveActive(
	ctx context.Context,
	packageID string,
) (packageapplication.ResolvedRelease, error) {
	if err := ctx.Err(); err != nil {
		return packageapplication.ResolvedRelease{}, err
	}
	if packageID != activerelease.OfficialPackageID {
		return packageapplication.ResolvedRelease{}, fmt.Errorf("unexpected package %q", packageID)
	}
	resolver.calls++
	return resolver.resolved, nil
}

func TestCatalogUsesFrozenReleaseFromRunContextAfterActivationChanges(t *testing.T) {
	frozen := buildActiveCatalogFixture(t)
	active := buildActiveCatalogFixture(t)
	active.Release.ReleaseDigest = "sha256:" + strings.Repeat("2", 64)
	resolver := &activeReleaseResolverStub{
		resolved: active,
		releases: map[string]packageapplication.ResolvedRelease{
			frozen.Release.ReleaseDigest: frozen,
		},
	}
	source := activerelease.NewCatalogSource(
		resolver,
		activerelease.OfficialPackageID,
		orchestration.ValidateAssistantDomainSkillCatalog,
	)
	ctx := skillpkg.WithPackageRelease(t.Context(), skillpkg.PackageReleaseIdentity{
		PackageID:     frozen.Release.PackageID,
		ReleaseDigest: frozen.Release.ReleaseDigest,
	})
	manifests, err := source.Load(ctx)
	if err != nil {
		t.Fatalf("load frozen package: %v", err)
	}
	rawTemplate, found, err := source.ResolvePresentationTemplate(
		ctx, "travel.route_map", "travel_companion",
	)
	if err != nil || !found {
		t.Fatalf("resolve frozen presentation template found=%v err=%v", found, err)
	}
	template, err := presentation.DecodeTemplate(rawTemplate)
	if err != nil || template.SkillID != "travel_companion" ||
		template.TemplateID != "travel.route_map" {
		t.Fatalf("decode frozen presentation template=%+v err=%v", template, err)
	}
	rawTemplate, found, err = source.ResolvePresentationTemplate(
		ctx, "assistant.tool_confirmation", "calendar_task",
	)
	if err != nil || !found {
		t.Fatalf("resolve platform presentation template found=%v err=%v", found, err)
	}
	template, err = presentation.DecodeTemplate(rawTemplate)
	if err != nil || template.SkillID != presentation.PlatformTemplateSkillID ||
		template.TemplateID != "assistant.tool_confirmation" {
		t.Fatalf("decode platform presentation template=%+v err=%v", template, err)
	}
	if len(manifests) == 0 || resolver.calls != 0 || resolver.exactCalls != 3 {
		t.Fatalf(
			"frozen load manifests=%d activeCalls=%d exactCalls=%d",
			len(manifests),
			resolver.calls,
			resolver.exactCalls,
		)
	}
}

func TestCatalogReadsActiveImmutablePackageOnEveryRequest(t *testing.T) {
	resolved := buildActiveCatalogFixture(t)
	resolver := &activeReleaseResolverStub{resolved: resolved}
	source := activerelease.NewCatalogSource(
		resolver,
		activerelease.OfficialPackageID,
		orchestration.ValidateAssistantDomainSkillCatalog,
	)

	first, err := source.ResolveSnapshot(t.Context())
	if err != nil {
		t.Fatalf("resolve first active package: %v", err)
	}
	items, err := source.ListCatalogItems(t.Context())
	if err != nil {
		t.Fatalf("list active package catalog: %v", err)
	}
	if resolver.calls != 2 {
		t.Fatalf("active pointer reads=%d, want 2", resolver.calls)
	}
	if first.PackageID != activerelease.OfficialPackageID ||
		first.ReleaseDigest != resolved.Release.ReleaseDigest ||
		len(first.Manifests) == 0 || len(items) != len(first.Manifests) {
		t.Fatalf("active catalog snapshot mismatch: %+v items=%d", first, len(items))
	}
	if !hasSkill(items, "fallback_general_search") {
		t.Fatalf("active package catalog misses fallback_general_search")
	}
	var travel catalogmodel.Item
	for _, item := range items {
		if item.SkillID == "travel_companion" {
			travel = item
			break
		}
	}
	if travel.ConfigurationSchemaDigest == "" ||
		travel.PackageID != resolved.Release.PackageID ||
		travel.ReleaseDigest != resolved.Release.ReleaseDigest ||
		len(travel.ConfigurationSchema) == 0 ||
		len(travel.RequiredConsentScopes) != 2 ||
		travel.RequiredConsentScopes[0] != "assistant.memory.preferences.read" ||
		travel.RequiredConsentScopes[1] != "travel.trip.read" ||
		travel.SetupTemplateRef != "assistant.skill.setup.travel_companion" ||
		travel.ActivationMode != "hybrid" ||
		travel.CoverMediaRef == "" ||
		len(travel.TargetUsers) == 0 ||
		len(travel.ExampleRefs) == 0 ||
		len(travel.AllowedSurfaceKinds) != 3 {
		t.Fatalf("active package catalog metadata is incomplete: %+v", travel)
	}
}

func TestCatalogFailsClosedWithoutActivePackageResolver(t *testing.T) {
	source := activerelease.NewCatalogSource(
		nil,
		activerelease.OfficialPackageID,
		orchestration.ValidateAssistantDomainSkillCatalog,
	)
	if _, err := source.Load(t.Context()); err == nil {
		t.Fatal("Load() succeeded without active release resolver")
	}
}

func TestActivePackageOwnsConfigurationSchemaValidation(t *testing.T) {
	resolved := buildActiveCatalogFixture(t)
	resolver := &activeReleaseResolverStub{resolved: resolved}
	source := activerelease.NewCatalogSource(
		resolver,
		activerelease.OfficialPackageID,
		orchestration.ValidateAssistantDomainSkillCatalog,
	)
	snapshot, err := source.ResolveSnapshot(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	schema := snapshot.InputSchemas["assistant.skill.input.travel_companion"]
	if schema.AssetDigest == "" || schema.Document == nil {
		t.Fatal("active package input schema digest is empty")
	}
	schemaRaw, err := json.Marshal(schema.Document)
	if err != nil {
		t.Fatalf("encode active package input schema: %v", err)
	}
	var schemaDocument map[string]any
	if err := json.Unmarshal(schemaRaw, &schemaDocument); err != nil ||
		schemaDocument["type"] != "object" {
		t.Fatalf("active package input schema document=%v err=%v", schemaDocument, err)
	}
	if err := source.ValidateConfiguration(
		t.Context(),
		"travel_companion",
		schema.AssetDigest,
		json.RawMessage(`{}`),
	); err != nil {
		t.Fatalf("validate empty configuration: %v", err)
	}
	if err := source.ValidateConfiguration(
		t.Context(),
		"travel_companion",
		"sha256:"+strings.Repeat("a", 64),
		json.RawMessage(`{}`),
	); !errors.Is(err, catalogmodel.ErrConfigurationSchemaDigestMismatch) {
		t.Fatalf("schema digest mismatch error=%v", err)
	}
	if err := source.ValidateConfiguration(
		t.Context(),
		"travel_companion",
		schema.AssetDigest,
		json.RawMessage(`{"unexpected":true}`),
	); !errors.Is(err, catalogmodel.ErrConfigurationInvalid) {
		t.Fatalf("invalid configuration error=%v", err)
	}
}

func TestPromptResolverReadsOnlyFrozenPackageAssets(t *testing.T) {
	frozen := buildActiveCatalogFixture(t)
	resolver := &activeReleaseResolverStub{
		releases: map[string]packageapplication.ResolvedRelease{
			frozen.Release.ReleaseDigest: frozen,
		},
	}
	prompts := activerelease.NewPromptResolver(
		resolver,
		activerelease.OfficialPackageID,
	)
	if _, err := prompts.ResolvePromptAssets(
		t.Context(),
		[]string{"prompt.placeholder"},
	); err == nil {
		t.Fatal("prompt resolver followed active state without a frozen Run release")
	}
	ctx := skillpkg.WithPackageRelease(t.Context(), skillpkg.PackageReleaseIdentity{
		PackageID:     frozen.Release.PackageID,
		ReleaseDigest: frozen.Release.ReleaseDigest,
	})
	resolved, err := prompts.ResolvePromptAssets(
		ctx,
		[]string{"prompt.placeholder"},
	)
	if err != nil || resolved != "build-only placeholder" {
		t.Fatalf("resolve frozen prompt=%q err=%v", resolved, err)
	}
	if _, err := prompts.ResolvePromptAssets(
		ctx,
		[]string{"prompt.not_in_release"},
	); err == nil {
		t.Fatal("prompt resolver accepted an asset outside the frozen package")
	}
}

func buildActiveCatalogFixture(t *testing.T) packageapplication.ResolvedRelease {
	t.Helper()
	root := filepath.Join(assistantServiceRoot(t), "resources", "skills", "assistant", "assistant_session")
	manifests, err := skillfixture.Load()
	if err != nil {
		t.Fatalf("load build-time Skill assets: %v", err)
	}
	bundle, err := resourcebuilder.NewSourceBuilderAt(root).Compile(t.Context())
	if err != nil {
		t.Fatalf("compile build-time profile assets: %v", err)
	}
	profiles := bundle.Profiles
	replayRaw, err := os.ReadFile(filepath.Join(root, "replay_corpus.json"))
	if err != nil {
		t.Fatalf("read build-time replay corpus: %v", err)
	}

	resolved := packageapplication.ResolvedRelease{
		Release: packagemodel.Release{
			PackageID:     activerelease.OfficialPackageID,
			ReleaseDigest: "sha256:" + strings.Repeat("1", 64),
		},
		Assets: map[string][]byte{},
	}
	appendAsset := func(assetID string, kind string, value any) {
		t.Helper()
		raw, marshalErr := json.Marshal(value)
		if marshalErr != nil {
			t.Fatalf("encode %s: %v", assetID, marshalErr)
		}
		resolved.Release.Assets = append(resolved.Release.Assets, packagemodel.Asset{
			AssetID:     assetID,
			Kind:        kind,
			AssetDigest: fmt.Sprintf("sha256:%x", sha256.Sum256(raw)),
		})
		resolved.Assets[assetID] = raw
	}
	for _, manifest := range manifests {
		appendAsset("manifest."+manifest.SkillID, packagemodel.AssetManifest, manifest)
	}
	for _, value := range profiles.CatalogProfiles {
		appendAsset("catalog."+value.ProfileID, packagemodel.AssetCatalog, value)
	}
	for _, value := range profiles.ActivationProfiles {
		appendAsset("activation."+value.ProfileID, packagemodel.AssetActivation, value)
	}
	for _, value := range profiles.InputProfiles {
		appendAsset("input."+value.ProfileID, packagemodel.AssetInput, value)
	}
	for assetID, raw := range bundle.InputSchemaAssets {
		var schema any
		if err := json.Unmarshal(raw, &schema); err != nil {
			t.Fatalf("decode input schema %s: %v", assetID, err)
		}
		appendAsset(assetID, packagemodel.AssetInputSchema, schema)
	}
	for _, value := range profiles.ContextProfiles {
		appendAsset("context."+value.ProfileID, packagemodel.AssetContext, value)
	}
	for _, value := range profiles.CapabilityProfiles {
		appendAsset("capability."+value.ProfileID, packagemodel.AssetCapability, value)
	}
	for _, value := range profiles.OrchestrationProfiles {
		appendAsset("orchestration."+value.ProfileID, packagemodel.AssetOrchestration, value)
	}
	for _, value := range profiles.TriggerProfiles {
		appendAsset("trigger."+value.ProfileID, packagemodel.AssetTrigger, value)
	}
	for _, value := range profiles.MemoryProfiles {
		appendAsset("memory."+value.ProfileID, packagemodel.AssetMemory, value)
	}
	for _, value := range profiles.PresentationProfiles {
		appendAsset("presentation."+value.ProfileID, packagemodel.AssetPresentation, value)
	}
	for assetID, raw := range bundle.PresentationTemplateAssets {
		var template any
		if err := json.Unmarshal(raw, &template); err != nil {
			t.Fatalf("decode presentation template %s: %v", assetID, err)
		}
		appendAsset(assetID, packagemodel.AssetPresentationTemplate, template)
	}
	for _, value := range profiles.EvaluationProfiles {
		appendAsset("evaluation."+value.ProfileID, packagemodel.AssetEvaluation, value)
	}
	declaredPrompts := map[string]struct{}{}
	for _, manifest := range manifests {
		for _, promptAssetID := range manifest.PromptAssets {
			if _, found := declaredPrompts[promptAssetID]; found {
				continue
			}
			declaredPrompts[promptAssetID] = struct{}{}
			resolved.Release.Assets = append(resolved.Release.Assets, packagemodel.Asset{
				AssetID: promptAssetID,
				Kind:    packagemodel.AssetPrompt,
			})
			resolved.Assets[promptAssetID] = []byte("build-only " + promptAssetID)
		}
	}
	resolved.Release.Assets = append(resolved.Release.Assets, packagemodel.Asset{
		AssetID: "prompt.placeholder",
		Kind:    packagemodel.AssetPrompt,
	})
	resolved.Assets["prompt.placeholder"] = []byte("build-only placeholder")
	resolved.Release.Assets = append(resolved.Release.Assets, packagemodel.Asset{
		AssetID: "replay.catalog",
		Kind:    packagemodel.AssetReplay,
	})
	resolved.Assets["replay.catalog"] = replayRaw
	return resolved
}

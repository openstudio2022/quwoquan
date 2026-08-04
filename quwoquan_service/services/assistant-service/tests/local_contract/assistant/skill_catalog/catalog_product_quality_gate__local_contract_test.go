// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/active-skill-package-catalog/spec.md#gwt-001
package local_contract

import (
	"crypto/sha256"
	"fmt"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application/catalogprojection"
	catalogmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

func TestCatalogQualityGatePublishesOnlyCompleteResolvedSkillMetadata(t *testing.T) {
	bundle := compileCatalogQualityFixture(t)
	travel := resolvedManifestByID(t, bundle.ResolvedManifests, "travel_companion")
	item, listed, err := projectBuildTimeCatalogItem(bundle, travel)
	if err != nil || !listed {
		t.Fatalf("project travel catalog listed=%v err=%v", listed, err)
	}
	if item.DomainID != "travel" || item.CatalogGroup.ID != "travel" ||
		len(item.TargetAudiences) != 6 || len(item.SurfaceKinds) != 3 ||
		item.RequiresConsent || len(item.RequiredConsentScopes) != 0 ||
		!hasSemanticLabel(item.ConsentScopeLabels, "assistant.memory.preferences.read") ||
		!hasSemanticLabel(item.ConsentScopeLabels, "assistant.learning.feedback_context.read") ||
		!hasSemanticLabel(item.ConsentScopeLabels, "travel.trip.read") ||
		len(item.Examples) != 3 {
		t.Fatalf("resolved catalog semantics are incomplete: %+v", item)
	}
	for _, example := range item.Examples {
		if !strings.Contains(example.PresentationTemplateRef, "@sha256:") ||
			example.PresentationTemplateDigest == "" {
			t.Fatalf("example template is not digest-qualified: %+v", example)
		}
	}

	hidden := resolvedManifestByID(t, bundle.ResolvedManifests, "fallback_general_search")
	if _, listed, err := projectBuildTimeCatalogItem(bundle, hidden); err != nil || listed {
		t.Fatalf("hidden routing Skill listed=%v err=%v", listed, err)
	}
}

func TestCatalogQualityGateRejectsPolicyAndTemplateDrift(t *testing.T) {
	bundle := compileCatalogQualityFixture(t)

	surfaceDrift := resolvedManifestByID(t, bundle.ResolvedManifests, "travel_companion")
	surfaceDrift.CatalogProfile.SurfaceKinds = append(
		[]skillpkg.CatalogSemanticLabel(nil),
		surfaceDrift.CatalogProfile.SurfaceKinds...,
	)
	surfaceDrift.CatalogProfile.SurfaceKinds[0].ID = "private_chat"
	if _, _, err := projectBuildTimeCatalogItem(bundle, surfaceDrift); err == nil ||
		!strings.Contains(err.Error(), "surface kinds metadata") {
		t.Fatalf("surface policy drift error=%v", err)
	}

	consentLabelDrift := resolvedManifestByID(
		t,
		bundle.ResolvedManifests,
		"travel_companion",
	)
	consentLabelDrift.CatalogProfile.ConsentScopes = append(
		[]skillpkg.CatalogSemanticLabel(nil),
		consentLabelDrift.CatalogProfile.ConsentScopes[1:]...,
	)
	if _, _, err := projectBuildTimeCatalogItem(
		bundle,
		consentLabelDrift,
	); err == nil || !strings.Contains(err.Error(), "consent scopes metadata") {
		t.Fatalf("optional consent label drift error=%v", err)
	}

	templateDrift := resolvedManifestByID(t, bundle.ResolvedManifests, "travel_companion")
	templateDrift.CatalogProfile.Examples = append(
		[]skillpkg.CatalogExample(nil),
		templateDrift.CatalogProfile.Examples...,
	)
	templateDrift.CatalogProfile.Examples[0].TemplateRef = "assistant.tool_confirmation"
	if _, _, err := projectBuildTimeCatalogItem(bundle, templateDrift); err == nil ||
		!strings.Contains(err.Error(), "outside its PresentationProfile") {
		t.Fatalf("template profile drift error=%v", err)
	}

	phantomMedia := resolvedManifestByID(t, bundle.ResolvedManifests, "travel_companion")
	phantomMedia.CatalogProfile.CoverMediaRef = "assistant.skill.unowned.cover"
	if _, _, err := projectBuildTimeCatalogItem(bundle, phantomMedia); err == nil ||
		!strings.Contains(err.Error(), "immutable media proof") {
		t.Fatalf("phantom media error=%v", err)
	}
}

func TestCatalogQualityGateRejectsDormantVerticalProfiles(t *testing.T) {
	profiles := skillpkg.ProfileAssetCatalog{
		ContextProfiles: []skillpkg.ContextProfile{{ProfileID: "context.travel_companion"}, {
			ProfileID: "context.retired_vertical",
		}},
	}
	err := profiles.ValidateManifestReferences([]skillpkg.Manifest{{
		ContextProfileRef: "context.travel_companion",
	}})
	if err == nil || !strings.Contains(err.Error(), "context.retired_vertical") {
		t.Fatalf("orphan vertical profile must fail package compilation, got %v", err)
	}
}

func compileCatalogQualityFixture(t *testing.T) resourcebuilder.SourceBundle {
	t.Helper()
	root := filepath.Join(assistantServiceRoot(t), "resources", "skill_packages", "official")
	bundle, err := resourcebuilder.NewSourceBuilderAt(root).Compile(t.Context())
	if err != nil {
		t.Fatalf("compile official Skill source: %v", err)
	}
	return bundle
}

func resolvedManifestByID(
	t *testing.T,
	manifests []skillpkg.Manifest,
	skillID string,
) skillpkg.Manifest {
	t.Helper()
	for _, manifest := range manifests {
		if manifest.SkillID == skillID {
			return manifest
		}
	}
	t.Fatalf("resolved Skill %q is missing", skillID)
	return skillpkg.Manifest{}
}

func projectBuildTimeCatalogItem(
	bundle resourcebuilder.SourceBundle,
	manifest skillpkg.Manifest,
) (catalogmodel.Item, bool, error) {
	schema := bundle.InputSchemaAssets[manifest.InputProfile.ConfigurationSchemaRef]
	digest := sha256.Sum256(schema)
	item, listed, err := catalogprojection.Project(catalogprojection.Input{
		Manifest:                  manifest,
		ConfigurationSchemaDigest: fmt.Sprintf("sha256:%x", digest),
		ConfigurationSchema:       schema,
		LoadTemplate: func(skillID string, templateID string) ([]byte, bool, error) {
			for _, owner := range []string{skillID, "quwoquan.official"} {
				raw, found := bundle.PresentationTemplateAssets["presentation_template:"+owner+":"+templateID]
				if found {
					return raw, true, nil
				}
			}
			return nil, false, nil
		},
	})
	return item, listed, err
}

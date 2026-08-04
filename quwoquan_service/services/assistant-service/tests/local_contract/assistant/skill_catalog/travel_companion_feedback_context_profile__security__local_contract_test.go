// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/feedback-context-injection/spec.md#gwt-001
package local_contract

import (
	"crypto/ed25519"
	"crypto/rand"
	"strings"
	"testing"
	"time"

	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

func TestOfficialTravelCompanionPackageDeclaresOptionalPersonalFeedbackContext(
	t *testing.T,
) {
	t.Parallel()
	bundle, err := resourcebuilder.NewSourceBuilder().Compile(t.Context())
	if err != nil {
		t.Fatalf("compile official Skill source: %v", err)
	}
	travel := findOfficialSkill(t, bundle.ResolvedManifests, "travel_companion")
	requirement := findContextRequirement(
		t,
		travel.ContextProfile.Requirements,
		"run.feedback_context",
	)
	if requirement.SlotID != "feedback_context" || requirement.Required ||
		requirement.Authority != "domain_canonical" ||
		requirement.Sensitivity != "private" ||
		requirement.FallbackPolicy != "omit" ||
		len(requirement.AcceptedSourceKinds) != 1 ||
		requirement.AcceptedSourceKinds[0] != "memory" ||
		len(requirement.ConsentScopes) != 1 ||
		requirement.ConsentScopes[0] != "assistant.learning.feedback_context.read" {
		t.Fatalf("feedback ContextProfile requirement=%+v", requirement)
	}
	var scopeLabel string
	for _, scope := range travel.CatalogProfile.ConsentScopes {
		if scope.ID == requirement.ConsentScopes[0] {
			scopeLabel = strings.TrimSpace(scope.DisplayText) + " " + strings.TrimSpace(scope.Description)
			break
		}
	}
	if !strings.Contains(scopeLabel, "脱敏") || !strings.Contains(scopeLabel, "原始") {
		t.Fatalf("feedback consent scope has no user-facing privacy explanation: %q", scopeLabel)
	}

	_, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	built, err := resourcebuilder.BuildPackage(bundle, resourcebuilder.PackageBuildOptions{
		PackageID:        "assistant.session.skills",
		PackageVersion:   "1.0.0",
		BuildID:          "feedback-context-local-contract",
		SourceRepository: "quwoquan",
		SourceRevision:   strings.Repeat("b", 40),
		BuiltAt:          time.Date(2026, time.August, 4, 10, 0, 0, 0, time.UTC),
		RuntimeCompatibility: packagemodel.RuntimeCompatibility{
			APIVersion:            packagemodel.RuntimeAPIVersion,
			MinimumRuntimeVersion: "1.0.0",
			MaximumRuntimeVersion: "1.0.0",
		},
		CapabilityGrants: []packagemodel.CapabilityGrant{{
			CapabilityID: "assistant.skill",
			Scope:        "official",
		}},
		SigningKeyID:      "feedback-context-local-contract-key",
		SigningPrivateKey: privateKey,
	})
	if err != nil {
		t.Fatalf("build official Skill package: %v", err)
	}
	assertBuiltAsset(t, built, packagemodel.AssetContext, "context:context.travel_companion")
	assertBuiltAsset(t, built, packagemodel.AssetCatalog, "catalog:catalog.travel_companion")
}

func findOfficialSkill(
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
	t.Fatalf("official Skill %q is missing", skillID)
	return skillpkg.Manifest{}
}

func findContextRequirement(
	t *testing.T,
	requirements []skillpkg.ContextRequirement,
	resolverRef string,
) skillpkg.ContextRequirement {
	t.Helper()
	for _, requirement := range requirements {
		if requirement.ResolverRef == resolverRef {
			return requirement
		}
	}
	t.Fatalf("context resolver %q is missing", resolverRef)
	return skillpkg.ContextRequirement{}
}

func assertBuiltAsset(
	t *testing.T,
	built resourcebuilder.BuiltPackage,
	kind string,
	assetID string,
) {
	t.Helper()
	for _, asset := range built.Release.Assets {
		if asset.Kind == kind && asset.AssetID == assetID {
			return
		}
	}
	t.Fatalf("built package misses %s asset %q", kind, assetID)
}

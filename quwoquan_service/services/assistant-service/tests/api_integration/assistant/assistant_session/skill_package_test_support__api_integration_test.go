package api_integration

import (
	"context"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

func testSkillPackageIdentityResolver() runruntime.SkillPackageIdentityResolver {
	return runruntime.StaticSkillPackageIdentityResolver{
		PackageID:     "assistant.session.skills",
		ReleaseDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	}
}

// integrationConsentSkillCatalog is an object-level active-package double.
// It reuses the canonical official package and marks the existing Trip reader
// requirement required only for the revocation/start-gate integration case.
// Production package semantics remain unchanged.
type integrationConsentSkillCatalog struct{}

func (integrationConsentSkillCatalog) Load(
	ctx context.Context,
) ([]skillpkg.Manifest, error) {
	manifests, err := skillfixture.Load()
	if err != nil {
		return nil, err
	}
	for manifestIndex := range manifests {
		if strings.TrimSpace(manifests[manifestIndex].SkillID) !=
			"travel_companion" {
			continue
		}
		requirements := append(
			[]skillpkg.ContextRequirement(nil),
			manifests[manifestIndex].ContextProfile.Requirements...,
		)
		for requirementIndex := range requirements {
			for _, scope := range requirements[requirementIndex].ConsentScopes {
				if strings.TrimSpace(scope) == "travel.trip.read" {
					requirements[requirementIndex].Required = true
				}
			}
		}
		manifests[manifestIndex].ContextProfile.Requirements = requirements
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return manifests, nil
}

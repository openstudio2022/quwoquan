package assistant_run_test

import (
	"context"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

func testSkillPackageIdentityResolver() runruntime.SkillPackageIdentityResolver {
	return runruntime.StaticSkillPackageIdentityResolver{
		PackageID:     "assistant.session.skills",
		ReleaseDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	}
}

func testPolicyResolver() runruntime.PolicyResolver {
	return runruntime.PolicyResolverFunc(func(
		_ context.Context,
		policyID string,
		_ string,
		skillID string,
		domainID string,
	) (runruntime.FrozenPolicySelection, error) {
		if policyID == "" {
			policyID = "assistant-default"
		}
		if strings.TrimSpace(skillID) == "" {
			skillID = "fallback_general_search"
		}
		if strings.TrimSpace(domainID) == "" {
			domainID = "assistant"
		}
		return runruntime.FrozenPolicySelection{
			PolicyID:        policyID,
			ReleaseDigest:   "e1a0a7e3379c544c2551da7aafba674ddae2ac9c7d08fdb5762301e9097c771d",
			Cohort:          "control",
			RolloutRevision: 1,
			RuleID:          "test-default",
			Template: runruntime.FrozenPolicyTemplate{
				TemplateID:      "test-template",
				SkillID:         skillID,
				DomainID:        domainID,
				PromptPolicy:    "test frozen prompt",
				AllowedTools:    []string{},
				SearchIntensity: "medium",
			},
		}, nil
	})
}

type rotatingSkillPackageResolver struct {
	packageID         string
	releaseDigest     string
	skillsByRelease   map[string]map[string]bool
	calls             int
	membershipCalls   int
	membershipRelease []skillpkg.PackageReleaseIdentity
}

func (resolver *rotatingSkillPackageResolver) ResolveActiveSkillPackage(
	ctx context.Context,
) (string, string, error) {
	if err := ctx.Err(); err != nil {
		return "", "", err
	}
	resolver.calls++
	return resolver.packageID, resolver.releaseDigest, nil
}

func (resolver *rotatingSkillPackageResolver) ContainsSkillInFrozenPackage(
	ctx context.Context,
	skillID string,
) (bool, error) {
	if err := ctx.Err(); err != nil {
		return false, err
	}
	identity, frozen := skillpkg.PackageReleaseFromContext(ctx)
	if !frozen || identity.PackageID != resolver.packageID {
		return false, runruntime.ErrSkillPackageUnavailable
	}
	resolver.membershipCalls++
	resolver.membershipRelease = append(resolver.membershipRelease, identity)
	if resolver.skillsByRelease == nil {
		return strings.TrimSpace(skillID) != "", nil
	}
	return resolver.skillsByRelease[identity.ReleaseDigest][strings.TrimSpace(skillID)], nil
}

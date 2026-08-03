package assistant_run_test

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
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
	packageID     string
	releaseDigest string
	calls         int
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

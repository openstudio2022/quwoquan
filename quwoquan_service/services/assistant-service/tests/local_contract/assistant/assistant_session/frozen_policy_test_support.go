package local_contract

import (
	"context"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

const testPolicyReleaseDigest = "e1a0a7e3379c544c2551da7aafba674ddae2ac9c7d08fdb5762301e9097c771d"

func testRunPolicyResolver() runruntime.PolicyResolver {
	return runruntime.PolicyResolverFunc(func(
		_ context.Context,
		policyID string,
		_ string,
		skillID string,
		domainID string,
	) (runruntime.FrozenPolicySelection, error) {
		selection := testFrozenPolicySelection(policyID, skillID, domainID)
		return runruntime.FrozenPolicySelection{
			PolicyID:        selection.PolicyID,
			ReleaseDigest:   selection.ReleaseDigest,
			Cohort:          selection.Cohort,
			RolloutRevision: selection.RolloutRevision,
			RuleID:          selection.RuleID,
			Template: runruntime.FrozenPolicyTemplate{
				TemplateID:      selection.Template.TemplateID,
				SkillID:         selection.Template.SkillID,
				DomainID:        selection.Template.DomainID,
				PromptPolicy:    selection.Template.PromptPolicy,
				AllowedTools:    append([]string(nil), selection.Template.AllowedTools...),
				SearchIntensity: selection.Template.SearchIntensity,
			},
		}, nil
	})
}

func testFrozenPolicySelection(
	policyID string,
	skillID string,
	domainID string,
) assistant.AssistantFrozenPolicySelection {
	if strings.TrimSpace(policyID) == "" {
		policyID = "assistant-default"
	}
	if strings.TrimSpace(skillID) == "" {
		skillID = "fallback_general_search"
	}
	if strings.TrimSpace(domainID) == "" {
		domainID = "assistant"
	}
	return assistant.AssistantFrozenPolicySelection{
		PolicyID:        policyID,
		ReleaseDigest:   testPolicyReleaseDigest,
		Cohort:          "control",
		RolloutRevision: 1,
		RuleID:          "test-default",
		Template: assistant.AssistantFrozenPolicyTemplate{
			TemplateID:      "test-template",
			SkillID:         skillID,
			DomainID:        domainID,
			PromptPolicy:    "test frozen policy prompt",
			AllowedTools:    []string{},
			SearchIntensity: "medium",
		},
	}
}

func testRunRequestContext(personaID string) assistant.AssistantRunRequestContext {
	return assistant.AssistantRunRequestContext{PersonaID: personaID}
}

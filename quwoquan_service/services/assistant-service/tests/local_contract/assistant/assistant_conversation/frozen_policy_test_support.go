package local_contract

import (
	"context"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
)

const testPolicyReleaseDigest = "e1a0a7e3379c544c2551da7aafba674ddae2ac9c7d08fdb5762301e9097c771d"

func testFrozenPolicyOption() orchestration.AssistantServiceOption {
	return orchestration.WithFrozenPolicyResolver(
		ports.FrozenPolicyResolverFunc(
			func(
				_ context.Context,
				policyID string,
				_ string,
				skillID string,
				domainID string,
			) (assistant.AssistantFrozenPolicySelection, error) {
				return testFrozenPolicySelection(
					policyID,
					skillID,
					domainID,
				), nil
			},
		),
	)
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

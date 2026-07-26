package local_contract

import (
	"context"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

func testFrozenPolicyOption() application.AssistantServiceOption {
	return application.WithFrozenPolicyResolver(
		application.FrozenPolicyResolverFunc(
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
		ReleaseVersion:  "test-release-v1",
		Cohort:          "control",
		RolloutRevision: 1,
		RuleID:          "test-default",
		Template: assistant.AssistantFrozenPolicyTemplate{
			TemplateID:      "test-template",
			SkillID:         skillID,
			DomainID:        domainID,
			PromptPolicy:    "test frozen policy prompt",
			AllowedTools:    []string{},
			SearchIntensity: "balanced",
		},
	}
}

func testRunRequestContext(personaID string) assistant.AssistantRunRequestContext {
	return assistant.AssistantRunRequestContext{PersonaID: personaID}
}

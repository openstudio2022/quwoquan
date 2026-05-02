package application

import (
	"context"
	"fmt"
	"strings"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

func SeedAssistantServiceFromScenarioPack(ctx context.Context, service *AssistantService, userID string, pack AssistantScenarioPack, seedRefs []string) error {
	if service == nil {
		return fmt.Errorf("assistant scenario seed: service is nil")
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = "user_m11_scenario"
	}
	for _, ref := range seedRefs {
		seedSet, ok := pack.SeedSets[ref].(map[string]any)
		if !ok {
			return fmt.Errorf("assistant scenario seed %q not found", ref)
		}
		rawSubscriptions, _ := seedSet["subscriptions"].([]any)
		for _, raw := range rawSubscriptions {
			obj, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			skillID := strings.TrimSpace(fmt.Sprint(obj["skillId"]))
			if skillID == "" {
				continue
			}
			domainID := strings.TrimSpace(fmt.Sprint(obj["domainId"]))
			if domainID == "" {
				domainID = "assistant"
			}
			if _, err := service.CreateSkillSubscription(ctx, userID, assistant.CreateSkillSubscriptionInput{
				SkillID:  skillID,
				DomainID: domainID,
				SearchQueryPlan: assistant.SkillSubscriptionSearchQueryPlan{
					RawText: "scenario seed: " + skillID,
					Queries: []string{skillID},
				},
				Trigger: assistant.SkillSubscriptionTrigger{
					Type: "cron",
					Cron: "0 8 * * *",
				},
				Destination: assistant.SkillSubscriptionDestination{
					DestinationType: "user",
					DestinationID:   userID,
				},
			}); err != nil {
				return fmt.Errorf("seed subscription %s: %w", skillID, err)
			}
		}
	}
	return nil
}

func SeedRefsForAssistantTurnScenarios(scenarios []AssistantScenarioFixture) []string {
	seen := map[string]bool{}
	out := []string{}
	for _, scenario := range scenarios {
		for _, ref := range scenario.SeedRefs {
			ref = strings.TrimSpace(ref)
			if ref == "" || seen[ref] {
				continue
			}
			seen[ref] = true
			out = append(out, ref)
		}
	}
	return out
}

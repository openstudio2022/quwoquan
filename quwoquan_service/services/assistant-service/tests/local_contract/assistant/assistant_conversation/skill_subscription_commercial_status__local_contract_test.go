package local_contract

import (
	"testing"

	"quwoquan_service/generated/operationsecurity"
)

func TestSkillSubscriptionOperationsAreCommerciallyExecutable(
	t *testing.T,
) {
	expected := map[string]struct{}{
		"assistant.skill_subscription.ListSkillSubscriptions":        {},
		"assistant.skill_subscription.CreateSkillSubscription":       {},
		"assistant.skill_subscription.GetSkillSubscription":          {},
		"assistant.skill_subscription.UpdateSkillSubscriptionStatus": {},
		"assistant.skill_subscription.TickSkillSubscriptionCron":     {},
	}
	for _, descriptor := range operationsecurity.ForDomain("assistant") {
		if _, ok := expected[descriptor.CanonicalOperationID]; !ok {
			continue
		}
		if descriptor.CommercialStatus != "ready" {
			t.Errorf(
				"%s commercial status=%q，期望 ready",
				descriptor.CanonicalOperationID,
				descriptor.CommercialStatus,
			)
		}
		if descriptor.AuthMode != "required" {
			t.Errorf(
				"%s auth mode=%q，期望 required",
				descriptor.CanonicalOperationID,
				descriptor.AuthMode,
			)
		}
		if descriptor.CanonicalOperationID ==
			"assistant.skill_subscription.TickSkillSubscriptionCron" {
			if descriptor.Principal != "service" {
				t.Errorf(
					"tick principal=%q，期望 service",
					descriptor.Principal,
				)
			}
			if len(descriptor.Scopes) != 1 ||
				descriptor.Scopes[0] !=
					"assistant.skill_subscription.tick" {
				t.Errorf(
					"tick scopes=%v，期望 assistant.skill_subscription.tick",
					descriptor.Scopes,
				)
			}
		}
		delete(expected, descriptor.CanonicalOperationID)
	}
	for operationID := range expected {
		t.Errorf("缺少 generated operation descriptor: %s", operationID)
	}
}

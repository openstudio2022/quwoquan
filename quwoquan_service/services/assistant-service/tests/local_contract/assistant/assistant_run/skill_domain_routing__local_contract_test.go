// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
package assistant_run_test

import (
	"testing"

	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/contextassembly"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

func TestSkillDomainRoutingUsesExplicitFrozenDomainInsteadOfSkillNaming(t *testing.T) {
	router := contextassembly.DefaultDomainRouter{}

	explicit := router.Route(assistant.AssistantTurn{
		SkillID:  "any.vertical.naming",
		DomainID: "travel",
	}, contextassembly.ClientContext{})
	if explicit != "travel" {
		t.Fatalf("explicit frozen domain=%q, want travel", explicit)
	}

	missing := router.Route(assistant.AssistantTurn{
		SkillID: "finance.private_advisor",
	}, contextassembly.ClientContext{})
	if missing != "assistant" {
		t.Fatalf(
			"missing frozen domain inferred from Skill naming: got %q, want assistant",
			missing,
		)
	}
}

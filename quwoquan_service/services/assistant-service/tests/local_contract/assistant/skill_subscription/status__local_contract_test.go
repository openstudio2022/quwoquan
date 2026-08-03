// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-002
package skill_subscription_test

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

func TestSkillSubscriptionTriggerTimezoneIsDeclaredByObjectLocalContracts(t *testing.T) {
	root := filepath.Join(
		"..", "..", "..", "..", "contracts", "assistant", "skill_subscription",
	)
	for _, fileName := range []string{"fields.yaml", "schema.yaml"} {
		raw, err := os.ReadFile(filepath.Join(root, fileName))
		if err != nil {
			t.Fatalf("read %s: %v", fileName, err)
		}
		if !strings.Contains(string(raw), "timezone") {
			t.Fatalf("%s does not expose canonical trigger timezone", fileName)
		}
	}
}

func TestSkillSubscriptionArchivedIsTerminal(t *testing.T) {
	for _, transition := range [][2]string{
		{"active", "paused"}, {"active", "archived"},
		{"paused", "active"}, {"paused", "archived"},
		{"active", "active"}, {"archived", "archived"},
	} {
		if err := skillmodel.ValidateTransition(transition[0], transition[1]); err != nil {
			t.Fatalf("transition=%v err=%v", transition, err)
		}
	}
	for _, target := range []string{"active", "paused"} {
		if err := skillmodel.ValidateTransition("archived", target); !errors.Is(err, skillmodel.ErrInvalidTransition) {
			t.Fatalf("archived -> %s err=%v", target, err)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-002
package skill_subscription_test

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	subscriptionpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/infrastructure/persistence"
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

// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003
func TestListSkillSubscriptionsKeepsMultipleStableIDsForOneSkill(t *testing.T) {
	t.Parallel()
	store := subscriptionpersistence.NewMemoryStore()
	now := time.Date(2026, 8, 4, 11, 0, 0, 0, time.UTC)
	for index, id := range []string{"subscription-a", "subscription-b"} {
		store.SeedSkillSubscription(skillmodel.SkillSubscription{
			SubscriptionID: id,
			Version:        1,
			Owner: skillmodel.SkillSubscriptionOwner{
				OwnerType: "user",
				OwnerID:   "account-a",
			},
			CreatedByUserID: "account-a",
			SkillID:         "travel_companion",
			DomainID:        "travel",
			Status:          skillmodel.SkillSubscriptionStatusActive,
			CreatedAt:       now.Add(time.Duration(index) * time.Minute),
			UpdatedAt:       now.Add(time.Duration(index) * time.Minute),
		})
	}
	view, err := subscriptionapplication.NewUseCases(
		store, nil, nil, func() time.Time { return now },
	).List(context.Background(), "account-a", "", 20)
	if err != nil {
		t.Fatalf("List() error=%v", err)
	}
	if len(view.Items) != 2 ||
		view.Items[0].SubscriptionID != "subscription-b" ||
		view.Items[1].SubscriptionID != "subscription-a" ||
		view.Items[0].SkillID != view.Items[1].SkillID {
		t.Fatalf("List() collapsed or reordered identities: %+v", view.Items)
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

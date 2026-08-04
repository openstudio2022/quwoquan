// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003
package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/infrastructure/control"
)

type visibilityStoreStub struct {
	cutoffs []time.Time
}

func (store *visibilityStoreStub) HiddenBefore(
	context.Context,
	string,
	string,
) (*time.Time, error) {
	if len(store.cutoffs) == 0 {
		return nil, nil
	}
	cutoff := store.cutoffs[len(store.cutoffs)-1]
	return &cutoff, nil
}

func (store *visibilityStoreStub) HideBefore(
	_ context.Context,
	_ string,
	_ string,
	cutoff time.Time,
) error {
	store.cutoffs = append(store.cutoffs, cutoff.UTC())
	return nil
}

func TestHideActivityHistoryReplayKeepsConfirmationCutoff(t *testing.T) {
	t.Parallel()
	confirmedAt := time.Date(2026, 8, 4, 12, 0, 0, 0, time.UTC)
	visibility := &visibilityStoreStub{}
	executor := control.NewExecutor(visibility, nil, nil, nil)
	request := model.Request{
		RequestID:   "control-request-hide",
		AccountID:   "account-a",
		SkillID:     "travel_companion",
		ConfirmedAt: &confirmedAt,
	}
	for range 2 {
		if err := executor.ExecuteSkillDataControlAction(
			context.Background(), request, model.ActionHideActivityHistory,
		); err != nil {
			t.Fatalf("ExecuteSkillDataControlAction() error=%v", err)
		}
	}
	if len(visibility.cutoffs) != 2 ||
		!visibility.cutoffs[0].Equal(confirmedAt) ||
		!visibility.cutoffs[1].Equal(confirmedAt) {
		t.Fatalf("hide cutoffs=%v, want stable confirmedAt=%s", visibility.cutoffs, confirmedAt)
	}
}

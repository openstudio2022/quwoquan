// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md
package assistant_policy_rollout_test

import (
	"context"
	"errors"
	"testing"
	"time"

	releasemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
)

type memoryRolloutStore struct {
	current  model.Rollout
	receipts map[string]receipt
}

type receipt struct {
	digest  string
	rollout model.Rollout
}

func (store *memoryRolloutStore) Get(
	_ context.Context,
	policyID string,
) (model.Rollout, bool, error) {
	return store.current, store.current.PolicyID == policyID, nil
}

func (store *memoryRolloutStore) GetCommandResult(
	_ context.Context,
	commandID string,
	commandDigest string,
	policyID string,
) (model.Rollout, bool, error) {
	existing, ok := store.receipts[commandID]
	if !ok {
		return model.Rollout{}, false, nil
	}
	if existing.digest != commandDigest || existing.rollout.PolicyID != policyID {
		return model.Rollout{}, false, model.ErrIdempotencyConflict
	}
	return existing.rollout, true, nil
}

func (store *memoryRolloutStore) Commit(
	_ context.Context,
	commandID string,
	commandDigest string,
	expectedRevision int,
	next model.Rollout,
	_ string,
) (model.Rollout, bool, error) {
	if store.receipts == nil {
		store.receipts = map[string]receipt{}
	}
	if existing, ok := store.receipts[commandID]; ok {
		if existing.digest != commandDigest {
			return model.Rollout{}, false, model.ErrIdempotencyConflict
		}
		return existing.rollout, true, nil
	}
	if store.current.Revision != expectedRevision {
		return model.Rollout{}, false, model.ErrRevisionConflict
	}
	store.current = next
	store.receipts[commandID] = receipt{digest: commandDigest, rollout: next}
	return next, false, nil
}

type releaseReader map[string]struct{}

func (reader releaseReader) Get(
	_ context.Context,
	_ string,
	releaseVersion string,
) (releasemodel.Release, bool, error) {
	_, ok := reader[releaseVersion]
	return releasemodel.Release{ReleaseVersion: releaseVersion}, ok, nil
}

type releaseCatalog map[string]releasemodel.Release

func (catalog releaseCatalog) Get(
	_ context.Context,
	_ string,
	releaseVersion string,
) (releasemodel.Release, bool, error) {
	release, ok := catalog[releaseVersion]
	return release, ok, nil
}

func TestPolicyRolloutActivationAndRollbackPreserveExactMappings(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 26, 9, 0, 0, 0, time.UTC)
	store := &memoryRolloutStore{}
	service := application.NewService(
		store,
		releaseReader{"v1": {}, "v2": {}},
		func() time.Time { return now },
	)
	buckets := []model.BucketDefinition{
		{Cohort: "control", WeightBasisPoints: 5000},
		{Cohort: "treatment", WeightBasisPoints: 5000},
	}
	first, err := service.Activate(context.Background(), "activate-1", application.ActivateInput{
		PolicyID:          "assistant-default",
		ExpectedRevision:  0,
		BucketDefinitions: buckets,
		Assignments: []model.CohortAssignment{
			{Cohort: "control", ReleaseVersion: "v1"},
			{Cohort: "treatment", ReleaseVersion: "v1"},
		},
		ActivatedBy: "service:policy-publisher",
	})
	if err != nil {
		t.Fatal(err)
	}
	second, err := service.Activate(context.Background(), "activate-2", application.ActivateInput{
		PolicyID:          "assistant-default",
		ExpectedRevision:  1,
		BucketDefinitions: buckets,
		Assignments: []model.CohortAssignment{
			{Cohort: "control", ReleaseVersion: "v1"},
			{Cohort: "treatment", ReleaseVersion: "v2"},
		},
		ActivatedBy: "service:policy-publisher",
	})
	if err != nil {
		t.Fatal(err)
	}
	rolledBack, err := service.Rollback(context.Background(), "rollback-1", application.RollbackInput{
		PolicyID:         "assistant-default",
		ExpectedRevision: 2,
		ActivatedBy:      "service:policy-publisher",
	})
	if err != nil {
		t.Fatal(err)
	}
	if first.Rollout.Revision != 1 ||
		second.Rollout.Revision != 2 ||
		rolledBack.Rollout.Revision != 3 ||
		rolledBack.Rollout.Assignments[1].ReleaseVersion != "v1" ||
		rolledBack.Rollout.PreviousAssignments[1].ReleaseVersion != "v2" {
		t.Fatalf("first=%+v second=%+v rollback=%+v", first, second, rolledBack)
	}
}

func TestPolicyRolloutReplaysBeforeEvaluatingAdvancedRevision(t *testing.T) {
	t.Parallel()
	store := &memoryRolloutStore{}
	service := application.NewService(store, releaseReader{"v1": {}}, time.Now)
	input := application.ActivateInput{
		PolicyID:         "assistant-default",
		ExpectedRevision: 0,
		BucketDefinitions: []model.BucketDefinition{
			{Cohort: "stable", WeightBasisPoints: 10000},
		},
		Assignments: []model.CohortAssignment{
			{Cohort: "stable", ReleaseVersion: "v1"},
		},
		ActivatedBy: "service:policy-publisher",
	}
	first, err := service.Activate(context.Background(), "activate-stable", input)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := service.Activate(context.Background(), "activate-stable", input)
	if err != nil {
		t.Fatal(err)
	}
	if first.Replayed || !replay.Replayed || replay.Rollout.Revision != 1 {
		t.Fatalf("first=%+v replay=%+v", first, replay)
	}
}

func TestPolicyRolloutRejectsMissingReleaseAndStaleRevision(t *testing.T) {
	t.Parallel()
	store := &memoryRolloutStore{}
	service := application.NewService(store, releaseReader{"v1": {}}, time.Now)
	_, err := service.Activate(context.Background(), "activate-missing", application.ActivateInput{
		PolicyID:         "assistant-default",
		ExpectedRevision: 0,
		BucketDefinitions: []model.BucketDefinition{
			{Cohort: "all", WeightBasisPoints: 10000},
		},
		Assignments: []model.CohortAssignment{
			{Cohort: "all", ReleaseVersion: "missing"},
		},
		ActivatedBy: "service:policy-publisher",
	})
	if !errors.Is(err, model.ErrReleaseNotFound) {
		t.Fatalf("missing release err=%v", err)
	}
	store.current = model.Rollout{PolicyID: "assistant-default", Revision: 4}
	_, err = service.Activate(context.Background(), "activate-stale", application.ActivateInput{
		PolicyID:         "assistant-default",
		ExpectedRevision: 3,
		BucketDefinitions: []model.BucketDefinition{
			{Cohort: "all", WeightBasisPoints: 10000},
		},
		Assignments: []model.CohortAssignment{
			{Cohort: "all", ReleaseVersion: "v1"},
		},
		ActivatedBy: "service:policy-publisher",
	})
	if !errors.Is(err, model.ErrRevisionConflict) {
		t.Fatalf("stale revision err=%v", err)
	}
}

func TestFrozenSelectionUsesStablePolicyPersonaBucketAndDefaultTemplate(
	t *testing.T,
) {
	t.Parallel()
	store := &memoryRolloutStore{current: model.Rollout{
		PolicyID: "assistant-default",
		Revision: 7,
		Status:   "active",
		BucketDefinitions: []model.BucketDefinition{
			{Cohort: "control", WeightBasisPoints: 5000},
			{Cohort: "treatment", WeightBasisPoints: 5000},
		},
		Assignments: []model.CohortAssignment{
			{Cohort: "control", ReleaseVersion: "v1"},
			{Cohort: "treatment", ReleaseVersion: "v1"},
		},
	}}
	catalog := releaseCatalog{"v1": {
		PolicyID:          "assistant-default",
		ReleaseVersion:    "v1",
		DefaultTemplateID: "default",
		Templates: []releasemodel.Template{{
			TemplateID:      "default",
			SkillID:         "fallback_general_search",
			DomainID:        "assistant",
			PromptPolicy:    "default prompt",
			AllowedTools:    []string{"app_search"},
			SearchIntensity: "balanced",
		}},
	}}
	service := application.NewService(store, catalog, time.Now)
	first, err := service.ResolveFrozenSelection(
		context.Background(),
		"assistant-default",
		"persona-stable",
		"",
		"",
	)
	if err != nil {
		t.Fatal(err)
	}
	second, err := service.ResolveFrozenSelection(
		context.Background(),
		"assistant-default",
		"persona-stable",
		"",
		"",
	)
	if err != nil {
		t.Fatal(err)
	}
	if first.Cohort != second.Cohort ||
		first.ReleaseVersion != "v1" ||
		first.RuleID != "default" ||
		first.Template.TemplateID != "default" ||
		first.RolloutRevision != 7 {
		t.Fatalf("first=%+v second=%+v", first, second)
	}
}

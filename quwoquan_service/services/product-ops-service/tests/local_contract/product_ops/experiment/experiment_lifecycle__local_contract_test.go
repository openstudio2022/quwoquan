package local_contract

import (
	"testing"
	"time"

	model "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
)

// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001
func TestExperimentLifecycleUsesDomainAggregateContract(t *testing.T) {
	now := time.Date(2026, time.July, 14, 10, 0, 0, 0, time.UTC)
	experiment := model.Experiment{
		ID:           "exp-1",
		Key:          "exp-1",
		Version:      1,
		Status:       "draft",
		AudienceRule: model.AudienceRule{Kind: "all"},
		Variants: []model.Variant{
			{Key: "control", AllocationBasisPoints: 5000},
			{Key: "treatment", AllocationBasisPoints: 5000},
		},
		CreatedAt: "2026-07-14T09:00:00Z",
		UpdatedAt: "2026-07-14T09:00:00Z",
	}

	next, err := experiment.UpdateRollout("running", []model.Variant{
		{Key: "control", AllocationBasisPoints: 2500},
		{Key: "treatment", AllocationBasisPoints: 7500},
	}, now)
	if err != nil {
		t.Fatalf("UpdateRollout() error = %v", err)
	}
	if next.Version != 2 || next.UpdatedAt != now.Format(time.RFC3339) {
		t.Fatalf("updated aggregate = %#v", next)
	}
	if _, err := experiment.UpdateRollout("running", []model.Variant{
		{Key: "control", AllocationBasisPoints: 6000},
		{Key: "treatment", AllocationBasisPoints: 3000},
	}, now); err == nil {
		t.Fatal("allocation that is not 10000 basis points must be rejected")
	}
}

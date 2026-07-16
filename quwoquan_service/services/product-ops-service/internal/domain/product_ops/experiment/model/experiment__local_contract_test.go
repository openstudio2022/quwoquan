package model

import (
	"errors"
	"testing"
	"time"
)

func TestExperimentUpdateRolloutEnforcesAllocationAndVersion(t *testing.T) {
	now := time.Date(2026, 7, 14, 10, 0, 0, 0, time.UTC)
	experiment := validExperiment()
	experiment.Status = "draft"
	next, err := experiment.UpdateRollout("running", []Variant{
		{Key: "control", AllocationBasisPoints: 2500},
		{Key: "treatment", AllocationBasisPoints: 7500},
	}, now)
	if err != nil {
		t.Fatalf("update rollout: %v", err)
	}
	if next.Version != experiment.Version+1 || next.UpdatedAt != now.Format(time.RFC3339) {
		t.Fatalf("unexpected next experiment: %+v", next)
	}
	if _, err := experiment.UpdateRollout("running", []Variant{
		{Key: "control", AllocationBasisPoints: 6000},
		{Key: "treatment", AllocationBasisPoints: 3000},
	}, now); err == nil {
		t.Fatal("allocation not totaling 10000 basis points must fail")
	}
	if _, err := experiment.UpdateRollout("running", []Variant{
		{Key: "control", AllocationBasisPoints: 5000},
		{Key: "control", AllocationBasisPoints: 5000},
	}, now); err == nil {
		t.Fatal("duplicate variant must fail")
	}
}

func TestExperimentAssignmentIsDeterministicAndRequiresRunningAggregate(t *testing.T) {
	now := time.Date(2026, 7, 14, 10, 0, 0, 0, time.UTC)
	experiment := validExperiment()
	first, err := experiment.Assign("persona-1", now)
	if err != nil {
		t.Fatalf("assign running experiment: %v", err)
	}
	second, err := experiment.Assign("persona-1", now.Add(time.Hour))
	if err != nil {
		t.Fatalf("reassign running experiment: %v", err)
	}
	if first.ID != second.ID || first.Variant != second.Variant {
		t.Fatalf("assignment must be deterministic: first=%+v second=%+v", first, second)
	}
	experiment.Status = "paused"
	if _, err := experiment.Assign("persona-2", now); !errors.Is(err, ErrDisabled) {
		t.Fatalf("paused experiment assignment error=%v, want ErrDisabled", err)
	}
}

func TestExperimentRolloutRejectsVariantMutationOutsideDraftAndEndedIsTerminal(t *testing.T) {
	now := time.Date(2026, 7, 14, 10, 0, 0, 0, time.UTC)
	experiment := validExperiment()
	mutated := []Variant{
		{Key: "control", AllocationBasisPoints: 2500},
		{Key: "treatment", AllocationBasisPoints: 7500},
	}
	if _, err := experiment.UpdateRollout("paused", mutated, now); err == nil {
		t.Fatal("running experiment variant mutation must fail")
	}
	experiment.Status = "ended"
	if _, err := experiment.UpdateRollout("running", experiment.Variants, now); err == nil {
		t.Fatal("ended experiment must be terminal")
	}
}

func TestExperimentLifecycleWindowIsValidatedAndEnforcedForAssignment(t *testing.T) {
	now := time.Date(2026, 7, 14, 10, 0, 0, 0, time.UTC)
	experiment := validExperiment()
	experiment.StartsAt = now.Add(time.Hour).Format(time.RFC3339)
	experiment.EndsAt = now.Add(2 * time.Hour).Format(time.RFC3339)
	if _, err := experiment.Assign("persona-1", now); !errors.Is(err, ErrDisabled) {
		t.Fatalf("assignment before window error=%v, want ErrDisabled", err)
	}
	if _, err := experiment.Assign("persona-1", now.Add(time.Hour)); err != nil {
		t.Fatalf("assignment at window start: %v", err)
	}
	if _, err := experiment.Assign("persona-2", now.Add(2*time.Hour)); !errors.Is(err, ErrDisabled) {
		t.Fatalf("assignment at exclusive window end error=%v, want ErrDisabled", err)
	}

	experiment.EndsAt = now.Format(time.RFC3339)
	if err := experiment.Validate(); err == nil {
		t.Fatal("endsAt before startsAt must fail")
	}
	experiment = validExperiment()
	experiment.Status = "scheduled"
	if err := experiment.Validate(); err == nil {
		t.Fatal("scheduled experiment without startsAt must fail")
	}
	experiment = validExperiment()
	experiment.UpdatedAt = "not-a-timestamp"
	if err := experiment.Validate(); err == nil {
		t.Fatal("invalid lifecycle timestamp must fail")
	}
}

func validExperiment() Experiment {
	return Experiment{
		ID: "exp-1", Key: "exp-1", Version: 1, Status: "running",
		AllocationSeed: "seed-1", AudienceRule: AudienceRule{Kind: "all"},
		Variants: []Variant{
			{Key: "control", AllocationBasisPoints: 5000},
			{Key: "treatment", AllocationBasisPoints: 5000},
		},
		CreatedAt: "2026-07-14T09:00:00Z", UpdatedAt: "2026-07-14T09:00:00Z",
	}
}

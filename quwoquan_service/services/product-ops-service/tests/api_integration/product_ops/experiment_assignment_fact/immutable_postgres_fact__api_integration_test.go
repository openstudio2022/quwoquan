package api_integration

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	experimentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/application"
	experimentpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/infrastructure/persistence"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
	assignmentdomain "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/domain"
	assignmentpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/infrastructure/persistence"
)

// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001
func TestExperimentAssignmentFactUsesCanonicalBucketAndImmutableIdentity(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	experiments, err := experimentpersistence.NewPostgresStore(assignmentPGPool)
	if err != nil {
		t.Fatal(err)
	}
	if err := experiments.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	assignments, err := assignmentpersistence.NewPostgresStore(assignmentPGPool)
	if err != nil {
		t.Fatal(err)
	}
	if err := assignments.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	facade, err := experimentapp.NewFacade(experiments, experiments, assignments, assignments)
	if err != nil {
		t.Fatal(err)
	}
	experimentID := fmt.Sprintf("assignment-fact-%d", time.Now().UnixNano())
	now := time.Now().UTC().Truncate(time.Second)
	_, err = assignmentPGPool.Exec(ctx, `
INSERT INTO experiments(id, key, version, status, variants, audience_rule, created_at, updated_at)
VALUES ($1,$1,1,'running',$2,$3,$4,$4)`,
		experimentID,
		`[{"key":"control","allocationBasisPoints":5000},{"key":"treatment","allocationBasisPoints":5000}]`,
		`{"kind":"all"}`,
		now,
	)
	if err != nil {
		t.Fatal(err)
	}
	experiment, err := facade.Get(ctx, experimentID)
	if err != nil {
		t.Fatal(err)
	}
	expected, err := experiment.Assign("persona:canonical", now)
	if err != nil {
		t.Fatal(err)
	}
	observation := assignmentapp.AssignmentObservation{
		ExperimentID: experiment.ID, ExperimentRevision: experiment.Version,
		SubjectKey: expected.SubjectKey, Variant: expected.Variant, ObservedAt: now,
	}
	first, inserted, err := facade.AssignmentFacts().AppendObserved(ctx, observation)
	if err != nil || !inserted {
		t.Fatalf("append canonical observation: inserted=%v fact=%+v err=%v", inserted, first, err)
	}
	replayed, inserted, err := facade.AssignmentFacts().AppendObserved(ctx, observation)
	if err != nil || inserted || replayed != first {
		t.Fatalf("replay canonical observation: inserted=%v fact=%+v err=%v", inserted, replayed, err)
	}
	wrong := observation
	if wrong.Variant == "control" {
		wrong.Variant = "treatment"
	} else {
		wrong.Variant = "control"
	}
	if _, _, err := facade.AssignmentFacts().AppendObserved(ctx, wrong); !errors.Is(err, assignmentapp.ErrInvalidObservation) {
		t.Fatalf("private bucket override error=%v, want ErrInvalidObservation", err)
	}
	read, err := facade.AssignmentFacts().Get(ctx, experimentID, expected.SubjectKey)
	if err != nil || read != first {
		t.Fatalf("read canonical fact=%+v err=%v", read, err)
	}
	_, stats, err := facade.AssignmentFacts().Stats(ctx, experimentID)
	if err != nil || stats.AssignedSubjects != 1 || stats.VariantCounts[first.Variant] != 1 {
		t.Fatalf("stats=%+v err=%v", stats, err)
	}
	conflict := first
	if conflict.Variant == "control" {
		conflict.Variant = "treatment"
	} else {
		conflict.Variant = "control"
	}
	if _, _, err := assignments.Append(ctx, conflict); err == nil {
		t.Fatal("immutable identity accepted a conflicting variant")
	}
	if _, err := assignments.Get(ctx, "missing", 1, "persona:missing"); !errors.Is(err, assignmentdomain.ErrNotFound) {
		t.Fatalf("missing fact error=%v, want ErrNotFound", err)
	}
}

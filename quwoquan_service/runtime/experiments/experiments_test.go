// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001
// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/bucketing-strategy-engine/spec.md#gwt-001
package runtimeexperiments

import (
	"context"
	"errors"
	"regexp"
	"testing"
)

func validExperiment() *Experiment {
	return &Experiment{
		ID:      "search_ranking",
		Enabled: true,
		Buckets: []BucketDef{
			{Name: "control", WeightPct: 50},
			{Name: "term_heat", WeightPct: 50},
		},
	}
}

func TestHashResolverUsesDeterministicContentDigest(t *testing.T) {
	hr := NewHashResolver()
	policy := validExperiment()
	if err := hr.Register(policy); err != nil {
		t.Fatalf("Register() error = %v", err)
	}
	wantDigest, err := PolicyDigest(policy)
	if err != nil {
		t.Fatalf("PolicyDigest() error = %v", err)
	}
	assignment, err := hr.Resolve(context.Background(), policy.ID, "persona-123")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if assignment.Bucket != "control" && assignment.Bucket != "term_heat" {
		t.Fatalf("unexpected bucket: %q", assignment.Bucket)
	}
	if assignment.PolicyDigest != wantDigest ||
		!regexp.MustCompile(`^sha256:[0-9a-f]{64}$`).MatchString(assignment.PolicyDigest) {
		t.Fatalf("PolicyDigest = %q, want %q", assignment.PolicyDigest, wantDigest)
	}
	changed := validExperiment()
	changed.Buckets[0].WeightPct = 60
	changed.Buckets[1].WeightPct = 40
	changedDigest, err := PolicyDigest(changed)
	if err != nil {
		t.Fatalf("PolicyDigest(changed) error = %v", err)
	}
	if changedDigest == wantDigest {
		t.Fatal("different policy content produced the same runtime identity")
	}

	// Register owns an immutable copy: later caller mutation cannot drift the
	// published policy or its identity.
	policy.Buckets[0].WeightPct = 100
	second, err := hr.Resolve(context.Background(), policy.ID, "persona-123")
	if err != nil {
		t.Fatalf("Resolve() after caller mutation error = %v", err)
	}
	if second != assignment {
		t.Fatalf("assignment drifted after caller mutation: first=%#v second=%#v", assignment, second)
	}
}

func TestHashResolverMissingAndDisabledFailClosed(t *testing.T) {
	hr := NewHashResolver()
	if assignment, err := hr.Resolve(context.Background(), "missing", "persona-1"); !errors.Is(err, ErrExperimentMissing) || assignment != (Assignment{}) {
		t.Fatalf("missing Resolve() = (%#v, %v)", assignment, err)
	}
	disabled := validExperiment()
	disabled.Enabled = false
	if err := hr.Register(disabled); err != nil {
		t.Fatalf("Register(disabled) error = %v", err)
	}
	if assignment, err := hr.Resolve(context.Background(), disabled.ID, "persona-1"); !errors.Is(err, ErrExperimentDisabled) || assignment != (Assignment{}) {
		t.Fatalf("disabled Resolve() = (%#v, %v)", assignment, err)
	}
	if assignment, err := hr.Resolve(context.Background(), disabled.ID, ""); !errors.Is(err, ErrInvalidExperiment) || assignment != (Assignment{}) {
		t.Fatalf("identity-less Resolve() = (%#v, %v)", assignment, err)
	}
}

func TestHashResolverRejectsInvalidPolicies(t *testing.T) {
	tests := []struct {
		name   string
		policy *Experiment
	}{
		{name: "nil", policy: nil},
		{name: "empty id", policy: &Experiment{Enabled: true, Buckets: []BucketDef{{Name: "control", WeightPct: 100}}}},
		{name: "no buckets", policy: &Experiment{ID: "experiment", Enabled: true}},
		{name: "all zero", policy: &Experiment{ID: "experiment", Enabled: true, Buckets: []BucketDef{{Name: "control", WeightPct: 0}}}},
		{name: "negative", policy: &Experiment{ID: "experiment", Enabled: true, Buckets: []BucketDef{{Name: "control", WeightPct: 110}, {Name: "treatment", WeightPct: -10}}}},
		{name: "partial weight", policy: &Experiment{ID: "experiment", Enabled: true, Buckets: []BucketDef{{Name: "control", WeightPct: 90}}}},
		{name: "mixed units", policy: &Experiment{ID: "experiment", Enabled: true, Buckets: []BucketDef{{Name: "control", WeightPct: 100}, {Name: "treatment", WeightBasisPoints: 10000}}}},
		{name: "duplicate", policy: &Experiment{ID: "experiment", Enabled: true, Buckets: []BucketDef{{Name: "control", WeightPct: 50}, {Name: "control", WeightPct: 50}}}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if err := NewHashResolver().Register(test.policy); !errors.Is(err, ErrInvalidExperiment) {
				t.Fatalf("Register() error = %v, want ErrInvalidExperiment", err)
			}
		})
	}
}

func TestHashResolverAcceptsZeroWeightArmWithoutAssigningIt(t *testing.T) {
	policy := &Experiment{
		ID:      "model_rollout",
		Enabled: true,
		Buckets: []BucketDef{
			{Name: "model", WeightPct: 100},
			{Name: "rule", WeightPct: 0},
		},
	}
	resolver := NewHashResolver()
	if err := resolver.Register(policy); err != nil {
		t.Fatalf("Register() error = %v", err)
	}
	if err := ValidateExperiment(policy); err != nil {
		t.Fatalf("ValidateExperiment() error = %v", err)
	}
	for _, subject := range []string{"persona-a", "persona-b", "session-c"} {
		assignment, err := resolver.Resolve(context.Background(), policy.ID, subject)
		if err != nil {
			t.Fatalf("Resolve(%q) error = %v", subject, err)
		}
		if assignment.Bucket != "model" {
			t.Fatalf("Resolve(%q) bucket = %q, want model", subject, assignment.Bucket)
		}
	}
}

func TestAssignBucketDeterministicAndDistributed(t *testing.T) {
	buckets := validExperiment().Buckets
	first, err := AssignBucket("distribution", "persona-abc", buckets)
	if err != nil {
		t.Fatalf("AssignBucket() error = %v", err)
	}
	second, err := AssignBucket("distribution", "persona-abc", buckets)
	if err != nil || second != first {
		t.Fatalf("second AssignBucket() = (%q, %v), want %q", second, err, first)
	}

	counts := map[string]int{}
	for index := 0; index < 1000; index++ {
		bucket, assignErr := AssignBucket(
			"distribution",
			fmtSubject(index),
			buckets,
		)
		if assignErr != nil {
			t.Fatalf("AssignBucket(%d) error = %v", index, assignErr)
		}
		counts[bucket]++
	}
	for bucket, count := range counts {
		if count < 300 {
			t.Errorf("bucket %q has %d assignments, expected >= 300", bucket, count)
		}
	}
}

func fmtSubject(index int) string {
	return string(rune('a'+index%26)) + string(rune('0'+index%10))
}

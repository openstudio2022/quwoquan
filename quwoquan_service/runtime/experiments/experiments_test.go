package runtimeexperiments

import (
	"context"
	"testing"
)

func TestStaticResolver_DefaultBucket(t *testing.T) {
	r := StaticResolver{}
	a, err := r.Resolve(context.Background(), "exp1", "user1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if a.Bucket != "control" {
		t.Errorf("expected 'control', got %q", a.Bucket)
	}
}

func TestStaticResolver_CustomBucket(t *testing.T) {
	r := StaticResolver{DefaultBucket: "treatment"}
	a, _ := r.Resolve(context.Background(), "exp1", "user1")
	if a.Bucket != "treatment" {
		t.Errorf("expected 'treatment', got %q", a.Bucket)
	}
}

func TestHashResolver_RegisterAndResolve(t *testing.T) {
	hr := NewHashResolver()
	hr.Register(&Experiment{
		ID:      "rec_algo_v2",
		Enabled: true,
		Buckets: []BucketDef{
			{Name: "control", WeightPct: 50},
			{Name: "treatment", WeightPct: 50},
		},
		PolicyVersion: "v2.0",
	})

	a, err := hr.Resolve(context.Background(), "rec_algo_v2", "user_123")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if a.Bucket != "control" && a.Bucket != "treatment" {
		t.Errorf("unexpected bucket: %q", a.Bucket)
	}
	if a.PolicyVersion != "v2.0" {
		t.Errorf("expected 'v2.0', got %q", a.PolicyVersion)
	}
}

func TestHashResolver_DisabledExperiment(t *testing.T) {
	hr := NewHashResolver()
	hr.Register(&Experiment{
		ID:      "disabled_exp",
		Enabled: false,
		Buckets: []BucketDef{{Name: "treatment", WeightPct: 100}},
	})

	a, _ := hr.Resolve(context.Background(), "disabled_exp", "user1")
	if a.Bucket != "control" {
		t.Errorf("disabled experiment should return 'control', got %q", a.Bucket)
	}
}

func TestHashResolver_NotFound(t *testing.T) {
	hr := NewHashResolver()
	a, _ := hr.Resolve(context.Background(), "nonexistent", "user1")
	if a.Bucket != "control" {
		t.Errorf("missing experiment should return 'control', got %q", a.Bucket)
	}
}

func TestHashResolver_DeterministicAssignment(t *testing.T) {
	hr := NewHashResolver()
	hr.Register(&Experiment{
		ID:      "det_test",
		Enabled: true,
		Buckets: []BucketDef{
			{Name: "A", WeightPct: 50},
			{Name: "B", WeightPct: 50},
		},
	})

	a1, _ := hr.Resolve(context.Background(), "det_test", "user_abc")
	a2, _ := hr.Resolve(context.Background(), "det_test", "user_abc")
	if a1.Bucket != a2.Bucket {
		t.Error("same user should get same bucket assignment")
	}
}

func TestHashResolver_DistributionReasonable(t *testing.T) {
	hr := NewHashResolver()
	hr.Register(&Experiment{
		ID:      "dist_test",
		Enabled: true,
		Buckets: []BucketDef{
			{Name: "A", WeightPct: 50},
			{Name: "B", WeightPct: 50},
		},
	})

	counts := map[string]int{}
	for i := 0; i < 1000; i++ {
		a, _ := hr.Resolve(context.Background(), "dist_test", string(rune('a'+i%26))+string(rune('0'+i%10)))
		counts[a.Bucket]++
	}

	// With 50/50 split and 1000 users, each bucket should have at least 300
	for bucket, count := range counts {
		if count < 300 {
			t.Errorf("bucket %q has %d assignments, expected >= 300 for 50%% weight", bucket, count)
		}
	}
}

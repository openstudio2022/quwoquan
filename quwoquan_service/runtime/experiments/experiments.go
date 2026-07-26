package runtimeexperiments

import (
	"context"
	"fmt"
	"hash/fnv"
	"sync"
)

type Assignment struct {
	ExperimentID    string
	Bucket          string
	PolicyVersion   string
	AssignmentTrace string
}

type Resolver interface {
	Resolve(ctx context.Context, experimentID string, subjectKey string) (Assignment, error)
}

// StaticResolver offers a deterministic default for tests and explicitly
// disabled experiments. Production recommendation/search traffic uses
// HashResolver (or AssignBucket through recpolicy); Product Ops assignment facts
// are intentionally not a second runtime resolver.
type StaticResolver struct {
	DefaultBucket string
}

func (r StaticResolver) Resolve(_ context.Context, experimentID string, _ string) (Assignment, error) {
	bucket := r.DefaultBucket
	if bucket == "" {
		bucket = "control"
	}
	return Assignment{
		ExperimentID:    experimentID,
		Bucket:          bucket,
		PolicyVersion:   "runtime-static-v1",
		AssignmentTrace: "static",
	}, nil
}

// Experiment defines the configuration for a single experiment.
type Experiment struct {
	ID            string
	Buckets       []BucketDef
	PolicyVersion string
	Enabled       bool
}

type BucketDef struct {
	Name              string
	WeightPct         int
	WeightBasisPoints int
}

// HashResolver is the canonical runtime bucketing implementation shared by
// recommendation and search.
type HashResolver struct {
	mu          sync.RWMutex
	experiments map[string]*Experiment
}

func NewHashResolver() *HashResolver {
	return &HashResolver{
		experiments: make(map[string]*Experiment),
	}
}

// Register adds or updates an experiment configuration.
func (r *HashResolver) Register(exp *Experiment) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.experiments[exp.ID] = exp
}

func (r *HashResolver) Resolve(_ context.Context, experimentID string, subjectKey string) (Assignment, error) {
	r.mu.RLock()
	exp, ok := r.experiments[experimentID]
	r.mu.RUnlock()

	if !ok || !exp.Enabled {
		return Assignment{
			ExperimentID:    experimentID,
			Bucket:          "control",
			PolicyVersion:   "not-found",
			AssignmentTrace: "experiment not found or disabled",
		}, nil
	}

	bucket := AssignBucket(experimentID, subjectKey, exp.Buckets)
	return Assignment{
		ExperimentID:    experimentID,
		Bucket:          bucket,
		PolicyVersion:   exp.PolicyVersion,
		AssignmentTrace: fmt.Sprintf("hash(%s+%s)", experimentID, subjectKey),
	}, nil
}

// AssignBucket deterministically maps (expID, subjectKey) to one of buckets via
// consistent FNV hashing on weightPct ranges. Exported so policy resolvers reuse
// the single canonical hashing impl instead of duplicating it.
func AssignBucket(expID, subjectKey string, buckets []BucketDef) string {
	h := fnv.New32a()
	h.Write([]byte(expID + ":" + subjectKey))
	hash := h.Sum32()
	scale := 100
	for _, bucket := range buckets {
		if bucket.WeightBasisPoints > 0 {
			scale = 10000
			break
		}
	}
	position := int(hash % uint32(scale))

	cumulative := 0
	for _, b := range buckets {
		weight := b.WeightPct
		if scale == 10000 {
			weight = b.WeightBasisPoints
		}
		cumulative += weight
		if position < cumulative {
			return b.Name
		}
	}

	if len(buckets) > 0 {
		return buckets[len(buckets)-1].Name
	}
	return "control"
}

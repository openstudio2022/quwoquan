package runtimeexperiments

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"hash/fnv"
	"strings"
	"sync"
)

var (
	ErrInvalidExperiment  = errors.New("runtimeexperiments: invalid experiment")
	ErrExperimentMissing  = errors.New("runtimeexperiments: experiment missing")
	ErrExperimentDisabled = errors.New("runtimeexperiments: experiment disabled")
)

type Assignment struct {
	ExperimentID    string
	Bucket          string
	PolicyDigest    string
	AssignmentTrace string
}

type Resolver interface {
	Resolve(ctx context.Context, experimentID string, subjectKey string) (Assignment, error)
}

// Experiment defines the complete runtime bucketing policy. Runtime identity is
// derived from this content; it is intentionally separate from Product Ops'
// immutable assignment-fact experimentRevision, which is not bound to this hot path.
type Experiment struct {
	ID      string      `json:"id"`
	Buckets []BucketDef `json:"buckets"`
	Enabled bool        `json:"enabled"`
}

type BucketDef struct {
	Name              string `json:"name"`
	WeightPct         int    `json:"weightPct"`
	WeightBasisPoints int    `json:"weightBasisPoints"`
}

type registeredExperiment struct {
	policy Experiment
	digest string
}

// HashResolver is the canonical runtime bucketing implementation shared by
// recommendation and search. Registered policies are validated, copied and
// content-addressed before publication so later caller mutation cannot drift the
// effective identity.
type HashResolver struct {
	mu          sync.RWMutex
	experiments map[string]registeredExperiment
}

func NewHashResolver() *HashResolver {
	return &HashResolver{
		experiments: make(map[string]registeredExperiment),
	}
}

// Register validates and atomically publishes one experiment policy.
func (r *HashResolver) Register(exp *Experiment) error {
	if r == nil {
		return fmt.Errorf("%w: nil resolver", ErrInvalidExperiment)
	}
	policy, digest, err := canonicalExperiment(exp)
	if err != nil {
		return err
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.experiments[policy.ID] = registeredExperiment{policy: policy, digest: digest}
	return nil
}

func (r *HashResolver) Resolve(
	ctx context.Context,
	experimentID string,
	subjectKey string,
) (Assignment, error) {
	if err := ctx.Err(); err != nil {
		return Assignment{}, err
	}
	experimentID = strings.TrimSpace(experimentID)
	subjectKey = strings.TrimSpace(subjectKey)
	if experimentID == "" || subjectKey == "" {
		return Assignment{}, fmt.Errorf(
			"%w: experimentID and subjectKey are required",
			ErrInvalidExperiment,
		)
	}
	r.mu.RLock()
	registered, ok := r.experiments[experimentID]
	r.mu.RUnlock()
	if !ok {
		return Assignment{}, fmt.Errorf("%w: %s", ErrExperimentMissing, experimentID)
	}
	if !registered.policy.Enabled {
		return Assignment{}, fmt.Errorf("%w: %s", ErrExperimentDisabled, experimentID)
	}

	bucket, err := AssignBucket(experimentID, subjectKey, registered.policy.Buckets)
	if err != nil {
		return Assignment{}, err
	}
	return Assignment{
		ExperimentID:    experimentID,
		Bucket:          bucket,
		PolicyDigest:    registered.digest,
		AssignmentTrace: "fnv1a32",
	}, nil
}

// PolicyDigest derives the canonical runtime identity of one valid assignment
// policy without registering it.
func PolicyDigest(exp *Experiment) (string, error) {
	_, digest, err := canonicalExperiment(exp)
	return digest, err
}

// ValidateExperiment applies the same canonical policy constraints used by
// Register and AssignBucket. Domain-specific policy owners must delegate here
// instead of maintaining a second bucket validator.
func ValidateExperiment(exp *Experiment) error {
	_, _, err := canonicalExperiment(exp)
	return err
}

func canonicalExperiment(exp *Experiment) (Experiment, string, error) {
	if exp == nil {
		return Experiment{}, "", fmt.Errorf("%w: nil policy", ErrInvalidExperiment)
	}
	policy := Experiment{
		ID:      strings.TrimSpace(exp.ID),
		Buckets: append([]BucketDef(nil), exp.Buckets...),
		Enabled: exp.Enabled,
	}
	if policy.ID == "" || policy.ID != exp.ID {
		return Experiment{}, "", fmt.Errorf(
			"%w: canonical experiment id is required",
			ErrInvalidExperiment,
		)
	}
	if _, err := validateBuckets(policy.Buckets); err != nil {
		return Experiment{}, "", err
	}
	encoded, err := json.Marshal(policy)
	if err != nil {
		return Experiment{}, "", fmt.Errorf("%w: encode policy: %v", ErrInvalidExperiment, err)
	}
	sum := sha256.Sum256(encoded)
	return policy, "sha256:" + hex.EncodeToString(sum[:]), nil
}

// AssignBucket deterministically maps (experimentID, subjectKey) to one bucket.
// Invalid or incomplete input returns an error; no implicit control bucket exists.
func AssignBucket(experimentID, subjectKey string, buckets []BucketDef) (string, error) {
	experimentID = strings.TrimSpace(experimentID)
	subjectKey = strings.TrimSpace(subjectKey)
	if experimentID == "" || subjectKey == "" {
		return "", fmt.Errorf(
			"%w: experimentID and subjectKey are required",
			ErrInvalidExperiment,
		)
	}
	scale, err := validateBuckets(buckets)
	if err != nil {
		return "", err
	}
	h := fnv.New32a()
	_, _ = h.Write([]byte(experimentID + ":" + subjectKey))
	position := int(h.Sum32() % uint32(scale))

	cumulative := 0
	for _, bucket := range buckets {
		weight := bucket.WeightPct
		if scale == 10000 {
			weight = bucket.WeightBasisPoints
		}
		cumulative += weight
		if position < cumulative {
			return bucket.Name, nil
		}
	}
	return "", fmt.Errorf("%w: bucket weights do not cover hash space", ErrInvalidExperiment)
}

func validateBuckets(buckets []BucketDef) (int, error) {
	if len(buckets) == 0 {
		return 0, fmt.Errorf("%w: buckets are required", ErrInvalidExperiment)
	}
	hasPercent := false
	hasBasisPoints := false
	total := 0
	names := make(map[string]struct{}, len(buckets))
	for _, bucket := range buckets {
		name := strings.TrimSpace(bucket.Name)
		if name == "" || name != bucket.Name {
			return 0, fmt.Errorf("%w: canonical bucket name is required", ErrInvalidExperiment)
		}
		if _, exists := names[name]; exists {
			return 0, fmt.Errorf("%w: duplicate bucket %q", ErrInvalidExperiment, name)
		}
		names[name] = struct{}{}
		if bucket.WeightPct > 0 {
			hasPercent = true
			total += bucket.WeightPct
		}
		if bucket.WeightBasisPoints > 0 {
			hasBasisPoints = true
			total += bucket.WeightBasisPoints
		}
		if bucket.WeightPct < 0 || bucket.WeightBasisPoints < 0 {
			return 0, fmt.Errorf("%w: bucket %q weight must be non-negative", ErrInvalidExperiment, name)
		}
	}
	if hasPercent == hasBasisPoints {
		return 0, fmt.Errorf(
			"%w: use exactly one weight unit for all buckets",
			ErrInvalidExperiment,
		)
	}
	scale := 100
	if hasBasisPoints {
		scale = 10000
	}
	if total != scale {
		return 0, fmt.Errorf(
			"%w: bucket weights total %d, expected %d",
			ErrInvalidExperiment,
			total,
			scale,
		)
	}
	return scale, nil
}

package application

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	runtimeexperiments "quwoquan_service/runtime/experiments"
)

const SearchRankingExperimentID = "search_ranking"

const (
	BucketControl  = "control"
	BucketTermHeat = "term_heat"
)

type ExperimentPolicyVariant struct {
	Key                   string `json:"key" bson:"key"`
	AllocationBasisPoints int    `json:"allocationBasisPoints" bson:"allocationBasisPoints"`
}

type ExperimentPolicy struct {
	ID        string                    `json:"id" bson:"_id"`
	Revision  int64                     `json:"revision" bson:"revision"`
	Status    string                    `json:"status" bson:"status"`
	Variants  []ExperimentPolicyVariant `json:"variants" bson:"variants"`
	StartsAt  string                    `json:"startsAt,omitempty" bson:"startsAt,omitempty"`
	EndsAt    string                    `json:"endsAt,omitempty" bson:"endsAt,omitempty"`
	UpdatedAt string                    `json:"updatedAt" bson:"updatedAt"`
	Digest    string                    `json:"digest" bson:"digest"`
}

type AssignmentObservation struct {
	ExperimentID       string
	ExperimentRevision int64
	SubjectKey         string
	Variant            string
	AssignedAt         time.Time
}

type AssignmentObservationPublisher interface {
	PublishExperimentAssignment(context.Context, AssignmentObservation) error
}

type Experiments struct {
	mu        sync.RWMutex
	policy    *ExperimentPolicy
	publisher AssignmentObservationPublisher
	now       func() time.Time
}

func NewExperiments(publisher AssignmentObservationPublisher) (*Experiments, error) {
	if publisher == nil {
		return nil, errors.New("search experiment assignment publisher is required")
	}
	return &Experiments{publisher: publisher, now: time.Now}, nil
}

func (e *Experiments) ApplyPolicy(policy ExperimentPolicy) error {
	canonical, err := CanonicalExperimentPolicy(policy)
	if err != nil {
		return err
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.policy != nil {
		switch {
		case canonical.Revision < e.policy.Revision:
			return nil
		case canonical.Revision == e.policy.Revision && canonical.Digest != e.policy.Digest:
			return errors.New("search experiment policy revision has conflicting content")
		case canonical.Revision == e.policy.Revision:
			return nil
		}
	}
	e.policy = &canonical
	return nil
}

func (e *Experiments) Assign(ctx context.Context, subjectKey string) (string, error) {
	if e == nil || e.publisher == nil {
		return "", errors.New("search ranking experiment resolver is unavailable")
	}
	e.mu.RLock()
	if e.policy == nil {
		e.mu.RUnlock()
		return "", errors.New("search ranking experiment policy is unavailable")
	}
	policy := *e.policy
	policy.Variants = append([]ExperimentPolicyVariant(nil), e.policy.Variants...)
	e.mu.RUnlock()
	now := e.now().UTC()
	if policy.Status != "running" || !insidePolicyWindow(policy, now) {
		return "", errors.New("search ranking experiment policy is not active")
	}
	buckets := make([]runtimeexperiments.BucketDef, 0, len(policy.Variants))
	for _, variant := range policy.Variants {
		buckets = append(buckets, runtimeexperiments.BucketDef{
			Name: variant.Key, WeightBasisPoints: variant.AllocationBasisPoints,
		})
	}
	bucket, err := runtimeexperiments.AssignBucket(policy.ID, subjectKey, buckets)
	if err != nil {
		return "", fmt.Errorf("assign search ranking experiment: %w", err)
	}
	if err := e.publisher.PublishExperimentAssignment(ctx, AssignmentObservation{
		ExperimentID: policy.ID, ExperimentRevision: policy.Revision,
		SubjectKey: strings.TrimSpace(subjectKey), Variant: bucket, AssignedAt: now,
	}); err != nil {
		return "", fmt.Errorf("publish search experiment assignment: %w", err)
	}
	return bucket, nil
}

func (e *Experiments) Healthy() error {
	if e == nil {
		return errors.New("search experiments are unavailable")
	}
	e.mu.RLock()
	defer e.mu.RUnlock()
	if e.policy == nil {
		return errors.New("search ranking ExperimentPolicyActivated has not been projected")
	}
	if e.policy.Status != "running" || !insidePolicyWindow(*e.policy, e.now().UTC()) {
		return errors.New("search ranking Experiment policy is not active")
	}
	return nil
}

func CanonicalExperimentPolicy(policy ExperimentPolicy) (ExperimentPolicy, error) {
	policy.ID = strings.TrimSpace(policy.ID)
	policy.Status = strings.TrimSpace(policy.Status)
	policy.StartsAt = strings.TrimSpace(policy.StartsAt)
	policy.EndsAt = strings.TrimSpace(policy.EndsAt)
	policy.UpdatedAt = strings.TrimSpace(policy.UpdatedAt)
	if policy.ID != SearchRankingExperimentID || policy.Revision <= 0 {
		return ExperimentPolicy{}, errors.New("search ranking experiment id and revision are invalid")
	}
	if policy.Status != "draft" && policy.Status != "scheduled" && policy.Status != "running" && policy.Status != "paused" && policy.Status != "ended" {
		return ExperimentPolicy{}, errors.New("search ranking experiment status is invalid")
	}
	if _, err := time.Parse(time.RFC3339Nano, policy.UpdatedAt); err != nil {
		return ExperimentPolicy{}, errors.New("search ranking experiment updatedAt is invalid")
	}
	if _, err := optionalPolicyTime(policy.StartsAt); err != nil {
		return ExperimentPolicy{}, fmt.Errorf("search ranking experiment startsAt: %w", err)
	}
	if _, err := optionalPolicyTime(policy.EndsAt); err != nil {
		return ExperimentPolicy{}, fmt.Errorf("search ranking experiment endsAt: %w", err)
	}
	seen := map[string]bool{}
	total := 0
	for index := range policy.Variants {
		policy.Variants[index].Key = strings.TrimSpace(policy.Variants[index].Key)
		variant := policy.Variants[index]
		if variant.Key != BucketControl && variant.Key != BucketTermHeat || seen[variant.Key] || variant.AllocationBasisPoints <= 0 {
			return ExperimentPolicy{}, errors.New("search ranking experiment variants are invalid")
		}
		seen[variant.Key] = true
		total += variant.AllocationBasisPoints
	}
	if len(seen) != 2 || total != 10_000 {
		return ExperimentPolicy{}, errors.New("search ranking experiment variants must allocate exactly 10000 basis points")
	}
	digestInput := policy
	digestInput.Digest = ""
	encoded, err := json.Marshal(digestInput)
	if err != nil {
		return ExperimentPolicy{}, err
	}
	policy.Digest = fmt.Sprintf("sha256:%x", sha256.Sum256(encoded))
	return policy, nil
}

func optionalPolicyTime(value string) (*time.Time, error) {
	if value == "" {
		return nil, nil
	}
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		return nil, err
	}
	parsed = parsed.UTC()
	return &parsed, nil
}

func insidePolicyWindow(policy ExperimentPolicy, now time.Time) bool {
	startsAt, startErr := optionalPolicyTime(policy.StartsAt)
	endsAt, endErr := optionalPolicyTime(policy.EndsAt)
	if startErr != nil || endErr != nil {
		return false
	}
	return (startsAt == nil || !now.Before(*startsAt)) && (endsAt == nil || now.Before(*endsAt))
}

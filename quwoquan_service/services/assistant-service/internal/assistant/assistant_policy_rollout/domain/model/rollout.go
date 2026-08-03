package model

import (
	"errors"
	"sort"
	"strings"
	"time"
)

var (
	ErrInvalidArgument     = errors.New("assistant policy rollout is invalid")
	ErrReleaseNotFound     = errors.New("assistant policy release not found")
	ErrRolloutNotFound     = errors.New("assistant policy rollout not found")
	ErrNoPreviousMapping   = errors.New("assistant policy rollout has no previous mapping")
	ErrRevisionConflict    = errors.New("assistant policy rollout revision conflict")
	ErrIdempotencyConflict = errors.New("assistant policy rollout idempotency conflict")
	ErrStorageUnavailable  = errors.New("assistant policy rollout storage unavailable")
)

type BucketDefinition struct {
	Cohort            string `json:"cohort" bson:"cohort"`
	WeightBasisPoints int    `json:"weightBasisPoints" bson:"weightBasisPoints"`
}

type CohortAssignment struct {
	Cohort        string `json:"cohort" bson:"cohort"`
	ReleaseDigest string `json:"releaseDigest" bson:"releaseDigest"`
}

type Rollout struct {
	PolicyID            string             `json:"policyId" bson:"policyId"`
	Revision            int                `json:"revision" bson:"revision"`
	Status              string             `json:"status" bson:"status"`
	BucketDefinitions   []BucketDefinition `json:"bucketDefinitions" bson:"bucketDefinitions"`
	Assignments         []CohortAssignment `json:"assignments" bson:"assignments"`
	PreviousAssignments []CohortAssignment `json:"previousAssignments" bson:"previousAssignments"`
	ActivatedAt         time.Time          `json:"activatedAt" bson:"activatedAt"`
	ActivatedBy         string             `json:"activatedBy" bson:"activatedBy"`
}

func Activate(
	current *Rollout,
	policyID string,
	expectedRevision int,
	buckets []BucketDefinition,
	assignments []CohortAssignment,
	activatedBy string,
	now time.Time,
) (Rollout, error) {
	normalizedBuckets, normalizedAssignments, err := normalizeMapping(
		buckets,
		assignments,
	)
	if err != nil {
		return Rollout{}, err
	}
	policyID = strings.TrimSpace(policyID)
	activatedBy = strings.TrimSpace(activatedBy)
	if policyID == "" || activatedBy == "" {
		return Rollout{}, ErrInvalidArgument
	}
	nextRevision := 1
	previous := []CohortAssignment{}
	if current != nil {
		if current.PolicyID != policyID || current.Revision != expectedRevision {
			return Rollout{}, ErrRevisionConflict
		}
		nextRevision = current.Revision + 1
		previous = append(previous, current.Assignments...)
	} else if expectedRevision != 0 {
		return Rollout{}, ErrRevisionConflict
	}
	return Rollout{
		PolicyID:            policyID,
		Revision:            nextRevision,
		Status:              "active",
		BucketDefinitions:   normalizedBuckets,
		Assignments:         normalizedAssignments,
		PreviousAssignments: previous,
		// MongoDB persists BSON datetimes at millisecond precision. Keeping the
		// aggregate at that precision makes first responses and receipt replays
		// byte-identical instead of creating a second temporal representation.
		ActivatedAt: now.UTC().Truncate(time.Millisecond),
		ActivatedBy: activatedBy,
	}, nil
}

func Rollback(
	current Rollout,
	expectedRevision int,
	activatedBy string,
	now time.Time,
) (Rollout, error) {
	if current.PolicyID == "" {
		return Rollout{}, ErrRolloutNotFound
	}
	if current.Revision != expectedRevision {
		return Rollout{}, ErrRevisionConflict
	}
	if len(current.PreviousAssignments) == 0 {
		return Rollout{}, ErrNoPreviousMapping
	}
	activatedBy = strings.TrimSpace(activatedBy)
	if activatedBy == "" {
		return Rollout{}, ErrInvalidArgument
	}
	return Rollout{
		PolicyID:            current.PolicyID,
		Revision:            current.Revision + 1,
		Status:              "active",
		BucketDefinitions:   append([]BucketDefinition(nil), current.BucketDefinitions...),
		Assignments:         append([]CohortAssignment(nil), current.PreviousAssignments...),
		PreviousAssignments: append([]CohortAssignment(nil), current.Assignments...),
		ActivatedAt:         now.UTC().Truncate(time.Millisecond),
		ActivatedBy:         activatedBy,
	}, nil
}

func normalizeMapping(
	buckets []BucketDefinition,
	assignments []CohortAssignment,
) ([]BucketDefinition, []CohortAssignment, error) {
	if len(buckets) == 0 || len(buckets) > 32 ||
		len(assignments) != len(buckets) {
		return nil, nil, ErrInvalidArgument
	}
	normalizedBuckets := append([]BucketDefinition(nil), buckets...)
	bucketNames := make(map[string]struct{}, len(buckets))
	totalWeight := 0
	for index := range normalizedBuckets {
		bucket := &normalizedBuckets[index]
		bucket.Cohort = strings.TrimSpace(bucket.Cohort)
		if bucket.Cohort == "" || bucket.WeightBasisPoints <= 0 {
			return nil, nil, ErrInvalidArgument
		}
		if _, duplicate := bucketNames[bucket.Cohort]; duplicate {
			return nil, nil, ErrInvalidArgument
		}
		bucketNames[bucket.Cohort] = struct{}{}
		totalWeight += bucket.WeightBasisPoints
	}
	if totalWeight != 10000 {
		return nil, nil, ErrInvalidArgument
	}
	normalizedAssignments := append([]CohortAssignment(nil), assignments...)
	assignmentNames := make(map[string]struct{}, len(assignments))
	for index := range normalizedAssignments {
		assignment := &normalizedAssignments[index]
		assignment.Cohort = strings.TrimSpace(assignment.Cohort)
		assignment.ReleaseDigest = strings.TrimSpace(assignment.ReleaseDigest)
		if assignment.Cohort == "" || assignment.ReleaseDigest == "" {
			return nil, nil, ErrInvalidArgument
		}
		if _, ok := bucketNames[assignment.Cohort]; !ok {
			return nil, nil, ErrInvalidArgument
		}
		if _, duplicate := assignmentNames[assignment.Cohort]; duplicate {
			return nil, nil, ErrInvalidArgument
		}
		assignmentNames[assignment.Cohort] = struct{}{}
	}
	sort.Slice(normalizedBuckets, func(i, j int) bool {
		return normalizedBuckets[i].Cohort < normalizedBuckets[j].Cohort
	})
	sort.Slice(normalizedAssignments, func(i, j int) bool {
		return normalizedAssignments[i].Cohort < normalizedAssignments[j].Cohort
	})
	return normalizedBuckets, normalizedAssignments, nil
}

package model

import (
	"errors"
	"fmt"
	"hash/fnv"
	"strings"
	"time"

	runtimeexperiments "quwoquan_service/runtime/experiments"
)

var (
	ErrNotFound            = errors.New("experiment not found")
	ErrDisabled            = errors.New("experiment is disabled")
	ErrVersionConflict     = errors.New("experiment version conflict")
	ErrIdempotencyConflict = errors.New("experiment idempotency conflict")
	ErrAssignmentNotFound  = errors.New("experiment assignment not found")
)

type Variant struct {
	Key                   string `json:"key"`
	AllocationBasisPoints int    `json:"allocationBasisPoints"`
}

type AudienceRule struct {
	Kind string `json:"kind"`
}

type Experiment struct {
	ID           string       `json:"id"`
	Key          string       `json:"key"`
	Version      int64        `json:"version"`
	Status       string       `json:"status"`
	Variants     []Variant    `json:"variants"`
	AudienceRule AudienceRule `json:"audienceRule"`
	StartsAt     string       `json:"startsAt,omitempty"`
	EndsAt       string       `json:"endsAt,omitempty"`
	CreatedAt    string       `json:"createdAt"`
	UpdatedAt    string       `json:"updatedAt"`
}

type AssignmentFact struct {
	ID                 string `json:"id"`
	ExperimentID       string `json:"experimentId"`
	SubjectKey         string `json:"subjectKey"`
	Variant            string `json:"variant"`
	ExperimentRevision int64  `json:"experimentRevision"`
	AssignedAt         string `json:"assignedAt"`
}

type Event struct {
	ID            string
	Type          string
	AggregateID   string
	AggregateType string
	Payload       []byte
	OccurredAt    time.Time
}

func (e Experiment) Validate() error {
	if strings.TrimSpace(e.ID) == "" || strings.TrimSpace(e.Key) == "" {
		return errors.New("experiment id and key are required")
	}
	if e.Version <= 0 {
		return errors.New("experiment version must be positive")
	}
	if strings.TrimSpace(e.Status) == "" {
		return errors.New("experiment status is required")
	}
	if _, known := experimentStatuses[e.Status]; !known {
		return fmt.Errorf("unknown experiment status %q", e.Status)
	}
	if strings.TrimSpace(e.AudienceRule.Kind) == "" {
		return errors.New("experiment audience rule kind is required")
	}
	if err := validateVariants(e.Variants); err != nil {
		return err
	}
	createdAt, err := parseRequiredTimestamp("createdAt", e.CreatedAt)
	if err != nil {
		return err
	}
	updatedAt, err := parseRequiredTimestamp("updatedAt", e.UpdatedAt)
	if err != nil {
		return err
	}
	if updatedAt.Before(createdAt) {
		return errors.New("experiment updatedAt cannot precede createdAt")
	}
	startsAt, err := parseOptionalTimestamp("startsAt", e.StartsAt)
	if err != nil {
		return err
	}
	endsAt, err := parseOptionalTimestamp("endsAt", e.EndsAt)
	if err != nil {
		return err
	}
	if !startsAt.IsZero() && !endsAt.IsZero() && !endsAt.After(startsAt) {
		return errors.New("experiment endsAt must be after startsAt")
	}
	if e.Status == "scheduled" && startsAt.IsZero() {
		return errors.New("scheduled experiment requires startsAt")
	}
	return nil
}

func (e Experiment) UpdateRollout(status string, variants []Variant, now time.Time) (Experiment, error) {
	status = strings.TrimSpace(status)
	if status == "" {
		return Experiment{}, errors.New("experiment status is required")
	}
	if err := validateVariants(variants); err != nil {
		return Experiment{}, err
	}
	if err := validateRolloutTransition(e.Status, status); err != nil {
		return Experiment{}, err
	}
	if e.Status != "draft" && !variantsEqual(e.Variants, variants) {
		return Experiment{}, errors.New("experiment variants can only change while draft")
	}
	next := e
	next.Status = status
	next.Variants = append([]Variant(nil), variants...)
	next.Version++
	next.UpdatedAt = now.UTC().Format(time.RFC3339)
	return next, next.Validate()
}

func (e Experiment) Assign(subjectKey string, now time.Time) (AssignmentFact, error) {
	subjectKey = strings.TrimSpace(subjectKey)
	if subjectKey == "" {
		return AssignmentFact{}, errors.New("subject key is required")
	}
	if e.Status != "running" {
		return AssignmentFact{}, ErrDisabled
	}
	startsAt, err := parseOptionalTimestamp("startsAt", e.StartsAt)
	if err != nil {
		return AssignmentFact{}, err
	}
	endsAt, err := parseOptionalTimestamp("endsAt", e.EndsAt)
	if err != nil {
		return AssignmentFact{}, err
	}
	now = now.UTC()
	if (!startsAt.IsZero() && now.Before(startsAt)) ||
		(!endsAt.IsZero() && !now.Before(endsAt)) {
		return AssignmentFact{}, ErrDisabled
	}
	experimentRevision := e.Version
	buckets := make([]runtimeexperiments.BucketDef, 0, len(e.Variants))
	for _, variant := range e.Variants {
		buckets = append(buckets, runtimeexperiments.BucketDef{
			Name:              variant.Key,
			WeightBasisPoints: variant.AllocationBasisPoints,
		})
	}
	selected, err := runtimeexperiments.AssignBucket(e.ID, subjectKey, buckets)
	if err != nil {
		return AssignmentFact{}, err
	}
	return AssignmentFact{
		ID:                 assignmentID(e.ID, experimentRevision, subjectKey),
		ExperimentID:       e.ID,
		SubjectKey:         subjectKey,
		Variant:            selected,
		ExperimentRevision: experimentRevision,
		AssignedAt:         now.UTC().Format(time.RFC3339),
	}, nil
}

func parseRequiredTimestamp(name, value string) (time.Time, error) {
	if strings.TrimSpace(value) == "" {
		return time.Time{}, fmt.Errorf("experiment %s is required", name)
	}
	return parseOptionalTimestamp(name, value)
}

func parseOptionalTimestamp(name, value string) (time.Time, error) {
	if strings.TrimSpace(value) == "" {
		return time.Time{}, nil
	}
	parsed, err := time.Parse(time.RFC3339, value)
	if err != nil {
		return time.Time{}, fmt.Errorf("experiment %s must be RFC3339: %w", name, err)
	}
	return parsed.UTC(), nil
}

func validateVariants(variants []Variant) error {
	if len(variants) == 0 {
		return errors.New("experiment variants are required")
	}
	total := 0
	seen := make(map[string]struct{}, len(variants))
	for _, variant := range variants {
		key := strings.TrimSpace(variant.Key)
		if key == "" || variant.AllocationBasisPoints <= 0 {
			return errors.New("experiment variant key and positive allocation are required")
		}
		if _, exists := seen[key]; exists {
			return fmt.Errorf("duplicate experiment variant %q", key)
		}
		seen[key] = struct{}{}
		total += variant.AllocationBasisPoints
	}
	if total != 10_000 {
		return errors.New("variant allocation must total 10000 basis points")
	}
	return nil
}

func validateRolloutTransition(current, next string) error {
	allowed := map[string]map[string]bool{
		"draft":     {"draft": true, "scheduled": true, "running": true},
		"scheduled": {"running": true, "paused": true, "ended": true},
		"running":   {"paused": true, "ended": true},
		"paused":    {"running": true, "ended": true},
		"ended":     {},
	}
	nextStates, known := allowed[current]
	if !known {
		return fmt.Errorf("unknown experiment status %q", current)
	}
	if !nextStates[next] {
		return fmt.Errorf("invalid experiment status transition %s -> %s", current, next)
	}
	return nil
}

var experimentStatuses = map[string]struct{}{
	"draft": {}, "scheduled": {}, "running": {}, "paused": {}, "ended": {},
}

func variantsEqual(left, right []Variant) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func assignmentID(experimentID string, experimentRevision int64, subjectKey string) string {
	hasher := fnv.New64a()
	_, _ = hasher.Write([]byte(experimentID))
	_, _ = hasher.Write([]byte{0})
	_, _ = hasher.Write([]byte(fmt.Sprintf("%d", experimentRevision)))
	_, _ = hasher.Write([]byte{0})
	_, _ = hasher.Write([]byte(subjectKey))
	return "assignment-" + fmt.Sprintf("%016x", hasher.Sum64())
}

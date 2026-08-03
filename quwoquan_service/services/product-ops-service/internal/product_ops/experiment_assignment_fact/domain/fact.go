package domain

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

var ErrNotFound = errors.New("experiment assignment not found")

type Fact struct {
	ID                 string `json:"id"`
	ExperimentID       string `json:"experimentId"`
	SubjectKey         string `json:"subjectKey"`
	Variant            string `json:"variant"`
	ExperimentRevision int64  `json:"experimentRevision"`
	AssignedAt         string `json:"assignedAt"`
}

func NewFact(fact Fact) (Fact, error) {
	fact.ID = strings.TrimSpace(fact.ID)
	fact.ExperimentID = strings.TrimSpace(fact.ExperimentID)
	fact.SubjectKey = strings.TrimSpace(fact.SubjectKey)
	fact.Variant = strings.TrimSpace(fact.Variant)
	fact.AssignedAt = strings.TrimSpace(fact.AssignedAt)
	if fact.ID == "" || fact.ExperimentID == "" || fact.SubjectKey == "" || fact.Variant == "" {
		return Fact{}, fmt.Errorf("assignment identity, experiment, subject and variant are required")
	}
	if fact.ExperimentRevision <= 0 {
		return Fact{}, fmt.Errorf("experimentRevision must be positive")
	}
	assignedAt, err := time.Parse(time.RFC3339, fact.AssignedAt)
	if err != nil {
		return Fact{}, fmt.Errorf("assignedAt must be RFC3339: %w", err)
	}
	fact.AssignedAt = assignedAt.UTC().Format(time.RFC3339)
	return fact, nil
}

type Stats struct {
	VariantCounts    map[string]int
	AssignedSubjects int
}

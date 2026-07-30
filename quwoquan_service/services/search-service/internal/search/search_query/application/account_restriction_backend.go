package application

import (
	"context"
	"errors"
	"fmt"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
)

// AccountRestrictionReader exposes the canonical local restriction projection
// without coupling the search use case to MongoDB.
type AccountRestrictionReader interface {
	RestrictedSubjects(
		ctx context.Context,
		subjects []string,
	) (map[string]bool, error)
}

// AccountRestrictionBackend removes suspended authors before shared ranking
// and limiting. A restriction read failure fails closed so a suspended subject
// can never become visible because the projection store is unavailable.
type AccountRestrictionBackend struct {
	inner        rtsearch.RecallBackend
	restrictions AccountRestrictionReader
}

func NewAccountRestrictionBackend(
	inner rtsearch.RecallBackend,
	restrictions AccountRestrictionReader,
) (*AccountRestrictionBackend, error) {
	if inner == nil || restrictions == nil {
		return nil, errors.New(
			"search account restriction backend requires recall and restriction readers",
		)
	}
	return &AccountRestrictionBackend{
		inner:        inner,
		restrictions: restrictions,
	}, nil
}

func (backend *AccountRestrictionBackend) Name() string {
	if backend == nil || backend.inner == nil {
		return "account_restriction"
	}
	return backend.inner.Name() + "+account_restriction"
}

func (backend *AccountRestrictionBackend) Recall(
	ctx context.Context,
	plan rtsearch.RetrievePlan,
) ([]rtsearch.RecallCandidate, error) {
	if backend == nil || backend.inner == nil || backend.restrictions == nil {
		return nil, errors.New("search account restriction backend is not configured")
	}
	candidates, err := backend.inner.Recall(ctx, plan)
	if err != nil {
		return nil, err
	}
	allSubjects := make([]string, 0, len(candidates))
	candidateSubjects := make([][]string, len(candidates))
	for index := range candidates {
		subjects := searchCandidateSubjectIDs(candidates[index].Document)
		candidateSubjects[index] = subjects
		allSubjects = append(allSubjects, subjects...)
	}
	restricted, err := backend.restrictions.RestrictedSubjects(ctx, allSubjects)
	if err != nil {
		return nil, fmt.Errorf("filter search account restrictions: %w", err)
	}
	visible := make([]rtsearch.RecallCandidate, 0, len(candidates))
	for index, candidate := range candidates {
		hidden := false
		for _, subject := range candidateSubjects[index] {
			if restricted[subject] {
				hidden = true
				break
			}
		}
		if !hidden {
			visible = append(visible, candidate)
		}
	}
	return visible, nil
}

func searchCandidateSubjectIDs(document rtsearch.Document) []string {
	seen := map[string]struct{}{}
	subjects := make([]string, 0, 6)
	add := func(value string) {
		value = strings.TrimSpace(value)
		if value == "" {
			return
		}
		if _, exists := seen[value]; exists {
			return
		}
		seen[value] = struct{}{}
		subjects = append(subjects, value)
	}
	if document.ObjectType == rtsearch.ObjectTypeUserProfile {
		add(document.ObjectID)
	}
	for _, field := range []string{
		"authorId",
		"userId",
		"personaId",
		"ownerId",
		"createdByPersonaId",
	} {
		add(document.Fields[field])
	}
	return subjects
}

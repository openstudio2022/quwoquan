package recommendation

import (
	"context"
	"errors"
	"strings"

	rtrec "quwoquan_service/runtime/recommendation"
)

// AccountRestrictionReader is the content recommendation read-side boundary
// for the monotonic UserSuspended/UserRestored projection. Every candidate must
// have an author/persona that can be checked through this port.
type AccountRestrictionReader interface {
	RestrictedSubjects(
		ctx context.Context,
		subjects []string,
	) (map[string]bool, error)
}

type accountRestrictionCandidateSource struct {
	source rtrec.CandidateSource
	reader AccountRestrictionReader
}

// GateAccountRestrictedSource filters each recall source before the engine's
// source quota, pre-rank, ranking and ranked-window limit. It asks the source
// for a bounded refill window, then returns no more than the caller's original
// budget. Mongo-backed sources additionally apply accountRestricted != true in
// their storage predicate, so the normal path filters before its own limit.
func GateAccountRestrictedSource(
	source rtrec.CandidateSource,
	reader AccountRestrictionReader,
) rtrec.CandidateSource {
	if source == nil {
		return nil
	}
	return accountRestrictionCandidateSource{source: source, reader: reader}
}

func (source accountRestrictionCandidateSource) Recall(
	ctx context.Context,
	request rtrec.RecallRequest,
) ([]rtrec.ContentCandidate, error) {
	if source.source == nil || source.reader == nil {
		return nil, errors.New(
			"content recommendation account restriction gate is not configured",
		)
	}
	originalLimit := request.Limit
	if originalLimit <= 0 {
		originalLimit = 60
	}
	request.Limit = accountRestrictionRefillLimit(originalLimit)
	candidates, err := source.source.Recall(ctx, request)
	if err != nil && len(candidates) == 0 {
		return nil, err
	}

	authors := make([]string, 0, len(candidates))
	for _, candidate := range candidates {
		if authorID := strings.TrimSpace(candidate.AuthorID); authorID != "" {
			authors = append(authors, authorID)
		}
	}
	restricted, restrictionErr := source.reader.RestrictedSubjects(ctx, authors)
	if restrictionErr != nil {
		return nil, restrictionErr
	}

	filtered := make([]rtrec.ContentCandidate, 0, min(originalLimit, len(candidates)))
	for _, candidate := range candidates {
		authorID := strings.TrimSpace(candidate.AuthorID)
		// Missing canonical author identity cannot be proven safe and is therefore
		// rejected at the gate rather than entering ranking or a durable window.
		if authorID == "" || restricted[authorID] {
			continue
		}
		filtered = append(filtered, candidate)
		if len(filtered) == originalLimit {
			break
		}
	}
	return filtered, err
}

func accountRestrictionRefillLimit(limit int) int {
	if limit <= 0 {
		return 60
	}
	refill := limit * 2
	if refill < limit+64 {
		refill = limit + 64
	}
	// This is an internal source query budget, not the engine output budget.
	// Keep it finite even when callers pass a malformed or oversized limit.
	if refill > 600 {
		refill = 600
	}
	if refill < limit {
		return limit
	}
	return refill
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package recommendation_test

import (
	"context"
	"errors"
	"testing"

	rtrec "quwoquan_service/runtime/recommendation"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

type accountRestrictionSourceForTest struct {
	candidates []rtrec.ContentCandidate
	limit      int
}

func (source *accountRestrictionSourceForTest) Recall(
	_ context.Context,
	request rtrec.RecallRequest,
) ([]rtrec.ContentCandidate, error) {
	source.limit = request.Limit
	limit := request.Limit
	if limit <= 0 || limit > len(source.candidates) {
		limit = len(source.candidates)
	}
	return append([]rtrec.ContentCandidate(nil), source.candidates[:limit]...), nil
}

type accountRestrictionReaderForTest struct {
	restricted map[string]bool
	err        error
}

func (reader accountRestrictionReaderForTest) RestrictedSubjects(
	_ context.Context,
	_ []string,
) (map[string]bool, error) {
	return reader.restricted, reader.err
}

func TestAccountRestrictionCandidateGateRefillsBeforeRankingLimit(t *testing.T) {
	source := &accountRestrictionSourceForTest{candidates: []rtrec.ContentCandidate{
		{ContentID: "post-restricted-1", AuthorID: "persona-restricted-1"},
		{ContentID: "post-restricted-2", AuthorID: "persona-restricted-2"},
		{ContentID: "post-visible-1", AuthorID: "persona-visible-1"},
		{ContentID: "post-visible-2", AuthorID: "persona-visible-2"},
	}}
	gated := recinfra.GateAccountRestrictedSource(
		source,
		accountRestrictionReaderForTest{restricted: map[string]bool{
			"persona-restricted-1": true,
			"persona-restricted-2": true,
		}},
	)

	candidates, err := gated.Recall(t.Context(), rtrec.RecallRequest{Limit: 2})
	if err != nil {
		t.Fatalf("filter account-restricted candidates: %v", err)
	}
	if source.limit <= 2 {
		t.Fatalf("source refill limit=%d, want greater than final limit", source.limit)
	}
	if len(candidates) != 2 ||
		candidates[0].ContentID != "post-visible-1" ||
		candidates[1].ContentID != "post-visible-2" {
		t.Fatalf("restriction gate returned %+v", candidates)
	}
}

func TestAccountRestrictionCandidateGateFailsClosed(t *testing.T) {
	source := &accountRestrictionSourceForTest{candidates: []rtrec.ContentCandidate{
		{ContentID: "post-missing-author"},
	}}
	gated := recinfra.GateAccountRestrictedSource(
		source,
		accountRestrictionReaderForTest{restricted: map[string]bool{}},
	)
	candidates, err := gated.Recall(t.Context(), rtrec.RecallRequest{Limit: 1})
	if err != nil || len(candidates) != 0 {
		t.Fatalf("missing author must be filtered: candidates=%+v err=%v", candidates, err)
	}

	dependencyErr := errors.New("restriction projection unavailable")
	gated = recinfra.GateAccountRestrictedSource(
		source,
		accountRestrictionReaderForTest{err: dependencyErr},
	)
	candidates, err = gated.Recall(t.Context(), rtrec.RecallRequest{Limit: 1})
	if !errors.Is(err, dependencyErr) || len(candidates) != 0 {
		t.Fatalf("reader failure did not fail closed: candidates=%+v err=%v", candidates, err)
	}
}

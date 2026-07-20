package main

import (
	"context"
	"testing"

	rtrec "quwoquan_service/runtime/recommendation"
)

type candidateSourceIdentity struct{ id string }

func (s *candidateSourceIdentity) Recall(
	context.Context,
	rtrec.RecallRequest,
) ([]rtrec.ContentCandidate, error) {
	return nil, nil
}

func TestRecommendationCandidateSourcesUsesOneFreshnessTrack(t *testing.T) {
	materialized := &candidateSourceIdentity{id: "rm_discovery_feed"}
	fallback := &candidateSourceIdentity{id: "posts"}

	got := recommendationCandidateSources(
		[]rtrec.CandidateSource{materialized},
		fallback,
	)
	if len(got) != 1 || got[0] != materialized {
		t.Fatalf("materialized recall must exclude stale posts fallback: %+v", got)
	}

	got = recommendationCandidateSources(nil, fallback)
	if len(got) != 1 || got[0] != fallback {
		t.Fatalf("fallback must remain available without materialized recall: %+v", got)
	}
}

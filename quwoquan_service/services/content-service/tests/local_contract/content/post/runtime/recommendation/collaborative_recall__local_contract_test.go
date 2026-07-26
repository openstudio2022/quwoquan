package recommendationlocalcontract

import (
	"context"
	"testing"

	"quwoquan_service/runtime/recommendation"
)

type stubCollaborativeStore struct {
	i2i       []recommendation.ContentCandidate
	u2i       []recommendation.ContentCandidate
	lastSeeds []string
}

func (s *stubCollaborativeStore) GetI2ICandidates(_ context.Context, seeds []string, limit int) ([]recommendation.ContentCandidate, error) {
	s.lastSeeds = append([]string(nil), seeds...)
	if limit > len(s.i2i) {
		limit = len(s.i2i)
	}
	return s.i2i[:limit], nil
}

func (s *stubCollaborativeStore) GetU2ICandidates(_ context.Context, _ string, limit int) ([]recommendation.ContentCandidate, error) {
	if limit > len(s.u2i) {
		limit = len(s.u2i)
	}
	return s.u2i[:limit], nil
}

func TestCollaborativeRecallSourceLocalContractTest(t *testing.T) {
	store := &stubCollaborativeStore{
		i2i: []recommendation.ContentCandidate{
			{ContentID: "shared", ContentType: "article"},
		},
		u2i: []recommendation.ContentCandidate{
			{ContentID: "shared", ContentType: "article"},
			{ContentID: "u2i-1", ContentType: "video"},
		},
	}
	src := recommendation.NewCollaborativeRecallSource(store, recommendation.CollaborativeRecallConfig{
		Enabled:          true,
		MaxI2ICandidates: 2,
		MaxU2ICandidates: 2,
		QuotaPct:         50,
	})

	candidates, err := src.Recall(context.Background(), recommendation.RecallRequest{
		UserID:         "u1",
		Limit:          4,
		SeedContentIDs: []string{"seed_1"},
		FeedRequestID:  "frq_not_a_content_seed",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(candidates) != 2 {
		t.Fatalf("quota should cap collaborative candidates to 2, got %d", len(candidates))
	}
	if candidates[0].RecallPath != recommendation.RecallPathCollaborativeI2I {
		t.Fatalf("first path = %s, want i2i", candidates[0].RecallPath)
	}
	if candidates[1].ContentID != "u2i-1" || candidates[1].RecallPath != recommendation.RecallPathCollaborativeU2I {
		t.Fatalf("u2i duplicate should be skipped and next materialized candidate used, got %+v", candidates)
	}
	if len(store.lastSeeds) != 1 || store.lastSeeds[0] != "seed_1" {
		t.Fatalf("i2i seeds must come from served content IDs, got %v", store.lastSeeds)
	}
}

func TestCollaborativeRecallSourceDisabledReturnsEmptyLocalContractTest(t *testing.T) {
	src := recommendation.NewCollaborativeRecallSource(&stubCollaborativeStore{
		i2i: []recommendation.ContentCandidate{{ContentID: "i2i-1"}},
	}, recommendation.CollaborativeRecallConfig{Enabled: false, QuotaPct: 50})

	candidates, err := src.Recall(context.Background(), recommendation.RecallRequest{UserID: "u1", Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	if len(candidates) != 0 {
		t.Fatalf("disabled collaborative source should return empty, got %d", len(candidates))
	}
}

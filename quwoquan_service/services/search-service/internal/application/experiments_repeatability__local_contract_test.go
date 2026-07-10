package application

import (
	"context"
	"testing"

	"quwoquan_service/services/search-service/internal/application/queryheat"
)

// Identity-less anonymous (empty subjectKey) must always resolve to control, and
// the SAME stable subject must always resolve to the SAME bucket — so an
// anonymous user's repeated query never jumps between control and term_heat.
func TestAssignEmptySubjectIsControlAndSticky(t *testing.T) {
	exp := NewExperiments(ExperimentConfig{}) // default 50/50 enabled

	for i := 0; i < 100; i++ {
		if got := exp.Assign(context.Background(), ""); got != BucketControl {
			t.Fatalf("empty subject must be control, got %q at iter %d", got, i)
		}
	}

	// A stable subject is deterministic across repeated assignments.
	const subj = "sess-abc-123"
	first := exp.Assign(context.Background(), subj)
	for i := 0; i < 100; i++ {
		if got := exp.Assign(context.Background(), subj); got != first {
			t.Fatalf("subject %q not sticky: got %q want %q at iter %d", subj, got, first, i)
		}
	}
	if first != BucketControl && first != BucketTermHeat {
		t.Fatalf("unexpected bucket %q", first)
	}
}

// The term_heat re-rank must yield a repeatable TopN: identical inputs in any
// candidate arrival order produce the identical objectType+objectId sequence
// (the decorator reuses rtsearch.SortHitsStable, the single order truth source).
func TestDecorateRepeatableTopNAcrossInputOrder(t *testing.T) {
	provider := fakeTermHeat{terms: []queryheat.TermHeat{{NormalizedTerm: "火锅", Relevance: 10}}}
	d := NewRankingDecorator(provider, forcedBucket(BucketTermHeat), 5.0, nil)

	resp := baseResponse()
	out1 := d.Decorate(context.Background(), resp, "成都", "user-1")

	// reverse the input hit order and re-run; re-ranked output keys must match.
	rev := baseResponse()
	rev.Hits[0], rev.Hits[1] = rev.Hits[1], rev.Hits[0]
	out2 := d.Decorate(context.Background(), rev, "成都", "user-1")

	if len(out1.Hits) != len(out2.Hits) || len(out1.Hits) == 0 {
		t.Fatalf("len mismatch/empty %d vs %d", len(out1.Hits), len(out2.Hits))
	}
	for i := range out1.Hits {
		k1 := string(out1.Hits[i].Target) + "|" + out1.Hits[i].ObjectID
		k2 := string(out2.Hits[i].Target) + "|" + out2.Hits[i].ObjectID
		if k1 != k2 {
			t.Fatalf("TopN not repeatable at %d: %q vs %q", i, k1, k2)
		}
	}
}

package search

import (
	"math/rand"
	"testing"
)

func keysOf(hits []RetrieveHit) []string {
	out := make([]string, len(hits))
	for i, h := range hits {
		out[i] = string(h.Target) + "|" + h.ObjectID
	}
	return out
}

// SortHitsStable must be a TOTAL order: identical multisets of hits produce the
// identical key sequence no matter the input arrival order. This is the search
// repeatability guarantee (no jump between identical queries / replicas).
func TestSortHitsStableTotalOrderUnderPermutation(t *testing.T) {
	base := []RetrieveHit{
		{Target: TargetArticle, ObjectID: "a3", Title: "同名", Score: 5},
		{Target: TargetArticle, ObjectID: "a1", Title: "同名", Score: 5}, // equal score+title -> ObjectID breaks
		{Target: TargetEntity, ObjectID: "e9", Title: "同名", Score: 5},  // equal score+title -> Target breaks
		{Target: TargetArticle, ObjectID: "a2", Title: "高分", Score: 9},
		{Target: TargetArticle, ObjectID: "a8", Title: "低分", Score: 1},
	}

	want := make([]RetrieveHit, len(base))
	copy(want, base)
	SortHitsStable(want)
	wantKeys := keysOf(want)

	rng := rand.New(rand.NewSource(7))
	for trial := 0; trial < 50; trial++ {
		shuffled := make([]RetrieveHit, len(base))
		copy(shuffled, base)
		rng.Shuffle(len(shuffled), func(i, j int) { shuffled[i], shuffled[j] = shuffled[j], shuffled[i] })
		SortHitsStable(shuffled)
		got := keysOf(shuffled)
		for i := range got {
			if got[i] != wantKeys[i] {
				t.Fatalf("trial %d: order not repeatable\n got=%v\nwant=%v", trial, got, wantKeys)
			}
		}
	}

	// Assert the exact expected total order:
	// Score 9 first; then the three score-5 ties ordered by Title asc, and within
	// the equal "同名" title by Target asc then ObjectID asc; Score 1 last.
	expected := []string{
		"article|a2", // 高分 score 9
		"article|a1", // 同名 score5, article, a1
		"article|a3", // 同名 score5, article, a3
		"entity|e9",  // 同名 score5, entity
		"article|a8", // 低分 score 1
	}
	for i := range expected {
		if wantKeys[i] != expected[i] {
			t.Fatalf("tie-break order wrong at %d: got=%v want=%v", i, wantKeys, expected)
		}
	}
}

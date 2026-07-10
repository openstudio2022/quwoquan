package queryheat

import (
	"testing"
	"time"
)

func fixedNow() time.Time { return time.Date(2026, 6, 16, 0, 0, 0, 0, time.UTC) }

// recentVsOld proves the recency half-life: at equal raw frequency, the more
// recent term must carry the higher decayed heat (and thus relevance).
func TestComputeRecencyDecay(t *testing.T) {
	now := fixedNow()
	cfg := Config{HalfLifeHours: 24, Now: func() time.Time { return now }}
	queries := []QueryRecord{
		{NormalizedTerm: "recent", CreatedAt: now.Add(-1 * time.Hour)},
		{NormalizedTerm: "old", CreatedAt: now.Add(-240 * time.Hour)},
	}
	heats := Compute(queries, nil, cfg)
	byTerm := HeatByTerm(heats)
	recent, old := byTerm["recent"], byTerm["old"]
	if recent.Frequency != 1 || old.Frequency != 1 {
		t.Fatalf("frequency not counted: recent=%d old=%d", recent.Frequency, old.Frequency)
	}
	if recent.DecayedHeat <= old.DecayedHeat {
		t.Fatalf("recent term must outweigh old at equal frequency: recent=%.4f old=%.4f", recent.DecayedHeat, old.DecayedHeat)
	}
	if heats[0].NormalizedTerm != "recent" {
		t.Fatalf("heats must sort by relevance desc, got first=%q", heats[0].NormalizedTerm)
	}
}

// ctrLift proves CTR weighting: two terms with identical frequency/recency but
// different click-through must rank the higher-CTR term first.
func TestComputeCTRWeighting(t *testing.T) {
	now := fixedNow()
	cfg := Config{HalfLifeHours: 72, CTRBoost: 2, Now: func() time.Time { return now }}
	at := now.Add(-1 * time.Hour)
	queries := []QueryRecord{
		{NormalizedTerm: "clicky", CreatedAt: at},
		{NormalizedTerm: "ignored", CreatedAt: at},
	}
	feedback := []FeedbackRecord{
		{NormalizedTerm: "clicky", EventType: "impression", CreatedAt: at},
		{NormalizedTerm: "clicky", EventType: "click", ObjectID: "post_1", CreatedAt: at},
		{NormalizedTerm: "ignored", EventType: "impression", CreatedAt: at},
	}
	byTerm := HeatByTerm(Compute(queries, feedback, cfg))
	clicky, ignored := byTerm["clicky"], byTerm["ignored"]
	if clicky.CTR != 1 {
		t.Fatalf("clicky CTR want 1, got %.4f", clicky.CTR)
	}
	if ignored.CTR != 0 {
		t.Fatalf("ignored CTR want 0, got %.4f", ignored.CTR)
	}
	if clicky.Relevance <= ignored.Relevance {
		t.Fatalf("high-CTR term must rank above zero-CTR: clicky=%.4f ignored=%.4f", clicky.Relevance, ignored.Relevance)
	}
	if len(clicky.TopObjectIDs) != 1 || clicky.TopObjectIDs[0] != "post_1" {
		t.Fatalf("query->object relevance must retain clicked object, got %v", clicky.TopObjectIDs)
	}
}

func TestRelatedTermsPrefersOverlapThenHeat(t *testing.T) {
	now := fixedNow()
	cfg := Config{HalfLifeHours: 72, Now: func() time.Time { return now }}
	at := now.Add(-1 * time.Hour)
	queries := []QueryRecord{
		{NormalizedTerm: "成都 美食", CreatedAt: at},
		{NormalizedTerm: "成都 火锅", CreatedAt: at},
		{NormalizedTerm: "成都 火锅", CreatedAt: at}, // hotter overlap term
		{NormalizedTerm: "北京 烤鸭", CreatedAt: at},
	}
	heats := Compute(queries, nil, cfg)
	related := RelatedTerms("成都", heats, 5)
	if len(related) == 0 {
		t.Fatalf("expected related terms for 成都")
	}
	// Overlapping terms come first, hottest overlap first.
	if related[0].NormalizedTerm != "成都 火锅" {
		t.Fatalf("hottest overlapping term must lead, got %q", related[0].NormalizedTerm)
	}
	for _, r := range related[:min(2, len(related))] {
		if r.NormalizedTerm == "北京 烤鸭" {
			t.Fatalf("non-overlapping term must not precede overlapping ones")
		}
	}
}

func TestRelatedTermsEmptyQueryFallsBackToHottest(t *testing.T) {
	now := fixedNow()
	cfg := Config{HalfLifeHours: 72, Now: func() time.Time { return now }}
	at := now.Add(-1 * time.Hour)
	queries := []QueryRecord{
		{NormalizedTerm: "hot", CreatedAt: at},
		{NormalizedTerm: "hot", CreatedAt: at},
		{NormalizedTerm: "cold", CreatedAt: at},
	}
	heats := Compute(queries, nil, cfg)
	related := RelatedTerms("", heats, 5)
	if len(related) == 0 || related[0].NormalizedTerm != "hot" {
		t.Fatalf("empty query must fall back to hottest term, got %v", related)
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

package recommendation

import (
	"math"
	"testing"
	"time"
)

func approxEq(a, b float64) bool { return math.Abs(a-b) < 1e-9 }

func findInterest(p InterestProfile, tagRef string) (TopInterest, bool) {
	for _, ti := range p.TopInterests {
		if ti.TagRef == tagRef {
			return ti, true
		}
	}
	return TopInterest{}, false
}

func TestComputeInterestProfile_NormalizationAndDimensions(t *testing.T) {
	now := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	f := &UserFeatures{
		TotalEvents:        50,
		TopicAffinities:    map[string]float64{"旅行": 10, "美食": 5, "摄影": 2},
		AudienceAffinities: map[string]float64{"学生": 4},
		FormatAffinities:   map[string]float64{"图文": 8},
		EntityAffinities:   map[string]float64{"稻城亚丁": 6},
	}

	p := ComputeInterestProfile(f, now, now, DefaultInterestProfileConfig())

	if p.LifecycleStage != StageActive {
		t.Fatalf("lifecycle = %s, want active", p.LifecycleStage)
	}
	if p.FreshnessDays != 0 {
		t.Fatalf("freshnessDays = %d, want 0", p.FreshnessDays)
	}

	travel, ok := findInterest(p, "旅行")
	if !ok {
		t.Fatal("旅行 missing from topInterests")
	}
	if !approxEq(travel.Score, 1.0) {
		t.Fatalf("旅行 score = %v, want 1.0 (per-dimension max norm)", travel.Score)
	}
	if travel.Dimension != DimTopic || travel.Level != 5 {
		t.Fatalf("旅行 dim=%s level=%d, want topic/5", travel.Dimension, travel.Level)
	}

	food, _ := findInterest(p, "美食")
	if !approxEq(food.Score, 0.5) { // 5/10
		t.Fatalf("美食 score = %v, want 0.5", food.Score)
	}

	if got := p.DimensionTops["topic"]; len(got) != 3 || got[0] != "旅行" {
		t.Fatalf("dimensionTops[topic] = %v, want [旅行 ...]", got)
	}
	if got := p.DimensionTops["entity"]; len(got) != 1 || got[0] != "稻城亚丁" {
		t.Fatalf("dimensionTops[entity] = %v", got)
	}

	// topInterests sorted desc by score
	for i := 1; i < len(p.TopInterests); i++ {
		if p.TopInterests[i-1].Score < p.TopInterests[i].Score {
			t.Fatalf("topInterests not sorted desc at %d", i)
		}
	}
}

func TestComputeInterestProfile_TopNTruncation(t *testing.T) {
	now := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	topic := map[string]float64{}
	for i := 0; i < 30; i++ {
		topic[string(rune('a'+i))] = float64(30 - i)
	}
	f := &UserFeatures{TotalEvents: 100, TopicAffinities: topic}
	cfg := DefaultInterestProfileConfig()
	cfg.TopN = 5

	p := ComputeInterestProfile(f, now, now, cfg)
	if len(p.TopInterests) != 5 {
		t.Fatalf("topInterests len = %d, want 5", len(p.TopInterests))
	}
}

func TestComputeInterestProfile_FreshnessDecayAndDormant(t *testing.T) {
	now := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	updatedAt := now.Add(-30 * 24 * time.Hour) // 30 days stale, halfLife=30 -> decay 0.5
	f := &UserFeatures{
		TotalEvents:     50,
		TopicAffinities: map[string]float64{"旅行": 10},
	}

	p := ComputeInterestProfile(f, updatedAt, now, DefaultInterestProfileConfig())

	if p.FreshnessDays != 30 {
		t.Fatalf("freshnessDays = %d, want 30", p.FreshnessDays)
	}
	if p.LifecycleStage != StageDormant {
		t.Fatalf("lifecycle = %s, want dormant", p.LifecycleStage)
	}
	travel, _ := findInterest(p, "旅行")
	if !approxEq(travel.Score, 0.5) {
		t.Fatalf("旅行 decayed score = %v, want 0.5", travel.Score)
	}
}

func TestComputeInterestProfile_NilAndEmpty(t *testing.T) {
	now := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)

	p := ComputeInterestProfile(nil, time.Time{}, now, DefaultInterestProfileConfig())
	if len(p.TopInterests) != 0 || p.LifecycleStage != StageNew {
		t.Fatalf("nil features: got %+v", p)
	}
	if p.DimensionTops == nil {
		t.Fatal("nil features: DimensionTops should be non-nil empty map")
	}

	empty := &UserFeatures{}
	p2 := ComputeInterestProfile(empty, now, now, DefaultInterestProfileConfig())
	if len(p2.TopInterests) != 0 {
		t.Fatalf("empty features: topInterests = %v", p2.TopInterests)
	}
	if p2.LifecycleStage != StageNew { // totalEvents 0 < 5
		t.Fatalf("empty features lifecycle = %s, want new", p2.LifecycleStage)
	}
}

func TestDecayFactor(t *testing.T) {
	cases := []struct {
		half, elapsed, want float64
	}{
		{30, 30, 0.5},
		{30, 60, 0.25},
		{30, 0, 1},
		{0, 10, 1},
		{-1, 10, 1},
	}
	for _, c := range cases {
		if got := DecayFactor(c.half, c.elapsed); !approxEq(got, c.want) {
			t.Fatalf("DecayFactor(%v,%v) = %v, want %v", c.half, c.elapsed, got, c.want)
		}
	}
}

func TestScoreToLevel(t *testing.T) {
	cases := []struct {
		score float64
		want  int
	}{
		{0, 0}, {-1, 0}, {0.1, 1}, {0.3, 2}, {0.5, 3}, {0.7, 4}, {0.9, 5}, {1.0, 5},
	}
	for _, c := range cases {
		if got := scoreToLevel(c.score); got != c.want {
			t.Fatalf("scoreToLevel(%v) = %d, want %d", c.score, got, c.want)
		}
	}
}

func TestClassifyLifecycle(t *testing.T) {
	cfg := DefaultInterestProfileConfig()
	if got := classifyLifecycle(100, 0, cfg); got != StageActive {
		t.Fatalf("active case = %s", got)
	}
	if got := classifyLifecycle(2, 0, cfg); got != StageNew {
		t.Fatalf("new case = %s", got)
	}
	if got := classifyLifecycle(100, 30, cfg); got != StageDormant {
		t.Fatalf("dormant case = %s", got)
	}
}

func TestInterestEntropy(t *testing.T) {
	if got := InterestEntropy(nil); got != 0 {
		t.Fatalf("empty entropy = %v, want 0", got)
	}
	// Single dominant interest → 0 bits.
	single := []TopInterest{{TagRef: "a", Score: 1.0}}
	if got := InterestEntropy(single); !approxEq(got, 0) {
		t.Fatalf("single entropy = %v, want 0", got)
	}
	// Two equal interests → 1 bit.
	two := []TopInterest{{TagRef: "a", Score: 0.5}, {TagRef: "b", Score: 0.5}}
	if got := InterestEntropy(two); !approxEq(got, 1) {
		t.Fatalf("two-equal entropy = %v, want 1", got)
	}
	// Four equal interests → 2 bits.
	four := []TopInterest{{Score: 0.25}, {Score: 0.25}, {Score: 0.25}, {Score: 0.25}}
	if got := InterestEntropy(four); !approxEq(got, 2) {
		t.Fatalf("four-equal entropy = %v, want 2", got)
	}
	// Skewed distribution has positive but lower-than-max entropy.
	skewed := []TopInterest{{Score: 0.9}, {Score: 0.1}}
	got := InterestEntropy(skewed)
	if got <= 0 || got >= 1 {
		t.Fatalf("skewed entropy = %v, want in (0,1)", got)
	}
}

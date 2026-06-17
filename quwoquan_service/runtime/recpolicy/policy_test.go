package recpolicy

import (
	"strings"
	"testing"
)

// minimal valid policy YAML used across tests.
const testPolicyYAML = `
version: 1
policyVersion: test-v1
defaultPreset: control
weightPresets:
  control:
    tagRelevance: 3.0
    popularity: 2.0
    freshness: 1.5
    negativePenalty: 5.0
    formatMatch: 0.6
  engagement_heavy:
    tagRelevance: 2.0
    popularity: 4.0
    freshness: 1.0
    negativePenalty: 5.0
    formatMatch: 0.8
scorer:
  popularity:
    viewCoefficient: 0.1
    likeCoefficient: 1.0
    commentCoefficient: 1.5
    shareCoefficient: 2.0
  freshnessHalfLifeHours: 24.0
  exploreFraction: 0.1
  maxAuthorPerFeed: 3
  coldStartAgeHours: 24.0
  coldStartViewThreshold: 100
experiments:
  - id: rec_scoring_weights
    enabled: true
    eligibleSegments: []
    buckets:
      - { name: control, weightPct: 60 }
      - { name: engagement_heavy, weightPct: 40 }
  - id: rec_premium_only
    enabled: true
    eligibleSegments: [travel_enthusiast]
    buckets:
      - { name: control, weightPct: 50 }
      - { name: engagement_heavy, weightPct: 50 }
segmentTargeting:
  - segment: travel_enthusiast
    presetOverride: engagement_heavy
  - segment: visual_content_lover
    weightDeltas:
      formatMatch: 0.4
guardrails:
  - metric: ctr
    baselinePreset: control
    minRatio: 0.95
    minSamples: 1000
    window: 24h
    action: suggest_only
exposureGovernance:
  frequencyAndNearDup:
    enabled: true
    maxSameAuthorPerWindow: 2
    maxSameTagPerWindow: 3
    maxSameTopicPerWindow: 3
    nearDupJaccardMax: 0.8
    softFallbackMinFillPct: 80
`

func mustParse(t *testing.T, raw string) *RecPolicy {
	t.Helper()
	p, err := Parse([]byte(raw))
	if err != nil {
		t.Fatalf("Parse failed: %v", err)
	}
	return p
}

func TestParse_Valid(t *testing.T) {
	p := mustParse(t, testPolicyYAML)
	if p.PolicyVersion != "test-v1" {
		t.Fatalf("policyVersion = %q", p.PolicyVersion)
	}
	if len(p.WeightPresets) != 2 {
		t.Fatalf("weightPresets = %d, want 2", len(p.WeightPresets))
	}
	if p.Scorer.Popularity.ShareCoefficient != 2.0 {
		t.Fatalf("share coeff = %v", p.Scorer.Popularity.ShareCoefficient)
	}
}

func TestValidate_Errors(t *testing.T) {
	cases := []struct {
		name   string
		mutate func(*RecPolicy)
		want   string
	}{
		{"missing default preset", func(p *RecPolicy) { p.DefaultPreset = "nope" }, "defaultPreset"},
		{"no version", func(p *RecPolicy) { p.PolicyVersion = "" }, "policyVersion"},
		{"halflife zero", func(p *RecPolicy) { p.Scorer.FreshnessHalfLifeHours = 0 }, "freshnessHalfLifeHours"},
		{"maxauthor zero", func(p *RecPolicy) { p.Scorer.MaxAuthorPerFeed = 0 }, "maxAuthorPerFeed"},
		{"explore out of range", func(p *RecPolicy) { p.Scorer.ExploreFraction = 2 }, "exploreFraction"},
		{"bucket sum not 100", func(p *RecPolicy) { p.Experiments[0].Buckets[0].WeightPct = 10 }, "want 100"},
		{"bad preset override", func(p *RecPolicy) { p.SegmentTargeting[0].PresetOverride = "ghost" }, "presetOverride"},
		{"bad weight dim", func(p *RecPolicy) { p.SegmentTargeting[1].WeightDeltas = map[string]float64{"nope": 1} }, "unknown weight dim"},
		{"guardrail action", func(p *RecPolicy) { p.Guardrails[0].Action = "auto_rollback" }, "only \"suggest_only\""},
		{"guardrail baseline", func(p *RecPolicy) { p.Guardrails[0].BaselinePreset = "ghost" }, "baselinePreset"},
		{"bad near dup threshold", func(p *RecPolicy) { p.ExposureGovernance.FrequencyAndNearDup.NearDupJaccardMax = 2 }, "frequencyAndNearDup"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			p := mustParse(t, testPolicyYAML)
			tc.mutate(p)
			err := p.Validate()
			if err == nil {
				t.Fatalf("expected validation error containing %q", tc.want)
			}
			if !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("error %q does not contain %q", err.Error(), tc.want)
			}
		})
	}
}

func TestResolveWeights_DefaultPresetWhenNoBucket(t *testing.T) {
	p := mustParse(t, testPolicyYAML)
	r := p.ResolveWeights("", nil)
	if r.Preset != "control" {
		t.Fatalf("preset = %q, want control", r.Preset)
	}
	if r.Weights.TagRelevance != 3.0 {
		t.Fatalf("tagRelevance = %v, want 3.0", r.Weights.TagRelevance)
	}
	if r.AppliedSegment != "" {
		t.Fatalf("appliedSegment = %q, want empty", r.AppliedSegment)
	}
}

func TestResolveWeights_BucketPreset(t *testing.T) {
	p := mustParse(t, testPolicyYAML)
	r := p.ResolveWeights("engagement_heavy", nil)
	if r.Preset != "engagement_heavy" || r.Weights.Popularity != 4.0 {
		t.Fatalf("got preset=%q popularity=%v", r.Preset, r.Weights.Popularity)
	}
}

func TestResolveWeights_SegmentPresetOverride(t *testing.T) {
	p := mustParse(t, testPolicyYAML)
	// bucket says control, but segment override forces engagement_heavy.
	r := p.ResolveWeights("control", []string{"travel_enthusiast"})
	if r.Preset != "engagement_heavy" {
		t.Fatalf("preset = %q, want engagement_heavy (segment override)", r.Preset)
	}
	if r.AppliedSegment != "travel_enthusiast" {
		t.Fatalf("appliedSegment = %q", r.AppliedSegment)
	}
}

func TestResolveWeights_SegmentWeightDeltas(t *testing.T) {
	p := mustParse(t, testPolicyYAML)
	base := p.WeightPresets["control"].FormatMatch
	r := p.ResolveWeights("control", []string{"visual_content_lover"})
	if got := r.Weights.FormatMatch; got != base+0.4 {
		t.Fatalf("formatMatch = %v, want %v", got, base+0.4)
	}
	if r.AppliedSegment != "visual_content_lover" {
		t.Fatalf("appliedSegment = %q", r.AppliedSegment)
	}
}

func TestResolveBucket_Eligibility(t *testing.T) {
	p := mustParse(t, testPolicyYAML)
	// rec_premium_only is gated to travel_enthusiast.
	if _, ok := p.ResolveBucket("rec_premium_only", "u1", nil); ok {
		t.Fatal("expected ineligible (no segments)")
	}
	if _, ok := p.ResolveBucket("rec_premium_only", "u1", []string{"travel_enthusiast"}); !ok {
		t.Fatal("expected eligible with matching segment")
	}
	// open experiment: always eligible.
	if _, ok := p.ResolveBucket("rec_scoring_weights", "u1", nil); !ok {
		t.Fatal("expected eligible for open experiment")
	}
	// disabled / missing experiment falls back.
	if got := p.ResolveBucketOr("ghost", "u1", nil, "champion"); got != "champion" {
		t.Fatalf("fallback = %q, want champion", got)
	}
}

func TestResolveBucket_Deterministic(t *testing.T) {
	p := mustParse(t, testPolicyYAML)
	b1, _ := p.ResolveBucket("rec_scoring_weights", "stable-user", nil)
	b2, _ := p.ResolveBucket("rec_scoring_weights", "stable-user", nil)
	if b1 != b2 {
		t.Fatalf("non-deterministic bucket: %q vs %q", b1, b2)
	}
}

func TestBaseline_Valid(t *testing.T) {
	// The codegen snapshot must always parse and validate.
	b := Baseline()
	if err := b.Validate(); err != nil {
		t.Fatalf("baseline invalid: %v", err)
	}
	if b.PolicyVersion != BaselinePolicyVersion {
		t.Fatalf("baseline policyVersion %q != const %q", b.PolicyVersion, BaselinePolicyVersion)
	}
	if _, ok := b.WeightPresets["control"]; !ok {
		t.Fatal("baseline missing control preset")
	}
}

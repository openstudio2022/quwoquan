// Package recpolicy is the single runtime source of truth for recommendation
// scoring policy: the 12-dimension weight presets, the secondary scorer
// coefficients, AB experiment definitions, segment targeting, and guardrails.
//
// The canonical data lives in metadata
// (contracts/metadata/recommendation/rec_model/policy.yaml). codegen_rec_policy
// captures a compile-time snapshot as the fail-safe Baseline (rec_policy_baseline.gen.go),
// and Store hot-loads the live YAML at runtime with validate-before-swap and
// last-good retention. No scoring weight / coefficient / experiment is ever
// hand-coded in the engine; changing the YAML changes behavior without code edits.
package recpolicy

import (
	"errors"
	"fmt"

	runtimeexperiments "quwoquan_service/runtime/experiments"
	"gopkg.in/yaml.v3"
)

// Experiment IDs (single source; consumed by the engine and the policy resolver).
const (
	ExpScoringWeights = "rec_scoring_weights"
	ExpModelVsRule    = "rec_model_vs_rule"
	ExpModelVersion   = "rec_model_version"
)

// GuardrailActionSuggestOnly is the only permitted guardrail action: guardrails
// produce advice for human review, never auto-mutate live policy or auto-roll-back.
const GuardrailActionSuggestOnly = "suggest_only"

// WeightPreset is a named 12-dimension scoring weight configuration. Field set
// mirrors the RuleScorer linear combination in runtime/recommendation.
type WeightPreset struct {
	TagRelevance    float64 `yaml:"tagRelevance" json:"tagRelevance"`
	AuthorAffinity  float64 `yaml:"authorAffinity" json:"authorAffinity"`
	Popularity      float64 `yaml:"popularity" json:"popularity"`
	Freshness       float64 `yaml:"freshness" json:"freshness"`
	SocialPrior     float64 `yaml:"socialPrior" json:"socialPrior"`
	ExploreBoost    float64 `yaml:"exploreBoost" json:"exploreBoost"`
	NegativePenalty float64 `yaml:"negativePenalty" json:"negativePenalty"`
	DwellBonus      float64 `yaml:"dwellBonus" json:"dwellBonus"`
	EntityAffinity  float64 `yaml:"entityAffinity" json:"entityAffinity"`
	TopicMatch      float64 `yaml:"topicMatch" json:"topicMatch"`
	AudienceMatch   float64 `yaml:"audienceMatch" json:"audienceMatch"`
	FormatMatch     float64 `yaml:"formatMatch" json:"formatMatch"`
}

// addDelta applies a signed delta to one named dimension. Returns false when the
// dimension name is unknown. Single source for the canonical dimension names
// (validWeightDim reuses it with a zero delta).
func (w *WeightPreset) addDelta(dim string, delta float64) bool {
	switch dim {
	case "tagRelevance":
		w.TagRelevance += delta
	case "authorAffinity":
		w.AuthorAffinity += delta
	case "popularity":
		w.Popularity += delta
	case "freshness":
		w.Freshness += delta
	case "socialPrior":
		w.SocialPrior += delta
	case "exploreBoost":
		w.ExploreBoost += delta
	case "negativePenalty":
		w.NegativePenalty += delta
	case "dwellBonus":
		w.DwellBonus += delta
	case "entityAffinity":
		w.EntityAffinity += delta
	case "topicMatch":
		w.TopicMatch += delta
	case "audienceMatch":
		w.AudienceMatch += delta
	case "formatMatch":
		w.FormatMatch += delta
	default:
		return false
	}
	return true
}

func validWeightDim(dim string) bool {
	var w WeightPreset
	return w.addDelta(dim, 0)
}

// PopularityCoeffs are the engagement sub-weights inside the log-scaled
// popularity term: log1p(view*view + like*like + comment*comment + share*share).
type PopularityCoeffs struct {
	ViewCoefficient    float64 `yaml:"viewCoefficient" json:"viewCoefficient"`
	LikeCoefficient    float64 `yaml:"likeCoefficient" json:"likeCoefficient"`
	CommentCoefficient float64 `yaml:"commentCoefficient" json:"commentCoefficient"`
	ShareCoefficient   float64 `yaml:"shareCoefficient" json:"shareCoefficient"`
}

// ScorerConfig holds every secondary coefficient previously hand-coded in
// scorer.go / engine.go, so they are all metadata-driven.
type ScorerConfig struct {
	Popularity             PopularityCoeffs `yaml:"popularity" json:"popularity"`
	FreshnessHalfLifeHours float64          `yaml:"freshnessHalfLifeHours" json:"freshnessHalfLifeHours"`
	ExploreFraction        float64          `yaml:"exploreFraction" json:"exploreFraction"`
	LongTermTagBoostFactor float64          `yaml:"longTermTagBoostFactor" json:"longTermTagBoostFactor"`
	CircleTagAffinityFactor float64         `yaml:"circleTagAffinityFactor" json:"circleTagAffinityFactor"`
	SocialInterestFactor   float64          `yaml:"socialInterestFactor" json:"socialInterestFactor"`
	EngagementBonusFactor  float64          `yaml:"engagementBonusFactor" json:"engagementBonusFactor"`
	ENERBonusFactor        float64          `yaml:"enerBonusFactor" json:"enerBonusFactor"`
	EntityCategoryFactor   float64          `yaml:"entityCategoryFactor" json:"entityCategoryFactor"`
	NegativePenaltyFactor  float64          `yaml:"negativePenaltyFactor" json:"negativePenaltyFactor"`
	MaxAuthorPerFeed       int              `yaml:"maxAuthorPerFeed" json:"maxAuthorPerFeed"`
	ColdStartAgeHours      float64          `yaml:"coldStartAgeHours" json:"coldStartAgeHours"`
	ColdStartViewThreshold int64            `yaml:"coldStartViewThreshold" json:"coldStartViewThreshold"`
}

// ExperimentBucket is one bucket of an AB experiment.
type ExperimentBucket struct {
	Name      string `yaml:"name" json:"name"`
	WeightPct int    `yaml:"weightPct" json:"weightPct"`
}

// ExperimentDef declares an AB experiment. EligibleSegments empty = all users;
// non-empty = only users in at least one listed segment participate.
type ExperimentDef struct {
	ID               string             `yaml:"id" json:"id"`
	Enabled          bool               `yaml:"enabled" json:"enabled"`
	EligibleSegments []string           `yaml:"eligibleSegments" json:"eligibleSegments"`
	Buckets          []ExperimentBucket `yaml:"buckets" json:"buckets"`
}

// SegmentTargeting overrides scoring for users in a population segment.
// presetOverride swaps the whole preset; weightDeltas adjust individual dims.
type SegmentTargeting struct {
	Segment        string             `yaml:"segment" json:"segment"`
	PresetOverride string             `yaml:"presetOverride" json:"presetOverride"`
	WeightDeltas   map[string]float64 `yaml:"weightDeltas" json:"weightDeltas"`
}

// Guardrail is a KPI floor for a policy change relative to a baseline preset.
// action is always suggest_only: advisors emit findings, humans approve.
type Guardrail struct {
	Metric         string  `yaml:"metric" json:"metric"`
	BaselinePreset string  `yaml:"baselinePreset" json:"baselinePreset"`
	MinRatio       float64 `yaml:"minRatio" json:"minRatio"`
	MinSamples     int     `yaml:"minSamples" json:"minSamples"`
	Window         string  `yaml:"window" json:"window"`
	Action         string  `yaml:"action" json:"action"`
}

// RecPolicy is the full recommendation scoring policy.
type RecPolicy struct {
	Version          int                     `yaml:"version" json:"version"`
	PolicyVersion    string                  `yaml:"policyVersion" json:"policyVersion"`
	DefaultPreset    string                  `yaml:"defaultPreset" json:"defaultPreset"`
	WeightPresets    map[string]WeightPreset `yaml:"weightPresets" json:"weightPresets"`
	Scorer           ScorerConfig            `yaml:"scorer" json:"scorer"`
	Experiments      []ExperimentDef         `yaml:"experiments" json:"experiments"`
	SegmentTargeting []SegmentTargeting      `yaml:"segmentTargeting" json:"segmentTargeting"`
	Guardrails       []Guardrail             `yaml:"guardrails" json:"guardrails"`
}

// ResolvedPolicy is the per-request resolved scoring configuration for a user
// after experiment bucket assignment and segment targeting.
type ResolvedPolicy struct {
	Weights        WeightPreset
	Scorer         ScorerConfig
	PolicyVersion  string
	Preset         string // resolved preset name (bucket or segment override)
	AppliedSegment string // segment that drove the override/deltas, "" if none
}

// Parse unmarshals YAML into a RecPolicy and validates it. A parse or validation
// error means the candidate is rejected (Store keeps last-good).
func Parse(raw []byte) (*RecPolicy, error) {
	var p RecPolicy
	if err := yaml.Unmarshal(raw, &p); err != nil {
		return nil, fmt.Errorf("recpolicy: decode yaml: %w", err)
	}
	if err := p.Validate(); err != nil {
		return nil, err
	}
	return &p, nil
}

// Validate enforces the structural invariants the engine relies on.
func (p *RecPolicy) Validate() error {
	if p == nil {
		return errors.New("recpolicy: nil policy")
	}
	if p.PolicyVersion == "" {
		return errors.New("recpolicy: policyVersion required")
	}
	if len(p.WeightPresets) == 0 {
		return errors.New("recpolicy: weightPresets required")
	}
	if _, ok := p.WeightPresets[p.DefaultPreset]; !ok {
		return fmt.Errorf("recpolicy: defaultPreset %q not in weightPresets", p.DefaultPreset)
	}
	if p.Scorer.FreshnessHalfLifeHours <= 0 {
		return errors.New("recpolicy: scorer.freshnessHalfLifeHours must be > 0")
	}
	if p.Scorer.MaxAuthorPerFeed <= 0 {
		return errors.New("recpolicy: scorer.maxAuthorPerFeed must be > 0")
	}
	if p.Scorer.ExploreFraction < 0 || p.Scorer.ExploreFraction > 1 {
		return errors.New("recpolicy: scorer.exploreFraction must be in [0,1]")
	}
	if p.Scorer.ColdStartAgeHours < 0 || p.Scorer.ColdStartViewThreshold < 0 {
		return errors.New("recpolicy: scorer cold-start thresholds must be >= 0")
	}
	for _, exp := range p.Experiments {
		if exp.ID == "" {
			return errors.New("recpolicy: experiment id required")
		}
		sum := 0
		for _, b := range exp.Buckets {
			if b.Name == "" {
				return fmt.Errorf("recpolicy: experiment %s has empty bucket name", exp.ID)
			}
			if b.WeightPct < 0 {
				return fmt.Errorf("recpolicy: experiment %s bucket %s weightPct < 0", exp.ID, b.Name)
			}
			sum += b.WeightPct
		}
		if exp.Enabled && sum != 100 {
			return fmt.Errorf("recpolicy: experiment %s bucket weightPct sum=%d, want 100", exp.ID, sum)
		}
	}
	for _, t := range p.SegmentTargeting {
		if t.Segment == "" {
			return errors.New("recpolicy: segmentTargeting.segment required")
		}
		if t.PresetOverride != "" {
			if _, ok := p.WeightPresets[t.PresetOverride]; !ok {
				return fmt.Errorf("recpolicy: segmentTargeting %s presetOverride %q not in weightPresets", t.Segment, t.PresetOverride)
			}
		}
		for dim := range t.WeightDeltas {
			if !validWeightDim(dim) {
				return fmt.Errorf("recpolicy: segmentTargeting %s unknown weight dim %q", t.Segment, dim)
			}
		}
	}
	for _, g := range p.Guardrails {
		if g.Action != GuardrailActionSuggestOnly {
			return fmt.Errorf("recpolicy: guardrail %s action %q: only %q allowed", g.Metric, g.Action, GuardrailActionSuggestOnly)
		}
		if _, ok := p.WeightPresets[g.BaselinePreset]; !ok {
			return fmt.Errorf("recpolicy: guardrail %s baselinePreset %q not in weightPresets", g.Metric, g.BaselinePreset)
		}
		if g.MinRatio <= 0 {
			return fmt.Errorf("recpolicy: guardrail %s minRatio must be > 0", g.Metric)
		}
	}
	return nil
}

func (p *RecPolicy) experiment(id string) *ExperimentDef {
	for i := range p.Experiments {
		if p.Experiments[i].ID == id {
			return &p.Experiments[i]
		}
	}
	return nil
}

func (p *RecPolicy) targetingFor(segment string) *SegmentTargeting {
	for i := range p.SegmentTargeting {
		if p.SegmentTargeting[i].Segment == segment {
			return &p.SegmentTargeting[i]
		}
	}
	return nil
}

// ResolveBucket assigns a user to a bucket for the given experiment, gated by
// segment eligibility. Returns (bucket, true) when assigned, ("", false) when
// the experiment is missing, disabled, or the user is not eligible.
// Bucket hashing reuses the runtime/experiments consistent-hash (single impl).
func (p *RecPolicy) ResolveBucket(expID, subjectKey string, segments []string) (string, bool) {
	exp := p.experiment(expID)
	if exp == nil || !exp.Enabled {
		return "", false
	}
	if len(exp.EligibleSegments) > 0 && !intersects(exp.EligibleSegments, segments) {
		return "", false
	}
	buckets := make([]runtimeexperiments.BucketDef, len(exp.Buckets))
	for i, b := range exp.Buckets {
		buckets[i] = runtimeexperiments.BucketDef{Name: b.Name, WeightPct: b.WeightPct}
	}
	return runtimeexperiments.AssignBucket(expID, subjectKey, buckets), true
}

// ResolveBucketOr is ResolveBucket with a fallback bucket when not assigned.
func (p *RecPolicy) ResolveBucketOr(expID, subjectKey string, segments []string, fallback string) string {
	if b, ok := p.ResolveBucket(expID, subjectKey, segments); ok {
		return b
	}
	return fallback
}

// ResolveWeights produces the per-request weights for a (bucket, segments) pair:
// pick the preset (bucket name, else defaultPreset), apply the highest-priority
// segment presetOverride, then additively apply every matched segment's
// weightDeltas. segments must be priority-sorted (MatchSegments output order).
func (p *RecPolicy) ResolveWeights(bucket string, segments []string) ResolvedPolicy {
	presetName := bucket
	if _, ok := p.WeightPresets[presetName]; !ok {
		presetName = p.DefaultPreset
	}
	appliedSegment := ""
	for _, seg := range segments {
		if t := p.targetingFor(seg); t != nil && t.PresetOverride != "" {
			if _, ok := p.WeightPresets[t.PresetOverride]; ok {
				presetName = t.PresetOverride
				appliedSegment = seg
				break
			}
		}
	}
	w := p.WeightPresets[presetName]
	for _, seg := range segments {
		t := p.targetingFor(seg)
		if t == nil || len(t.WeightDeltas) == 0 {
			continue
		}
		for dim, d := range t.WeightDeltas {
			w.addDelta(dim, d)
		}
		if appliedSegment == "" {
			appliedSegment = seg
		}
	}
	return ResolvedPolicy{
		Weights:        w,
		Scorer:         p.Scorer,
		PolicyVersion:  p.PolicyVersion,
		Preset:         presetName,
		AppliedSegment: appliedSegment,
	}
}

func intersects(a, b []string) bool {
	if len(a) == 0 || len(b) == 0 {
		return false
	}
	set := make(map[string]struct{}, len(a))
	for _, x := range a {
		set[x] = struct{}{}
	}
	for _, y := range b {
		if _, ok := set[y]; ok {
			return true
		}
	}
	return false
}

// Baseline returns the compile-time policy snapshot captured by codegen_rec_policy.
// It panics if the generated snapshot is invalid, which codegen + tests prevent.
func Baseline() *RecPolicy {
	p, err := Parse([]byte(baselinePolicyYAML))
	if err != nil {
		panic("recpolicy: generated baseline is invalid: " + err.Error())
	}
	return p
}

// Package recpolicy is the single runtime source of truth for recommendation
// scoring policy: the 12-dimension weight presets, the secondary scorer
// coefficients, AB experiment definitions, segment targeting, and guardrails.
//
// The canonical data lives in metadata
// (services/content-service/resources/policies/content/post/recommendation_policy.yaml). codegen_rec_policy
// captures a compile-time snapshot as the fail-safe Baseline (rec_policy_baseline.gen.go),
// and Store hot-loads the live YAML at runtime with validate-before-swap and
// last-good retention. No scoring weight / coefficient / experiment is ever
// hand-coded in the engine; changing the YAML changes behavior without code edits.
package recpolicy

import (
	"errors"
	"fmt"

	"gopkg.in/yaml.v3"
	runtimeexperiments "quwoquan_service/runtime/experiments"
)

// Experiment IDs (single source; consumed by the engine and the policy resolver).
const (
	ExpScoringWeights = "rec_scoring_weights"
	ExpModelVsRule    = "rec_model_vs_rule"
	ExpModelChannel   = "rec_model_channel"
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
	SearchIntent    float64 `yaml:"searchIntent" json:"searchIntent"`
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
	case "searchIntent":
		w.SearchIntent += delta
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
	Popularity              PopularityCoeffs `yaml:"popularity" json:"popularity"`
	FreshnessHalfLifeHours  float64          `yaml:"freshnessHalfLifeHours" json:"freshnessHalfLifeHours"`
	ExploreFraction         float64          `yaml:"exploreFraction" json:"exploreFraction"`
	LongTermTagBoostFactor  float64          `yaml:"longTermTagBoostFactor" json:"longTermTagBoostFactor"`
	CircleTagAffinityFactor float64          `yaml:"circleTagAffinityFactor" json:"circleTagAffinityFactor"`
	SocialInterestFactor    float64          `yaml:"socialInterestFactor" json:"socialInterestFactor"`
	EngagementBonusFactor   float64          `yaml:"engagementBonusFactor" json:"engagementBonusFactor"`
	ENERBonusFactor         float64          `yaml:"enerBonusFactor" json:"enerBonusFactor"`
	EntityCategoryFactor    float64          `yaml:"entityCategoryFactor" json:"entityCategoryFactor"`
	SearchIntentFactor      float64          `yaml:"searchIntentFactor" json:"searchIntentFactor"`
	NegativePenaltyFactor   float64          `yaml:"negativePenaltyFactor" json:"negativePenaltyFactor"`
	// QualityScoreFactor scales the projected item qualityScore/recScore signal.
	// It must be consumed from rm_discovery_feed projection only; feed read paths
	// must not synchronously compute quality.
	QualityScoreFactor float64 `yaml:"qualityScoreFactor" json:"qualityScoreFactor"`
	// IntersectionSignalFactor scales the single-point intersection fusion in the
	// rule scorer: social/intersection-origin candidates earn a bounded socialPrior
	// lift proportional to the viewer's revealed engagement with the matching kind.
	IntersectionSignalFactor float64 `yaml:"intersectionSignalFactor" json:"intersectionSignalFactor"`
	// Candidate-level intersection fusion. Fact strength/freshness must outrank
	// affinity probability; affinity is advisory and requires a confidence label
	// before it can be projected into candidates.
	IntersectionFactFactor      float64 `yaml:"intersectionFactFactor" json:"intersectionFactFactor"`
	IntersectionFreshnessFactor float64 `yaml:"intersectionFreshnessFactor" json:"intersectionFreshnessFactor"`
	IntersectionAffinityFactor  float64 `yaml:"intersectionAffinityFactor" json:"intersectionAffinityFactor"`
	MaxAuthorPerFeed            int     `yaml:"maxAuthorPerFeed" json:"maxAuthorPerFeed"`
	ColdStartAgeHours           float64 `yaml:"coldStartAgeHours" json:"coldStartAgeHours"`
	ColdStartViewThreshold      int64   `yaml:"coldStartViewThreshold" json:"coldStartViewThreshold"`
	// DiversityStrategy selects the rerank diversity algorithm: "greedy" (default
	// type/author/top-tag dedup + explore/cold-start injection) or "mmr" (Maximal
	// Marginal Relevance balancing relevance vs novelty by DiversityLambda).
	DiversityStrategy string `yaml:"diversityStrategy" json:"diversityStrategy"`
	// DiversityLambda ∈ [0,1] is the MMR relevance weight (1-λ is the novelty
	// weight). Only consulted when DiversityStrategy == "mmr".
	DiversityLambda float64 `yaml:"diversityLambda" json:"diversityLambda"`
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

// IntersectionMixing controls how the fact channel and the affinity (probability)
// channel are blended when assembling intersection-driven surfaces. Fact signals
// always outrank affinity; affinityWeight is advisory only and maxAffinityPerSurface
// caps how many affinity-only reasons can appear on one surface.
type IntersectionMixing struct {
	FactWeight            float64 `yaml:"factWeight" json:"factWeight"`
	AffinityWeight        float64 `yaml:"affinityWeight" json:"affinityWeight"`
	MaxAffinityPerSurface int     `yaml:"maxAffinityPerSurface" json:"maxAffinityPerSurface"`
}

// IntersectionConfig is the metadata-driven policy for the intersection module:
// cross-session cooldown, per-request candidate window, per-dimension freshness
// TTL, and fact/affinity mixing. It replaces the previously hand-coded constants
// in content-service IntersectionService. The cooldown TTL is co-registered in
// _shared/redis_keyspace.yaml: rec:icool.
type IntersectionConfig struct {
	CooldownDays int `yaml:"cooldownDays" json:"cooldownDays"`
	// NegativeFeedbackCooldownDays is the cross-session cooldown window applied to a
	// subject after an explicit intersection negative feedback (feedbackKinds). Unlike
	// the exposure cooldown (seen → demote), this window means "filter out, do not
	// recommend" and is co-registered in _shared/redis_keyspace.yaml: rec:ineg.
	NegativeFeedbackCooldownDays int                `yaml:"negativeFeedbackCooldownDays" json:"negativeFeedbackCooldownDays"`
	MaxCandidateWindow           int                `yaml:"maxCandidateWindow" json:"maxCandidateWindow"`
	FreshnessTTLDaysByDimension  map[string]int     `yaml:"freshnessTtlDaysByDimension" json:"freshnessTtlDaysByDimension"`
	Mixing                       IntersectionMixing `yaml:"mixing" json:"mixing"`
}

// ExposureVisibilityConfig controls client-side visible/impressed/dwell thresholds.
// It is consumed by App reporters and server-side validators; values are
// metadata-first to avoid hidden UI/runtime constants.
type ExposureVisibilityConfig struct {
	ImpressionAreaThreshold float64 `yaml:"impressionAreaThreshold" json:"impressionAreaThreshold"`
	ImpressionMinDwellMs    int     `yaml:"impressionMinDwellMs" json:"impressionMinDwellMs"`
	DwellMinReportMs        int     `yaml:"dwellMinReportMs" json:"dwellMinReportMs"`
}

// ExposureSamplingConfig controls weak-signal sampling before events hit cloud.
type ExposureSamplingConfig struct {
	VisibleSampleRate    float64 `yaml:"visibleSampleRate" json:"visibleSampleRate"`
	ImpressionSampleRate float64 `yaml:"impressionSampleRate" json:"impressionSampleRate"`
	DwellSampleRate      float64 `yaml:"dwellSampleRate" json:"dwellSampleRate"`
}

// ExposureReportingConfig bounds client batching and server ingestion pressure.
type ExposureReportingConfig struct {
	BehaviorBatchMaxSize         int `yaml:"behaviorBatchMaxSize" json:"behaviorBatchMaxSize"`
	BehaviorFlushIntervalMs      int `yaml:"behaviorFlushIntervalMs" json:"behaviorFlushIntervalMs"`
	IngestRateLimitPerUserPerMin int `yaml:"ingestRateLimitPerUserPerMinute" json:"ingestRateLimitPerUserPerMinute"`
	IngestGlobalRateLimitPerSec  int `yaml:"ingestGlobalRateLimitPerSecond" json:"ingestGlobalRateLimitPerSecond"`
	IngestInflightLimit          int `yaml:"ingestInflightLimit" json:"ingestInflightLimit"`
	ClientEventIDWindowMs        int `yaml:"clientEventIdWindowMs" json:"clientEventIdWindowMs"`
}

// ExposureMemoryConfig controls Redis day-bucket windows and cardinality budget.
type ExposureMemoryConfig struct {
	ServedTTLHours             int `yaml:"servedTtlHours" json:"servedTtlHours"`
	ImpressedTTLHours          int `yaml:"impressedTtlHours" json:"impressedTtlHours"`
	NegativeTTLHours           int `yaml:"negativeTtlHours" json:"negativeTtlHours"`
	FatigueHalfLifeHours       int `yaml:"fatigueHalfLifeHours" json:"fatigueHalfLifeHours"`
	DayBucketCardinalityBudget int `yaml:"dayBucketCardinalityBudget" json:"dayBucketCardinalityBudget"`
}

// DynamicExposureBudgetConfig is the P1 traffic-pool control surface.
type DynamicExposureBudgetConfig struct {
	Enabled                         bool    `yaml:"enabled" json:"enabled"`
	TrialMinServed                  int     `yaml:"trialMinServed" json:"trialMinServed"`
	PromotionCTRThreshold           float64 `yaml:"promotionCtrThreshold" json:"promotionCtrThreshold"`
	PromotionCompletionThreshold    float64 `yaml:"promotionCompletionThreshold" json:"promotionCompletionThreshold"`
	RetirementNegativeRateThreshold float64 `yaml:"retirementNegativeRateThreshold" json:"retirementNegativeRateThreshold"`
}

// FrequencyAndNearDupConfig controls soft frequency caps and near-duplicate
// diversity after scoring. The runtime relaxes these caps when needed to avoid
// empty feeds.
type FrequencyAndNearDupConfig struct {
	Enabled                bool    `yaml:"enabled" json:"enabled"`
	MaxSameAuthorPerWindow int     `yaml:"maxSameAuthorPerWindow" json:"maxSameAuthorPerWindow"`
	MaxSameTagPerWindow    int     `yaml:"maxSameTagPerWindow" json:"maxSameTagPerWindow"`
	MaxSameTopicPerWindow  int     `yaml:"maxSameTopicPerWindow" json:"maxSameTopicPerWindow"`
	NearDupJaccardMax      float64 `yaml:"nearDupJaccardMax" json:"nearDupJaccardMax"`
	SoftFallbackMinFillPct int     `yaml:"softFallbackMinFillPct" json:"softFallbackMinFillPct"`
}

// CollaborativeRecallConfig is the P1 non-deep collaborative recall control surface.
type CollaborativeRecallConfig struct {
	Enabled          bool `yaml:"enabled" json:"enabled"`
	MaxI2ICandidates int  `yaml:"maxI2ICandidates" json:"maxI2ICandidates"`
	MaxU2ICandidates int  `yaml:"maxU2ICandidates" json:"maxU2ICandidates"`
	QuotaPct         int  `yaml:"quotaPct" json:"quotaPct"`
}

// ExposureGovernanceConfig groups all exposure-governance policy knobs.
type ExposureGovernanceConfig struct {
	Visibility          ExposureVisibilityConfig    `yaml:"visibility" json:"visibility"`
	Sampling            ExposureSamplingConfig      `yaml:"sampling" json:"sampling"`
	Reporting           ExposureReportingConfig     `yaml:"reporting" json:"reporting"`
	Memory              ExposureMemoryConfig        `yaml:"memory" json:"memory"`
	DynamicBudget       DynamicExposureBudgetConfig `yaml:"dynamicBudget" json:"dynamicBudget"`
	FrequencyAndNearDup FrequencyAndNearDupConfig   `yaml:"frequencyAndNearDup" json:"frequencyAndNearDup"`
	CollaborativeRecall CollaborativeRecallConfig   `yaml:"collaborativeRecall" json:"collaborativeRecall"`
}

// Ops intervention action / target-type closed sets (single source; the engine
// applier and validation both consume these constants).
const (
	OpsActionPin    = "pin"
	OpsActionDemote = "demote"
	OpsActionBlock  = "block"

	OpsTargetContent = "content"
	OpsTargetAuthor  = "author"
	OpsTargetTag     = "tag"
)

// OpsIntervention is one manual operational intervention applied to the ranked
// feed: pin (force to top with a score boost), demote (scale score down), or
// block (remove from feed). It is the config truth source for运营 governance and
// takes effect via hot-reload without any UI. Each applied intervention is
// audited via recommendation_feed_ops_intervention_audit_total.
type OpsIntervention struct {
	ID         string  `yaml:"id" json:"id"`
	Action     string  `yaml:"action" json:"action"`
	TargetType string  `yaml:"targetType" json:"targetType"`
	Target     string  `yaml:"target" json:"target"`
	Scenario   string  `yaml:"scenario" json:"scenario"`
	Weight     float64 `yaml:"weight" json:"weight"`
	Reason     string  `yaml:"reason" json:"reason"`
	ExpiresAt  string  `yaml:"expiresAt" json:"expiresAt"`
}

// OpsInterventionConfig groups the manual运营 intervention rules. Empty +
// disabled is a zero-cost no-op on the main ranking path.
type OpsInterventionConfig struct {
	Enabled       bool              `yaml:"enabled" json:"enabled"`
	Interventions []OpsIntervention `yaml:"interventions" json:"interventions"`
}

func validOpsAction(a string) bool {
	switch a {
	case OpsActionPin, OpsActionDemote, OpsActionBlock:
		return true
	default:
		return false
	}
}

func validOpsTargetType(t string) bool {
	switch t {
	case OpsTargetContent, OpsTargetAuthor, OpsTargetTag:
		return true
	default:
		return false
	}
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

// RecallFusionConfig 是多路召回合并的轻量融合策略（W9/B10，S0 反过度设计：
// policy 权重表 + 源配额，不做 RRF；融合公式升级只改本配置的消费实现，契约不变）。
// SourceQuotaPct：recallPath → 该源候选数占召回池的百分比上限（未登记 = 不限）。
// SourceBoost：recallPath → 精排分乘数（未登记 = 1.0；fact 优先原则下 boost
// 只做源间校准，不得用于伪造单条内容分）。
type RecallFusionConfig struct {
	Enabled        bool               `yaml:"enabled" json:"enabled"`
	SourceQuotaPct map[string]int     `yaml:"sourceQuotaPct" json:"sourceQuotaPct"`
	SourceBoost    map[string]float64 `yaml:"sourceBoost" json:"sourceBoost"`
}

// ObjectCardConfig 是首页混合对象卡的 Content 页面布局策略。对象卡候选、公开
// 快照、理由和召回路径由 Recommendation 在同一 RankedRecommendationWindow
// 冻结；Content 只按固定间隔和上限计算锚点，不执行第二召回。
type ObjectCardConfig struct {
	Enabled bool `yaml:"enabled" json:"enabled"`
	// EveryN 每 N 条内容后注入 1 张对象卡（anchorIndex = N, 2N, ...）。
	EveryN int `yaml:"everyN" json:"everyN"`
	// MaxCards 单页对象卡上限（防对象卡挤占内容主体）。
	MaxCards int `yaml:"maxCards" json:"maxCards"`
	// AllowedKinds 允许注入的对象卡类别闭集（entity_homepage/user_card/circle_card）。
	// S0 只开 entity_homepage；user_card/circle_card 为 S1 触发开启。
	AllowedKinds []string `yaml:"allowedKinds" json:"allowedKinds"`
}

// RecPolicy is the full recommendation scoring policy.
type RecPolicy struct {
	effectiveHash string
	DefaultPreset string                  `yaml:"defaultPreset" json:"defaultPreset"`
	WeightPresets map[string]WeightPreset `yaml:"weightPresets" json:"weightPresets"`
	// ScenarioRouting maps a feed scenario (FeedType, e.g. homepage/circle/search)
	// to its base weight preset, so one ranking pipeline serves every surface with
	// scenario-appropriate objectives. Experiment buckets still win over the
	// scenario base; segment overrides/deltas still apply on top. Unmapped → default.
	ScenarioRouting    map[string]string        `yaml:"scenarioRouting" json:"scenarioRouting"`
	Scorer             ScorerConfig             `yaml:"scorer" json:"scorer"`
	Experiments        []ExperimentDef          `yaml:"experiments" json:"experiments"`
	SegmentTargeting   []SegmentTargeting       `yaml:"segmentTargeting" json:"segmentTargeting"`
	Guardrails         []Guardrail              `yaml:"guardrails" json:"guardrails"`
	Intersection       IntersectionConfig       `yaml:"intersection" json:"intersection"`
	ExposureGovernance ExposureGovernanceConfig `yaml:"exposureGovernance" json:"exposureGovernance"`
	OpsIntervention    OpsInterventionConfig    `yaml:"opsIntervention" json:"opsIntervention"`
	ABAdmission        ABAdmissionConfig        `yaml:"abAdmission" json:"abAdmission"`
	ObjectCards        ObjectCardConfig         `yaml:"objectCards" json:"objectCards"`
	RecallFusion       RecallFusionConfig       `yaml:"recallFusion" json:"recallFusion"`
}

// ResolvedPolicy is the per-request resolved scoring configuration for a user
// after experiment bucket assignment and segment targeting.
type ResolvedPolicy struct {
	Weights        WeightPreset
	Scorer         ScorerConfig
	PolicyDigest   string
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
	p.effectiveHash = policyHash(&p)
	return &p, nil
}

// Validate enforces the structural invariants the engine relies on.
func (p *RecPolicy) Validate() error {
	if p == nil {
		return errors.New("recpolicy: nil policy")
	}
	if len(p.WeightPresets) == 0 {
		return errors.New("recpolicy: weightPresets required")
	}
	if _, ok := p.WeightPresets[p.DefaultPreset]; !ok {
		return fmt.Errorf("recpolicy: defaultPreset %q not in weightPresets", p.DefaultPreset)
	}
	for scenario, preset := range p.ScenarioRouting {
		if _, ok := p.WeightPresets[preset]; !ok {
			return fmt.Errorf("recpolicy: scenarioRouting[%s] preset %q not in weightPresets", scenario, preset)
		}
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
	switch p.Scorer.DiversityStrategy {
	case "", "greedy", "mmr":
	default:
		return fmt.Errorf("recpolicy: scorer.diversityStrategy %q invalid (greedy|mmr)", p.Scorer.DiversityStrategy)
	}
	if p.Scorer.DiversityLambda < 0 || p.Scorer.DiversityLambda > 1 {
		return errors.New("recpolicy: scorer.diversityLambda must be in [0,1]")
	}
	if p.Scorer.IntersectionSignalFactor < 0 {
		return errors.New("recpolicy: scorer.intersectionSignalFactor must be >= 0")
	}
	if p.Scorer.QualityScoreFactor < 0 {
		return errors.New("recpolicy: scorer.qualityScoreFactor must be >= 0")
	}
	if p.Scorer.IntersectionFactFactor < 0 ||
		p.Scorer.IntersectionFreshnessFactor < 0 ||
		p.Scorer.IntersectionAffinityFactor < 0 {
		return errors.New("recpolicy: scorer intersection candidate factors must be >= 0")
	}
	if p.Scorer.IntersectionAffinityFactor > 0 &&
		p.Scorer.IntersectionFactFactor <= p.Scorer.IntersectionAffinityFactor {
		return errors.New("recpolicy: scorer.intersectionFactFactor must be greater than intersectionAffinityFactor")
	}
	if p.Scorer.SearchIntentFactor < 0 {
		return errors.New("recpolicy: scorer.searchIntentFactor must be >= 0")
	}
	for _, exp := range p.Experiments {
		buckets := make([]runtimeexperiments.BucketDef, len(exp.Buckets))
		for index, bucket := range exp.Buckets {
			buckets[index] = runtimeexperiments.BucketDef{
				Name:      bucket.Name,
				WeightPct: bucket.WeightPct,
			}
		}
		if err := runtimeexperiments.ValidateExperiment(&runtimeexperiments.Experiment{
			ID:      exp.ID,
			Buckets: buckets,
			Enabled: exp.Enabled,
		}); err != nil {
			return fmt.Errorf("recpolicy: experiment %q: %w", exp.ID, err)
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
	if p.Intersection.CooldownDays < 0 {
		return errors.New("recpolicy: intersection.cooldownDays must be >= 0")
	}
	if p.Intersection.NegativeFeedbackCooldownDays < 0 {
		return errors.New("recpolicy: intersection.negativeFeedbackCooldownDays must be >= 0")
	}
	if p.Intersection.MaxCandidateWindow < 0 {
		return errors.New("recpolicy: intersection.maxCandidateWindow must be >= 0")
	}
	for dim, ttl := range p.Intersection.FreshnessTTLDaysByDimension {
		if ttl < 0 {
			return fmt.Errorf("recpolicy: intersection.freshnessTtlDaysByDimension[%s] must be >= 0", dim)
		}
	}
	if p.Intersection.Mixing.FactWeight < 0 || p.Intersection.Mixing.AffinityWeight < 0 {
		return errors.New("recpolicy: intersection.mixing weights must be >= 0")
	}
	if p.Intersection.Mixing.MaxAffinityPerSurface < 0 {
		return errors.New("recpolicy: intersection.mixing.maxAffinityPerSurface must be >= 0")
	}
	if err := validateExposureGovernance(p.ExposureGovernance); err != nil {
		return err
	}
	if err := validateOpsIntervention(p.OpsIntervention); err != nil {
		return err
	}
	if err := validateABAdmission(p.ABAdmission); err != nil {
		return err
	}
	if err := validateObjectCards(p.ObjectCards); err != nil {
		return err
	}
	if err := validateRecallFusion(p.RecallFusion); err != nil {
		return err
	}
	return nil
}

func validateRecallFusion(cfg RecallFusionConfig) error {
	if !cfg.Enabled {
		return nil
	}
	for source, pct := range cfg.SourceQuotaPct {
		if pct <= 0 || pct > 100 {
			return fmt.Errorf("recpolicy: recallFusion.sourceQuotaPct[%s] must be in (0,100], got %d", source, pct)
		}
	}
	for source, boost := range cfg.SourceBoost {
		if boost <= 0 || boost > 5 {
			return fmt.Errorf("recpolicy: recallFusion.sourceBoost[%s] must be in (0,5], got %v", source, boost)
		}
	}
	return nil
}

func validateObjectCards(cfg ObjectCardConfig) error {
	if !cfg.Enabled {
		return nil
	}
	if cfg.EveryN <= 0 {
		return errors.New("recpolicy: objectCards.everyN must be > 0 when enabled")
	}
	if cfg.MaxCards <= 0 {
		return errors.New("recpolicy: objectCards.maxCards must be > 0 when enabled")
	}
	allowed := map[string]bool{
		"entity_homepage": true,
		"user_card":       true,
		"circle_card":     true,
	}
	if len(cfg.AllowedKinds) == 0 {
		return errors.New("recpolicy: objectCards.allowedKinds required when enabled")
	}
	for _, kind := range cfg.AllowedKinds {
		if !allowed[kind] {
			return fmt.Errorf("recpolicy: objectCards.allowedKinds contains unknown kind %q", kind)
		}
	}
	return nil
}

// ABRollbackConfig declares the rollback guard for an online experiment: when the
// challenger's primary metric drops below regressionRatio × control, the bucket is
// a rollback candidate. autoRollback gates whether the rollback is automatic
// (true) or advisory/human-approved (false, default — same governance posture as
// Guardrail.action=suggest_only).
type ABRollbackConfig struct {
	RegressionRatio float64 `yaml:"regressionRatio" json:"regressionRatio"`
	AutoRollback    bool    `yaml:"autoRollback" json:"autoRollback"`
}

// ABAdmissionConfig is the single source of truth for online AB admission: an
// experiment bucket may only inform promotion/rollback decisions once it clears
// minSamplesPerBucket, the bucket split is within maxBucketSkewPct of design, and
// the primary metric effect clears minDetectableEffect at significanceLevel.
// Consumed by the admission validator (RecordABExperimentValidity feeds SLI
// ab_experiment_validity); the experiment definitions themselves live in
// RecPolicy.Experiments.
type ABAdmissionConfig struct {
	MinSamplesPerBucket int              `yaml:"minSamplesPerBucket" json:"minSamplesPerBucket"`
	SignificanceLevel   float64          `yaml:"significanceLevel" json:"significanceLevel"`
	MinDetectableEffect float64          `yaml:"minDetectableEffect" json:"minDetectableEffect"`
	MaxBucketSkewPct    float64          `yaml:"maxBucketSkewPct" json:"maxBucketSkewPct"`
	PrimaryMetric       string           `yaml:"primaryMetric" json:"primaryMetric"`
	Rollback            ABRollbackConfig `yaml:"rollback" json:"rollback"`
}

func validateABAdmission(cfg ABAdmissionConfig) error {
	// Zero-value (unconfigured) admission is permitted: it disables admission
	// gating rather than forcing every deployment to declare experiment stats.
	zero := ABAdmissionConfig{}
	if cfg == zero {
		return nil
	}
	if cfg.MinSamplesPerBucket <= 0 {
		return errors.New("recpolicy: abAdmission.minSamplesPerBucket must be > 0")
	}
	if cfg.SignificanceLevel <= 0 || cfg.SignificanceLevel >= 1 {
		return errors.New("recpolicy: abAdmission.significanceLevel must be in (0,1)")
	}
	if cfg.MinDetectableEffect <= 0 {
		return errors.New("recpolicy: abAdmission.minDetectableEffect must be > 0")
	}
	if cfg.MaxBucketSkewPct < 0 || cfg.MaxBucketSkewPct > 100 {
		return errors.New("recpolicy: abAdmission.maxBucketSkewPct must be in [0,100]")
	}
	if cfg.PrimaryMetric == "" {
		return errors.New("recpolicy: abAdmission.primaryMetric required")
	}
	if cfg.Rollback.RegressionRatio <= 0 || cfg.Rollback.RegressionRatio > 1 {
		return errors.New("recpolicy: abAdmission.rollback.regressionRatio must be in (0,1]")
	}
	return nil
}

func validateOpsIntervention(cfg OpsInterventionConfig) error {
	seen := make(map[string]struct{}, len(cfg.Interventions))
	for i, iv := range cfg.Interventions {
		if iv.ID == "" {
			return fmt.Errorf("recpolicy: opsIntervention[%d] id required (audit key)", i)
		}
		if _, dup := seen[iv.ID]; dup {
			return fmt.Errorf("recpolicy: opsIntervention duplicate id %q", iv.ID)
		}
		seen[iv.ID] = struct{}{}
		if !validOpsAction(iv.Action) {
			return fmt.Errorf("recpolicy: opsIntervention %s action %q invalid (pin|demote|block)", iv.ID, iv.Action)
		}
		if !validOpsTargetType(iv.TargetType) {
			return fmt.Errorf("recpolicy: opsIntervention %s targetType %q invalid (content|author|tag)", iv.ID, iv.TargetType)
		}
		if iv.Target == "" {
			return fmt.Errorf("recpolicy: opsIntervention %s target required", iv.ID)
		}
		switch iv.Action {
		case OpsActionDemote:
			if iv.Weight < 0 || iv.Weight >= 1 {
				return fmt.Errorf("recpolicy: opsIntervention %s demote weight must be in [0,1)", iv.ID)
			}
		case OpsActionPin:
			if iv.Weight < 0 {
				return fmt.Errorf("recpolicy: opsIntervention %s pin weight (boost) must be >= 0", iv.ID)
			}
		}
	}
	return nil
}

func validateExposureGovernance(cfg ExposureGovernanceConfig) error {
	if cfg.Visibility.ImpressionAreaThreshold < 0 || cfg.Visibility.ImpressionAreaThreshold > 1 {
		return errors.New("recpolicy: exposureGovernance.visibility.impressionAreaThreshold must be in [0,1]")
	}
	if cfg.Visibility.ImpressionMinDwellMs < 0 || cfg.Visibility.DwellMinReportMs < 0 {
		return errors.New("recpolicy: exposureGovernance.visibility dwell thresholds must be >= 0")
	}
	for name, rate := range map[string]float64{
		"visibleSampleRate":    cfg.Sampling.VisibleSampleRate,
		"impressionSampleRate": cfg.Sampling.ImpressionSampleRate,
		"dwellSampleRate":      cfg.Sampling.DwellSampleRate,
	} {
		if rate < 0 || rate > 1 {
			return fmt.Errorf("recpolicy: exposureGovernance.sampling.%s must be in [0,1]", name)
		}
	}
	if cfg.Reporting.BehaviorBatchMaxSize < 0 ||
		cfg.Reporting.BehaviorFlushIntervalMs < 0 ||
		cfg.Reporting.IngestRateLimitPerUserPerMin < 0 ||
		cfg.Reporting.IngestGlobalRateLimitPerSec < 0 ||
		cfg.Reporting.IngestInflightLimit < 0 ||
		cfg.Reporting.ClientEventIDWindowMs < 0 {
		return errors.New("recpolicy: exposureGovernance.reporting values must be >= 0")
	}
	if cfg.Memory.ServedTTLHours < 0 ||
		cfg.Memory.ImpressedTTLHours < 0 ||
		cfg.Memory.NegativeTTLHours < 0 ||
		cfg.Memory.FatigueHalfLifeHours < 0 ||
		cfg.Memory.DayBucketCardinalityBudget < 0 {
		return errors.New("recpolicy: exposureGovernance.memory values must be >= 0")
	}
	if cfg.DynamicBudget.TrialMinServed < 0 ||
		cfg.DynamicBudget.PromotionCTRThreshold < 0 ||
		cfg.DynamicBudget.PromotionCompletionThreshold < 0 ||
		cfg.DynamicBudget.RetirementNegativeRateThreshold < 0 {
		return errors.New("recpolicy: exposureGovernance.dynamicBudget values must be >= 0")
	}
	if cfg.FrequencyAndNearDup.MaxSameAuthorPerWindow < 0 ||
		cfg.FrequencyAndNearDup.MaxSameTagPerWindow < 0 ||
		cfg.FrequencyAndNearDup.MaxSameTopicPerWindow < 0 ||
		cfg.FrequencyAndNearDup.NearDupJaccardMax < 0 ||
		cfg.FrequencyAndNearDup.NearDupJaccardMax > 1 ||
		cfg.FrequencyAndNearDup.SoftFallbackMinFillPct < 0 ||
		cfg.FrequencyAndNearDup.SoftFallbackMinFillPct > 100 {
		return errors.New("recpolicy: exposureGovernance.frequencyAndNearDup values invalid")
	}
	if cfg.CollaborativeRecall.MaxI2ICandidates < 0 ||
		cfg.CollaborativeRecall.MaxU2ICandidates < 0 ||
		cfg.CollaborativeRecall.QuotaPct < 0 ||
		cfg.CollaborativeRecall.QuotaPct > 100 {
		return errors.New("recpolicy: exposureGovernance.collaborativeRecall quota/candidate values invalid")
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
	bucket, err := runtimeexperiments.AssignBucket(expID, subjectKey, buckets)
	if err != nil {
		return "", false
	}
	return bucket, true
}

// ResolveBucketOr is ResolveBucket with a fallback bucket when not assigned.
func (p *RecPolicy) ResolveBucketOr(expID, subjectKey string, segments []string, fallback string) string {
	if b, ok := p.ResolveBucket(expID, subjectKey, segments); ok {
		return b
	}
	return fallback
}

// PresetForScenario maps a feed scenario (FeedType string) to its base weight
// preset. Falls back to DefaultPreset when the scenario is unmapped or the mapped
// preset is unknown. Use this as the ResolveBucketOr fallback so experiment
// buckets still win and segment overrides/deltas still apply in ResolveWeights.
func (p *RecPolicy) PresetForScenario(scenario string) string {
	if scenario != "" {
		if preset, ok := p.ScenarioRouting[scenario]; ok {
			if _, valid := p.WeightPresets[preset]; valid {
				return preset
			}
		}
	}
	return p.DefaultPreset
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
		PolicyDigest:   p.effectiveHash,
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

package recommendation

import (
	"context"
	"math"
	"sort"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	messaging "quwoquan_service/runtime/messaging"
)

// InterestDimension is one of the four tag-affinity dimensions tracked per user.
type InterestDimension string

const (
	DimTopic    InterestDimension = "topic"
	DimAudience InterestDimension = "audience"
	DimFormat   InterestDimension = "format"
	DimEntity   InterestDimension = "entity"
)

// LifecycleStage classifies a user's overall engagement maturity.
type LifecycleStage string

const (
	StageNew     LifecycleStage = "new"
	StageActive  LifecycleStage = "active"
	StageDormant LifecycleStage = "dormant"
)

// TopInterest is one ranked interest entry in the derived profile.
type TopInterest struct {
	TagRef    string            `bson:"tagRef" json:"tagRef"`
	Dimension InterestDimension `bson:"dimension" json:"dimension"`
	Score     float64           `bson:"score" json:"score"` // normalized 0..1 (decay applied)
	Level     int               `bson:"level" json:"level"` // 0..5
}

// InterestProfile is the derived, consumer-facing interest portrait.
// It is NOT persisted in rm_recommend_feature: Recompute publishes it via the
// UserInterestRecomputed event and the user-domain projector persists it into
// rm_user_profile_view.interestProfile (single source of truth in the user
// domain). The recommendation engine reads raw affinities/segments locally; the
// assistant reads the profile through the user-service GetUserInterestProfile API.
type InterestProfile struct {
	TopInterests      []TopInterest       `bson:"topInterests" json:"topInterests"`
	DimensionTops     map[string][]string `bson:"dimensionTops" json:"dimensionTops"`
	LifecycleStage    LifecycleStage      `bson:"lifecycleStage" json:"lifecycleStage"`
	FreshnessDays     int                 `bson:"freshnessDays" json:"freshnessDays"`
	DecayHalfLifeDays int                 `bson:"decayHalfLifeDays" json:"decayHalfLifeDays"`
	RecomputedAt      time.Time           `bson:"recomputedAt" json:"recomputedAt"`
}

// InterestProfileConfig tunes aggregation. Zero value is invalid; use
// DefaultInterestProfileConfig and override individual fields.
type InterestProfileConfig struct {
	TopN              int // max entries in TopInterests
	PerDimensionN     int // max entries per dimension in DimensionTops
	DecayHalfLifeDays int // freshness half-life for score decay
	DormantAfterDays  int // freshness threshold to classify dormant
	NewBelowEvents    int // totalEvents threshold to classify new
}

// DefaultInterestProfileConfig returns sensible cold-start defaults.
func DefaultInterestProfileConfig() InterestProfileConfig {
	return InterestProfileConfig{
		TopN:              12,
		PerDimensionN:     6,
		DecayHalfLifeDays: 30,
		DormantAfterDays:  21,
		NewBelowEvents:    5,
	}
}

func (c InterestProfileConfig) withDefaults() InterestProfileConfig {
	d := DefaultInterestProfileConfig()
	if c.TopN <= 0 {
		c.TopN = d.TopN
	}
	if c.PerDimensionN <= 0 {
		c.PerDimensionN = d.PerDimensionN
	}
	if c.DecayHalfLifeDays <= 0 {
		c.DecayHalfLifeDays = d.DecayHalfLifeDays
	}
	if c.DormantAfterDays <= 0 {
		c.DormantAfterDays = d.DormantAfterDays
	}
	if c.NewBelowEvents <= 0 {
		c.NewBelowEvents = d.NewBelowEvents
	}
	return c
}

// DecayFactor returns 0.5^(elapsedDays/halfLifeDays), clamped to [0,1].
// Used both for freshness score decay and for the periodic DecayAll job.
func DecayFactor(halfLifeDays, elapsedDays float64) float64 {
	if halfLifeDays <= 0 || elapsedDays <= 0 {
		return 1
	}
	f := math.Pow(0.5, elapsedDays/halfLifeDays)
	switch {
	case f < 0:
		return 0
	case f > 1:
		return 1
	default:
		return f
	}
}

// scoreToLevel maps a normalized 0..1 score to a 0..5 level.
func scoreToLevel(score float64) int {
	switch {
	case score <= 0:
		return 0
	case score < 0.2:
		return 1
	case score < 0.4:
		return 2
	case score < 0.6:
		return 3
	case score < 0.8:
		return 4
	default:
		return 5
	}
}

// ComputeInterestProfile derives the interest profile from raw user features.
// Pure function (no IO): freshness decay is applied to scores so that stale
// interests rank lower without mutating the raw affinity counters.
func ComputeInterestProfile(f *UserFeatures, updatedAt, now time.Time, cfg InterestProfileConfig) InterestProfile {
	cfg = cfg.withDefaults()

	freshnessDays := 0
	if !updatedAt.IsZero() && now.After(updatedAt) {
		freshnessDays = int(now.Sub(updatedAt).Hours() / 24)
	}
	decay := DecayFactor(float64(cfg.DecayHalfLifeDays), float64(freshnessDays))

	if f == nil {
		return InterestProfile{
			DimensionTops:     map[string][]string{},
			LifecycleStage:    StageNew,
			FreshnessDays:     freshnessDays,
			DecayHalfLifeDays: cfg.DecayHalfLifeDays,
			RecomputedAt:      now.UTC(),
		}
	}

	dims := []struct {
		dim InterestDimension
		m   map[string]float64
	}{
		{DimTopic, f.TopicAffinities},
		{DimAudience, f.AudienceAffinities},
		{DimFormat, f.FormatAffinities},
		{DimEntity, f.EntityAffinities},
	}

	var all []TopInterest
	dimTops := make(map[string][]string, len(dims))
	for _, d := range dims {
		entries := normalizeDimension(d.dim, d.m, decay)
		topRefs := make([]string, 0, cfg.PerDimensionN)
		for i, e := range entries {
			if i >= cfg.PerDimensionN {
				break
			}
			topRefs = append(topRefs, e.TagRef)
		}
		if len(topRefs) > 0 {
			dimTops[string(d.dim)] = topRefs
		}
		all = append(all, entries...)
	}

	sort.SliceStable(all, func(i, j int) bool {
		if all[i].Score != all[j].Score {
			return all[i].Score > all[j].Score
		}
		return all[i].TagRef < all[j].TagRef
	})
	if len(all) > cfg.TopN {
		all = all[:cfg.TopN]
	}

	return InterestProfile{
		TopInterests:      all,
		DimensionTops:     dimTops,
		LifecycleStage:    classifyLifecycle(f.TotalEvents, freshnessDays, cfg),
		FreshnessDays:     freshnessDays,
		DecayHalfLifeDays: cfg.DecayHalfLifeDays,
		RecomputedAt:      now.UTC(),
	}
}

// normalizeDimension scales affinity values into [0,1] by the dimension max,
// applies the freshness decay, and returns entries sorted desc by score.
func normalizeDimension(dim InterestDimension, m map[string]float64, decay float64) []TopInterest {
	if len(m) == 0 {
		return nil
	}
	maxVal := 0.0
	for _, v := range m {
		if v > maxVal {
			maxVal = v
		}
	}
	if maxVal <= 0 {
		return nil
	}
	out := make([]TopInterest, 0, len(m))
	for tag, v := range m {
		if v <= 0 {
			continue
		}
		score := (v / maxVal) * decay
		out = append(out, TopInterest{TagRef: tag, Dimension: dim, Score: score, Level: scoreToLevel(score)})
	}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Score != out[j].Score {
			return out[i].Score > out[j].Score
		}
		return out[i].TagRef < out[j].TagRef
	})
	return out
}

func classifyLifecycle(totalEvents, freshnessDays int, cfg InterestProfileConfig) LifecycleStage {
	if freshnessDays >= cfg.DormantAfterDays {
		return StageDormant
	}
	if totalEvents < cfg.NewBelowEvents {
		return StageNew
	}
	return StageActive
}

// InterestEntropy returns the Shannon entropy (in bits) of the normalized
// top-interest score distribution. 0 means a single dominant interest; higher
// values mean a more diverse profile. Returns 0 for empty input. Pure function;
// used as a diversity signal for flywheel evaluation.
func InterestEntropy(top []TopInterest) float64 {
	if len(top) == 0 {
		return 0
	}
	sum := 0.0
	for _, t := range top {
		if t.Score > 0 {
			sum += t.Score
		}
	}
	if sum <= 0 {
		return 0
	}
	entropy := 0.0
	for _, t := range top {
		if t.Score <= 0 {
			continue
		}
		p := t.Score / sum
		entropy -= p * math.Log2(p)
	}
	if entropy < 0 {
		return 0
	}
	return entropy
}

// InterestProfileAggregator derives a user's interest profile from raw
// rm_recommend_feature features and publishes a UserInterestRecomputed event
// so the user-domain projector persists it into rm_user_profile_view
// (single source of truth in the user domain). It also periodically decays the
// raw affinities to prevent $inc monotonic growth.
type InterestProfileAggregator struct {
	coll      *mongo.Collection
	cfg       InterestProfileConfig
	publisher messaging.EventPublisher
	segments  []SegmentDef
}

// InterestProfileAggregatorOption configures optional aggregator behavior.
type InterestProfileAggregatorOption func(*InterestProfileAggregator)

// WithSegments injects the rule-based segment definitions (SSOT loaded from
// segments.yaml) used to derive a user's segment memberships during recompute.
func WithSegments(defs []SegmentDef) InterestProfileAggregatorOption {
	return func(a *InterestProfileAggregator) { a.segments = defs }
}

func NewInterestProfileAggregator(db *mongo.Database, cfg InterestProfileConfig, publisher messaging.EventPublisher, opts ...InterestProfileAggregatorOption) *InterestProfileAggregator {
	a := &InterestProfileAggregator{
		coll:      db.Collection("rm_recommend_feature"),
		cfg:       cfg.withDefaults(),
		publisher: publisher,
	}
	for _, o := range opts {
		o(a)
	}
	return a
}

// Recompute reads the user's raw features, derives the interest profile, and
// publishes UserInterestRecomputed for the user-domain projector to persist.
// No-op when there is no feature document or no publisher wired.
func (a *InterestProfileAggregator) Recompute(ctx context.Context, userID string) error {
	if userID == "" || a.publisher == nil {
		return nil
	}
	var doc struct {
		UpdatedAt    time.Time `bson:"updatedAt"`
		UserFeatures struct {
			TotalEvents        int                `bson:"totalEvents"`
			TopicAffinities    map[string]float64 `bson:"topicAffinities"`
			AudienceAffinities map[string]float64 `bson:"audienceAffinities"`
			FormatAffinities   map[string]float64 `bson:"formatAffinities"`
			EntityAffinities   map[string]float64 `bson:"entityAffinities"`
		} `bson:"userFeatures"`
	}
	err := a.coll.FindOne(ctx, bson.M{"userId": userID}).Decode(&doc)
	if err == mongo.ErrNoDocuments {
		interestRecomputeTotal.WithLabelValues("empty").Inc()
		return nil
	}
	if err != nil {
		interestRecomputeTotal.WithLabelValues("error").Inc()
		return err
	}
	feat := &UserFeatures{
		TotalEvents:        doc.UserFeatures.TotalEvents,
		TopicAffinities:    doc.UserFeatures.TopicAffinities,
		AudienceAffinities: doc.UserFeatures.AudienceAffinities,
		FormatAffinities:   doc.UserFeatures.FormatAffinities,
		EntityAffinities:   doc.UserFeatures.EntityAffinities,
	}
	now := time.Now().UTC()
	profile := ComputeInterestProfile(feat, doc.UpdatedAt, now, a.cfg)
	segments := MatchSegments(profile, a.segments)
	interestRecomputeTotal.WithLabelValues("ok").Inc()
	interestTopInterestCount.Observe(float64(len(profile.TopInterests)))
	interestLifecycleTotal.WithLabelValues(string(profile.LifecycleStage)).Inc()
	interestEntropy.Observe(InterestEntropy(profile.TopInterests))
	interestSegmentMembership.Observe(float64(len(segments)))
	for _, seg := range segments {
		interestSegmentHitTotal.WithLabelValues(seg).Inc()
	}

	// Persist the computed segments back into rm_recommend_feature (top-level)
	// so the recommendation engine's FeatureStore can load them for policy
	// segment targeting without recomputing. Segment computation stays
	// single-sourced here (MatchSegments); this write and the published event
	// are two CQRS projections of that one computation (engine targeting +
	// user-domain profile view). Best-effort: a write failure degrades only
	// this request's targeting, the event below still refreshes the profile.
	if segments == nil {
		segments = []string{}
	}
	if _, uerr := a.coll.UpdateOne(ctx,
		bson.M{"userId": userID},
		bson.M{"$set": bson.M{"segments": segments, "segmentsUpdatedAt": now}},
	); uerr != nil {
		interestRecomputeTotal.WithLabelValues("segment_persist_error").Inc()
	}

	return a.publisher.Publish(ctx, messaging.DomainEvent{
		Type:          "UserInterestRecomputed",
		AggregateType: "UserProfile",
		AggregateID:   userID,
		Payload: map[string]any{
			"userId":          userID,
			"interestProfile": profile,
			"segments":        segments,
		},
		OccurredAt: now.Format(time.RFC3339Nano),
	})
}

// DecayAll multiplies every user's affinity maps by the half-life decay factor
// for `sinceDays`, preventing $inc monotonic growth from permanently
// fossilizing old interests. Intended to run on a periodic tick.
func (a *InterestProfileAggregator) DecayAll(ctx context.Context, sinceDays float64) error {
	factor := DecayFactor(float64(a.cfg.DecayHalfLifeDays), sinceDays)
	if factor >= 1 {
		return nil
	}
	pipeline := mongo.Pipeline{}
	for _, field := range []string{
		"userFeatures.topicAffinities",
		"userFeatures.audienceAffinities",
		"userFeatures.formatAffinities",
		"userFeatures.entityAffinities",
		"userFeatures.entityInstanceAffinities",
	} {
		pipeline = append(pipeline, bson.D{{Key: "$set", Value: bson.M{
			field: decayObjectExpr("$"+field, factor),
		}}})
	}
	_, err := a.coll.UpdateMany(ctx, bson.M{"userFeatures": bson.M{"$exists": true}}, pipeline)
	return err
}

// decayObjectExpr builds an aggregation expression that multiplies every value
// of a map<string,number> field by `factor`, leaving non-object fields untouched.
func decayObjectExpr(fieldRef string, factor float64) bson.M {
	return bson.M{
		"$cond": bson.A{
			bson.M{"$eq": bson.A{bson.M{"$type": fieldRef}, "object"}},
			bson.M{"$arrayToObject": bson.M{
				"$map": bson.M{
					"input": bson.M{"$objectToArray": fieldRef},
					"as":    "kv",
					"in": bson.M{
						"k": "$$kv.k",
						"v": bson.M{"$multiply": bson.A{"$$kv.v", factor}},
					},
				},
			}},
			fieldRef,
		},
	}
}

package recommendation

import (
	"context"
	"log/slog"
	"math"
	"math/rand"
	"time"

	"quwoquan_service/runtime/recpolicy"
)

// ScoredCandidate is a candidate with a model-assigned score.
type ScoredCandidate struct {
	Candidate ContentCandidate
	Score     float64
	Detail    map[string]float64 // individual feature contributions (for explainability/debugging)
}

// ScoringFeatures packages all inputs needed by a scorer.
type ScoringFeatures struct {
	Session *SessionState
	User    *UserFeatureVector
	Weights ScoringWeights
	// Scorer carries the secondary coefficients (popularity sub-weights,
	// freshness half-life, formula mix factors) resolved from the policy.
	// Never hand-coded in the scorer; sourced from recpolicy.
	Scorer        recpolicy.ScorerConfig
	ExploreRate   float64
	Deterministic bool // when true (e.g. cursor pagination), skip random explore boost for stable ordering
}

// ModelScorer assigns scores to a batch of candidates.
// Implementations: RuleScorer (baseline), RemoteModelScorer (ML), CascadeScorer (failover).
type ModelScorer interface {
	ScoreBatch(ctx context.Context, features *ScoringFeatures, candidates []ContentCandidate) ([]ScoredCandidate, error)
}

// ---------------------------------------------------------------------------
// RuleScorer — hand-crafted weighted formula (baseline)
// ---------------------------------------------------------------------------

// RuleScorer is the baseline scorer using a hand-crafted formula.
// It encapsulates the scoring logic that was previously hardcoded in engine.go,
// enhanced with user-level feature integration.
type RuleScorer struct{}

func (s *RuleScorer) ScoreBatch(_ context.Context, features *ScoringFeatures, candidates []ContentCandidate) ([]ScoredCandidate, error) {
	now := time.Now()
	w := features.Weights
	sc := features.Scorer
	// Half-life is policy-validated > 0; guard only against a zero-value
	// ScorerConfig reaching here (would divide by zero in freshness decay).
	halfLife := sc.FreshnessHalfLifeHours
	if halfLife <= 0 {
		halfLife = recpolicy.Baseline().Scorer.FreshnessHalfLifeHours
		sc = recpolicy.Baseline().Scorer
	}
	session := features.Session
	if session == nil {
		session = &SessionState{}
	}
	user := features.User

	scored := make([]ScoredCandidate, 0, len(candidates))
	for _, c := range candidates {
		detail := make(map[string]float64, 8)

		// Tag relevance: session-level real-time interest
		tagScore := 0.0
		for _, tag := range c.Tags {
			if tw, ok := session.TagWeights[tag]; ok {
				tagScore += tw
			}
		}
		detail["tagRelevance"] = tagScore

		// Author affinity: enriched by user-level feature store
		authorAffinity := 0.0
		if user != nil && user.AuthorAffinities != nil {
			if aff, ok := user.AuthorAffinities[c.AuthorID]; ok {
				authorAffinity = aff
			}
		}
		detail["authorAffinity"] = authorAffinity

		// Long-term tag affinity from feature store (complements session signals)
		longTermTagBoost := 0.0
		if user != nil && user.TagAffinities != nil {
			for _, tag := range c.Tags {
				if aff, ok := user.TagAffinities[tag]; ok {
					longTermTagBoost += aff
				}
			}
		}
		detail["longTermTagBoost"] = longTermTagBoost

		// Popularity: log-scaled weighted engagement (coefficients from policy)
		popularity := math.Log1p(
			float64(c.ViewCount)*sc.Popularity.ViewCoefficient +
				float64(c.LikeCount)*sc.Popularity.LikeCoefficient +
				float64(c.CommentCount)*sc.Popularity.CommentCoefficient +
				float64(c.ShareCount)*sc.Popularity.ShareCoefficient,
		)
		detail["popularity"] = popularity

		// Freshness: exponential decay, half-life from policy
		ageHours := now.Sub(c.PublishedAt).Hours()
		if ageHours < 0 {
			ageHours = 0
		}
		freshness := math.Exp(-ageHours / halfLife)
		detail["freshness"] = freshness

		// Exploration boost: random perturbation for diversity (disabled when Deterministic for cursor pagination)
		exploreBoost := 0.0
		if features.ExploreRate > 0 && !features.Deterministic {
			exploreBoost = rand.Float64() * features.ExploreRate
		}
		detail["exploreBoost"] = exploreBoost

		// User engagement rate bonus (active users get slightly different treatment)
		engagementBonus := 0.0
		if user != nil && user.EngagementRate > 0 {
			engagementBonus = math.Log1p(user.EngagementRate) * sc.EngagementBonusFactor
		}
		detail["engagementBonus"] = engagementBonus

		// Social prior: circle tag match + social interest density (author follow handled by authorAffinity)
		socialPrior := 0.0
		if user != nil && len(user.CircleTagAffinities) > 0 {
			for _, tag := range c.Tags {
				if aff, ok := user.CircleTagAffinities[tag]; ok {
					socialPrior += aff * sc.CircleTagAffinityFactor
				}
			}
		}
		if user != nil && user.SocialInterestScore > 0 {
			socialPrior += math.Log1p(user.SocialInterestScore) * sc.SocialInterestFactor
		}
		detail["socialPrior"] = socialPrior

		// Negative penalty: suppress content with same author/tags as disliked items
		negativePenalty := 0.0
		if session != nil && len(session.NegativeIDs) > 0 {
			for _, tag := range c.Tags {
				if tw, ok := session.TagWeights[tag]; ok && tw < 0 {
					negativePenalty += math.Abs(tw) * sc.NegativePenaltyFactor
				}
			}
		}
		detail["negativePenalty"] = negativePenalty

		// Entity affinity: boost for content matching user's entity interests (instance + category)
		entityAffinity := 0.0
		if user != nil && len(c.EntityRefs) > 0 {
			if user.EntityInstanceAffinities != nil {
				for _, ref := range c.EntityRefs {
					if aff, ok := user.EntityInstanceAffinities[ref]; ok {
						entityAffinity += aff
					}
				}
			}
			if user.EntityAffinities != nil {
				for _, ref := range c.EntityRefs {
					if aff, ok := user.EntityAffinities[ref]; ok {
						entityAffinity += aff * sc.EntityCategoryFactor
					}
				}
			}
		}
		detail["entityAffinity"] = entityAffinity

		// ENER: type-specific engagement rate de-bias
		enerBoost := 0.0
		if user != nil && user.TypeENER != nil {
			if ener, ok := user.TypeENER[c.ContentType]; ok && ener > 0 {
				enerBoost = math.Log1p(ener*10) * sc.ENERBonusFactor
			}
		}
		detail["enerBoost"] = enerBoost

		// Four-dim tag matching: classify candidate tags and match against user affinities
		topicMatch := 0.0
		audienceMatch := 0.0
		formatMatch := 0.0
		if user != nil && len(c.Tags) > 0 {
			for _, tag := range c.Tags {
				dim := ClassifyTagDimension(tag)
				switch dim {
				case DimensionTopic:
					if user.TopicAffinities != nil {
						topicMatch += user.TopicAffinities[tag]
					}
				case DimensionAudience:
					if user.AudienceAffinities != nil {
						audienceMatch += user.AudienceAffinities[tag]
					}
				case DimensionFormat:
					if user.FormatAffinities != nil {
						formatMatch += user.FormatAffinities[tag]
					}
				}
			}
		}
		detail["topicMatch"] = topicMatch
		detail["audienceMatch"] = audienceMatch
		detail["formatMatch"] = formatMatch

		score := w.TagRelevance*(tagScore+longTermTagBoost*sc.LongTermTagBoostFactor) +
			w.AuthorAffinity*authorAffinity +
			w.Popularity*popularity +
			w.Freshness*freshness +
			w.ExploreBoost*exploreBoost +
			w.DwellBonus*(engagementBonus+enerBoost) +
			w.SocialPrior*socialPrior +
			w.EntityAffinity*entityAffinity +
			w.TopicMatch*topicMatch +
			w.AudienceMatch*audienceMatch +
			w.FormatMatch*formatMatch -
			w.NegativePenalty*negativePenalty

		detail["total"] = score

		scored = append(scored, ScoredCandidate{Candidate: c, Score: score, Detail: detail})
	}

	return scored, nil
}

// ---------------------------------------------------------------------------
// RemoteModelScorer — calls external ML model service
// ---------------------------------------------------------------------------

// ModelServiceClient abstracts the ML model service call.
// Implemented in infrastructure layer with actual HTTP/gRPC transport.
type ModelServiceClient interface {
	Predict(ctx context.Context, req *ModelPredictRequest) (*ModelPredictResponse, error)
}

// ModelPredictRequest is sent to the model service.
// Aligned with contracts/metadata/rec_model_service/fields.yaml and OpenAPI.
type ModelPredictRequest struct {
	Scenario       string             `json:"scenario"`
	UserID         string             `json:"userId"`
	SessionID      string             `json:"sessionId"`
	ModelVersion   string             `json:"modelVersion,omitempty"`
	UserFeatures   *UserFeatureVector `json:"userFeatures,omitempty"`
	SessionSignals *SessionState      `json:"sessionSignals,omitempty"`
	Candidates     []CandidateInput   `json:"candidates"`
	Context        map[string]any     `json:"context,omitempty"`
}

// CandidateInput is the candidate feature vector sent to the model.
type CandidateInput struct {
	ContentID    string   `json:"contentId"`
	ContentType  string   `json:"contentType"`
	AuthorID     string   `json:"authorId"`
	Tags         []string `json:"tagRefs"`
	EntityRefs   []string `json:"entityRefs,omitempty"`
	AgeHours     float64  `json:"ageHours"`
	ViewCount    int64    `json:"viewCount"`
	LikeCount    int64    `json:"likeCount"`
	CommentCount int64    `json:"commentCount"`
	ShareCount   int64    `json:"shareCount"`
	RecallPath   string   `json:"recallPath"`
}

// ModelPredictResponse is the model service response.
type ModelPredictResponse struct {
	Scores []CandidateScore `json:"scores"`
}

// CandidateScore is a per-candidate score from the model.
type CandidateScore struct {
	ContentID string             `json:"contentId"`
	Score     float64            `json:"score"`
	Detail    map[string]float64 `json:"detail,omitempty"`
}

// RemoteModelScorer delegates scoring to an external ML model service.
type RemoteModelScorer struct {
	client       ModelServiceClient
	Scenario     string // scenario sent to model service, e.g. content_feed
	ModelVersion string // "champion" or "challenger"; empty means server default
}

func NewRemoteModelScorer(client ModelServiceClient, scenario string) *RemoteModelScorer {
	if scenario == "" {
		scenario = "content_feed"
	}
	return &RemoteModelScorer{client: client, Scenario: scenario}
}

// WithModelVersion returns a copy of the scorer that requests a specific model version.
func (s *RemoteModelScorer) WithModelVersion(v string) *RemoteModelScorer {
	return &RemoteModelScorer{client: s.client, Scenario: s.Scenario, ModelVersion: v}
}

func (s *RemoteModelScorer) ScoreBatch(ctx context.Context, features *ScoringFeatures, candidates []ContentCandidate) ([]ScoredCandidate, error) {
	now := time.Now()
	inputs := make([]CandidateInput, len(candidates))
	for i, c := range candidates {
		ageHours := now.Sub(c.PublishedAt).Hours()
		if ageHours < 0 {
			ageHours = 0
		}
		inputs[i] = CandidateInput{
			ContentID:    c.ContentID,
			ContentType:  c.ContentType,
			AuthorID:     c.AuthorID,
			Tags:         c.Tags,
			EntityRefs:   c.EntityRefs,
			AgeHours:     ageHours,
			ViewCount:    c.ViewCount,
			LikeCount:    c.LikeCount,
			CommentCount: c.CommentCount,
			ShareCount:   c.ShareCount,
			RecallPath:   c.RecallPath,
		}
	}

	session := features.Session
	if session == nil {
		session = &SessionState{}
	}

	var reqCtx map[string]any
	if s.ModelVersion != "" {
		reqCtx = map[string]any{"modelVersion": s.ModelVersion}
	}

	resp, err := s.client.Predict(ctx, &ModelPredictRequest{
		Scenario:       s.Scenario,
		UserID:         session.UserID,
		SessionID:      session.SessionID,
		ModelVersion:   s.ModelVersion,
		UserFeatures:   features.User,
		SessionSignals: session,
		Candidates:     inputs,
		Context:        reqCtx,
	})
	if err != nil {
		return nil, err
	}

	scoreMap := make(map[string]CandidateScore, len(resp.Scores))
	for _, cs := range resp.Scores {
		scoreMap[cs.ContentID] = cs
	}

	result := make([]ScoredCandidate, 0, len(candidates))
	for _, c := range candidates {
		cs, ok := scoreMap[c.ContentID]
		if !ok {
			continue
		}
		result = append(result, ScoredCandidate{
			Candidate: c,
			Score:     cs.Score,
			Detail:    cs.Detail,
		})
	}

	return result, nil
}

// ---------------------------------------------------------------------------
// CascadeScorer — primary with fallback on error/timeout
// ---------------------------------------------------------------------------

// CascadeScorer tries the primary scorer first. On error or timeout,
// it falls back to the secondary scorer (typically RuleScorer).
// This ensures feed requests NEVER fail due to model unavailability.
type CascadeScorer struct {
	Primary  ModelScorer
	Fallback ModelScorer
	Timeout  time.Duration
	Logger   *slog.Logger
}

func NewCascadeScorer(primary, fallback ModelScorer, timeout time.Duration) *CascadeScorer {
	return &CascadeScorer{
		Primary:  primary,
		Fallback: fallback,
		Timeout:  timeout,
	}
}

func (c *CascadeScorer) ScoreBatch(ctx context.Context, features *ScoringFeatures, candidates []ContentCandidate) ([]ScoredCandidate, error) {
	scoreCtx := ctx
	if c.Timeout > 0 {
		var cancel context.CancelFunc
		scoreCtx, cancel = context.WithTimeout(ctx, c.Timeout)
		defer cancel()
	}

	result, err := c.Primary.ScoreBatch(scoreCtx, features, candidates)
	if err == nil {
		return result, nil
	}

	if c.Logger != nil {
		c.Logger.Warn("rec.model.cascade_fallback",
			slog.String("err", err.Error()),
			slog.Int("candidates", len(candidates)))
	}
	if scoreCtx.Err() != nil {
		RecordModelTimeout()
		RecordModelTimeoutMetric()
	}

	return c.Fallback.ScoreBatch(ctx, features, candidates)
}

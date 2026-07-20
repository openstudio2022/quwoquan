package recommendation

import (
	"context"
	"fmt"
	"log/slog"
	"math"
	"strings"
	"time"

	"quwoquan_service/runtime/recpolicy"
)

// ScoredCandidate is a candidate with a model-assigned score.
type ScoredCandidate struct {
	Candidate      ContentCandidate
	Score          float64
	Detail         map[string]float64 // individual feature contributions (for explainability/debugging)
	ModelReleaseID string             // 实际命中的模型发布；规则分或模型降级为空
}

// ScoringFeatures packages all inputs needed by a scorer.
type ScoringFeatures struct {
	Session *SessionState
	User    *UserFeatureVector
	Weights ScoringWeights
	// FeatureSnapshotAt 是本次请求读取用户/候选特征后的统一快照时刻。
	// 在线评分与训练曝光事实必须消费同一时刻，禁止各自在调用点重新取 now，
	// 否则 ageHours 会形成难以复现的训练/在线偏斜。
	FeatureSnapshotAt time.Time
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
	now := features.FeatureSnapshotAt
	if now.IsZero() {
		now = time.Now().UTC()
	}
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

	// Batch exposure total feeds the UCB1 exploration radius (see
	// ucbExplorationRadius): more total corpus exposure widens the confidence
	// bound, so under-served content keeps an exploration budget at scale.
	var totalExposure int64
	for _, c := range candidates {
		if c.ViewCount > 0 {
			totalExposure += c.ViewCount
		}
	}

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

		// Exploration boost: UCB1-style exposure-aware confidence radius (replaces
		// the prior pure-random perturbation). Under-exposed / cold-start content
		// (low ViewCount relative to the corpus) earns a larger, *deterministic*
		// exploration lift — a principled exposure-bias correction rather than
		// noise, and reproducible across cursor pages. Scaled by the policy-driven
		// ExploreRate so the contribution range matches prior behavior.
		exploreBoost := 0.0
		if features.ExploreRate > 0 && !features.Deterministic {
			exploreBoost = features.ExploreRate * ucbExplorationRadius(c.ViewCount, totalExposure)
		}
		detail["exploreBoost"] = exploreBoost

		// Projected item quality: only consume rm_discovery_feed qualityScore.
		// Missing/zero quality stays conservative and does not trigger read-path
		// recomputation.
		qualityScore := clamp01(c.QualityScore)
		detail["qualityScore"] = qualityScore

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
		// Intersection signal fusion (single injection point): a candidate recalled
		// via a social/intersection origin earns a bounded lift scaled by the viewer's
		// revealed engagement with the matching intersection kind. Fact-channel only;
		// keeps the intersection signal in one dimension rather than scattering it.
		if user != nil && sc.IntersectionSignalFactor > 0 {
			switch c.RecallPath {
			case "social_friend":
				socialPrior += math.Log1p(float64(user.SharedFolloweesCount)) * sc.IntersectionSignalFactor
			case "social_circle":
				socialPrior += math.Log1p(float64(user.SharedCircleCount)) * sc.IntersectionSignalFactor
			}
		}
		intersectionFact := math.Log1p(nonNegative(c.IntersectionFactStrength))*sc.IntersectionFactFactor +
			clamp01(c.IntersectionFreshness)*sc.IntersectionFreshnessFactor
		intersectionAffinity := 0.0
		if strings.TrimSpace(c.IntersectionConfidenceLabel) != "" {
			intersectionAffinity = clamp01(c.AffinityIntersectionScore) * sc.IntersectionAffinityFactor
		}
		socialPrior += intersectionFact + intersectionAffinity
		detail["intersectionFact"] = intersectionFact
		detail["intersectionAffinity"] = intersectionAffinity
		detail["socialPrior"] = socialPrior

		// Negative penalty: suppress content with tags that accumulated negative
		// weights. Explicit content-level negatives are handled by ExposureFilter
		// via candidate point lookups, not by loading large NegativeIDs sets.
		negativePenalty := 0.0
		if session != nil {
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

		// Search intent: recent search query/related terms lift matching feed
		// candidates. The feature is freshness-gated in FeatureStore and weighted
		// through recpolicy so it cannot become a dead or unbounded side channel.
		searchIntentBoost := 0.0
		if user != nil && sc.SearchIntentFactor > 0 {
			searchIntentBoost = searchIntentScore(user, c) * sc.SearchIntentFactor
		}
		detail["searchIntentBoost"] = searchIntentBoost

		score := w.TagRelevance*(tagScore+longTermTagBoost*sc.LongTermTagBoostFactor) +
			w.AuthorAffinity*authorAffinity +
			w.Popularity*popularity +
			w.Freshness*freshness +
			w.ExploreBoost*(exploreBoost+qualityScore*sc.QualityScoreFactor) +
			w.DwellBonus*(engagementBonus+enerBoost) +
			w.SocialPrior*socialPrior +
			w.EntityAffinity*entityAffinity +
			w.TopicMatch*topicMatch +
			w.AudienceMatch*audienceMatch +
			w.FormatMatch*formatMatch +
			w.SearchIntent*searchIntentBoost -
			w.NegativePenalty*negativePenalty

		detail["total"] = score

		scored = append(scored, ScoredCandidate{Candidate: c, Score: score, Detail: detail})
	}

	return scored, nil
}

func searchIntentScore(user *UserFeatureVector, c ContentCandidate) float64 {
	if user == nil {
		return 0
	}
	score := 0.0
	if len(user.SearchTopObjectAffinities) > 0 {
		if aff, ok := user.SearchTopObjectAffinities[c.ContentID]; ok && aff > 0 {
			score += aff
		}
		for _, ref := range c.EntityRefs {
			if aff, ok := user.SearchTopObjectAffinities[ref]; ok && aff > 0 {
				score += aff * 0.5
			}
		}
	}
	if len(user.SearchTermAffinities) > 0 {
		hay := candidateSearchHaystack(c)
		for term, aff := range user.SearchTermAffinities {
			if aff <= 0 {
				continue
			}
			term = strings.ToLower(strings.TrimSpace(term))
			if term == "" {
				continue
			}
			if strings.Contains(hay, term) {
				score += aff
			}
		}
	}
	if user.SearchTermHeat > 0 && score > 0 {
		score *= math.Log1p(user.SearchTermHeat)
	}
	return score
}

func candidateSearchHaystack(c ContentCandidate) string {
	parts := make([]string, 0, 2+len(c.Tags)+len(c.EntityRefs))
	parts = append(parts, c.Title, c.ContentType)
	parts = append(parts, c.Tags...)
	parts = append(parts, c.EntityRefs...)
	return strings.ToLower(strings.Join(parts, " "))
}

// ucbExplorationRadius returns the UCB1 confidence radius for an item given its
// own exposure (views ≈ arm pulls n_i) and the corpus total exposure (N), clamped
// to [0,1]. radius = sqrt( ln(1+N) / (1+n_i) ): brand-new content (n_i=0) earns
// the widest bound; heavily-exposed content asymptotes toward 0. As corpus traffic
// (N) grows the bound widens, preserving an exploration budget at scale. The value
// is deterministic, so exploration is reproducible across cursor pages.
func ucbExplorationRadius(views, totalViews int64) float64 {
	if views < 0 {
		views = 0
	}
	if totalViews < 0 {
		totalViews = 0
	}
	radius := math.Sqrt(math.Log1p(float64(totalViews)) / float64(1+views))
	if radius > 1 {
		return 1
	}
	if radius < 0 {
		return 0
	}
	return radius
}

func nonNegative(v float64) float64 {
	if v < 0 {
		return 0
	}
	return v
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
	ContentID   string   `json:"contentId"`
	ContentType string   `json:"contentType"`
	AuthorID    string   `json:"authorId"`
	Tags        []string `json:"tagRefs"`
	EntityRefs  []string `json:"entityRefs,omitempty"`
	AgeHours    float64  `json:"ageHours"`
	// PublishHour（N3-3）：发布时刻的 UTC 小时（0-23；publishedAt 缺失为 -1）。
	// 服务端派生随请求下发，与训练侧 itemFeatures.publishHour 同源，消除
	// 该特征的训练-在线偏斜（此前在线恒 0）。
	PublishHour                 int     `json:"publishHour"`
	ViewCount                   int64   `json:"viewCount"`
	LikeCount                   int64   `json:"likeCount"`
	CommentCount                int64   `json:"commentCount"`
	ShareCount                  int64   `json:"shareCount"`
	RecallPath                  string  `json:"recallPath"`
	QualityScore                float64 `json:"qualityScore,omitempty"`
	ContentVertical             string  `json:"contentVertical,omitempty"`
	SupplySource                string  `json:"supplySource,omitempty"`
	IntersectionFactStrength    float64 `json:"intersectionFactStrength,omitempty"`
	IntersectionFreshness       float64 `json:"intersectionFreshness,omitempty"`
	AffinityIntersectionScore   float64 `json:"affinityIntersectionScore,omitempty"`
	IntersectionSourceRefTop    string  `json:"intersectionSourceRefTop,omitempty"`
	IntersectionConfidenceLabel string  `json:"intersectionConfidenceLabel,omitempty"`
	IntersectionClass           string  `json:"intersectionClass,omitempty"`
}

// ModelPredictResponse is the model service response.
type ModelPredictResponse struct {
	Scores         []CandidateScore `json:"scores"`
	ModelReleaseID string           `json:"modelReleaseId,omitempty"`
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
	now := features.FeatureSnapshotAt
	if now.IsZero() {
		now = time.Now().UTC()
	}
	inputs := make([]CandidateInput, len(candidates))
	for i, c := range candidates {
		inputs[i] = candidateInputAt(c, now)
	}

	session := features.Session
	if session == nil {
		session = &SessionState{}
	}

	// 上下文时间特征与训练侧 Python datetime.weekday() 保持同构：
	// requestDayOfWeek 使用 Monday=0..Sunday=6，而 Go time.Weekday 是 Sunday=0。
	reqCtx := map[string]any{
		"requestHour":      now.Hour(),
		"requestDayOfWeek": (int(now.Weekday()) + 6) % 7,
	}
	if s.ModelVersion != "" {
		reqCtx["modelVersion"] = s.ModelVersion
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
	if resp == nil {
		return nil, fmt.Errorf("model scorer returned an empty response")
	}
	if len(candidates) > 0 && strings.TrimSpace(resp.ModelReleaseID) == "" {
		// 模型服务允许用 NULL 表达“未命中激活发布”；这对 transport 合法，
		// 但不能被线上引擎误报成 model 成功。返回错误交给 CascadeScorer 的
		// RuleScorer 兜底，保证 fallback 指标与曝光 modelReleaseId 都诚实。
		return nil, fmt.Errorf("model scorer returned no active model release")
	}

	scoreMap := make(map[string]CandidateScore, len(resp.Scores))
	expected := make(map[string]struct{}, len(candidates))
	for _, candidate := range candidates {
		expected[candidate.ContentID] = struct{}{}
	}
	for _, cs := range resp.Scores {
		if _, ok := expected[cs.ContentID]; !ok {
			return nil, fmt.Errorf("model scorer returned unknown candidate %q", cs.ContentID)
		}
		if _, duplicate := scoreMap[cs.ContentID]; duplicate {
			return nil, fmt.Errorf("model scorer returned duplicate candidate %q", cs.ContentID)
		}
		scoreMap[cs.ContentID] = cs
	}
	if len(scoreMap) != len(expected) {
		return nil, fmt.Errorf(
			"model scorer returned %d/%d candidate scores",
			len(scoreMap),
			len(expected),
		)
	}

	result := make([]ScoredCandidate, 0, len(candidates))
	for _, c := range candidates {
		cs, ok := scoreMap[c.ContentID]
		if !ok {
			continue
		}
		result = append(result, ScoredCandidate{
			Candidate:      c,
			Score:          cs.Score,
			Detail:         cs.Detail,
			ModelReleaseID: resp.ModelReleaseID,
		})
	}

	return result, nil
}

// candidateInputAt 是在线模型请求与曝光训练快照共用的候选特征装配真相源。
// 任何新增/退役候选特征都必须只在此处完成一次，并由两条链路共同消费。
func candidateInputAt(c ContentCandidate, snapshotAt time.Time) CandidateInput {
	ageHours := snapshotAt.Sub(c.PublishedAt).Hours()
	if ageHours < 0 {
		ageHours = 0
	}
	publishHour := -1
	if !c.PublishedAt.IsZero() {
		publishHour = c.PublishedAt.UTC().Hour()
	}
	return CandidateInput{
		ContentID:                   c.ContentID,
		ContentType:                 c.ContentType,
		AuthorID:                    c.AuthorID,
		Tags:                        append([]string(nil), c.Tags...),
		EntityRefs:                  append([]string(nil), c.EntityRefs...),
		AgeHours:                    ageHours,
		PublishHour:                 publishHour,
		ViewCount:                   c.ViewCount,
		LikeCount:                   c.LikeCount,
		CommentCount:                c.CommentCount,
		ShareCount:                  c.ShareCount,
		RecallPath:                  c.RecallPath,
		QualityScore:                c.QualityScore,
		ContentVertical:             c.ContentVertical,
		SupplySource:                c.SupplySource,
		IntersectionFactStrength:    c.IntersectionFactStrength,
		IntersectionFreshness:       c.IntersectionFreshness,
		AffinityIntersectionScore:   c.AffinityIntersectionScore,
		IntersectionSourceRefTop:    c.IntersectionSourceRefTop,
		IntersectionConfidenceLabel: c.IntersectionConfidenceLabel,
		IntersectionClass:           c.IntersectionClass,
	}
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
	result, _, err := c.ScoreBatchWithPath(ctx, features, candidates)
	return result, err
}

// ScoreBatchWithPath 与 ScoreBatch 同语义，额外返回本次是否发生了降级
// （usedFallback=true 表示 Primary 失败、结果来自 Fallback）。engine 据此
// 上报真实的 scorer 路径（model / rule_fallback），修正 model_fallback_rate
// 的语义（此前误用实验分桶名，降级不可测）。
func (c *CascadeScorer) ScoreBatchWithPath(
	ctx context.Context,
	features *ScoringFeatures,
	candidates []ContentCandidate,
) ([]ScoredCandidate, bool, error) {
	scoreCtx := ctx
	if c.Timeout > 0 {
		var cancel context.CancelFunc
		scoreCtx, cancel = context.WithTimeout(ctx, c.Timeout)
		defer cancel()
	}

	result, err := c.Primary.ScoreBatch(scoreCtx, features, candidates)
	if err == nil {
		return result, false, nil
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

	fallbackResult, fallbackErr := c.Fallback.ScoreBatch(ctx, features, candidates)
	return fallbackResult, true, fallbackErr
}

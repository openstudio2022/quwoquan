package recommendation

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log/slog"
	"math"
	"sort"
	"strings"
	"sync"
	"time"

	learning "quwoquan_service/runtime/learning"
	"quwoquan_service/runtime/recpolicy"
)

// FeedType identifies the kind of recommendation feed.
type FeedType string

const (
	FeedDiscovery FeedType = "discovery"
	FeedCircle    FeedType = "circle"
	FeedFollow    FeedType = "follow"
	FeedSimilar   FeedType = "similar"
	FeedTopic     FeedType = "topic"
	FeedHomepage  FeedType = "homepage"
	FeedSearch    FeedType = "search"
)

const (
	FeedSortRecommend = "recommend"
	defaultCursorTTL  = 10 * time.Minute
)

// GetFeedRequest defines input for feed generation.
type GetFeedRequest struct {
	UserID        string
	SessionID     string
	FeedType      FeedType
	Sort          string
	CircleID      string
	TopicID       string
	HomepageID    string
	Surface       string
	FeedRequestID string
	Cursor        string
	Limit         int
}

// FeedResponse holds the recommendation result.
type FeedResponse struct {
	Items      []FeedItem `json:"items"`
	NextCursor string     `json:"nextCursor,omitempty"`
}

// FeedItem represents a single item in the feed.
type FeedItem struct {
	ContentID   string   `json:"contentId"`
	ContentType string   `json:"contentType"`
	AuthorID    string   `json:"authorId"`
	Title       string   `json:"title,omitempty"`
	Tags        []string `json:"tags,omitempty"`
	Score       float64  `json:"score"`
	RecallPath  string   `json:"recallPath,omitempty"`
}

type feedCursorState struct {
	Version   int    `json:"v"`
	SessionID string `json:"sid"`
	Offset    int    `json:"off"`
	ExpiresAt int64  `json:"exp"`
}

// ContentCandidate is a candidate from the recall layer.
type ContentCandidate struct {
	ContentID    string
	ContentType  string
	AuthorID     string
	Title        string
	Tags         []string
	EntityRefs   []string
	PublishedAt  time.Time
	ViewCount    int64
	LikeCount    int64
	CommentCount int64
	ShareCount   int64
	RecallPath   string
}

// CandidateSource provides content candidates for recall.
type CandidateSource interface {
	Recall(ctx context.Context, req RecallRequest) ([]ContentCandidate, error)
}

type RecallRequest struct {
	FeedType      FeedType
	UserID        string
	CircleID      string
	TopicID       string
	HomepageID    string
	Surface       string
	FeedRequestID string
	Tags          []string
	Limit         int
	Cursor        string
}

// ScoringWeights controls the relative importance of each scoring dimension.
// It is an alias for recpolicy.WeightPreset: scoring weights are policy data
// (metadata-driven, hot-reloadable), never hand-coded constants.
type ScoringWeights = recpolicy.WeightPreset

// Engine orchestrates the full recommendation pipeline:
//
//	Recall → PreRank → Filter → FeatureAssembly → ModelScore → Rerank
//
// Each stage is pluggable via interfaces, with sensible defaults.
type Engine struct {
	sessions SessionReader
	sources  []CandidateSource

	scorer    ModelScorer
	features  FeatureProvider
	preRanker PreRanker

	recallTimeout  time.Duration
	featureTimeout time.Duration

	socialMiner *SocialInterestMiner

	// policyStore is the single source of scoring weights, secondary
	// coefficients, AB experiments, and segment targeting. Never nil; defaults
	// to the codegen baseline. Hot-reloadable via recpolicy.StartSyncLoop.
	policyStore *recpolicy.Store

	logger         *slog.Logger
	feedback       *FeedbackRecorder
	exposureFilter ExposureFilter
	exposureMemory ExposureMemory
}

// EngineOption configures the Engine.
type EngineOption func(*Engine)

// WithPolicyStore injects the recommendation policy store. When omitted, the
// engine uses the codegen baseline policy.
func WithPolicyStore(s *recpolicy.Store) EngineOption {
	return func(e *Engine) {
		if s != nil {
			e.policyStore = s
		}
	}
}

func WithLogger(l *slog.Logger) EngineOption {
	return func(e *Engine) { e.logger = l }
}

func WithFeedbackRecorder(f *FeedbackRecorder) EngineOption {
	return func(e *Engine) { e.feedback = f }
}

func WithExposureGovernance(memory ExposureMemory, filter ExposureFilter) EngineOption {
	return func(e *Engine) {
		e.exposureMemory = memory
		e.exposureFilter = filter
	}
}

// WithRecallTimeout sets the per-source recall deadline.
func WithRecallTimeout(d time.Duration) EngineOption {
	return func(e *Engine) { e.recallTimeout = d }
}

// WithScorer sets the model scorer (RuleScorer, RemoteModelScorer, CascadeScorer).
func WithScorer(s ModelScorer) EngineOption {
	return func(e *Engine) { e.scorer = s }
}

// WithFeatureProvider sets the user feature provider.
func WithFeatureProvider(fp FeatureProvider) EngineOption {
	return func(e *Engine) { e.features = fp }
}

// WithPreRanker sets the pre-ranking filter.
func WithPreRanker(pr PreRanker) EngineOption {
	return func(e *Engine) { e.preRanker = pr }
}

// WithSocialMiner enables social interest enrichment during feature assembly.
func WithSocialMiner(m *SocialInterestMiner) EngineOption {
	return func(e *Engine) { e.socialMiner = m }
}

// NewEngine creates a recommendation engine.
// sessions accepts *HotPath, *SessionCache, or any SessionReader.
func NewEngine(sessions SessionReader, sources []CandidateSource, opts ...EngineOption) *Engine {
	e := &Engine{
		sessions:       sessions,
		sources:        sources,
		scorer:         &RuleScorer{},
		features:       &NullFeatureProvider{},
		preRanker:      &NullPreRanker{},
		policyStore:    recpolicy.NewStoreFromBaseline(),
		recallTimeout:  150 * time.Millisecond,
		featureTimeout: 50 * time.Millisecond,
	}
	for _, opt := range opts {
		opt(e)
	}
	return e
}

// GetFeed generates a personalized feed.
// Pipeline: Session → Recall → PreRank → Filter → Features → Score → Rerank
func (e *Engine) GetFeed(ctx context.Context, req GetFeedRequest) (*FeedResponse, error) {
	pipelineStart := time.Now()

	if req.Limit <= 0 {
		req.Limit = 20
	}
	req.Sort = normalizeSort(req.Sort)

	pagingOffset := 0
	sessionID := strings.TrimSpace(req.SessionID)
	rawCursor := strings.TrimSpace(req.Cursor)
	if req.Sort == FeedSortRecommend && rawCursor != "" {
		if state, ok := decodeFeedCursor(rawCursor, pipelineStart); ok {
			pagingOffset = state.Offset
			if sessionID == "" {
				sessionID = state.SessionID
			}
		}
		// recommend 模式下的 cursor 为 opaque token，不下传给 recall 层。
		req.Cursor = ""
	}
	if sessionID != "" {
		req.SessionID = sessionID
	}

	// Stage 1: Load session state (from SessionCache or HotPath)
	session, err := e.sessions.GetSessionState(ctx, req.UserID, req.SessionID)
	if err != nil {
		session = &SessionState{UserID: req.UserID, SessionID: req.SessionID}
	}

	// Stage 2: Parallel recall from all sources
	recallStart := time.Now()
	recallBuf := acquireCandidates()
	e.parallelRecallInto(ctx, req, session, recallBuf)
	allCandidates := *recallBuf
	// Stable order for cursor pagination: same candidate set yields same order across requests.
	sort.Slice(allCandidates, func(i, j int) bool {
		return allCandidates[i].ContentID < allCandidates[j].ContentID
	})
	recallLatency := time.Since(recallStart)

	// Stage 3: Pre-rank (lightweight filter before expensive scoring)
	windowLimit := req.Limit*5 + pagingOffset + req.Limit
	preranked := e.preRanker.PreRank(ctx, allCandidates, windowLimit)

	// Stage 4: Filter served + impressed + negative + dedup.
	// Long-window exposure memory is resolved by candidate membership point
	// lookups, not by loading per-user SMembers into SessionState.
	exposedSet := toSet(session.ExposedIDs)
	negativeSet := toSet(session.NegativeIDs)
	hiddenAuthors := toSet(session.HiddenAuthorIDs)
	hiddenTypes := toSet(session.HiddenContentTypes)
	filteredBuf := acquireCandidates()
	seen := make(map[string]bool, len(preranked))
	for _, c := range preranked {
		if exposedSet[c.ContentID] ||
			negativeSet[c.ContentID] ||
			hiddenAuthors[c.AuthorID] ||
			hiddenTypes[c.ContentType] ||
			seen[c.ContentID] {
			continue
		}
		seen[c.ContentID] = true
		*filteredBuf = append(*filteredBuf, c)
	}
	filtered := *filteredBuf
	if e.exposureFilter != nil {
		exposureFiltered, filterErr := e.exposureFilter.FilterCandidates(ctx, req.UserID, filtered, pipelineStart)
		if filterErr != nil {
			if e.logger != nil {
				e.logger.Warn("rec.exposure_filter.error", slog.String("err", filterErr.Error()))
			}
		} else {
			filtered = exposureFiltered
		}
	}

	// Stage 5: Feature assembly (user features from feature store, with timeout)
	var userFeatures *UserFeatureVector
	if e.features != nil {
		featCtx, featCancel := context.WithTimeout(ctx, e.featureTimeout)
		userFeatures, _ = e.features.GetFeatures(featCtx, req.UserID)
		featCancel()
	}

	// Enrich with social interest mining if projector hasn't populated social fields
	if e.socialMiner != nil && (userFeatures == nil || len(userFeatures.CircleTagAffinities) == 0) {
		socialCtx, socialCancel := context.WithTimeout(ctx, e.featureTimeout)
		socialVec, socialErr := e.socialMiner.Mine(socialCtx, req.UserID)
		socialCancel()
		if socialErr == nil && socialVec != nil {
			if userFeatures == nil {
				userFeatures = &UserFeatureVector{}
			}
			if len(userFeatures.CircleTagAffinities) == 0 {
				userFeatures.CircleTagAffinities = socialVec.CircleTagAffinities
			}
			if userFeatures.SocialInterestScore == 0 {
				userFeatures.SocialInterestScore = socialVec.SocialDensity
			}
			if len(socialVec.FriendTagIntersection) > 0 {
				if userFeatures.TagAffinities == nil {
					userFeatures.TagAffinities = make(map[string]float64)
				}
				for tag, weight := range socialVec.FriendTagIntersection {
					userFeatures.TagAffinities[tag] += weight
				}
			}
		}
	}

	// Stage 5.5: Resolve scoring policy now that user segments are known.
	// Weights, secondary coefficients, AB buckets, and segment targeting all
	// come from the hot-reloadable policy (no hand-coded constants). Bucket
	// hashing keys on userID for stable assignment; segments gate eligibility
	// and drive preset overrides / weight deltas.
	policy := e.policyStore.Current()
	var userSegments []string
	if userFeatures != nil {
		userSegments = userFeatures.Segments
	}
	// Scenario routing: the feed scenario (FeedType) selects the base preset
	// (e.g. homepage/similar → premium for deep consumption). Experiment buckets
	// still win; segment overrides/deltas still apply inside ResolveWeights.
	scenarioBasePreset := policy.PresetForScenario(string(req.FeedType))
	scoringBucket := policy.ResolveBucketOr(recpolicy.ExpScoringWeights, req.UserID, userSegments, scenarioBasePreset)
	resolved := policy.ResolveWeights(scoringBucket, userSegments)
	modelBucket := policy.ResolveBucketOr(recpolicy.ExpModelVsRule, req.UserID, userSegments, "rule")
	modelVersion := policy.ResolveBucketOr(recpolicy.ExpModelVersion, req.UserID, userSegments, "champion")

	scoringFeatures := &ScoringFeatures{
		Session:       session,
		User:          userFeatures,
		Weights:       resolved.Weights,
		Scorer:        resolved.Scorer,
		ExploreRate:   resolved.Scorer.ExploreFraction,
		Deterministic: req.Sort == FeedSortRecommend, // stable ordering for recommend + cursor pagination (no random explore boost)
	}

	// Stage 6: Model scoring (RuleScorer, RemoteModelScorer, or CascadeScorer)
	// model_vs_rule experiment: "model" uses primary scorer; "rule" uses fallback.
	// model_version experiment: when "challenger", ask model service for canary version.
	scoreStart := time.Now()
	activeScorer := e.scorer
	if modelBucket == "rule" {
		if cascade, ok := e.scorer.(*CascadeScorer); ok {
			activeScorer = cascade.Fallback
		}
	} else if modelVersion == "challenger" {
		if cascade, ok := e.scorer.(*CascadeScorer); ok {
			if remote, ok := cascade.Primary.(*RemoteModelScorer); ok {
				activeScorer = &CascadeScorer{
					Primary:  remote.WithModelVersion("challenger"),
					Fallback: cascade.Fallback,
					Timeout:  cascade.Timeout,
					Logger:   cascade.Logger,
				}
			}
		}
	}
	scored, scoreErr := activeScorer.ScoreBatch(ctx, scoringFeatures, filtered)
	if scoreErr != nil {
		if e.logger != nil {
			e.logger.Error("rec.score.error", slog.String("err", scoreErr.Error()))
		}
		scored = make([]ScoredCandidate, 0)
	}
	scoreLatency := time.Since(scoreStart)

	// Shadow scoring: async call to challenger model for offline comparison
	if modelBucket == "model" && modelVersion == "champion" && e.feedback != nil {
		if cascade, ok := e.scorer.(*CascadeScorer); ok {
			if remote, ok := cascade.Primary.(*RemoteModelScorer); ok {
				shadowScorer := remote.WithModelVersion("challenger")
				go func() {
					shadowCtx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
					defer cancel()
					shadowScored, err := shadowScorer.ScoreBatch(shadowCtx, scoringFeatures, filtered)
					if err != nil {
						if e.logger != nil {
							e.logger.Debug("rec.shadow.error", slog.String("err", err.Error()))
						}
						return
					}
					e.recordShadowScores(shadowCtx, req.UserID, req.SessionID, shadowScored)
				}()
			}
		}
	}

	// Sort by score (scorer returns unsorted). Tie-break by ContentID for stable pagination.
	sort.Slice(scored, func(i, j int) bool {
		if scored[i].Score != scored[j].Score {
			return scored[i].Score > scored[j].Score
		}
		return scored[i].Candidate.ContentID < scored[j].Candidate.ContentID
	})

	// Release intermediate pooled buffers after scoring
	releaseCandidates(recallBuf)
	releaseCandidates(filteredBuf)

	// Stage 7: Rerank (diversity + author dedup) — diversity/cold-start
	// thresholds come from the resolved policy, not hand-coded constants.
	rerankStart := time.Now()
	reranked := e.rerank(scored, windowLimit, resolved.Scorer)
	reranked = applyFrequencyAndNearDupCaps(reranked, windowLimit, policy.ExposureGovernance.FrequencyAndNearDup)
	reranked = applyDynamicExposureBudget(reranked, windowLimit, policy.ExposureGovernance.DynamicBudget, modelBucket)
	rerankLatency := time.Since(rerankStart)

	topicEntropy := computeTopicEntropy(reranked)
	authorRepeatRate, authorHHI, distinctAuthors := computeAuthorDiversity(reranked)
	geoCoverage, distinctGeoBuckets := computeGeoCoverage(reranked)
	distinctTopics := computeDistinctTopicCount(reranked)

	allItems := make([]FeedItem, 0, len(reranked))
	for _, s := range reranked {
		allItems = append(allItems, FeedItem{
			ContentID:   s.Candidate.ContentID,
			ContentType: s.Candidate.ContentType,
			AuthorID:    s.Candidate.AuthorID,
			Title:       s.Candidate.Title,
			Tags:        s.Candidate.Tags,
			Score:       s.Score,
			RecallPath:  s.Candidate.RecallPath,
		})
	}

	start := pagingOffset
	if start < 0 {
		start = 0
	}
	if start > len(allItems) {
		start = len(allItems)
	}
	end := start + req.Limit
	if end > len(allItems) {
		end = len(allItems)
	}
	items := allItems[start:end]

	var nextCursor string
	if req.Sort == FeedSortRecommend && end < len(allItems) {
		nextCursor = encodeFeedCursor(feedCursorState{
			Version:   1,
			SessionID: req.SessionID,
			Offset:    end,
			ExpiresAt: time.Now().Add(defaultCursorTTL).Unix(),
		})
	}
	if req.Sort != FeedSortRecommend && end < len(allItems) && len(items) > 0 {
		nextCursor = items[len(items)-1].ContentID
	}

	resp := &FeedResponse{
		Items:      items,
		NextCursor: nextCursor,
	}

	// Observability: emit pipeline metrics
	totalLatency := time.Since(pipelineStart)
	if e.logger != nil {
		sourceBreakdown := map[string]int{}
		for _, c := range allCandidates {
			sourceBreakdown[c.RecallPath]++
		}
		LogMetrics(e.logger, PipelineMetrics{
			UserID:             req.UserID,
			SessionID:          req.SessionID,
			RecallLatency:      recallLatency,
			ScoreLatency:       scoreLatency,
			RerankLatency:      rerankLatency,
			TotalLatency:       totalLatency,
			CandidateCount:     len(allCandidates),
			FilteredCount:      len(filtered),
			ResultCount:        len(items),
			SourceBreakdown:    sourceBreakdown,
			ModelUsed:          modelBucket,
			ExperimentBucket:   scoringBucket,
			PolicyVersion:      resolved.PolicyVersion,
			ScoringPreset:      resolved.Preset,
			Segment:            resolved.AppliedSegment,
			TopicEntropy:       topicEntropy,
			AuthorRepeatRate:   authorRepeatRate,
			AuthorHHI:          authorHHI,
			GeoCoverage:        geoCoverage,
			DistinctAuthors:    distinctAuthors,
			DistinctTopics:     distinctTopics,
			DistinctGeoBuckets: distinctGeoBuckets,
		})
		if topicEntropy < 1.5 && topicEntropy > 0 && len(items) >= 5 {
			e.logger.Warn("rec.diversity.low_entropy",
				slog.Float64("topicEntropy", topicEntropy),
				slog.String("userId", req.UserID),
				slog.Int("resultCount", len(items)))
		}
	}

	// Learning: record impressions asynchronously (fire-and-forget)
	if e.feedback != nil {
		feedbackItems := make([]FeedItem, len(items))
		copy(feedbackItems, items)
		go func() {
			fbCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			defer cancel()
			_ = e.feedback.RecordImpression(fbCtx, req.UserID, req.SessionID, feedbackItems)
		}()
	}

	RecordPipelineResult(modelBucket, len(items) == 0)

	if e.exposureMemory != nil && req.UserID != "" && len(items) > 0 {
		servedItems := make([]FeedItem, len(items))
		copy(servedItems, items)
		RecordServedItems(len(servedItems))
		go func() {
			servedCtx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
			defer cancel()
			if err := e.exposureMemory.RecordServed(servedCtx, req.UserID, servedItems, time.Now().UTC()); err != nil && e.logger != nil {
				e.logger.Warn("rec.exposure.served_write_failed", slog.String("err", err.Error()))
			}
		}()
	}

	return resp, nil
}

func normalizeSort(raw string) string {
	switch strings.TrimSpace(strings.ToLower(raw)) {
	case "", FeedSortRecommend:
		return FeedSortRecommend
	default:
		return FeedSortRecommend
	}
}

func decodeFeedCursor(raw string, now time.Time) (feedCursorState, bool) {
	decoded, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(raw))
	if err != nil {
		return feedCursorState{}, false
	}
	var state feedCursorState
	if err := json.Unmarshal(decoded, &state); err != nil {
		return feedCursorState{}, false
	}
	if state.Version <= 0 || state.Offset < 0 {
		return feedCursorState{}, false
	}
	if state.ExpiresAt > 0 && now.Unix() > state.ExpiresAt {
		return feedCursorState{}, false
	}
	return state, true
}

func encodeFeedCursor(state feedCursorState) string {
	raw, err := json.Marshal(state)
	if err != nil {
		return ""
	}
	return base64.RawURLEncoding.EncodeToString(raw)
}

// parallelRecallInto fans out to all sources concurrently with per-source timeout,
// appending results into the provided pooled buffer.
func (e *Engine) parallelRecallInto(ctx context.Context, req GetFeedRequest, session *SessionState, out *[]ContentCandidate) {
	interestTags := topNTags(session.TagWeights, 10)
	recallReq := RecallRequest{
		FeedType:      req.FeedType,
		UserID:        req.UserID,
		CircleID:      req.CircleID,
		TopicID:       req.TopicID,
		HomepageID:    req.HomepageID,
		Surface:       req.Surface,
		FeedRequestID: req.FeedRequestID,
		Tags:          interestTags,
		Limit:         req.Limit * 3,
		Cursor:        req.Cursor,
	}

	recallCtx := ctx
	if e.recallTimeout > 0 {
		var cancel context.CancelFunc
		recallCtx, cancel = context.WithTimeout(ctx, e.recallTimeout)
		defer cancel()
	}

	if len(e.sources) <= 1 {
		for _, src := range e.sources {
			candidates, err := src.Recall(recallCtx, recallReq)
			if err != nil {
				if e.logger != nil {
					e.logger.Warn("rec.recall.source_error", slog.String("err", err.Error()))
				}
				continue
			}
			*out = append(*out, candidates...)
		}
		return
	}

	type result struct {
		candidates []ContentCandidate
	}
	results := make([]result, len(e.sources))
	var wg sync.WaitGroup
	for i, src := range e.sources {
		wg.Add(1)
		go func(idx int, s CandidateSource) {
			defer wg.Done()
			candidates, err := s.Recall(recallCtx, recallReq)
			if err != nil {
				if e.logger != nil {
					e.logger.Warn("rec.recall.source_error", slog.String("err", err.Error()))
				}
				return
			}
			results[idx] = result{candidates: candidates}
		}(i, src)
	}
	wg.Wait()

	for _, r := range results {
		*out = append(*out, r.candidates...)
	}
}

// rerank applies diversity constraints: content type variety, author dedup, tag dedup,
// explore injection, and cold-start minimum guarantee.
func (e *Engine) rerank(scored []ScoredCandidate, limit int, scorer recpolicy.ScorerConfig) []ScoredCandidate {
	if scorer.DiversityStrategy == "mmr" {
		return e.rerankMMR(scored, limit, scorer)
	}
	if len(scored) == 0 {
		return scored
	}
	if limit <= 0 || limit > len(scored) {
		limit = len(scored)
	}

	typeCount := make(map[string]int)
	authorCount := make(map[string]int)
	maxPerType := (limit / 3) + 1
	maxPerAuthor := scorer.MaxAuthorPerFeed
	coldStartAgeHours := scorer.ColdStartAgeHours
	coldStartViewThreshold := scorer.ColdStartViewThreshold

	// Tag dedup: track recent top tags to avoid consecutive same-tag content
	recentTopTags := make([]string, 0, 3)
	topTagOf := func(c ContentCandidate) string {
		if len(c.Tags) > 0 {
			return c.Tags[0]
		}
		return ""
	}

	var result []ScoredCandidate
	var exploreBuffer []ScoredCandidate
	var coldStartBuffer []ScoredCandidate

	for _, s := range scored {
		ct := s.Candidate.ContentType
		author := s.Candidate.AuthorID

		if typeCount[ct] >= maxPerType {
			continue
		}
		if author != "" && authorCount[author] >= maxPerAuthor {
			continue
		}

		// Same top-tag dedup: no 3 consecutive items sharing the same top tag
		topTag := topTagOf(s.Candidate)
		if topTag != "" && len(recentTopTags) >= 2 &&
			recentTopTags[len(recentTopTags)-1] == topTag &&
			recentTopTags[len(recentTopTags)-2] == topTag {
			continue
		}

		// Separate explore and cold-start candidates for injection
		if s.Candidate.RecallPath == "explore_recall" {
			exploreBuffer = append(exploreBuffer, s)
			continue
		}
		ageHours := time.Since(s.Candidate.PublishedAt).Hours()
		if ageHours < coldStartAgeHours && s.Candidate.ViewCount < coldStartViewThreshold {
			coldStartBuffer = append(coldStartBuffer, s)
			continue
		}

		result = append(result, s)
		typeCount[ct]++
		if author != "" {
			authorCount[author]++
		}
		recentTopTags = append(recentTopTags, topTag)

		if len(result) >= limit {
			break
		}
	}

	// Explore injection: at least 1 per 5 items
	exploreTarget := int(float64(limit) * scorer.ExploreFraction)
	if exploreTarget < 1 && len(exploreBuffer) > 0 {
		exploreTarget = 1
	}

	// Cold-start guarantee: new content (<24h) at least 10% of results
	coldStartTarget := limit / 10
	if coldStartTarget < 1 && len(coldStartBuffer) > 0 {
		coldStartTarget = 1
	}

	// Inject explore items at even intervals, respecting diversity constraints
	final := make([]ScoredCandidate, 0, limit)
	exploreIdx := 0
	coldIdx := 0
	resultIdx := 0
	for i := 0; i < limit; i++ {
		if (i+1)%5 == 0 && exploreIdx < len(exploreBuffer) && exploreIdx < exploreTarget {
			s := exploreBuffer[exploreIdx]
			final = append(final, s)
			typeCount[s.Candidate.ContentType]++
			if s.Candidate.AuthorID != "" {
				authorCount[s.Candidate.AuthorID]++
			}
			exploreIdx++
		} else if (i+1)%10 == 0 && coldIdx < len(coldStartBuffer) && coldIdx < coldStartTarget {
			s := coldStartBuffer[coldIdx]
			final = append(final, s)
			typeCount[s.Candidate.ContentType]++
			if s.Candidate.AuthorID != "" {
				authorCount[s.Candidate.AuthorID]++
			}
			coldIdx++
		} else if resultIdx < len(result) {
			final = append(final, result[resultIdx])
			resultIdx++
		} else if exploreIdx < len(exploreBuffer) {
			final = append(final, exploreBuffer[exploreIdx])
			exploreIdx++
		} else if coldIdx < len(coldStartBuffer) {
			final = append(final, coldStartBuffer[coldIdx])
			coldIdx++
		}
	}

	// Fill remaining slots from any source, applying the same diversity constraints
	if len(final) < limit {
		existing := make(map[string]bool, len(final))
		for _, f := range final {
			existing[f.Candidate.ContentID] = true
		}
		for _, s := range scored {
			if len(final) >= limit {
				break
			}
			if existing[s.Candidate.ContentID] {
				continue
			}
			ct := s.Candidate.ContentType
			author := s.Candidate.AuthorID
			if typeCount[ct] >= maxPerType {
				continue
			}
			if author != "" && authorCount[author] >= maxPerAuthor {
				continue
			}
			topTag := topTagOf(s.Candidate)
			if topTag != "" && len(recentTopTags) >= 2 &&
				recentTopTags[len(recentTopTags)-1] == topTag &&
				recentTopTags[len(recentTopTags)-2] == topTag {
				continue
			}
			final = append(final, s)
			typeCount[ct]++
			if author != "" {
				authorCount[author]++
			}
			recentTopTags = append(recentTopTags, topTag)
		}
	}

	return final
}

func applyDynamicExposureBudget(
	items []ScoredCandidate,
	limit int,
	cfg recpolicy.DynamicExposureBudgetConfig,
	bucket string,
) []ScoredCandidate {
	if !cfg.Enabled || strings.EqualFold(strings.TrimSpace(bucket), "disable_exposure_dynamic_budget") {
		return items
	}
	if len(items) == 0 {
		return items
	}
	if limit <= 0 || limit > len(items) {
		limit = len(items)
	}
	remaining := make([]ScoredCandidate, 0, len(items))
	selected := make([]ScoredCandidate, 0, limit)
	poolCounts := map[string]int{}

	// Quotas are exposure-share constraints, not rank replacement. We preserve
	// existing score order within every pool and only reserve small trial/rising
	// lanes so young/high-feedback content can earn measured exposure.
	quotas := dynamicBudgetQuotas(limit, cfg)
	for _, s := range items {
		pool := exposurePoolForCandidate(s.Candidate, cfg)
		if quota := quotas[pool]; quota > 0 && poolCounts[pool] < quota && len(selected) < limit {
			selected = append(selected, s)
			poolCounts[pool]++
			continue
		}
		remaining = append(remaining, s)
	}
	existing := make(map[string]struct{}, len(selected))
	for _, s := range selected {
		existing[s.Candidate.ContentID] = struct{}{}
	}
	for _, s := range remaining {
		if len(selected) >= limit {
			break
		}
		if _, ok := existing[s.Candidate.ContentID]; ok {
			continue
		}
		selected = append(selected, s)
		poolCounts[exposurePoolForCandidate(s.Candidate, cfg)]++
	}
	for pool, count := range poolCounts {
		RecordDynamicBudgetSelection(pool, bucket, count)
	}
	if len(selected) == 0 {
		return items
	}
	reordered := make([]ScoredCandidate, 0, len(items))
	reordered = append(reordered, selected...)
	for _, s := range items {
		if _, ok := existing[s.Candidate.ContentID]; ok {
			continue
		}
		reordered = append(reordered, s)
	}
	return reordered
}

func dynamicBudgetQuotas(limit int, cfg recpolicy.DynamicExposureBudgetConfig) map[string]int {
	trial := int(math.Ceil(float64(limit) * 0.2))
	rising := int(math.Ceil(float64(limit) * 0.3))
	if trial < 1 {
		trial = 1
	}
	if rising < 1 {
		rising = 1
	}
	if cfg.TrialMinServed > 0 && trial > cfg.TrialMinServed {
		trial = cfg.TrialMinServed
	}
	return map[string]int{
		"trial":  trial,
		"rising": rising,
	}
}

func exposurePoolForCandidate(c ContentCandidate, cfg recpolicy.DynamicExposureBudgetConfig) string {
	served := c.ViewCount
	ctr := rate(c.LikeCount+c.CommentCount+c.ShareCount, served)
	negativeRate := 0.0
	if c.ViewCount > 0 {
		// share/comment/like are the only available online aggregates in this
		// candidate shape. Negative-rate storage lands in rm_exposure_state; until
		// then, retired remains explicit future state and never inferred falsely.
		negativeRate = 0
	}
	switch {
	case cfg.RetirementNegativeRateThreshold > 0 && negativeRate >= cfg.RetirementNegativeRateThreshold:
		return "retired"
	case served < int64(cfg.TrialMinServed):
		return "trial"
	case ctr >= cfg.PromotionCTRThreshold:
		return "rising"
	case time.Since(c.PublishedAt) > 30*24*time.Hour && ctr > 0:
		return "evergreen"
	default:
		return "mature"
	}
}

func rate(numerator int64, denominator int64) float64 {
	if denominator <= 0 {
		return 0
	}
	return float64(numerator) / float64(denominator)
}

func applyFrequencyAndNearDupCaps(items []ScoredCandidate, limit int, cfg recpolicy.FrequencyAndNearDupConfig) []ScoredCandidate {
	if !cfg.Enabled || len(items) == 0 {
		return items
	}
	if limit <= 0 || limit > len(items) {
		limit = len(items)
	}
	minFill := limit * cfg.SoftFallbackMinFillPct / 100
	if minFill <= 0 {
		minFill = limit
	}
	selected := make([]ScoredCandidate, 0, limit)
	held := make([]ScoredCandidate, 0, len(items))
	reasonCounts := map[string]int{}
	authorCount := map[string]int{}
	tagCount := map[string]int{}
	topicCount := map[string]int{}
	selectedFeatures := make([]map[string]struct{}, 0, limit)

	for _, item := range items {
		if len(selected) >= limit {
			held = append(held, item)
			continue
		}
		if reason := frequencyOrNearDupViolation(item, authorCount, tagCount, topicCount, selectedFeatures, cfg); reason != "" {
			reasonCounts[reason]++
			held = append(held, item)
			continue
		}
		selected = append(selected, item)
		observeFrequency(item.Candidate, authorCount, tagCount, topicCount)
		selectedFeatures = append(selectedFeatures, candidateFeatureSet(item.Candidate))
	}

	// Soft fallback: caps must not empty or under-fill the feed. Refill by
	// original score order when the constrained pass cannot satisfy minFill.
	for _, item := range held {
		if len(selected) >= limit || len(selected) >= minFill {
			break
		}
		selected = append(selected, item)
	}
	if len(selected) == 0 {
		return items
	}
	for reason, count := range reasonCounts {
		if reason == "near_dup" {
			RecordNearDupFilter(count)
			continue
		}
		RecordFrequencyCapFilter(reason, count)
	}
	reordered := make([]ScoredCandidate, 0, len(items))
	reordered = append(reordered, selected...)
	seen := map[string]struct{}{}
	for _, item := range selected {
		seen[item.Candidate.ContentID] = struct{}{}
	}
	for _, item := range items {
		if _, ok := seen[item.Candidate.ContentID]; ok {
			continue
		}
		reordered = append(reordered, item)
	}
	return reordered
}

func frequencyOrNearDupViolation(
	item ScoredCandidate,
	authorCount map[string]int,
	tagCount map[string]int,
	topicCount map[string]int,
	selectedFeatures []map[string]struct{},
	cfg recpolicy.FrequencyAndNearDupConfig,
) string {
	c := item.Candidate
	if cfg.MaxSameAuthorPerWindow > 0 && c.AuthorID != "" && authorCount[c.AuthorID] >= cfg.MaxSameAuthorPerWindow {
		return "author"
	}
	if cfg.MaxSameTagPerWindow > 0 {
		for _, tag := range c.Tags {
			if tag != "" && tagCount[tag] >= cfg.MaxSameTagPerWindow {
				return "tag"
			}
		}
	}
	if cfg.MaxSameTopicPerWindow > 0 {
		for _, topic := range c.EntityRefs {
			if topic != "" && topicCount[topic] >= cfg.MaxSameTopicPerWindow {
				return "topic"
			}
		}
	}
	if cfg.NearDupJaccardMax > 0 {
		features := candidateFeatureSet(c)
		for _, existing := range selectedFeatures {
			if jaccardSimilarity(features, existing) >= cfg.NearDupJaccardMax {
				return "near_dup"
			}
		}
	}
	return ""
}

func observeFrequency(c ContentCandidate, authorCount map[string]int, tagCount map[string]int, topicCount map[string]int) {
	if c.AuthorID != "" {
		authorCount[c.AuthorID]++
	}
	for _, tag := range c.Tags {
		if tag != "" {
			tagCount[tag]++
		}
	}
	for _, topic := range c.EntityRefs {
		if topic != "" {
			topicCount[topic]++
		}
	}
}

// rerankMMR implements Maximal Marginal Relevance reranking: it iteratively
// selects the candidate maximizing λ·relevance − (1−λ)·maxSimilarityToSelected,
// where similarity is the Jaccard overlap of {author, type, tags, entityRefs}.
// This actively balances relevance against novelty (a DPP/MMR-class diversity
// objective) instead of the greedy path's post-hoc dedup, and is activated only
// when policy scorer.diversityStrategy == "mmr". Author/type caps from policy are
// honored as hard constraints, with a fill fallback so the surface is never
// under-filled. Relevance is min-max normalized over the candidate set.
func (e *Engine) rerankMMR(scored []ScoredCandidate, limit int, scorer recpolicy.ScorerConfig) []ScoredCandidate {
	if len(scored) == 0 {
		return scored
	}
	if limit <= 0 || limit > len(scored) {
		limit = len(scored)
	}
	lambda := scorer.DiversityLambda
	if lambda <= 0 || lambda > 1 {
		lambda = 0.7
	}
	maxPerAuthor := scorer.MaxAuthorPerFeed
	maxPerType := (limit / 3) + 1

	minS, maxS := scored[0].Score, scored[0].Score
	for _, s := range scored {
		if s.Score < minS {
			minS = s.Score
		}
		if s.Score > maxS {
			maxS = s.Score
		}
	}
	span := maxS - minS
	rel := func(s ScoredCandidate) float64 {
		if span <= 0 {
			return 1
		}
		return (s.Score - minS) / span
	}

	feats := make([]map[string]struct{}, len(scored))
	for i, s := range scored {
		feats[i] = candidateFeatureSet(s.Candidate)
	}

	selected := make([]ScoredCandidate, 0, limit)
	selectedFeats := make([]map[string]struct{}, 0, limit)
	used := make([]bool, len(scored))
	typeCount := make(map[string]int)
	authorCount := make(map[string]int)

	for len(selected) < limit {
		bestIdx := -1
		bestMMR := math.Inf(-1)
		for i, s := range scored {
			if used[i] {
				continue
			}
			ct := s.Candidate.ContentType
			author := s.Candidate.AuthorID
			if maxPerType > 0 && typeCount[ct] >= maxPerType {
				continue
			}
			if author != "" && maxPerAuthor > 0 && authorCount[author] >= maxPerAuthor {
				continue
			}
			maxSim := 0.0
			for _, sf := range selectedFeats {
				if sim := jaccardSimilarity(feats[i], sf); sim > maxSim {
					maxSim = sim
				}
			}
			mmr := lambda*rel(s) - (1-lambda)*maxSim
			if mmr > bestMMR {
				bestMMR = mmr
				bestIdx = i
			}
		}
		if bestIdx < 0 {
			// All remaining candidates blocked by caps: relax to avoid under-fill,
			// taking the highest-relevance unused candidate.
			for i := range scored {
				if !used[i] {
					bestIdx = i
					break
				}
			}
		}
		if bestIdx < 0 {
			break
		}
		s := scored[bestIdx]
		used[bestIdx] = true
		selected = append(selected, s)
		selectedFeats = append(selectedFeats, feats[bestIdx])
		typeCount[s.Candidate.ContentType]++
		if s.Candidate.AuthorID != "" {
			authorCount[s.Candidate.AuthorID]++
		}
	}
	return selected
}

// candidateFeatureSet is the diversity signature of a candidate: author, content
// type, tags and entity refs. Two candidates sharing more of these are more
// similar (used by the MMR novelty term).
func candidateFeatureSet(c ContentCandidate) map[string]struct{} {
	set := make(map[string]struct{}, 2+len(c.Tags)+len(c.EntityRefs))
	if c.AuthorID != "" {
		set["author:"+c.AuthorID] = struct{}{}
	}
	if c.ContentType != "" {
		set["type:"+c.ContentType] = struct{}{}
	}
	for _, t := range c.Tags {
		if t != "" {
			set["tag:"+t] = struct{}{}
		}
	}
	for _, ref := range c.EntityRefs {
		if ref != "" {
			set["entity:"+ref] = struct{}{}
		}
	}
	return set
}

// jaccardSimilarity returns |A∩B| / |A∪B| ∈ [0,1].
func jaccardSimilarity(a, b map[string]struct{}) float64 {
	if len(a) == 0 || len(b) == 0 {
		return 0
	}
	small, large := a, b
	if len(b) < len(a) {
		small, large = b, a
	}
	inter := 0
	for k := range small {
		if _, ok := large[k]; ok {
			inter++
		}
	}
	union := len(a) + len(b) - inter
	if union == 0 {
		return 0
	}
	return float64(inter) / float64(union)
}

// computeTopicEntropy calculates Shannon entropy of topic tag distribution.
// Higher entropy = more diverse; lower = more concentrated (potential filter bubble).
func computeTopicEntropy(items []ScoredCandidate) float64 {
	topicCounts := make(map[string]int)
	total := 0
	for _, item := range items {
		for _, tag := range item.Candidate.Tags {
			if ClassifyTagDimension(tag) == DimensionTopic {
				topicCounts[tag]++
				total++
			}
		}
	}
	if total == 0 {
		return 0
	}
	entropy := 0.0
	for _, count := range topicCounts {
		p := float64(count) / float64(total)
		if p > 0 {
			entropy -= p * math.Log2(p)
		}
	}
	return entropy
}

func computeAuthorDiversity(items []ScoredCandidate) (repeatRate float64, hhi float64, distinctAuthors int) {
	authorCounts := make(map[string]int)
	total := 0
	for _, item := range items {
		author := strings.TrimSpace(item.Candidate.AuthorID)
		if author == "" {
			continue
		}
		authorCounts[author]++
		total++
	}
	if total == 0 {
		return 0, 0, 0
	}
	distinctAuthors = len(authorCounts)
	repeatRate = 1 - float64(distinctAuthors)/float64(total)
	for _, count := range authorCounts {
		p := float64(count) / float64(total)
		hhi += p * p
	}
	return repeatRate, hhi, distinctAuthors
}

func computeGeoCoverage(items []ScoredCandidate) (coverage float64, distinctGeoBuckets int) {
	geoCounts := make(map[string]int)
	total := 0
	for _, item := range items {
		bucket := primaryGeoBucket(item.Candidate.Tags)
		if bucket == "" {
			continue
		}
		geoCounts[bucket]++
		total++
	}
	if total == 0 {
		return 0, 0
	}
	distinctGeoBuckets = len(geoCounts)
	return float64(distinctGeoBuckets) / float64(len(items)), distinctGeoBuckets
}

func computeDistinctTopicCount(items []ScoredCandidate) int {
	topics := make(map[string]struct{})
	for _, item := range items {
		for _, tag := range item.Candidate.Tags {
			if ClassifyTagDimension(tag) == DimensionTopic {
				topics[tag] = struct{}{}
			}
		}
	}
	return len(topics)
}

func primaryGeoBucket(tags []string) string {
	for _, tag := range tags {
		if strings.HasPrefix(tag, "Topic/地理/行政区/") {
			parts := strings.Split(tag, "/")
			if len(parts) >= 5 {
				return parts[4]
			}
		}
	}
	return ""
}

func topNTags(weights map[string]float64, n int) []string {
	type tw struct {
		tag    string
		weight float64
	}
	var pairs []tw
	for t, w := range weights {
		if w > 0 {
			pairs = append(pairs, tw{t, w})
		}
	}
	sort.Slice(pairs, func(i, j int) bool { return pairs[i].weight > pairs[j].weight })

	result := make([]string, 0, n)
	for i, p := range pairs {
		if i >= n {
			break
		}
		result = append(result, p.tag)
	}
	return result
}

func toSet(ss []string) map[string]bool {
	m := make(map[string]bool, len(ss))
	for _, s := range ss {
		m[s] = true
	}
	return m
}

// recordShadowScores writes shadow (challenger) scores as learning events
// for offline champion-vs-challenger comparison.
func (e *Engine) recordShadowScores(ctx context.Context, userID, sessionID string, scored []ScoredCandidate) {
	if e.feedback == nil || e.feedback.recorder == nil {
		return
	}
	for _, s := range scored {
		_ = e.feedback.recorder.RecordEvent(ctx, learning.Event{
			EventID:    fmt.Sprintf("rec_shadow_%s_%s_%d", userID, s.Candidate.ContentID, time.Now().UnixNano()),
			EventType:  "rec_shadow",
			Scenario:   "content_feed",
			OccurredAt: time.Now().UTC().Format(time.RFC3339),
			UserID:     userID,
			TargetID:   s.Candidate.ContentID,
			Labels: map[string]string{
				"sessionId":    sessionID,
				"modelVersion": "challenger",
			},
			Context: map[string]any{
				"shadowScore": s.Score,
				"detail":      s.Detail,
			},
		})
	}
}

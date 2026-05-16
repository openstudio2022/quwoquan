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

	experiments "quwoquan_service/runtime/experiments"
	learning "quwoquan_service/runtime/learning"
)

// FeedType identifies the kind of recommendation feed.
type FeedType string

const (
	FeedDiscovery FeedType = "discovery"
	FeedCircle    FeedType = "circle"
	FeedFollow    FeedType = "follow"
	FeedSimilar   FeedType = "similar"
)

const (
	FeedSortRecommend = "recommend"
	defaultCursorTTL  = 10 * time.Minute
)

// GetFeedRequest defines input for feed generation.
type GetFeedRequest struct {
	UserID    string
	SessionID string
	FeedType  FeedType
	Sort      string
	CircleID  string
	Cursor    string
	Limit     int
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
	FeedType FeedType
	UserID   string
	CircleID string
	Tags     []string
	Limit    int
	Cursor   string
}

// ScoringWeights controls the relative importance of each scoring dimension.
// Tunable via runtime/experiments AB framework.
type ScoringWeights struct {
	TagRelevance    float64
	AuthorAffinity  float64
	Popularity      float64
	Freshness       float64
	SocialPrior     float64
	ExploreBoost    float64
	NegativePenalty float64
	DwellBonus      float64
	EntityAffinity  float64
	TopicMatch      float64
	AudienceMatch   float64
	FormatMatch     float64
}

// DefaultWeights returns production-default scoring weights.
func DefaultWeights() ScoringWeights {
	return ScoringWeights{
		TagRelevance:    3.0,
		AuthorAffinity:  1.5,
		Popularity:      2.0,
		Freshness:       1.5,
		SocialPrior:     1.0,
		ExploreBoost:    0.5,
		NegativePenalty: 5.0,
		DwellBonus:      0.8,
		EntityAffinity:  1.2,
		TopicMatch:      1.0,
		AudienceMatch:   0.8,
		FormatMatch:     0.6,
	}
}

// Engine orchestrates the full recommendation pipeline:
//
//	Recall → PreRank → Filter → FeatureAssembly → ModelScore → Rerank
//
// Each stage is pluggable via interfaces, with sensible defaults.
type Engine struct {
	sessions SessionReader
	sources  []CandidateSource
	weights  ScoringWeights

	scorer    ModelScorer
	features  FeatureProvider
	preRanker PreRanker

	exploreFraction  float64
	maxAuthorPerFeed int
	recallTimeout    time.Duration
	featureTimeout   time.Duration

	socialMiner *SocialInterestMiner

	expResolver experiments.Resolver
	logger      *slog.Logger
	feedback    *FeedbackRecorder
}

// EngineOption configures the Engine.
type EngineOption func(*Engine)

func WithWeights(w ScoringWeights) EngineOption {
	return func(e *Engine) { e.weights = w }
}

func WithExploreFraction(f float64) EngineOption {
	return func(e *Engine) { e.exploreFraction = f }
}

func WithMaxAuthorPerFeed(n int) EngineOption {
	return func(e *Engine) { e.maxAuthorPerFeed = n }
}

func WithExperimentResolver(r experiments.Resolver) EngineOption {
	return func(e *Engine) { e.expResolver = r }
}

func WithLogger(l *slog.Logger) EngineOption {
	return func(e *Engine) { e.logger = l }
}

func WithFeedbackRecorder(f *FeedbackRecorder) EngineOption {
	return func(e *Engine) { e.feedback = f }
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
		sessions:         sessions,
		sources:          sources,
		weights:          DefaultWeights(),
		scorer:           &RuleScorer{},
		features:         &NullFeatureProvider{},
		preRanker:        &NullPreRanker{},
		exploreFraction:  0.1,
		maxAuthorPerFeed: 3,
		recallTimeout:    150 * time.Millisecond,
		featureTimeout:   50 * time.Millisecond,
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

	weights := e.weights
	modelBucket := "rule"
	modelVersion := "champion"
	if e.expResolver != nil {
		weights = ResolveWeights(ctx, e.expResolver, req.UserID)
		modelBucket = ResolveModelBucket(ctx, e.expResolver, req.UserID)
		modelVersion = ResolveModelVersion(ctx, e.expResolver, req.UserID)
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

	// Stage 4: Filter exposed + negative + dedup
	exposedSet := toSet(session.ExposedIDs)
	negativeSet := toSet(session.NegativeIDs)
	filteredBuf := acquireCandidates()
	seen := make(map[string]bool, len(preranked))
	for _, c := range preranked {
		if exposedSet[c.ContentID] || negativeSet[c.ContentID] || seen[c.ContentID] {
			continue
		}
		seen[c.ContentID] = true
		*filteredBuf = append(*filteredBuf, c)
	}
	filtered := *filteredBuf

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

	scoringFeatures := &ScoringFeatures{
		Session:       session,
		User:          userFeatures,
		Weights:       weights,
		ExploreRate:   e.exploreFraction,
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

	// Stage 7: Rerank (diversity + author dedup)
	rerankStart := time.Now()
	reranked := e.rerank(scored, windowLimit)
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
			ExperimentBucket:   modelBucket,
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
		FeedType: req.FeedType,
		UserID:   req.UserID,
		CircleID: req.CircleID,
		Tags:     interestTags,
		Limit:    req.Limit * 3,
		Cursor:   req.Cursor,
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
func (e *Engine) rerank(scored []ScoredCandidate, limit int) []ScoredCandidate {
	if len(scored) == 0 {
		return scored
	}
	if limit <= 0 || limit > len(scored) {
		limit = len(scored)
	}

	typeCount := make(map[string]int)
	authorCount := make(map[string]int)
	maxPerType := (limit / 3) + 1
	maxPerAuthor := e.maxAuthorPerFeed
	if maxPerAuthor <= 0 {
		maxPerAuthor = 3
	}

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
		if ageHours < 24 && s.Candidate.ViewCount < 100 {
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
	exploreTarget := int(float64(limit) * e.exploreFraction)
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

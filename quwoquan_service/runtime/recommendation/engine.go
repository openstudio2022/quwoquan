package recommendation

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"log/slog"
	"sort"
	"strings"
	"sync"
	"time"

	experiments "quwoquan_service/runtime/experiments"
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
	if e.expResolver != nil {
		weights = ResolveWeights(ctx, e.expResolver, req.UserID)
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

	scoringFeatures := &ScoringFeatures{
		Session:      session,
		User:         userFeatures,
		Weights:      weights,
		ExploreRate:  e.exploreFraction,
		Deterministic: req.Sort == FeedSortRecommend, // stable ordering for recommend + cursor pagination (no random explore boost)
	}

	// Stage 6: Model scoring (RuleScorer, RemoteModelScorer, or CascadeScorer)
	scoreStart := time.Now()
	scored, scoreErr := e.scorer.ScoreBatch(ctx, scoringFeatures, filtered)
	if scoreErr != nil {
		if e.logger != nil {
			e.logger.Error("rec.score.error", slog.String("err", scoreErr.Error()))
		}
		scored = make([]ScoredCandidate, 0)
	}
	scoreLatency := time.Since(scoreStart)

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
			UserID:          req.UserID,
			SessionID:       req.SessionID,
			RecallLatency:   recallLatency,
			ScoreLatency:    scoreLatency,
			RerankLatency:   rerankLatency,
			TotalLatency:    totalLatency,
			CandidateCount:  len(allCandidates),
			FilteredCount:   len(filtered),
			ResultCount:     len(items),
			SourceBreakdown: sourceBreakdown,
		})
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
	exploreTarget := limit / 5
	if exploreTarget < 1 && len(exploreBuffer) > 0 {
		exploreTarget = 1
	}

	// Cold-start guarantee: new content (<24h) at least 10% of results
	coldStartTarget := limit / 10
	if coldStartTarget < 1 && len(coldStartBuffer) > 0 {
		coldStartTarget = 1
	}

	// Inject explore items at even intervals
	final := make([]ScoredCandidate, 0, limit)
	exploreIdx := 0
	coldIdx := 0
	resultIdx := 0
	for i := 0; i < limit; i++ {
		if (i+1)%5 == 0 && exploreIdx < len(exploreBuffer) && exploreIdx < exploreTarget {
			final = append(final, exploreBuffer[exploreIdx])
			exploreIdx++
		} else if (i+1)%10 == 0 && coldIdx < len(coldStartBuffer) && coldIdx < coldStartTarget {
			final = append(final, coldStartBuffer[coldIdx])
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

	// Fill remaining slots from any source
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
			author := s.Candidate.AuthorID
			if author != "" && authorCount[author] >= maxPerAuthor {
				continue
			}
			final = append(final, s)
			if author != "" {
				authorCount[author]++
			}
		}
	}

	return final
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

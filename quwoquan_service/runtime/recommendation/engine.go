package recommendation

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log/slog"
	"sort"
	"strings"
	"sync"
	"time"

	"quwoquan_service/runtime/id"
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

	// RankingVersion 标识当前精排/打分管线版本，随 feed envelope 下发，
	// 供观测与 AB 把命中归因到具体排序修订（对齐 search-service 的 RankingVersion 约定）。
	RankingVersion = "rec-v1"
	// ReasonVersion 标识交集理由生成管线版本，随 feed envelope 下发。
	ReasonVersion = "reason-v1"
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
	ChannelID     string
	Vertical      string
	FeedRequestID string
	Cursor        string
	Limit         int
	// DeferDeliveryAccounting（N3-3 served 口径）：调用方在装配层还会过滤候选
	// （hydration 失败/不可见跳过）时置 true——engine 跳过 served/learning
	// impression 记账，由调用方按最终下发集调用 RecordDelivery。否则被丢弃的
	// 候选会被曝光过滤拉黑（用户从未见过）并污染训练样本分母。
	DeferDeliveryAccounting bool
}

// DeliveryAttribution 是延迟记账所需的本次评分归因（RecordDelivery 消费）。
type DeliveryAttribution struct {
	FeedRequestID  string
	ChannelID      string
	ModelBucket    string
	ModelVersion   string
	ModelReleaseID string
	ScoringBucket  string
}

// NewFeedRequestID 生成服务端权威 feedRequestId（frq_ 前缀 ULID）。
// 这是 feedRequestId 生成的唯一入口，engine 与 content-service feed 应用层共用。
func NewFeedRequestID() string {
	return id.MustGenerate(id.PrefixFeedRequest)
}

// FeedResponse holds the recommendation result.
type FeedResponse struct {
	Items      []FeedItem `json:"items"`
	NextCursor string     `json:"nextCursor,omitempty"`
	// FeedRequestID 为服务端权威生成的归因 id（frq_ 前缀 ULID）。
	// 首刷由 engine 生成；分页时回显请求携带的同一 id 以保持归因连续。
	FeedRequestID string `json:"feedRequestId,omitempty"`
	// RankingVersion / ReasonVersion 为本次结果的排序与理由管线版本，随 envelope 下发。
	RankingVersion string `json:"rankingVersion,omitempty"`
	ReasonVersion  string `json:"reasonVersion,omitempty"`
	// Attribution 仅在 DeferDeliveryAccounting 模式下回传（RecordDelivery 输入）。
	Attribution DeliveryAttribution `json:"-"`
}

// FeedItem represents a single item in the feed.
type FeedItem struct {
	ContentID       string   `json:"contentId"`
	ContentType     string   `json:"contentType"`
	AuthorID        string   `json:"authorId"`
	Title           string   `json:"title,omitempty"`
	Tags            []string `json:"tags,omitempty"`
	Score           float64  `json:"score"`
	RecallPath      string   `json:"recallPath,omitempty"`
	QualityScore    float64  `json:"qualityScore,omitempty"`
	ContentVertical string   `json:"contentVertical,omitempty"`
	SupplySource    string   `json:"supplySource,omitempty"`
	// trainingFeatures 只在进程内随最终下发集流转，不进入客户端 wire。
	// FeedbackRecorder 将其写入不可变曝光事实，训练不得再回查当前可变宽表。
	trainingFeatures *trainingFeatureSnapshot
}

type feedCursorState struct {
	Version   int    `json:"v"`
	SessionID string `json:"sid"`
	Offset    int    `json:"off"`
	ExpiresAt int64  `json:"exp"`
}

// ContentCandidate is a candidate from the recall layer.
type ContentCandidate struct {
	ContentID                   string
	ContentType                 string
	AuthorID                    string
	Title                       string
	Tags                        []string
	EntityRefs                  []string
	PublishedAt                 time.Time
	ViewCount                   int64
	LikeCount                   int64
	CommentCount                int64
	ShareCount                  int64
	RecallPath                  string
	QualityScore                float64
	ContentVertical             string
	SupplySource                string
	IntersectionFactStrength    float64
	IntersectionFreshness       float64
	AffinityIntersectionScore   float64
	IntersectionSourceRefTop    string
	IntersectionConfidenceLabel string
	IntersectionClass           string
}

// CandidateSource provides content candidates for recall.
type CandidateSource interface {
	Recall(ctx context.Context, req RecallRequest) ([]ContentCandidate, error)
}

type RecallRequest struct {
	FeedType       FeedType
	UserID         string
	CircleID       string
	TopicID        string
	HomepageID     string
	Surface        string
	Vertical       string
	FeedRequestID  string
	SeedContentIDs []string
	Tags           []string
	Limit          int
	Cursor         string
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

// NegativeFeedbackReader exposes a user's full explicit-negative content set so
// feed paths that bypass recall (repository fallback) can honor it. *HotPath
// implements this; session readers that do not track negatives simply return
// nothing and the engine recall filter remains the primary enforcement point.
type NegativeFeedbackReader interface {
	NegativeContentIDs(ctx context.Context, userID string) ([]string, error)
}

// FeedbackExclusions is the strong negative-feedback set every feed path must
// honor regardless of recall vs fallback: explicitly disliked/hidden content,
// hidden authors and hidden content types. Repeat-exposure governance
// (served/impressed) stays inside the recall pipeline and is deliberately not
// part of this product-level hard rule.
type FeedbackExclusions struct {
	NegativeContentIDs map[string]bool
	HiddenAuthors      map[string]bool
	HiddenContentTypes map[string]bool
}

// LoadFeedbackExclusions resolves the strong negative-feedback exclusions for a
// user from the same source of truth the recall filter uses (session hidden
// sets + negative content set), so engine and fallback feed paths converge on
// one truth instead of diverging per path.
func (e *Engine) LoadFeedbackExclusions(ctx context.Context, userID, sessionID string) FeedbackExclusions {
	excl := FeedbackExclusions{
		NegativeContentIDs: map[string]bool{},
		HiddenAuthors:      map[string]bool{},
		HiddenContentTypes: map[string]bool{},
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return excl
	}
	if session, err := e.sessions.GetSessionState(ctx, userID, sessionID); err == nil && session != nil {
		excl.HiddenAuthors = toSet(session.HiddenAuthorIDs)
		excl.HiddenContentTypes = toSet(session.HiddenContentTypes)
	}
	if reader, ok := e.sessions.(NegativeFeedbackReader); ok {
		if ids, err := reader.NegativeContentIDs(ctx, userID); err == nil {
			excl.NegativeContentIDs = toSet(ids)
		}
	}
	return excl
}

// GetFeed generates a personalized feed.
// Pipeline: Session → Recall → PreRank → Filter → Features → Score → Rerank
func (e *Engine) GetFeed(ctx context.Context, req GetFeedRequest) (*FeedResponse, error) {
	pipelineStart := time.Now()

	if req.Limit <= 0 {
		req.Limit = 20
	}
	req.Sort = normalizeSort(req.Sort)

	// feedRequestId 服务端权威化：首刷无 id 时由 engine 生成 frq_ ULID；
	// 分页/继续加载时客户端回显原 id，这里直接复用以保持同一 feed 会话归因连续。
	req.FeedRequestID = strings.TrimSpace(req.FeedRequestID)
	if req.FeedRequestID == "" {
		req.FeedRequestID = NewFeedRequestID()
	}

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
		// Redis 会话读失败 fail-open 为空会话（个性化降级为冷启动路径），
		// 降级必须可观测（N1-2）。
		RecordRedisDegraded("session_state")
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
	// Stage 2.5: Recall fusion source quota (W9/B10 轻量融合)：按 policy 源配额
	// 截断单源候选占比，防单源霸屏；boost 在打分后应用（applyRecallSourceBoost）。
	allCandidates = applySourceQuota(allCandidates, e.policyStore.Current().RecallFusion, req.Limit*3)
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
			// 曝光过滤 Redis 失败 fail-open（不过滤继续下发）——重复曝光风险
			// 上升，降级必须可观测（N1-2）。
			RecordRedisDegraded("exposure_filter")
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
		Session:           session,
		User:              userFeatures,
		Weights:           resolved.Weights,
		FeatureSnapshotAt: time.Now().UTC(),
		Scorer:            resolved.Scorer,
		ExploreRate:       resolved.Scorer.ExploreFraction,
		Deterministic:     req.Sort == FeedSortRecommend, // stable ordering for recommend + cursor pagination (no random explore boost)
	}

	// Stage 6: Model scoring (RuleScorer, RemoteModelScorer, or CascadeScorer)
	// model_vs_rule experiment: "model" uses primary scorer; "rule" uses fallback.
	// model_version experiment: when "challenger", ask model service for canary version.
	scoreStart := time.Now()
	activeScorer := e.scorer
	// actualScorerPath 是真实使用的打分路径（区别于实验分桶）：
	// "rule"=分桶主动规则分；"model"=模型分成功；"rule_fallback"=模型故障降级。
	// model_fallback_rate 只统计 rule_fallback（此前误用分桶名导致降级不可测）。
	actualScorerPath := modelBucket
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
	var scored []ScoredCandidate
	var scoreErr error
	if cascade, ok := activeScorer.(*CascadeScorer); ok {
		var usedFallback bool
		scored, usedFallback, scoreErr = cascade.ScoreBatchWithPath(ctx, scoringFeatures, filtered)
		if usedFallback {
			actualScorerPath = "rule_fallback"
		}
	} else {
		scored, scoreErr = activeScorer.ScoreBatch(ctx, scoringFeatures, filtered)
	}
	if scoreErr != nil {
		if e.logger != nil {
			e.logger.Error("rec.score.error", slog.String("err", scoreErr.Error()))
		}
		scored = make([]ScoredCandidate, 0)
	}
	modelReleaseID := ""
	if actualScorerPath == "model" {
		for _, candidate := range scored {
			if candidate.ModelReleaseID != "" {
				modelReleaseID = candidate.ModelReleaseID
				break
			}
		}
	}
	scoreLatency := time.Since(scoreStart)

	// Shadow scoring（W9 S0 shadow-only 常开）：主打 rule 时异步请求 champion
	// 模型分留档（积累训练样本与 replay 对比证据，LTR 爬坡的 S1 触发依据）；
	// 主打 model champion 时 shadow challenger（canary 对比，原语义保留）。
	// 全部异步 + 500ms 超时，不影响线上排序延迟。
	if e.feedback != nil {
		if cascade, ok := e.scorer.(*CascadeScorer); ok {
			if remote, ok := cascade.Primary.(*RemoteModelScorer); ok {
				var shadowScorer ModelScorer
				switch {
				case modelBucket == "rule":
					shadowScorer = remote
				case modelVersion == "champion":
					shadowScorer = remote.WithModelVersion("challenger")
				}
				if shadowScorer != nil {
					RecordShadowScore("attempted")
					go func() {
						shadowCtx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
						defer cancel()
						shadowScored, err := shadowScorer.ScoreBatch(shadowCtx, scoringFeatures, filtered)
						if err != nil {
							RecordShadowScore("failed")
							if e.logger != nil {
								e.logger.Debug("rec.shadow.error", slog.String("err", err.Error()))
							}
							return
						}
						RecordShadowScore("succeeded")
						e.recordShadowScores(shadowCtx, req.UserID, req.SessionID, shadowScored)
					}()
				}
			}
		}
	}

	// Recall fusion source boost (W9)：policy 源间校准乘数（默认 1.0 中性）。
	applyRecallSourceBoost(scored, policy.RecallFusion)

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

	// Stage 6.5: Operational interventions (pin/demote/block). Config truth source
	// is the hot-reloadable policy; empty/disabled is a zero-cost no-op. Applied
	// before rerank so pins lead and demoted/blocked items respect diversity caps.
	scored = applyOpsInterventions(scored, policy.OpsIntervention, string(req.FeedType), pipelineStart)

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
		trainingFeatures := newTrainingFeatureSnapshot(
			userFeatures,
			candidateInputAt(s.Candidate, scoringFeatures.FeatureSnapshotAt),
			scoringFeatures.FeatureSnapshotAt,
		)
		allItems = append(allItems, FeedItem{
			ContentID:        s.Candidate.ContentID,
			ContentType:      s.Candidate.ContentType,
			AuthorID:         s.Candidate.AuthorID,
			Title:            s.Candidate.Title,
			Tags:             s.Candidate.Tags,
			Score:            s.Score,
			RecallPath:       s.Candidate.RecallPath,
			QualityScore:     s.Candidate.QualityScore,
			ContentVertical:  s.Candidate.ContentVertical,
			SupplySource:     s.Candidate.SupplySource,
			trainingFeatures: trainingFeatures,
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
		Items:          items,
		NextCursor:     nextCursor,
		FeedRequestID:  req.FeedRequestID,
		RankingVersion: RankingVersion,
		ReasonVersion:  ReasonVersion,
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
			ModelUsed:          actualScorerPath,
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

	RecordPipelineResult(actualScorerPath, len(items) == 0)

	attribution := DeliveryAttribution{
		FeedRequestID:  req.FeedRequestID,
		ChannelID:      req.ChannelID,
		ModelBucket:    modelBucket,
		ModelReleaseID: modelReleaseID,
		ScoringBucket:  scoringBucket,
	}
	if modelBucket == "model" {
		attribution.ModelVersion = modelVersion
	}
	if req.DeferDeliveryAccounting {
		// N3-3 served 口径：装配层还会过滤候选，记账推迟到最终下发集
		// （调用方 RecordDelivery）。归因随响应回传。
		resp.Attribution = attribution
		return resp, nil
	}
	e.RecordDelivery(ctx, req.UserID, req.SessionID, attribution, items)

	return resp, nil
}

// RecordDelivery 按最终下发集记账（N3-3 served 口径）：learning impression
// 训练事实 + served 曝光记忆 + served 指标。items 必须是真实进入响应的内容
// （装配层 hydration 失败被丢弃的候选不得计入，否则曝光过滤拉黑未曾展示的
// 内容、训练样本分母被污染）。
func (e *Engine) RecordDelivery(
	ctx context.Context,
	userID, sessionID string,
	attribution DeliveryAttribution,
	items []FeedItem,
) {
	if len(items) == 0 {
		return
	}
	if e.feedback != nil {
		feedbackItems := make([]FeedItem, len(items))
		copy(feedbackItems, items)
		impressionAttribution := ImpressionAttribution{
			FeedRequestID:  attribution.FeedRequestID,
			ModelBucket:    attribution.ModelBucket,
			ModelVersion:   attribution.ModelVersion,
			ModelReleaseID: attribution.ModelReleaseID,
		}
		// 训练事实必须在响应返回前进入进程内可靠缓冲；不能把 enqueue 本身
		// fire-and-forget，否则优雅关闭时 Stop 可能先于 goroutine，整批曝光丢失。
		// BufferedRecorder 的实际 Mongo flush 仍异步批处理，不把存储 RTT 放进 feed P95。
		if err := e.feedback.RecordImpression(
			ctx,
			userID,
			sessionID,
			impressionAttribution,
			feedbackItems,
		); err != nil && e.logger != nil {
			e.logger.Warn(
				"rec.impression.write_failed",
				slog.String("feedRequestId", attribution.FeedRequestID),
				slog.String("error", err.Error()),
			)
		}
	}
	if e.exposureMemory != nil && userID != "" {
		servedItems := make([]FeedItem, len(items))
		copy(servedItems, items)
		RecordServedItems(len(servedItems))
		RecordServedItemsByAttribution(servedItems, attribution.ChannelID, RankingVersion, ReasonVersion, attribution.ScoringBucket)
		go func() {
			servedCtx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
			defer cancel()
			if err := e.exposureMemory.RecordServed(servedCtx, userID, servedItems, time.Now().UTC()); err != nil && e.logger != nil {
				e.logger.Warn("rec.exposure.served_write_failed", slog.String("err", err.Error()))
			}
		}()
	}
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
		FeedType:       req.FeedType,
		UserID:         req.UserID,
		CircleID:       req.CircleID,
		TopicID:        req.TopicID,
		HomepageID:     req.HomepageID,
		Surface:        req.Surface,
		Vertical:       req.Vertical,
		FeedRequestID:  req.FeedRequestID,
		SeedContentIDs: recentSeedContentIDs(session.ExposedIDs, 20),
		Tags:           interestTags,
		Limit:          req.Limit * 3,
		Cursor:         req.Cursor,
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
				RecordRecallSourceFailure(recallSourceLabel(src))
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
				RecordRecallSourceFailure(recallSourceLabel(s))
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

// recallSourceLabel 从源类型派生低基数指标标签（去包路径与指针前缀）。
func recallSourceLabel(src CandidateSource) string {
	if src == nil {
		return "unknown"
	}
	name := fmt.Sprintf("%T", src)
	name = strings.TrimPrefix(name, "*")
	if idx := strings.LastIndex(name, "."); idx >= 0 {
		name = name[idx+1:]
	}
	return name
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

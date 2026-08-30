package recommendation

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sort"
	"strings"
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

var (
	ErrInvalidFeedCursor                   = errors.New("invalid or expired recommendation feed cursor")
	ErrRecallSourceCandidateBudgetExceeded = errors.New("recall source candidate budget exceeded")
	ErrRecallSourceInflightBudgetExceeded  = errors.New("recall source inflight budget exceeded")
	ErrRecallGlobalInflightBudgetExceeded  = errors.New("recall global inflight budget exceeded")
	ErrRecallSourceCountBudgetExceeded     = errors.New("recall source count budget exceeded")
)

const (
	FeedSortRecommend = "recommend"
)

// GetFeedRequest defines input for feed generation.
type GetFeedRequest struct {
	UserID    string
	PersonaID string
	SessionID string
	// RankedWindowSubjectID is an internal, namespaced storage/quota subject
	// derived by the content owner. It is the canonical actor for named or
	// verified-device traffic and the session for identity-less public traffic.
	// It is never accepted from the public feed wire contract.
	RankedWindowSubjectID string
	FeedType              FeedType
	Sort                  string
	CircleID              string
	TopicID               string
	HomepageID            string
	Surface               string
	ChannelID             string
	Vertical              string
	FeedRequestID         string
	// ActiveReleaseID binds the request to the environment-scoped canonical
	// supply snapshot selected by content-service. Recall sources that consume
	// data-engineering projections must use this release identifier rather than
	// independently selecting an active release.
	ActiveReleaseID      string
	ActiveManifestDigest string
	// Continuation is decoded only by content-service's request-scoped AEAD
	// cursor. The engine never accepts an offset or a client-visible inner token.
	Continuation *RankedFeedContinuation
	Limit        int
	// FeedbackExclusions is the request-start snapshot of non-bypassable Redis
	// filters. content-service loads it fail-closed and reuses it across recall,
	// hydration and explicit PostReader paths.
	FeedbackExclusions *FeedbackExclusions
	// DeferDeliveryAccounting（N3-3 served 口径）：调用方在装配层还会过滤候选
	// （hydration 失败/不可见跳过）时置 true——engine 跳过 served/learning
	// impression 记账，由调用方按最终下发集调用 RecordDelivery。否则被丢弃的
	// 候选会被曝光过滤拉黑（用户从未见过）并污染训练样本分母。
	DeferDeliveryAccounting bool
}

// DeliveryAttribution 是延迟记账所需的本次评分归因（RecordDelivery 消费）。
type DeliveryAttribution struct {
	FeedRequestID  string
	PersonaID      string
	ChannelID      string
	ModelBucket    string
	ModelChannel   string
	ModelReleaseID string
	ScoringBucket  string
	PolicyDigest   string
}

// NewFeedRequestID 生成服务端权威 feedRequestId（frq_ 前缀 ULID）。
// 这是 feedRequestId 生成的唯一入口，engine 与 content-service feed 应用层共用。
func NewFeedRequestID() string {
	return id.MustGenerate(id.PrefixFeedRequest)
}

func (e *Engine) healthyEmptyFeedResponse(req GetFeedRequest, policyDigest string) *FeedResponse {
	policyDigest = strings.TrimSpace(policyDigest)
	if policyDigest == "" {
		policyDigest = e.policyStore.EffectiveHash()
	}
	RecordPipelineResult("rule", true)
	return &FeedResponse{
		Items:           []FeedItem{},
		FeedRequestID:   req.FeedRequestID,
		PolicyDigest:    policyDigest,
		TerminalOutcome: FeedTerminalEmpty,
		FailureStage:    FailureStageNone,
		Attribution: DeliveryAttribution{
			FeedRequestID: req.FeedRequestID,
			PersonaID:     req.PersonaID,
			ChannelID:     req.ChannelID,
			PolicyDigest:  policyDigest,
		},
	}
}

// FeedResponse holds the recommendation result.
type FeedResponse struct {
	Items []FeedItem `json:"items"`
	// NextContinuation is sealed by content-service's outer AEAD cursor. It is
	// never serialized directly and contains no recomputable offset.
	NextContinuation *RankedFeedContinuation `json:"-"`
	// FeedRequestID 为服务端权威生成的归因 id（frq_ 前缀 ULID）。
	// 首刷由 engine 生成；分页时回显请求携带的同一 id 以保持归因连续。
	FeedRequestID string `json:"feedRequestId,omitempty"`
	// PolicyDigest 是本次结果唯一的推荐策略身份，供行为与观测归因。
	PolicyDigest string `json:"policyDigest,omitempty"`
	// Attribution 仅在 DeferDeliveryAccounting 模式下回传（RecordDelivery 输入）。
	Attribution DeliveryAttribution `json:"-"`
	// TerminalOutcome / FailureStage 仅在服务内用于 feed 终态观测，不进入 wire。
	TerminalOutcome FeedTerminalOutcome `json:"-"`
	FailureStage    FailureStage        `json:"-"`
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
	SourceOwner     string   `json:"-"`
	ReleaseID       string   `json:"-"`
	ManifestDigest  string   `json:"-"`
	LifecycleStatus string   `json:"-"`
	// trainingFeatures 只在进程内随最终下发集流转，不进入客户端 wire。
	// FeedbackRecorder 将其写入不可变曝光事实，训练不得再回查当前可变宽表。
	trainingFeatures *trainingFeatureSnapshot
	// rank 是本次服务端重排后的全局一基序位，仅供不可变曝光事实使用。
	// 它不进入客户端 wire，不能由端侧行为 position 回写覆盖。
	rank int
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
	SourceOwner                 string
	ReleaseID                   string
	ManifestDigest              string
	LifecycleStatus             string
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
	FeedType             FeedType
	UserID               string
	CircleID             string
	TopicID              string
	HomepageID           string
	Surface              string
	Vertical             string
	FeedRequestID        string
	ActiveReleaseID      string
	ActiveManifestDigest string
	SeedContentIDs       []string
	Tags                 []string
	// Limit is the hard per-source admitted-output budget. A release-aware
	// source may place one active-release anchor in the immediately following,
	// equally bounded handoff window when its primary window contains no
	// canonical candidate. The engine never scans beyond 2*Limit; farther output
	// is rejected fail-closed.
	Limit int
}

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
	// recallSourceSlots bounds goroutines whose dependency ignores context.
	// Production binds its capacity to content-service's canonical feed
	// max_inflight; the runtime default is fail-closed at one per source.
	recallSourceMaxInflight        int
	recallSourceSlots              []chan struct{}
	recallGlobalMaxInflight        int
	recallGlobalSlots              chan struct{}
	recallSourceMaximumCount       int
	recallSourceConfigurationError error

	socialMiner *SocialInterestMiner

	// policyStore is the single source of scoring weights, secondary
	// coefficients, AB experiments, and segment targeting. Never nil; defaults
	// to the codegen baseline. Hot-reloadable via recpolicy.StartSyncLoop.
	policyStore *recpolicy.Store

	logger         *slog.Logger
	feedback       *FeedbackRecorder
	exposureFilter ExposureFilter
	exposureMemory ExposureMemory
	rankedWindows  RankedFeedWindowStore
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

// WithRecallSourceMaxInflight binds each recall source to the owning feed
// operation's canonical inflight budget. It prevents repeated timed-out calls
// from leaking an unbounded number of goroutines when a dependency violates the
// CandidateSource context contract.
func WithRecallSourceMaxInflight(limit int) EngineOption {
	return func(e *Engine) {
		if limit > 0 {
			e.recallSourceMaxInflight = limit
		}
	}
}

// WithRecallGlobalMaxInflight caps all unfinished recall dependency calls
// across sources and concurrent feed requests for this engine instance.
func WithRecallGlobalMaxInflight(limit int) EngineOption {
	return func(e *Engine) {
		if limit > 0 {
			e.recallGlobalMaxInflight = limit
		}
	}
}

// WithRecallSourceMaximumCount rejects an oversized production composition;
// sources are never silently truncated because ordering affects recall fusion.
func WithRecallSourceMaximumCount(limit int) EngineOption {
	return func(e *Engine) {
		if limit > 0 {
			e.recallSourceMaximumCount = limit
		}
	}
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

// WithRankedFeedWindowStore overrides provider discovery for focused tests or
// alternative recommendation Redis adapters. Production normally discovers
// the store from HotPath/SessionCache.
func WithRankedFeedWindowStore(store RankedFeedWindowStore) EngineOption {
	return func(e *Engine) { e.rankedWindows = store }
}

// NewEngine creates a recommendation engine.
// sessions accepts *HotPath, *SessionCache, or any SessionReader.
func NewEngine(sessions SessionReader, sources []CandidateSource, opts ...EngineOption) *Engine {
	e := &Engine{
		sessions:                 sessions,
		sources:                  sources,
		scorer:                   &RuleScorer{},
		features:                 &NullFeatureProvider{},
		preRanker:                &NullPreRanker{},
		policyStore:              recpolicy.NewStoreFromBaseline(),
		recallTimeout:            150 * time.Millisecond,
		featureTimeout:           50 * time.Millisecond,
		recallSourceMaxInflight:  1,
		recallGlobalMaxInflight:  12,
		recallSourceMaximumCount: 12,
	}
	if provider, ok := sessions.(RankedFeedWindowStoreProvider); ok {
		e.rankedWindows = provider.RankedFeedWindowStore()
	}
	for _, opt := range opts {
		opt(e)
	}
	if len(e.sources) > e.recallSourceMaximumCount {
		e.recallSourceConfigurationError = fmt.Errorf(
			"%w: actual=%d maximum=%d",
			ErrRecallSourceCountBudgetExceeded,
			len(e.sources),
			e.recallSourceMaximumCount,
		)
	}
	e.recallGlobalSlots = make(chan struct{}, e.recallGlobalMaxInflight)
	e.recallSourceSlots = make([]chan struct{}, len(e.sources))
	for index := range e.recallSourceSlots {
		e.recallSourceSlots[index] = make(chan struct{}, e.recallSourceMaxInflight)
	}
	return e
}

// FeedbackExclusions is the strong negative-feedback set every feed path must
// honor regardless of recall vs explicit PostReader query: disliked/hidden content,
// hidden authors and hidden content types. Repeat-exposure governance
// (served/impressed) stays inside the recall pipeline and is deliberately not
// part of this product-level hard rule.
type FeedbackExclusions struct {
	NegativeContentIDs map[string]bool
	HiddenAuthors      map[string]bool
	HiddenContentTypes map[string]bool
}

func emptyFeedbackExclusions() FeedbackExclusions {
	return FeedbackExclusions{
		NegativeContentIDs: map[string]bool{},
		HiddenAuthors:      map[string]bool{},
		HiddenContentTypes: map[string]bool{},
	}
}

// LoadFeedbackExclusions resolves the strong negative-feedback exclusions from
// the dedicated hard-fact reader. Errors are returned instead of becoming an
// empty set, so recall and explicit PostReader paths fail closed together.
func (e *Engine) LoadFeedbackExclusions(ctx context.Context, userID, _ string) (FeedbackExclusions, error) {
	excl := emptyFeedbackExclusions()
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return excl, nil
	}
	reader, ok := e.sessions.(HardExclusionReader)
	if !ok {
		return excl, fmt.Errorf("hard exclusion reader is unavailable")
	}
	loaded, err := reader.LoadHardExclusions(ctx, userID)
	if err != nil {
		return excl, err
	}
	if loaded.NegativeContentIDs == nil {
		loaded.NegativeContentIDs = map[string]bool{}
	}
	if loaded.HiddenAuthors == nil {
		loaded.HiddenAuthors = map[string]bool{}
	}
	if loaded.HiddenContentTypes == nil {
		loaded.HiddenContentTypes = map[string]bool{}
	}
	return loaded, nil
}

// GetFeed generates a personalized feed.
// Pipeline: Session → Recall → PreRank → Filter → Features → Score → Rerank
func (e *Engine) GetFeed(ctx context.Context, req GetFeedRequest) (*FeedResponse, error) {
	pipelineStart := time.Now()

	if req.Limit <= 0 {
		req.Limit = 20
	}
	req.Sort = normalizeSort(req.Sort)
	if req.Continuation != nil {
		return e.getRankedFeedWindowPage(ctx, req)
	}
	if e.recallSourceConfigurationError != nil {
		return nil, NewFeedFailure(
			FailureStageRecallAllFailed,
			e.recallSourceConfigurationError,
		)
	}
	initialRecommend := (req.FeedType == FeedDiscovery || req.FeedType == FeedSimilar) &&
		req.Sort == FeedSortRecommend
	terminalOutcome := FeedTerminalSuccess
	terminalStage := FailureStageNone

	// feedRequestId 服务端权威化：首刷无 id 时由 engine 生成 frq_ ULID；
	// 分页/继续加载时客户端回显原 id，这里直接复用以保持同一 feed 会话归因连续。
	req.FeedRequestID = strings.TrimSpace(req.FeedRequestID)
	if req.FeedRequestID == "" {
		req.FeedRequestID = NewFeedRequestID()
	}
	req.SessionID = strings.TrimSpace(req.SessionID)

	hardExclusions := req.FeedbackExclusions
	if hardExclusions == nil {
		loaded, hardErr := e.LoadFeedbackExclusions(ctx, req.UserID, req.SessionID)
		if hardErr != nil {
			return nil, NewFeedFailure(FailureStageHardExclusionStateUnavailable, hardErr)
		}
		hardExclusions = &loaded
	}

	// Stage 1: Load session state (from SessionCache or HotPath)
	session, err := e.sessions.GetSessionState(ctx, req.UserID, req.SessionID)
	if err != nil {
		// Redis 会话读失败 fail-open 为空会话（个性化降级为冷启动路径），
		// 降级必须可观测（N1-2）。
		RecordRedisDegraded("session_state")
		session = &SessionState{UserID: req.UserID, SessionID: req.SessionID}
		terminalOutcome = FeedTerminalDegraded
		terminalStage = FailureStagePersonalizationUnavailable
	}

	// Stage 2: Parallel recall from all sources
	recallStart := time.Now()
	recallBuf := acquireCandidates()
	defer releaseCandidates(recallBuf)
	recallStats := e.parallelRecallInto(ctx, req, session, recallBuf)
	allCandidates := *recallBuf
	allCandidates = bindCandidatesToActiveRelease(
		allCandidates,
		req.ActiveReleaseID,
		req.ActiveManifestDigest,
	)
	// Stable order for cursor pagination: same candidate set yields same order across requests.
	sort.Slice(allCandidates, func(i, j int) bool {
		return allCandidates[i].ContentID < allCandidates[j].ContentID
	})
	// applySourceQuota compacts its input slice in place. Preserve the complete,
	// release-bound recall set so an approved canonical release candidate cannot
	// be crowded out solely by source quota or pre-rank window truncation.
	releaseBoundRecall := append([]ContentCandidate(nil), allCandidates...)
	// Stage 2.5: Recall fusion source quota (source-quota 轻量融合)：按 policy 源配额
	// 截断单源候选占比，防单源霸屏；boost 在打分后应用（applyRecallSourceBoost）。
	rankedWindowLimit := rankedFeedWindowLimit(req.Limit)
	allCandidates = applySourceQuota(allCandidates, e.policyStore.Current().RecallFusion, rankedWindowLimit)
	allCandidates = retainActiveReleaseAnchor(
		allCandidates,
		releaseBoundRecall,
		req.ActiveReleaseID,
		req.ActiveManifestDigest,
		rankedWindowLimit,
	)
	recallLatency := time.Since(recallStart)
	if len(allCandidates) == 0 {
		switch {
		case recallStats.failed > 0 && recallStats.succeeded == 0:
			return nil, NewFeedFailure(
				FailureStageRecallAllFailed,
				fmt.Errorf("all %d applicable recall sources failed", recallStats.failed),
			)
		case recallStats.failed > 0:
			return nil, NewFeedFailure(
				FailureStageRecallPartialFailedEmpty,
				fmt.Errorf("%d recall sources failed and healthy sources returned no candidates", recallStats.failed),
			)
		case initialRecommend:
			return e.healthyEmptyFeedResponse(req, ""), nil
		}
	}
	if recallStats.failed > 0 && len(allCandidates) > 0 {
		terminalOutcome = FeedTerminalDegraded
		terminalStage = FailureStageRecallPartialFailed
	}

	// Stage 3: Pre-rank (lightweight filter before expensive scoring)
	windowLimit := rankedWindowLimit
	preranked := e.preRanker.PreRank(ctx, allCandidates, windowLimit)
	preranked = retainActiveReleaseAnchor(
		preranked,
		releaseBoundRecall,
		req.ActiveReleaseID,
		req.ActiveManifestDigest,
		windowLimit,
	)

	// Stage 4: Filter served + impressed + negative + dedup.
	// Long-window exposure memory is resolved by candidate membership point
	// lookups, not by loading per-user SMembers into SessionState.
	exposedSet := toSet(session.ExposedIDs)
	negativeSet := hardExclusions.NegativeContentIDs
	hiddenAuthors := hardExclusions.HiddenAuthors
	hiddenTypes := hardExclusions.HiddenContentTypes
	filteredBuf := acquireCandidates()
	defer releaseCandidates(filteredBuf)
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
	eligibleBeforeLongTermExposure := append([]ContentCandidate(nil), filtered...)
	if e.exposureFilter != nil {
		exposureFiltered, filterErr := e.exposureFilter.FilterCandidates(ctx, req.UserID, filtered, pipelineStart)
		if filterErr != nil {
			// 本请求已在上方应用 fail-closed 的 hardExclusions snapshot；
			// served/impressed 曝光记忆读取失败只允许放宽重复曝光，不能把
			// negative/hide 内容重新放回候选。
			RecordRedisDegraded("exposure_filter")
			terminalOutcome = FeedTerminalDegraded
			terminalStage = FailureStageExposureMemoryUnavailable
			if e.logger != nil {
				e.logger.Warn("rec.exposure_filter.error", slog.String("err", filterErr.Error()))
			}
		} else {
			filtered = exposureFiltered
			if initialRecommend &&
				len(filtered) == 0 &&
				len(eligibleBeforeLongTermExposure) > 0 {
				relaxedFilter, ok := e.exposureFilter.(RelaxedExposureFilter)
				if ok {
					relaxed, relaxedErr := relaxedFilter.FilterCandidatesRelaxedExposure(
						ctx,
						req.UserID,
						eligibleBeforeLongTermExposure,
						pipelineStart,
					)
					if relaxedErr != nil {
						RecordRedisDegraded("exposure_relaxed_filter")
						// eligibleBeforeLongTermExposure 已经应用本请求的硬排除快照；
						// relaxed Redis 读失败时可以恢复该集合并标记软降级。
						filtered = eligibleBeforeLongTermExposure
						terminalOutcome = FeedTerminalDegraded
						terminalStage = FailureStageExposureMemoryUnavailable
						if e.logger != nil {
							e.logger.Warn("rec.exposure_relaxed_filter.error", slog.String("err", relaxedErr.Error()))
						}
					} else if len(relaxed) > 0 {
						filtered = relaxed
						terminalOutcome = FeedTerminalDegraded
						terminalStage = FailureStageExposureExhausted
					}
				}
			}
		}
	}
	if initialRecommend && len(filtered) == 0 {
		return e.healthyEmptyFeedResponse(req, ""), nil
	}
	if initialRecommend && strings.TrimSpace(req.ActiveReleaseID) != "" &&
		!containsActiveReleaseCandidate(
			filtered,
			req.ActiveReleaseID,
			req.ActiveManifestDigest,
		) {
		return e.healthyEmptyFeedResponse(req, ""), nil
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
	modelChannel := policy.ResolveBucketOr(recpolicy.ExpModelChannel, req.UserID, userSegments, "champion")

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
	// model_channel experiment: when "challenger", ask model service for the canary channel.
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
	} else if modelChannel == "challenger" {
		if cascade, ok := e.scorer.(*CascadeScorer); ok {
			if remote, ok := cascade.Primary.(*RemoteModelScorer); ok {
				activeScorer = &CascadeScorer{
					Primary:  remote.WithModelChannel("challenger"),
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
		var fallbackStage FailureStage
		scored, usedFallback, fallbackStage, scoreErr = cascade.ScoreBatchWithFailureStage(
			ctx,
			scoringFeatures,
			filtered,
		)
		if usedFallback {
			actualScorerPath = "rule_fallback"
			if terminalOutcome == FeedTerminalSuccess {
				terminalOutcome = FeedTerminalDegraded
				terminalStage = fallbackStage
			}
		}
	} else {
		scored, scoreErr = activeScorer.ScoreBatch(ctx, scoringFeatures, filtered)
	}
	if scoreErr != nil {
		if e.logger != nil {
			e.logger.Error("rec.score.error", slog.String("err", scoreErr.Error()))
		}
		stage := FailureStageOf(scoreErr)
		if stage == FailureStageNone {
			stage = FailureStageScorerUnavailable
		}
		return nil, NewFeedFailure(stage, scoreErr)
	}
	if len(filtered) > 0 && len(scored) == 0 {
		return nil, NewFeedFailure(
			FailureStageScorerEmptyOutput,
			fmt.Errorf("scorer returned no output for %d candidates", len(filtered)),
		)
	}
	if initialRecommend && strings.TrimSpace(req.ActiveReleaseID) != "" &&
		!containsActiveReleaseScoredCandidate(
			scored,
			req.ActiveReleaseID,
			req.ActiveManifestDigest,
		) {
		return nil, NewFeedFailure(
			FailureStageScorerEmptyOutput,
			fmt.Errorf("scorer omitted the eligible active-release candidate"),
		)
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
				case modelChannel == "champion":
					shadowScorer = remote.WithModelChannel("challenger")
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

	// Stage 6.5: Operational interventions (pin/demote/block). Config truth source
	// is the hot-reloadable policy; empty/disabled is a zero-cost no-op. Applied
	// before rerank so pins lead and demoted/blocked items respect diversity caps.
	scored = applyOpsInterventions(scored, policy.OpsIntervention, string(req.FeedType), pipelineStart)
	if initialRecommend && strings.TrimSpace(req.ActiveReleaseID) != "" &&
		!containsActiveReleaseScoredCandidate(
			scored,
			req.ActiveReleaseID,
			req.ActiveManifestDigest,
		) {
		return e.healthyEmptyFeedResponse(req, resolved.PolicyDigest), nil
	}

	// Stage 7: Rerank (diversity + author dedup) — diversity/cold-start
	// thresholds come from the resolved policy, not hand-coded constants.
	rerankStart := time.Now()
	reranked := e.rerank(scored, windowLimit, resolved.Scorer)
	reranked = applyFrequencyAndNearDupCaps(reranked, windowLimit, policy.ExposureGovernance.FrequencyAndNearDup)
	reranked = applyDynamicExposureBudget(reranked, windowLimit, policy.ExposureGovernance.DynamicBudget, modelBucket)
	if initialRecommend && strings.TrimSpace(req.ActiveReleaseID) != "" {
		reranked = retainActiveReleaseScoredAnchor(
			reranked,
			scored,
			req.ActiveReleaseID,
			req.ActiveManifestDigest,
			req.Limit,
		)
		if !containsActiveReleaseScoredCandidate(
			reranked,
			req.ActiveReleaseID,
			req.ActiveManifestDigest,
		) {
			return e.healthyEmptyFeedResponse(req, resolved.PolicyDigest), nil
		}
	}
	rerankLatency := time.Since(rerankStart)

	topicEntropy := computeTopicEntropy(reranked)
	authorRepeatRate, authorHHI, distinctAuthors := computeAuthorDiversity(reranked)
	geoCoverage, distinctGeoBuckets := computeGeoCoverage(reranked)
	distinctTopics := computeDistinctTopicCount(reranked)

	allItems := make([]FeedItem, 0, len(reranked))
	for index, s := range reranked {
		trainingFeatures := newTrainingFeatureSnapshot(
			userFeatures,
			candidateInputAt(
				s.Candidate,
				scoringFeatures.FeatureSnapshotAt,
				userFeatures,
			),
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
			SourceOwner:      s.Candidate.SourceOwner,
			ReleaseID:        s.Candidate.ReleaseID,
			ManifestDigest:   s.Candidate.ManifestDigest,
			LifecycleStatus:  s.Candidate.LifecycleStatus,
			trainingFeatures: trainingFeatures,
			rank:             index + 1,
		})
	}
	if len(allItems) > RankedFeedWindowMaxItems {
		allItems = allItems[:RankedFeedWindowMaxItems]
	}

	end := req.Limit
	if end > len(allItems) {
		end = len(allItems)
	}
	items := allItems[:end]
	if initialRecommend && len(items) == 0 {
		return e.healthyEmptyFeedResponse(req, resolved.PolicyDigest), nil
	}
	if len(items) == 0 {
		terminalOutcome = FeedTerminalEmpty
		terminalStage = FailureStageNone
	}

	resp := &FeedResponse{
		Items:           items,
		FeedRequestID:   req.FeedRequestID,
		PolicyDigest:    resolved.PolicyDigest,
		TerminalOutcome: terminalOutcome,
		FailureStage:    terminalStage,
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
			PolicyDigest:       resolved.PolicyDigest,
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
		PersonaID:      req.PersonaID,
		ChannelID:      req.ChannelID,
		ModelBucket:    modelBucket,
		ModelReleaseID: modelReleaseID,
		ScoringBucket:  scoringBucket,
		PolicyDigest:   resolved.PolicyDigest,
	}
	if modelBucket == "model" {
		attribution.ModelChannel = modelChannel
	}
	if end < len(allItems) {
		windowItems := make([]rankedFeedWindowItem, 0, len(allItems))
		windowValid := true
		for index, item := range allItems {
			windowItem, windowErr := newRankedFeedWindowItem(item, index+1)
			if windowErr != nil {
				windowValid = false
				if e.logger != nil {
					e.logger.Error(
						"rec.ranked_window.snapshot_invalid",
						slog.String("feedRequestId", req.FeedRequestID),
						slog.String("error", windowErr.Error()),
					)
				}
				break
			}
			windowItems = append(windowItems, windowItem)
		}
		if windowValid && e.rankedWindows != nil {
			createdWindow, windowErr := e.rankedWindows.Create(ctx, rankedFeedWindow{
				Binding: rankedFeedBindingFromRequest(req),
				Provenance: rankedFeedWindowProvenance{
					CandidateWatermark: rankedFeedCandidateWatermark(allCandidates),
					PolicyDigest:       resolved.PolicyDigest,
					ModelReleaseID:     modelReleaseID,
					FeatureSnapshotAt:  scoringFeatures.FeatureSnapshotAt.UTC().Format(time.RFC3339Nano),
					ScorerPath:         actualScorerPath,
				},
				Items:           windowItems,
				Attribution:     attribution,
				TerminalOutcome: terminalOutcome,
				FailureStage:    terminalStage,
			})
			if windowErr == nil {
				resp.NextContinuation = &RankedFeedContinuation{
					WindowID:       createdWindow.WindowID,
					AfterOrdinal:   end,
					AfterContentID: allItems[end-1].ContentID,
					ExpiresAt:      createdWindow.ExpiresAt,
				}
			} else {
				windowValid = false
				if e.logger != nil {
					e.logger.Warn(
						"rec.ranked_window.create_failed",
						slog.String("feedRequestId", req.FeedRequestID),
						slog.String("error", windowErr.Error()),
					)
				}
			}
		} else if e.rankedWindows == nil {
			windowValid = false
		}
		if !windowValid {
			// The first page remains usable, but issuing a continuation would
			// invite live recomputation. Surface a degraded terminal and stop.
			RecordRedisDegraded("ranked_feed_window")
			terminalOutcome = FeedTerminalDegraded
			terminalStage = FailureStageRankedWindowUnavailable
			resp.NextContinuation = nil
			resp.TerminalOutcome = terminalOutcome
			resp.FailureStage = terminalStage
		}
	}
	if req.DeferDeliveryAccounting {
		// N3-3 served 口径：装配层还会过滤候选，记账推迟到最终下发集
		// （调用方 RecordDelivery）。归因随响应回传。
		resp.Attribution = attribution
		return resp, nil
	}
	if err := e.RecordDelivery(ctx, req.UserID, req.SessionID, attribution, items); err != nil {
		return nil, err
	}

	return resp, nil
}

func (e *Engine) getRankedFeedWindowPage(
	ctx context.Context,
	req GetFeedRequest,
) (*FeedResponse, error) {
	continuation := req.Continuation
	if continuation == nil ||
		strings.TrimSpace(req.FeedRequestID) == "" ||
		strings.TrimSpace(continuation.WindowID) == "" ||
		continuation.AfterOrdinal <= 0 ||
		strings.TrimSpace(continuation.AfterContentID) == "" ||
		continuation.ExpiresAt.IsZero() ||
		!continuation.ExpiresAt.After(time.Now().UTC()) {
		return nil, ErrInvalidFeedCursor
	}
	if e.rankedWindows == nil {
		return nil, NewFeedFailure(
			FailureStageRankedWindowUnavailable,
			fmt.Errorf("ranked feed window store is unavailable"),
		)
	}
	if strings.TrimSpace(req.RankedWindowSubjectID) == "" {
		return nil, ErrInvalidFeedCursor
	}
	window, err := e.rankedWindows.Load(
		ctx,
		req.RankedWindowSubjectID,
		continuation.WindowID,
	)
	if err != nil {
		if errors.Is(err, ErrRankedFeedWindowNotFound) ||
			errors.Is(err, ErrRankedFeedWindowBindingMismatch) ||
			errors.Is(err, ErrRankedFeedWindowAnchorMismatch) {
			return nil, ErrInvalidFeedCursor
		}
		return nil, NewFeedFailure(FailureStageRankedWindowUnavailable, err)
	}
	if !rankedFeedWindowMatchesRequest(window, req) ||
		window.ExpiresAt.UnixMilli() != continuation.ExpiresAt.UnixMilli() {
		return nil, ErrInvalidFeedCursor
	}
	anchorIndex := continuation.AfterOrdinal - 1
	if anchorIndex < 0 || anchorIndex >= len(window.Items)-1 ||
		window.Items[anchorIndex].Ordinal != continuation.AfterOrdinal ||
		window.Items[anchorIndex].Item.ContentID != strings.TrimSpace(continuation.AfterContentID) {
		return nil, ErrInvalidFeedCursor
	}
	start := continuation.AfterOrdinal
	end := start + req.Limit
	if end > len(window.Items) {
		end = len(window.Items)
	}
	items := make([]FeedItem, 0, end-start)
	for _, entry := range window.Items[start:end] {
		items = append(items, entry.feedItem())
	}
	response := &FeedResponse{
		Items:           items,
		FeedRequestID:   window.Binding.FeedRequestID,
		PolicyDigest:    window.Provenance.PolicyDigest,
		Attribution:     window.Attribution,
		TerminalOutcome: window.TerminalOutcome,
		FailureStage:    window.FailureStage,
	}
	if end < len(window.Items) {
		response.NextContinuation = &RankedFeedContinuation{
			WindowID:       window.WindowID,
			AfterOrdinal:   end,
			AfterContentID: window.Items[end-1].Item.ContentID,
			ExpiresAt:      window.ExpiresAt,
		}
	}
	if req.DeferDeliveryAccounting {
		return response, nil
	}
	if err := e.RecordDelivery(
		ctx,
		window.Binding.ActorID,
		window.Binding.SessionID,
		window.Attribution,
		items,
	); err != nil {
		return nil, err
	}
	return response, nil
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
) error {
	if len(items) == 0 {
		return nil
	}
	if e.feedback != nil {
		feedbackItems := make([]FeedItem, len(items))
		copy(feedbackItems, items)
		impressionAttribution := ImpressionAttribution{
			FeedRequestID:  attribution.FeedRequestID,
			PersonaID:      attribution.PersonaID,
			ModelBucket:    attribution.ModelBucket,
			ModelChannel:   attribution.ModelChannel,
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
		); err != nil {
			if e.logger != nil {
				e.logger.Warn(
					"rec.impression.write_failed",
					slog.String("feedRequestId", attribution.FeedRequestID),
					slog.String("error", err.Error()),
				)
			}
			return fmt.Errorf("record recommendation delivery impression: %w", err)
		}
	}
	if e.exposureMemory != nil && userID != "" {
		servedItems := make([]FeedItem, len(items))
		copy(servedItems, items)
		RecordServedItems(len(servedItems))
		RecordServedItemsByAttribution(servedItems, attribution.ChannelID, attribution.PolicyDigest, attribution.ScoringBucket)
		go func() {
			servedCtx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
			defer cancel()
			if err := e.exposureMemory.RecordServed(servedCtx, userID, servedItems, time.Now().UTC()); err != nil && e.logger != nil {
				e.logger.Warn("rec.exposure.served_write_failed", slog.String("err", err.Error()))
			}
		}()
	}
	return nil
}

func normalizeSort(raw string) string {
	switch strings.TrimSpace(strings.ToLower(raw)) {
	case "", FeedSortRecommend:
		return FeedSortRecommend
	default:
		return FeedSortRecommend
	}
}

func bindCandidatesToActiveRelease(
	candidates []ContentCandidate,
	activeReleaseID string,
	activeManifestDigest string,
) []ContentCandidate {
	activeReleaseID = strings.TrimSpace(activeReleaseID)
	activeManifestDigest = strings.TrimSpace(activeManifestDigest)
	if activeReleaseID == "" || len(candidates) == 0 {
		return candidates
	}
	filtered := make([]ContentCandidate, 0, len(candidates))
	removed := 0
	for _, candidate := range candidates {
		owner := strings.TrimSpace(candidate.SourceOwner)
		supplySource := strings.TrimSpace(strings.ToLower(candidate.SupplySource))
		isCanonicalData := owner == "qwq_data" || supplySource == "data_engineering"
		if isCanonicalData &&
			(strings.TrimSpace(candidate.ReleaseID) != activeReleaseID ||
				(activeManifestDigest != "" &&
					strings.TrimSpace(candidate.ManifestDigest) != activeManifestDigest) ||
				strings.TrimSpace(candidate.LifecycleStatus) != "active") {
			removed++
			continue
		}
		filtered = append(filtered, candidate)
	}
	RecordFeedGateFiltered("active_release", removed)
	return filtered
}

func isActiveReleaseCandidate(
	candidate ContentCandidate,
	activeReleaseID string,
	activeManifestDigest string,
) bool {
	activeReleaseID = strings.TrimSpace(activeReleaseID)
	activeManifestDigest = strings.TrimSpace(activeManifestDigest)
	if activeReleaseID == "" {
		return false
	}
	owner := strings.TrimSpace(candidate.SourceOwner)
	supplySource := strings.TrimSpace(strings.ToLower(candidate.SupplySource))
	return (owner == "qwq_data" || supplySource == "data_engineering") &&
		strings.TrimSpace(candidate.ReleaseID) == activeReleaseID &&
		(activeManifestDigest == "" ||
			strings.TrimSpace(candidate.ManifestDigest) == activeManifestDigest) &&
		strings.TrimSpace(candidate.LifecycleStatus) == "active"
}

func containsActiveReleaseCandidate(
	candidates []ContentCandidate,
	activeReleaseID string,
	activeManifestDigest string,
) bool {
	for _, candidate := range candidates {
		if isActiveReleaseCandidate(candidate, activeReleaseID, activeManifestDigest) {
			return true
		}
	}
	return false
}

func containsActiveReleaseScoredCandidate(
	candidates []ScoredCandidate,
	activeReleaseID string,
	activeManifestDigest string,
) bool {
	for _, candidate := range candidates {
		if isActiveReleaseCandidate(candidate.Candidate, activeReleaseID, activeManifestDigest) {
			return true
		}
	}
	return false
}

// retainActiveReleaseAnchor keeps one candidate from the currently active
// immutable release when a generic quota or pre-rank window would otherwise
// select only UGC/non-canonical candidates. It never resurrects stale release
// candidates: recalled has already passed bindCandidatesToActiveRelease.
func retainActiveReleaseAnchor(
	selected []ContentCandidate,
	recalled []ContentCandidate,
	activeReleaseID string,
	activeManifestDigest string,
	limit int,
) []ContentCandidate {
	activeReleaseID = strings.TrimSpace(activeReleaseID)
	if activeReleaseID == "" {
		return selected
	}
	for _, candidate := range selected {
		if isActiveReleaseCandidate(candidate, activeReleaseID, activeManifestDigest) {
			return selected
		}
	}

	var anchor ContentCandidate
	found := false
	for _, candidate := range recalled {
		if isActiveReleaseCandidate(candidate, activeReleaseID, activeManifestDigest) {
			anchor = candidate
			found = true
			break
		}
	}
	if !found {
		return selected
	}

	if limit <= 0 || len(selected) < limit {
		return append(selected, anchor)
	}
	if len(selected) == 0 {
		return []ContentCandidate{anchor}
	}
	out := append([]ContentCandidate(nil), selected...)
	out[len(out)-1] = anchor
	return out
}

// retainActiveReleaseScoredAnchor reserves one slot on the initial page for an
// active-release candidate that has already passed hard exclusions, exposure,
// scoring and operational policy. It does not revive candidates rejected by
// any of those gates; it only prevents generic diversity/budget truncation from
// crowding every canonical item out of the first page.
func retainActiveReleaseScoredAnchor(
	selected []ScoredCandidate,
	eligible []ScoredCandidate,
	activeReleaseID string,
	activeManifestDigest string,
	firstPageLimit int,
) []ScoredCandidate {
	if strings.TrimSpace(activeReleaseID) == "" || firstPageLimit <= 0 {
		return selected
	}
	pageEnd := firstPageLimit
	if pageEnd > len(selected) {
		pageEnd = len(selected)
	}
	if containsActiveReleaseScoredCandidate(
		selected[:pageEnd],
		activeReleaseID,
		activeManifestDigest,
	) {
		return selected
	}

	anchorIndex := -1
	for index, candidate := range selected {
		if isActiveReleaseCandidate(
			candidate.Candidate,
			activeReleaseID,
			activeManifestDigest,
		) {
			anchorIndex = index
			break
		}
	}
	if anchorIndex >= 0 {
		out := append([]ScoredCandidate(nil), selected...)
		target := pageEnd - 1
		anchor := out[anchorIndex]
		copy(out[target+1:anchorIndex+1], out[target:anchorIndex])
		out[target] = anchor
		return out
	}

	var anchor ScoredCandidate
	found := false
	for _, candidate := range eligible {
		if isActiveReleaseCandidate(
			candidate.Candidate,
			activeReleaseID,
			activeManifestDigest,
		) {
			anchor = candidate
			found = true
			break
		}
	}
	if !found {
		return selected
	}
	if len(selected) < firstPageLimit {
		return append(selected, anchor)
	}
	if pageEnd == 0 {
		return []ScoredCandidate{anchor}
	}
	out := append([]ScoredCandidate(nil), selected...)
	out[pageEnd-1] = anchor
	return out
}

type recallTerminalStats struct {
	succeeded int
	failed    int
	skipped   int
}

// parallelRecallInto fans out to all sources concurrently with per-source timeout.
// Skipped/not-applicable, succeeded-empty and failed are distinct terminal states;
// candidates returned alongside an error are retained as degraded partial recall.
func (e *Engine) parallelRecallInto(
	ctx context.Context,
	req GetFeedRequest,
	session *SessionState,
	out *[]ContentCandidate,
) recallTerminalStats {
	interestTags := topNTags(session.TagWeights, 10)
	recallReq := RecallRequest{
		FeedType:             req.FeedType,
		UserID:               req.UserID,
		CircleID:             req.CircleID,
		TopicID:              req.TopicID,
		HomepageID:           req.HomepageID,
		Surface:              req.Surface,
		Vertical:             req.Vertical,
		FeedRequestID:        req.FeedRequestID,
		ActiveReleaseID:      req.ActiveReleaseID,
		ActiveManifestDigest: req.ActiveManifestDigest,
		SeedContentIDs:       recentSeedContentIDs(session.ExposedIDs, 20),
		Tags:                 interestTags,
		Limit:                rankedFeedWindowLimit(req.Limit),
	}

	recallCtx := ctx
	if e.recallTimeout > 0 {
		var cancel context.CancelFunc
		recallCtx, cancel = context.WithTimeout(ctx, e.recallTimeout)
		defer cancel()
	}

	type result struct {
		index      int
		candidates []ContentCandidate
		err        error
	}
	results := make([]result, len(e.sources))
	completed := make([]bool, len(e.sources))
	resultCh := make(chan result, len(e.sources))
	for i, src := range e.sources {
		slot := e.recallSourceSlots[i]
		select {
		case slot <- struct{}{}:
		default:
			resultCh <- result{
				index: i,
				err: fmt.Errorf(
					"%w: source=%s maximum=%d",
					ErrRecallSourceInflightBudgetExceeded,
					recallSourceLabel(src),
					e.recallSourceMaxInflight,
				),
			}
			continue
		}
		select {
		case e.recallGlobalSlots <- struct{}{}:
		default:
			<-slot
			resultCh <- result{
				index: i,
				err: fmt.Errorf(
					"%w: maximum=%d",
					ErrRecallGlobalInflightBudgetExceeded,
					e.recallGlobalMaxInflight,
				),
			}
			continue
		}
		go func(idx int, s CandidateSource, sourceSlot chan struct{}) {
			released := false
			releaseSlots := func() {
				if released {
					return
				}
				<-sourceSlot
				<-e.recallGlobalSlots
				released = true
			}
			defer releaseSlots()
			if s == nil {
				releaseSlots()
				resultCh <- result{index: idx, err: SkipRecall("nil source")}
				return
			}
			candidates, err := s.Recall(recallCtx, recallReq)
			candidates, admissionErr := admitRecallSourceOutput(
				recallCtx,
				candidates,
				recallReq,
				recallSourceLabel(s),
			)
			err = errors.Join(err, admissionErr)
			releaseSlots()
			resultCh <- result{index: idx, candidates: candidates, err: err}
		}(i, src, slot)
	}

	// CandidateSource is required to honor recallCtx, but the orchestrator must
	// still reach a terminal state when a broken dependency ignores cancellation.
	// Each source sends at most one result into a fanout-sized buffer, so a late
	// return never blocks after this request has stopped collecting.
	remaining := len(e.sources)
	accept := func(r result) {
		if r.index < 0 || r.index >= len(results) || completed[r.index] {
			return
		}
		results[r.index] = r
		completed[r.index] = true
		remaining--
	}
	deadlineReached := false
	for remaining > 0 && !deadlineReached {
		select {
		case r := <-resultCh:
			accept(r)
		case <-recallCtx.Done():
			// Preserve results that completed before the deadline and are already
			// queued; never wait for a non-cooperative source after this drain.
			for {
				select {
				case r := <-resultCh:
					accept(r)
				default:
					deadlineReached = true
				}
				if deadlineReached {
					break
				}
			}
		}
	}
	if recallErr := recallCtx.Err(); recallErr != nil {
		for i := range results {
			if !completed[i] {
				results[i] = result{index: i, err: recallErr}
			}
		}
	}

	stats := recallTerminalStats{}
	for i, r := range results {
		*out = append(*out, r.candidates...)
		switch {
		case IsRecallSkipped(r.err) &&
			!errors.Is(r.err, ErrRecallSourceCandidateBudgetExceeded) &&
			!errors.Is(r.err, ErrRecallSourceInflightBudgetExceeded) &&
			!errors.Is(r.err, ErrRecallGlobalInflightBudgetExceeded):
			stats.skipped++
		case r.err != nil:
			stats.failed++
			RecordRecallSourceFailure(recallSourceLabel(e.sources[i]))
			if e.logger != nil {
				e.logger.Warn(
					"rec.recall.source_error",
					slog.String("source", recallSourceLabel(e.sources[i])),
					slog.String("err", r.err.Error()),
				)
			}
		default:
			stats.succeeded++
		}
	}
	return stats
}

// admitRecallSourceOutput enforces the CandidateSource output contract before
// candidates enter any sorting, quota or ranking work. Work and retained memory
// are bounded by the primary req.Limit window plus one equally bounded
// release-anchor handoff window. A source cannot force an unbounded scan by
// placing an anchor at an arbitrary position in an oversized slice.
func admitRecallSourceOutput(
	ctx context.Context,
	candidates []ContentCandidate,
	req RecallRequest,
	source string,
) ([]ContentCandidate, error) {
	maximum := req.Limit
	if maximum <= 0 {
		maximum = rankedFeedWindowLimit(20)
	}
	if len(candidates) <= maximum {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		return candidates, nil
	}

	budgetErr := fmt.Errorf(
		"%w: source=%s actual=%d maximum=%d",
		ErrRecallSourceCandidateBudgetExceeded,
		source,
		len(candidates),
		maximum,
	)
	if err := ctx.Err(); err != nil {
		return nil, errors.Join(budgetErr, err)
	}

	bounded := make([]ContentCandidate, maximum)
	for index := range bounded {
		if index%32 == 0 {
			if err := ctx.Err(); err != nil {
				return nil, errors.Join(budgetErr, err)
			}
		}
		bounded[index] = candidates[index]
	}

	// Source contract permits one equally sized handoff window for an anchor
	// crowded out of the primary source window. Never search candidates beyond
	// that second bounded window: arbitrary-position recovery would restore the
	// unbounded scan this admission boundary exists to prevent.
	if strings.TrimSpace(req.ActiveReleaseID) != "" &&
		!containsActiveReleaseCandidate(
			bounded,
			req.ActiveReleaseID,
			req.ActiveManifestDigest,
		) {
		if err := ctx.Err(); err != nil {
			return nil, errors.Join(budgetErr, err)
		}
		handoffEnd := maximum * 2
		if handoffEnd > len(candidates) {
			handoffEnd = len(candidates)
		}
		for index := maximum; index < handoffEnd; index++ {
			if index%32 == 0 {
				if err := ctx.Err(); err != nil {
					return nil, errors.Join(budgetErr, err)
				}
			}
			handoff := candidates[index]
			if isActiveReleaseCandidate(
				handoff,
				req.ActiveReleaseID,
				req.ActiveManifestDigest,
			) {
				bounded[len(bounded)-1] = handoff
				break
			}
		}
	}
	return bounded, budgetErr
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
				"modelChannel": "challenger",
			},
			Context: map[string]any{
				"shadowScore": s.Score,
				"detail":      s.Detail,
			},
		})
	}
}

package recommendation

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"

	"quwoquan_service/runtime/boundedrecord"
)

// RedisClient abstracts Redis operations for the hot path.
type RedisClient interface {
	Get(ctx context.Context, key string) (string, error)
	Set(ctx context.Context, key string, value string, ttl time.Duration) error
	SetNX(ctx context.Context, key string, value string, ttl time.Duration) (bool, error)
	Del(ctx context.Context, keys ...string) error
	SAdd(ctx context.Context, key string, members ...string) error
	SRem(ctx context.Context, key string, members ...string) error
	SIsMember(ctx context.Context, key string, member string) (bool, error)
	HIncrByFloat(ctx context.Context, key, field string, incr float64) error
	Expire(ctx context.Context, key string, ttl time.Duration) error
}

// RedisPipeliner is the required batched-read capability for recommendation
// Redis adapters. Feed reads must not retain a sequential/parallel compatibility
// path because that creates a second runtime composition with different latency
// and failure semantics.
type RedisPipeliner interface {
	PipelineRead(ctx context.Context, ops []PipelineOp) error
}

// RedisPipelineClient is the single commercial HotPath Redis contract.
// Requiring both command and pipeline capabilities at construction time makes
// a non-pipelined adapter a compile-time composition error.
type RedisPipelineClient interface {
	RedisClient
	RedisPipeliner
}

// PipelineOpType identifies the Redis command within a pipeline batch.
type PipelineOpType int

const (
	PipelineHGetAll   PipelineOpType = iota // result in Op.Hash
	PipelineSMembers                        // result in Op.Set
	PipelineSIsMember                       // input Op.Member, result in Op.Bool（N3-2）
)

// PipelineOp represents a single command in a pipeline batch.
// Callers populate Type+Key (and Member for SIsMember) before exec;
// the implementation fills Hash, Set or Bool.
type PipelineOp struct {
	Type   PipelineOpType
	Key    string
	Member string            // input for PipelineSIsMember
	Hash   map[string]string // populated after exec for PipelineHGetAll
	Set    []string          // populated after exec for PipelineSMembers
	Bool   bool              // populated after exec for PipelineSIsMember
}

// SessionReader reads session state for feed generation.
// Implemented by HotPath, SessionCache, etc.
type SessionReader interface {
	GetSessionState(ctx context.Context, userID, sessionID string) (*SessionState, error)
}

// RankedFeedWindowStoreProvider exposes the same rec-scene Redis already used
// by the recommendation hot path. Engine discovery through this narrow port
// prevents production from silently falling back to an in-process second cache.
type RankedFeedWindowStoreProvider interface {
	RankedFeedWindowStore() RankedFeedWindowStore
}

// HardExclusionReader reads the user-scoped facts that may never be bypassed:
// explicit negative content, hidden authors and hidden content types. It is
// intentionally separate from SessionReader so a soft personalization read
// failure can degrade without turning hard exclusions into an empty set.
type HardExclusionReader interface {
	LoadHardExclusions(ctx context.Context, userID string) (FeedbackExclusions, error)
}

// SignalProcessor writes behavior signals.
// Implemented by HotPath, BufferedHotPath, etc.
type SignalProcessor interface {
	ProcessSignal(ctx context.Context, signal BehaviorSignal) error
	ProcessSignalBatch(ctx context.Context, signals []BehaviorSignal) error
}

// ExposureMemory writes authoritative exposure states.
// served is cloud authoritative and write-behind; impressed/negative come from
// client feedback ingestion. Implementations must use per-candidate point
// membership for reads, never long-window SMembers on request path.
type ExposureMemory interface {
	RecordServed(ctx context.Context, userID string, items []FeedItem, at time.Time) error
	RecordImpressed(ctx context.Context, userID, contentID string, at time.Time) error
	RecordNegative(ctx context.Context, userID, contentID string) error
}

// ExposureFilter filters candidates by served/impressed/negative memory.
type ExposureFilter interface {
	FilterCandidates(ctx context.Context, userID string, candidates []ContentCandidate, at time.Time) ([]ContentCandidate, error)
}

// RelaxedExposureFilter is used only for an initial recommend page whose
// otherwise eligible real candidates were exhausted by served/impressed memory.
// Implementations must still enforce subject closure and explicit negatives.
type RelaxedExposureFilter interface {
	FilterCandidatesRelaxedExposure(ctx context.Context, userID string, candidates []ContentCandidate, at time.Time) ([]ContentCandidate, error)
}

// FeedbackIngestor provides cloud-side idempotency for client behavior events.
type FeedbackIngestor interface {
	AcceptEvent(ctx context.Context, signal BehaviorSignal) (bool, error)
}

// FeedbackReplayReader performs the read-only half of behavior idempotency.
// Command handlers use it before contacting mutable dependencies so an already
// committed client event keeps its successful outcome during dependency outages.
type FeedbackReplayReader interface {
	HasAcceptedEvent(ctx context.Context, userID, clientEventID string) (bool, error)
}

// RedisKeyPresenceReader lets idempotency readers distinguish an absent key
// from a Redis failure without coupling recommendation to a concrete adapter.
type RedisKeyPresenceReader interface {
	HasKey(ctx context.Context, key string) (bool, error)
}

type SubjectClosureGuard interface {
	IsSubjectClosed(ctx context.Context, subjectID string) (bool, error)
}

// Key patterns aligned with contracts/metadata/_shared/redis_keyspace.yaml.
//
// Redis Cluster hash-tag convention: {userId} is wrapped in braces so that all
// session-scoped keys for the same user land on the same cluster slot, enabling
// pipeline reads and atomic multi-key operations without cross-slot errors.
//
// Actual key format (cluster-safe):
//
//	rec:session_signals:{<userId>}:<sessionId>   → hash   TTL 1800s
//	rec:served:{<userId>}:<yyyyMMdd>             → set    TTL 172800s
//	rec:impressed:{<userId>}:<yyyyMMdd>          → set    TTL 604800s
//	rec:negative:{<userId>}                      → set    TTL 604800s
//	rec:hidden_authors:{<userId>}                → set    TTL 604800s
//	rec:hidden_types:{<userId>}                  → set    TTL 604800s
//	rec:event_dedup:{<userId>}:<clientEventId>   → string TTL 86400s
//	rec:realtime_interest:{<userId>}:<sessionId> → string TTL 1800s
//
// In standalone mode Redis ignores the braces and treats the key verbatim.
const (
	sessionTTL       = 30 * time.Minute
	servedTTL        = 48 * time.Hour
	impressedTTL     = 7 * 24 * time.Hour
	negativeTTL      = 7 * 24 * time.Hour
	hiddenTTL        = 7 * 24 * time.Hour
	clientEventIDTTL = 24 * time.Hour

	signalKeyPrefix        = "rec:session_signals:"
	servedKeyPrefix        = "rec:served:"
	impressedKeyPrefix     = "rec:impressed:"
	negativeKeyPrefix      = "rec:negative:"
	hiddenAuthorsKeyPrefix = "rec:hidden_authors:"
	hiddenTypesKeyPrefix   = "rec:hidden_types:"
	eventDedupKeyPrefix    = "rec:event_dedup:"
	interestKeyPrefix      = "rec:realtime_interest:"
)

// BehaviorSignal represents a user behavior event for hot path processing.
type BehaviorSignal struct {
	ClientEventID   string    `json:"clientEventId,omitempty"`
	State           string    `json:"state,omitempty"`
	UserID          string    `json:"userId"`
	PersonaID       string    `json:"personaId,omitempty"`
	DeviceActorID   string    `json:"deviceActorId,omitempty"`
	SessionID       string    `json:"sessionId"`
	FeedSessionID   string    `json:"feedSessionId,omitempty"`
	ContentID       string    `json:"contentId"`
	Action          string    `json:"action"`
	ContentType     string    `json:"contentType,omitempty"`
	Tags            []string  `json:"tags,omitempty"`
	Duration        float64   `json:"duration,omitempty"`
	Timestamp       time.Time `json:"timestamp"`
	AuthorID        string    `json:"authorId,omitempty"`
	ReferralSource  string    `json:"referralSource,omitempty"`
	EngagementDepth int       `json:"engagementDepth,omitempty"`
	ConsumedRatio   float64   `json:"consumedRatio,omitempty"`
	TotalUnits      int       `json:"totalUnits,omitempty"`
	EffectivePlayMS int       `json:"effectivePlayMs,omitempty"`
	EntityRefs      []string  `json:"entityRefs,omitempty"`
	FeedRequestID   string    `json:"feedRequestId,omitempty"`
	Position        int       `json:"position,omitempty"`
	CommentLength   int       `json:"commentLength,omitempty"`
	// feed 下发频道与唯一策略摘要，全事件携带，使 HotPath / served-impressed
	// 记账与特征投影可按同一不可变策略身份归因。
	ChannelID       string `json:"channelId,omitempty"`
	PolicyDigest    string `json:"policyDigest,omitempty"`
	RecallPath      string `json:"recallPath,omitempty"`
	ContentVertical string `json:"contentVertical,omitempty"`
	SupplySource    string `json:"supplySource,omitempty"`
	// ExperimentBucket（N1-3）：服务端按 policy 确定性分桶重算（不信任端侧），
	// 使行为归因指标可按 experiment_bucket 切分（AB 漏斗对比的分子侧）。
	ExperimentBucket string `json:"experimentBucket,omitempty"`
	// 交集转化归因（S6）：触发该行为的交集维度（identity/location/content/interest/relationship）
	// 与路径制 tagRef 锚点（唯一真相源 control_plane/governance/taxonomy），供推荐回流与交集转化漏斗按维度/tagRef 下钻。
	IntersectionDimension string   `json:"intersectionDimension,omitempty"`
	IntersectionTagRefs   []string `json:"intersectionTagRefs,omitempty"`
	// 交集漏斗归因（曝光/点击/转化）：交集稳定标识 IntersectionID 与类别 IntersectionClass
	// （fact|affinity）。与 App BehaviorEvent.intersectionId/intersectionClass 字段对齐（R08
	// 端云一致性），使「交集曝光 → 点击 → 转化」可按同一 intersectionId 与事实/概率类别下钻。
	IntersectionID         string `json:"intersectionId,omitempty"`
	IntersectionClass      string `json:"intersectionClass,omitempty"`
	IntersectionSourceRef  string `json:"intersectionSourceRef,omitempty"`
	IntersectionEvidenceID string `json:"intersectionEvidenceId,omitempty"`
}

// EffectiveSessionID returns the feed-scoped session ID for recommendation
// attribution. Falls back to the trace-level SessionID if FeedSessionID is empty.
func (s BehaviorSignal) EffectiveSessionID() string {
	if s.FeedSessionID != "" {
		return s.FeedSessionID
	}
	return s.SessionID
}

// SignalWeights is the single source of truth for supported actions and their
// base tag-weight contribution, aligned with behaviors.yaml signal_weight.
// An action absent from this map is rejected by BehaviorService.ProcessBatch.
var SignalWeights = map[string]float64{
	"impression":          0.1,
	"click":               0.5,
	"intersection_expand": 0.2,
	"dwell":               1.0,
	"like":                2.0,
	"share":               3.0,
	"dislike":             -5.0,
	"undo_dislike":        0.0,
	"hide_author":         -5.0,
	"hide_content_type":   -4.0,
	"report":              -10.0,
	"skip":                -0.3,
	"comment":             2.5,
	"follow":              4.0,
	"author_view":         1.5,
	"entity_page_view":    1.5,
	"tag_click":           1.8,
	// 播放位置比例只用于观测；seek 可直接跨越阈值，不能作为推荐正反馈。
	"play_progress": 0.0,
	// 只有服务端有效播放 policy 准入后的事件才能进入推荐。
	"effective_play": 1.0,
	"content_depth":  1.0,
	// 交集转化三类行动（S6）：关注人 follow / 进圈子 join_circle / 加联系人 add_contact。
	"join_circle": 4.0,
	"add_contact": 4.5,
	// 小艺对话浮现兴趣回流（P3）：payload 仅带 tagRefs，不绑定具体 post。
	"assistant_interest": 1.6,
	// 新用户首启兴趣采集（W11 interest-onboarding-prior）：四维标签选择写入
	// 推荐先验，首刷 TagRecall 立即可用；不绑定具体 post。
	"onboarding_interest": 2.5,
	// 交集负反馈（F 推荐差异化）：不绑定 post（subjectId 为交集主体对象），在通用 HotPath
	// 内为 inert（ContentID 空 → RecordNegative 被守卫跳过）；真实降权 / 冷却由
	// content-service behavior_service 经 IntersectionFeedbackSink → IntersectionService
	// 写 rec:ineg 交集负反馈冷却集完成。此处权重仅用于登记为受支持动作 + 对齐 behaviors.yaml。
	"intersection_feedback": -5.0,
	// 显式「想去」事件是 coWishlistedEntity 的真实意图源。HotPath 只把动作登记为
	// 受支持并保留弱推荐权重；持久事实投影由 content-service 写 entity_wishlist_events。
	"wishlist_add":    3.2,
	"wishlist_remove": -3.2,
}

// ReferralSourceMultiplier maps referral sources to tag weight multipliers.
var ReferralSourceMultiplier = map[string]float64{
	"organic_feed":      1.0,
	"friend_share":      1.5,
	"chat_link":         1.8,
	"circle_post":       1.3,
	"author_profile":    1.2,
	"entity_page":       1.2,
	"search":            2.0,
	"push_notification": 0.8,
	"deep_link":         0.5,
	// 用户在「我的交集 / 我的影响力」中心主动点击交集对象：强关系探索意图，
	// 高于 organic_feed / author_profile，与 friend_share 同级。
	"my_intersections": 1.5,
	// 创作者从发布结果页查看自己的作品只参与来源归因，不学习为消费兴趣。
	"publish_result": 0.0,
}

// DepthLevelCoefficient maps engagementDepth level (0-4) to tag weight coefficient.
var DepthLevelCoefficient = [5]float64{0.0, 0.3, 0.7, 1.2, 2.0}

// HotPath manages session-level recommendation state in Redis.
type HotPath struct {
	redis             RedisPipelineClient
	guard             SubjectClosureGuard
	rankedWindowQuota boundedrecord.Policy
}

type HotPathOption func(*HotPath)

func WithSubjectClosureGuard(guard SubjectClosureGuard) HotPathOption {
	return func(hotPath *HotPath) {
		hotPath.guard = guard
	}
}

func WithRankedFeedWindowQuotaPolicy(policy boundedrecord.Policy) HotPathOption {
	return func(hotPath *HotPath) {
		hotPath.rankedWindowQuota = policy
	}
}

func NewHotPath(redis RedisPipelineClient, options ...HotPathOption) *HotPath {
	hotPath := &HotPath{
		redis:             redis,
		rankedWindowQuota: DefaultRankedFeedWindowQuotaPolicy(),
	}
	for _, option := range options {
		if option != nil {
			option(hotPath)
		}
	}
	return hotPath
}

// RankedFeedWindowStore returns a non-sliding immutable-window adapter over the
// existing recommendation Redis scene.
func (h *HotPath) RankedFeedWindowStore() RankedFeedWindowStore {
	if h == nil || h.redis == nil {
		return nil
	}
	return NewRedisRankedFeedWindowStore(h.redis, h.rankedWindowQuota)
}

func (h *HotPath) isSubjectClosed(
	ctx context.Context,
	subjectID string,
) (bool, error) {
	if h == nil || h.guard == nil || strings.TrimSpace(subjectID) == "" {
		return false, nil
	}
	return h.guard.IsSubjectClosed(ctx, subjectID)
}

// sessionKey builds a Redis key suffix with a cluster hash tag on userId.
// Format: {<userId>}:<sessionId>
//
// The hash tag {userId} ensures rec session/exposure keys for the same user
// always map to the same Redis Cluster slot,
// making pipeline reads and multi-key operations safe in cluster mode.
// Standalone Redis ignores the braces — behaviour is identical.
func sessionKey(userID, sessionID string) string {
	if sessionID == "" {
		sessionID = "default"
	}
	return "{" + userID + "}:" + sessionID
}

func userDayKey(userID string, at time.Time) string {
	if at.IsZero() {
		at = time.Now().UTC()
	}
	return userHashKey(userID) + ":" + at.UTC().Format("20060102")
}

func userScopedKey(userID string) string {
	return userHashKey(userID)
}

func eventDedupKey(userID, clientEventID string) string {
	return eventDedupKeyPrefix + userHashKey(userID) + ":" + clientEventID
}

// ProcessSignal updates session-level state from a behavior signal.
// Tag weight is computed as: baseWeight × depthCoefficient × referralMultiplier
func (h *HotPath) ProcessSignal(ctx context.Context, signal BehaviorSignal) error {
	closed, err := h.isSubjectClosed(ctx, signal.UserID)
	if err != nil {
		return err
	}
	if closed {
		return nil
	}
	if strings.TrimSpace(strings.ToLower(signal.Action)) == "undo_dislike" {
		return h.RestoreNegative(ctx, signal.UserID, signal.ContentID)
	}
	sk := sessionKey(signal.UserID, signal.EffectiveSessionID())

	switch normalizeFeedbackState(signal) {
	case "impressed":
		if err := h.RecordImpressed(ctx, signal.UserID, signal.ContentID, signal.Timestamp); err != nil {
			return err
		}
	case "negative":
		if err := h.RecordNegative(ctx, signal.UserID, signal.ContentID); err != nil {
			return err
		}
	}

	baseWeight := SignalWeights[signal.Action]
	if baseWeight < 0 {
		if err := h.RecordNegative(ctx, signal.UserID, signal.ContentID); err != nil {
			return err
		}
	}
	if signal.Action == "hide_author" && signal.AuthorID != "" {
		if err := h.addHiddenAuthor(ctx, signal.UserID, signal.AuthorID); err != nil {
			return err
		}
	}
	if signal.Action == "hide_content_type" && signal.ContentType != "" {
		if err := h.addHiddenType(ctx, signal.UserID, signal.ContentType); err != nil {
			return err
		}
	}

	effectiveWeight := computeEffectiveTagWeight(baseWeight, signal.EngagementDepth, signal.ReferralSource)

	if len(signal.Tags) > 0 {
		if err := h.updateTagWeights(ctx, sk, signal.Tags, effectiveWeight); err != nil {
			return err
		}
	}

	return h.updateInterest(ctx, sk, signal)
}

func normalizeFeedbackState(signal BehaviorSignal) string {
	if state := strings.TrimSpace(strings.ToLower(signal.State)); state != "" {
		return state
	}
	switch strings.TrimSpace(strings.ToLower(signal.Action)) {
	case "impression":
		return "impressed"
	case "dwell":
		return "dwell"
	case "dislike", "hide_author", "hide_content_type", "report":
		return "negative"
	// 交集负反馈：语义为 negative，但 subject 维度冷却由 IntersectionService 承接，
	// 通用 rec:negative 因 ContentID 空而被守卫跳过（不污染内容级过滤集）。
	case "intersection_feedback":
		return "negative"
	// click 是独立漏斗态（七态：served/visible/impressed/click/dwell/interaction/negative）：
	// CTR = click / impressed 直接由此态分离，区别于点赞/评论/分享等深度互动（interaction）。
	case "click":
		return "click"
	case "like", "share", "comment", "follow", "join_circle", "add_contact", "author_view", "entity_page_view", "tag_click", "play_progress", "content_depth":
		return "interaction"
	default:
		return ""
	}
}

// computeEffectiveTagWeight applies depth and referral source multipliers.
// Formula: baseWeight × depthCoefficient[depth] × referralMultiplier[source]
// When depth is 0 (unset / pre-existing), coefficient defaults to 1.0 (no suppression).
// Only depth > 0 applies the DepthLevelCoefficient lookup.
func computeEffectiveTagWeight(baseWeight float64, depth int, referralSource string) float64 {
	if baseWeight <= 0 {
		return baseWeight
	}

	depthCoeff := 1.0
	if depth > 0 && depth < len(DepthLevelCoefficient) {
		depthCoeff = DepthLevelCoefficient[depth]
	}

	sourceMultiplier := 1.0
	if referralSource != "" {
		if m, ok := ReferralSourceMultiplier[referralSource]; ok {
			sourceMultiplier = m
		}
	}

	return baseWeight * depthCoeff * sourceMultiplier
}

// ProcessSignalBatch processes multiple signals concurrently.
// Groups by session key and processes groups in parallel.
func (h *HotPath) ProcessSignalBatch(ctx context.Context, signals []BehaviorSignal) error {
	if len(signals) <= 1 {
		for _, s := range signals {
			if err := h.ProcessSignal(ctx, s); err != nil {
				return err
			}
		}
		return nil
	}

	groups := make(map[string][]BehaviorSignal, len(signals)/2+1)
	for _, s := range signals {
		sk := sessionKey(s.UserID, s.EffectiveSessionID())
		groups[sk] = append(groups[sk], s)
	}

	var (
		mu       sync.Mutex
		firstErr error
		wg       sync.WaitGroup
	)

	for _, sigs := range groups {
		wg.Add(1)
		go func(batch []BehaviorSignal) {
			defer wg.Done()
			for _, s := range batch {
				if err := h.ProcessSignal(ctx, s); err != nil {
					mu.Lock()
					if firstErr == nil {
						firstErr = err
					}
					mu.Unlock()
					return
				}
			}
		}(sigs)
	}

	wg.Wait()
	return firstErr
}

// GetSessionState returns the full session state through the canonical
// single-RTT pipeline.
func (h *HotPath) GetSessionState(ctx context.Context, userID, sessionID string) (*SessionState, error) {
	closed, err := h.isSubjectClosed(ctx, userID)
	if err != nil {
		return nil, err
	}
	if closed {
		return &SessionState{
			UserID:     userID,
			SessionID:  sessionID,
			TagWeights: map[string]float64{},
		}, nil
	}
	sk := sessionKey(userID, sessionID)
	return h.getSessionStatePipeline(ctx, h.redis, sk, userID, sessionID)
}

// getSessionStatePipeline sends HGetAll + small user-level SMembers in a single RTT.
// served/impressed/negative are intentionally not returned here: filtering uses
// candidate membership point lookups through ExposureFilter to avoid long-window
// SMembers payloads on the feed request path.
func (h *HotPath) getSessionStatePipeline(ctx context.Context, p RedisPipeliner, sk, userID, sessionID string) (*SessionState, error) {
	ops := []PipelineOp{
		{Type: PipelineHGetAll, Key: signalKeyPrefix + sk},
		{Type: PipelineSMembers, Key: hiddenAuthorsKeyPrefix + userHashKey(userID)},
		{Type: PipelineSMembers, Key: hiddenTypesKeyPrefix + userHashKey(userID)},
	}
	if err := p.PipelineRead(ctx, ops); err != nil {
		return nil, err
	}

	tagWeights := make(map[string]float64, len(ops[0].Hash))
	for k, v := range ops[0].Hash {
		var f float64
		fmt.Sscanf(v, "%f", &f)
		tagWeights[k] = f
	}

	return &SessionState{
		UserID:             userID,
		SessionID:          sessionID,
		TagWeights:         tagWeights,
		ExposedIDs:         nil,
		NegativeIDs:        nil,
		HiddenAuthorIDs:    ops[1].Set,
		HiddenContentTypes: ops[2].Set,
	}, nil
}

// IsExposed checks if a content ID was served in the current day bucket.
func (h *HotPath) IsExposed(ctx context.Context, userID, sessionID, contentID string) (bool, error) {
	closed, err := h.isSubjectClosed(ctx, userID)
	if err != nil || closed {
		return false, err
	}
	return h.redis.SIsMember(ctx, servedKeyPrefix+userDayKey(userID, time.Now().UTC()), contentID)
}

// SessionState holds the real-time session context for recommendations.
type SessionState struct {
	UserID             string             `json:"userId"`
	SessionID          string             `json:"sessionId"`
	TagWeights         map[string]float64 `json:"tagWeights"`
	ExposedIDs         []string           `json:"exposedIds"`
	NegativeIDs        []string           `json:"negativeIds"`
	HiddenAuthorIDs    []string           `json:"hiddenAuthorIds"`
	HiddenContentTypes []string           `json:"hiddenContentTypes"`
}

func (h *HotPath) RecordServed(ctx context.Context, userID string, items []FeedItem, at time.Time) error {
	if len(items) == 0 || strings.TrimSpace(userID) == "" {
		return nil
	}
	closed, err := h.isSubjectClosed(ctx, userID)
	if err != nil || closed {
		return err
	}
	ids := make([]string, 0, len(items))
	for _, item := range items {
		if id := strings.TrimSpace(item.ContentID); id != "" {
			ids = append(ids, id)
		}
	}
	if len(ids) == 0 {
		return nil
	}
	key := servedKeyPrefix + userDayKey(userID, at)
	if err := h.redis.SAdd(ctx, key, ids...); err != nil {
		return err
	}
	return h.redis.Expire(ctx, key, servedTTL)
}

func (h *HotPath) RecordImpressed(ctx context.Context, userID, contentID string, at time.Time) error {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(contentID) == "" {
		return nil
	}
	closed, err := h.isSubjectClosed(ctx, userID)
	if err != nil || closed {
		return err
	}
	key := impressedKeyPrefix + userDayKey(userID, at)
	if err := h.redis.SAdd(ctx, key, contentID); err != nil {
		return err
	}
	return h.redis.Expire(ctx, key, impressedTTL)
}

func (h *HotPath) RecordNegative(ctx context.Context, userID, contentID string) error {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(contentID) == "" {
		return nil
	}
	closed, err := h.isSubjectClosed(ctx, userID)
	if err != nil || closed {
		return err
	}
	key := negativeKeyPrefix + userScopedKey(userID)
	if err := h.redis.SAdd(ctx, key, contentID); err != nil {
		return err
	}
	return h.redis.Expire(ctx, key, negativeTTL)
}

func (h *HotPath) RestoreNegative(
	ctx context.Context,
	userID string,
	contentID string,
) error {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(contentID) == "" {
		return nil
	}
	closed, err := h.isSubjectClosed(ctx, userID)
	if err != nil || closed {
		return err
	}
	return h.redis.SRem(
		ctx,
		negativeKeyPrefix+userScopedKey(userID),
		contentID,
	)
}

// LoadHardExclusions resolves all non-bypassable user filters from one Redis
// pipeline snapshot. Any read error is returned so the caller can fail closed.
func (h *HotPath) LoadHardExclusions(
	ctx context.Context,
	userID string,
) (FeedbackExclusions, error) {
	exclusions := emptyFeedbackExclusions()
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return exclusions, nil
	}
	closed, err := h.isSubjectClosed(ctx, userID)
	if err != nil {
		return exclusions, err
	}
	if closed {
		return exclusions, nil
	}
	keys := []string{
		negativeKeyPrefix + userScopedKey(userID),
		hiddenAuthorsKeyPrefix + userHashKey(userID),
		hiddenTypesKeyPrefix + userHashKey(userID),
	}
	sets := make([][]string, len(keys))
	ops := make([]PipelineOp, 0, len(keys))
	for _, key := range keys {
		ops = append(ops, PipelineOp{Type: PipelineSMembers, Key: key})
	}
	if err := h.redis.PipelineRead(ctx, ops); err != nil {
		return exclusions, err
	}
	for index := range ops {
		sets[index] = ops[index].Set
	}
	exclusions.NegativeContentIDs = toSet(sets[0])
	exclusions.HiddenAuthors = toSet(sets[1])
	exclusions.HiddenContentTypes = toSet(sets[2])
	return exclusions, nil
}

func (h *HotPath) AcceptEvent(ctx context.Context, signal BehaviorSignal) (bool, error) {
	closed, err := h.isSubjectClosed(ctx, signal.UserID)
	if err != nil || closed {
		return false, err
	}
	clientEventID := strings.TrimSpace(signal.ClientEventID)
	if clientEventID == "" {
		return true, nil
	}
	userID := strings.TrimSpace(signal.UserID)
	if userID == "" {
		userID = "anonymous"
	}
	return h.redis.SetNX(ctx, eventDedupKey(userID, clientEventID), "1", clientEventIDTTL)
}

// HasAcceptedEvent checks the same durable Redis receipt used by AcceptEvent
// without creating or extending it.
func (h *HotPath) HasAcceptedEvent(
	ctx context.Context,
	userID, clientEventID string,
) (bool, error) {
	clientEventID = strings.TrimSpace(clientEventID)
	if clientEventID == "" {
		return false, nil
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		userID = "anonymous"
	}
	reader, ok := h.redis.(RedisKeyPresenceReader)
	if !ok {
		return false, fmt.Errorf("behavior idempotency receipt reader is unavailable")
	}
	return reader.HasKey(ctx, eventDedupKey(userID, clientEventID))
}

func (h *HotPath) FilterCandidates(ctx context.Context, userID string, candidates []ContentCandidate, at time.Time) ([]ContentCandidate, error) {
	if len(candidates) == 0 || strings.TrimSpace(userID) == "" {
		return candidates, nil
	}
	closed, err := h.isSubjectClosed(ctx, userID)
	if err != nil {
		return nil, err
	}
	if closed {
		return nil, nil
	}
	servedDays := dayKeys(userID, at, int(servedTTL/(24*time.Hour)))
	impressedDays := dayKeys(userID, at, int(impressedTTL/(24*time.Hour)))
	negativeKey := negativeKeyPrefix + userScopedKey(userID)
	// N3-2：canonical pipeline 单次 RTT 批量点查，消除
	// O(N×(1+served天+impressed天)) 的逐条往返。
	return h.filterCandidatesPipeline(
		ctx,
		h.redis,
		candidates,
		negativeKey,
		servedDays,
		impressedDays,
	)
}

// FilterCandidatesRelaxedExposure relaxes only served/impressed history.
// Explicit negatives and subject-closure erasure semantics remain fail-closed.
func (h *HotPath) FilterCandidatesRelaxedExposure(
	ctx context.Context,
	userID string,
	candidates []ContentCandidate,
	_ time.Time,
) ([]ContentCandidate, error) {
	if len(candidates) == 0 || strings.TrimSpace(userID) == "" {
		return candidates, nil
	}
	closed, err := h.isSubjectClosed(ctx, userID)
	if err != nil {
		return nil, err
	}
	if closed {
		return nil, nil
	}
	negativeKey := negativeKeyPrefix + userScopedKey(userID)
	return h.filterCandidatesPipeline(
		ctx,
		h.redis,
		candidates,
		negativeKey,
		nil,
		nil,
	)
}

// filterCandidatesPipeline 单次 pipeline 批量执行全部成员点查（N3-2，消除
// O(N×(1+served天+impressed天)) 的逐条 RTT：全部 SISMEMBER 装进一个 pipeline，
// 网络往返 1 次）。过滤语义固定为 negative 优先（计 suppressed）、
// served 次之、impressed 最后（served/impressed 分开计重复曝光）。
func (h *HotPath) filterCandidatesPipeline(
	ctx context.Context,
	pipeliner RedisPipeliner,
	candidates []ContentCandidate,
	negativeKey string,
	servedDays []string,
	impressedDays []string,
) ([]ContentCandidate, error) {
	opsPerCandidate := 1 + len(servedDays) + len(impressedDays)
	ops := make([]PipelineOp, 0, len(candidates)*opsPerCandidate)
	// candidateOpStart[i] 是第 i 个候选的 op 起始下标；空 contentID 候选为 -1。
	candidateOpStart := make([]int, len(candidates))
	for i, c := range candidates {
		contentID := strings.TrimSpace(c.ContentID)
		if contentID == "" {
			candidateOpStart[i] = -1
			continue
		}
		candidateOpStart[i] = len(ops)
		ops = append(ops, PipelineOp{Type: PipelineSIsMember, Key: negativeKey, Member: contentID})
		for _, keySuffix := range servedDays {
			ops = append(ops, PipelineOp{Type: PipelineSIsMember, Key: servedKeyPrefix + keySuffix, Member: contentID})
		}
		for _, keySuffix := range impressedDays {
			ops = append(ops, PipelineOp{Type: PipelineSIsMember, Key: impressedKeyPrefix + keySuffix, Member: contentID})
		}
	}
	if len(ops) == 0 {
		return candidates, nil
	}
	if err := pipeliner.PipelineRead(ctx, ops); err != nil {
		return nil, err
	}

	filtered := make([]ContentCandidate, 0, len(candidates))
	dupServed, dupImpressed := 0, 0
	for i, c := range candidates {
		start := candidateOpStart[i]
		if start < 0 {
			continue
		}
		if ops[start].Bool {
			feedNegativeCandidateSuppressedTotal.Inc()
			continue
		}
		servedHit := false
		for j := 0; j < len(servedDays); j++ {
			if ops[start+1+j].Bool {
				servedHit = true
				break
			}
		}
		if servedHit {
			dupServed++
			continue
		}
		impressedHit := false
		impressedBase := start + 1 + len(servedDays)
		for j := 0; j < len(impressedDays); j++ {
			if ops[impressedBase+j].Bool {
				impressedHit = true
				break
			}
		}
		if impressedHit {
			dupImpressed++
			continue
		}
		filtered = append(filtered, c)
	}
	RecordDuplicateExposureFiltered("served", dupServed)
	RecordDuplicateExposureFiltered("impressed", dupImpressed)
	return filtered, nil
}

func dayKeys(userID string, at time.Time, days int) []string {
	if days <= 0 {
		days = 1
	}
	if at.IsZero() {
		at = time.Now().UTC()
	}
	out := make([]string, 0, days)
	for i := 0; i < days; i++ {
		out = append(out, userDayKey(userID, at.AddDate(0, 0, -i)))
	}
	return out
}

func userHashKey(userID string) string {
	return "{" + userID + "}"
}

func (h *HotPath) addHiddenAuthor(ctx context.Context, userID, authorID string) error {
	key := hiddenAuthorsKeyPrefix + userHashKey(userID)
	if err := h.redis.SAdd(ctx, key, authorID); err != nil {
		return err
	}
	return h.redis.Expire(ctx, key, hiddenTTL)
}

func (h *HotPath) addHiddenType(ctx context.Context, userID, contentType string) error {
	key := hiddenTypesKeyPrefix + userHashKey(userID)
	if err := h.redis.SAdd(ctx, key, contentType); err != nil {
		return err
	}
	return h.redis.Expire(ctx, key, hiddenTTL)
}

func (h *HotPath) updateTagWeights(ctx context.Context, sk string, tags []string, weight float64) error {
	key := signalKeyPrefix + sk
	for _, tag := range tags {
		if err := h.redis.HIncrByFloat(ctx, key, tag, weight); err != nil {
			return err
		}
	}
	return h.redis.Expire(ctx, key, sessionTTL)
}

func (h *HotPath) updateInterest(ctx context.Context, sk string, signal BehaviorSignal) error {
	key := interestKeyPrefix + sk
	data, _ := json.Marshal(signal)
	return h.redis.Set(ctx, key, string(data), sessionTTL)
}

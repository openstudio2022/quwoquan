package recommendation

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"
	"time"
)

// RedisClient abstracts Redis operations for the hot path.
type RedisClient interface {
	Get(ctx context.Context, key string) (string, error)
	Set(ctx context.Context, key string, value string, ttl time.Duration) error
	SetNX(ctx context.Context, key string, value string, ttl time.Duration) (bool, error)
	Del(ctx context.Context, keys ...string) error
	SAdd(ctx context.Context, key string, members ...string) error
	SMembers(ctx context.Context, key string) ([]string, error)
	SIsMember(ctx context.Context, key string, member string) (bool, error)
	HIncrByFloat(ctx context.Context, key, field string, incr float64) error
	HGetAll(ctx context.Context, key string) (map[string]string, error)
	Expire(ctx context.Context, key string, ttl time.Duration) error
}

// RedisPipeliner is optionally implemented by RedisClient adapters that
// support pipelining multiple reads into a single RTT.
// When HotPath detects this interface, GetSessionState sends all session and
// cross-session reads in one pipeline instead of parallel goroutines.
type RedisPipeliner interface {
	PipelineRead(ctx context.Context, ops []PipelineOp) error
}

// PipelineOpType identifies the Redis command within a pipeline batch.
type PipelineOpType int

const (
	PipelineHGetAll  PipelineOpType = iota // result in Op.Hash
	PipelineSMembers                       // result in Op.Set
)

// PipelineOp represents a single command in a pipeline batch.
// Callers populate Type+Key before exec; the implementation fills Hash or Set.
type PipelineOp struct {
	Type PipelineOpType
	Key  string
	Hash map[string]string // populated after exec for PipelineHGetAll
	Set  []string          // populated after exec for PipelineSMembers
}

// SessionReader reads session state for feed generation.
// Implemented by HotPath, SessionCache, etc.
type SessionReader interface {
	GetSessionState(ctx context.Context, userID, sessionID string) (*SessionState, error)
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

// FeedbackIngestor provides cloud-side idempotency for client behavior events.
type FeedbackIngestor interface {
	AcceptEvent(ctx context.Context, signal BehaviorSignal) (bool, error)
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
	EntityRefs      []string  `json:"entityRefs,omitempty"`
	FeedRequestID   string    `json:"feedRequestId,omitempty"`
	Position        int       `json:"position,omitempty"`
	CommentLength   int       `json:"commentLength,omitempty"`
	// 阶段五归因：feed 下发频道与精排版本，全事件携带，使 HotPath / served-impressed 双轨记账与
	// 特征投影可按频道与精排版本分桶（AB / replay）。与 App BehaviorEvent.channelId/rankingVersion 对齐。
	ChannelID      string `json:"channelId,omitempty"`
	RankingVersion string `json:"rankingVersion,omitempty"`
	// 交集转化归因（S6）：触发该行为的交集维度（identity/location/content/interest/relationship）
	// 与路径制 tagRef 锚点（唯一真相源 publish/v1/tags），供推荐回流与交集转化漏斗按维度/tagRef 下钻。
	IntersectionDimension string   `json:"intersectionDimension,omitempty"`
	IntersectionTagRefs   []string `json:"intersectionTagRefs,omitempty"`
	// 交集漏斗归因（曝光/点击/转化）：交集稳定标识 IntersectionID 与类别 IntersectionClass
	// （fact|affinity）。与 App BehaviorEvent.intersectionId/intersectionClass 字段对齐（R08
	// 端云一致性），使「交集曝光 → 点击 → 转化」可按同一 intersectionId 与事实/概率类别下钻。
	IntersectionID    string `json:"intersectionId,omitempty"`
	IntersectionClass string `json:"intersectionClass,omitempty"`
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
	"impression":        0.1,
	"click":             0.5,
	"dwell":             1.0,
	"like":              2.0,
	"share":             3.0,
	"dislike":           -5.0,
	"hide_author":       -5.0,
	"hide_content_type": -4.0,
	"report":            -10.0,
	"skip":              -0.3,
	"comment":           2.5,
	"follow":            4.0,
	"author_view":       1.5,
	"entity_page_view":  1.2,
	"tag_click":         1.8,
	"play_progress":     1.0,
	"content_depth":     1.0,
	// 交集转化三类行动（S6）：关注人 follow / 进圈子 join_circle / 加联系人 add_contact。
	"join_circle": 4.0,
	"add_contact": 4.5,
	// 小艺对话浮现兴趣回流（P3）：payload 仅带 tagRefs，不绑定具体 post。
	"assistant_interest": 1.6,
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
}

// DepthLevelCoefficient maps engagementDepth level (0-4) to tag weight coefficient.
var DepthLevelCoefficient = [5]float64{0.0, 0.3, 0.7, 1.2, 2.0}

// HotPath manages session-level recommendation state in Redis.
type HotPath struct {
	redis RedisClient
}

func NewHotPath(redis RedisClient) *HotPath {
	return &HotPath{redis: redis}
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

// GetSessionState returns the full session state for the recommendation engine.
// Prefers pipeline (single RTT) when the underlying RedisClient implements
// RedisPipeliner; falls back to 3 parallel goroutines otherwise.
func (h *HotPath) GetSessionState(ctx context.Context, userID, sessionID string) (*SessionState, error) {
	sk := sessionKey(userID, sessionID)

	if pipeliner, ok := h.redis.(RedisPipeliner); ok {
		return h.getSessionStatePipeline(ctx, pipeliner, sk, userID, sessionID)
	}
	return h.getSessionStateParallel(ctx, sk, userID, sessionID)
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

// getSessionStateParallel reads tag weights and small user-level hidden sets.
func (h *HotPath) getSessionStateParallel(ctx context.Context, sk, userID, sessionID string) (*SessionState, error) {
	var (
		tagWeights       map[string]float64
		hiddenAuthors    []string
		hiddenTypes      []string
		tagErr           error
		hiddenAuthorsErr error
		hiddenTypesErr   error
	)

	var wg sync.WaitGroup
	wg.Add(3)

	go func() {
		defer wg.Done()
		tagWeights, tagErr = h.getTagWeights(ctx, sk)
	}()
	go func() {
		defer wg.Done()
		hiddenAuthors, hiddenAuthorsErr = h.getHiddenAuthors(ctx, userID)
	}()
	go func() {
		defer wg.Done()
		hiddenTypes, hiddenTypesErr = h.getHiddenTypes(ctx, userID)
	}()

	wg.Wait()

	if tagErr != nil {
		return nil, tagErr
	}
	if hiddenAuthorsErr != nil {
		return nil, hiddenAuthorsErr
	}
	if hiddenTypesErr != nil {
		return nil, hiddenTypesErr
	}

	return &SessionState{
		UserID:             userID,
		SessionID:          sessionID,
		TagWeights:         tagWeights,
		ExposedIDs:         nil,
		NegativeIDs:        nil,
		HiddenAuthorIDs:    hiddenAuthors,
		HiddenContentTypes: hiddenTypes,
	}, nil
}

// IsExposed checks if a content ID was served in the current day bucket.
func (h *HotPath) IsExposed(ctx context.Context, userID, sessionID, contentID string) (bool, error) {
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
	key := negativeKeyPrefix + userScopedKey(userID)
	if err := h.redis.SAdd(ctx, key, contentID); err != nil {
		return err
	}
	return h.redis.Expire(ctx, key, negativeTTL)
}

// NegativeContentIDs returns the user's accumulated explicit-negative content
// set (dislike / hide / report). Feed paths that bypass the recall pipeline
// (repository fallback) read this so explicit negative feedback is honored on
// every feed path, not only inside engine recall. The set is per-user (not
// day-bucketed) and stays small by product semantics, so a single SMembers off
// the hot recall path is acceptable.
func (h *HotPath) NegativeContentIDs(ctx context.Context, userID string) ([]string, error) {
	if strings.TrimSpace(userID) == "" {
		return nil, nil
	}
	return h.redis.SMembers(ctx, negativeKeyPrefix+userScopedKey(userID))
}

func (h *HotPath) AcceptEvent(ctx context.Context, signal BehaviorSignal) (bool, error) {
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

func (h *HotPath) FilterCandidates(ctx context.Context, userID string, candidates []ContentCandidate, at time.Time) ([]ContentCandidate, error) {
	if len(candidates) == 0 || strings.TrimSpace(userID) == "" {
		return candidates, nil
	}
	filtered := make([]ContentCandidate, 0, len(candidates))
	servedDays := dayKeys(userID, at, int(servedTTL/(24*time.Hour)))
	impressedDays := dayKeys(userID, at, int(impressedTTL/(24*time.Hour)))
	negativeKey := negativeKeyPrefix + userScopedKey(userID)
	// 重复曝光拦截度量：被 served/impressed 命中即「若不过滤就会再次曝光」的候选。
	// served/impressed 双轨分开计数，喂 recommendation_feed_duplicate_exposure_total，
	// 让重复曝光率 SLO（repeat_exposure_rate <= 0.01）可度量而非 objective_only。
	// negative 命中走显式负反馈语义，不计入重复曝光。
	dupServed, dupImpressed := 0, 0
	for _, c := range candidates {
		contentID := strings.TrimSpace(c.ContentID)
		if contentID == "" {
			continue
		}
		blocked, err := h.redis.SIsMember(ctx, negativeKey, contentID)
		if err != nil {
			return nil, err
		}
		if blocked {
			continue
		}
		if served, err := h.memberOfAny(ctx, servedKeyPrefix, servedDays, contentID); err != nil {
			return nil, err
		} else if served {
			dupServed++
			continue
		}
		if impressed, err := h.memberOfAny(ctx, impressedKeyPrefix, impressedDays, contentID); err != nil {
			return nil, err
		} else if impressed {
			dupImpressed++
			continue
		}
		filtered = append(filtered, c)
	}
	RecordDuplicateExposureFiltered("served", dupServed)
	RecordDuplicateExposureFiltered("impressed", dupImpressed)
	return filtered, nil
}

func (h *HotPath) memberOfAny(ctx context.Context, prefix string, dayKeys []string, contentID string) (bool, error) {
	for _, keySuffix := range dayKeys {
		ok, err := h.redis.SIsMember(ctx, prefix+keySuffix, contentID)
		if err != nil {
			return false, err
		}
		if ok {
			return true, nil
		}
	}
	return false, nil
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

func (h *HotPath) getTagWeights(ctx context.Context, sk string) (map[string]float64, error) {
	key := signalKeyPrefix + sk
	raw, err := h.redis.HGetAll(ctx, key)
	if err != nil {
		return nil, err
	}
	weights := make(map[string]float64, len(raw))
	for k, v := range raw {
		var f float64
		fmt.Sscanf(v, "%f", &f)
		weights[k] = f
	}
	return weights, nil
}

func (h *HotPath) getHiddenAuthors(ctx context.Context, userID string) ([]string, error) {
	return h.redis.SMembers(ctx, hiddenAuthorsKeyPrefix+userHashKey(userID))
}

func (h *HotPath) getHiddenTypes(ctx context.Context, userID string) ([]string, error) {
	return h.redis.SMembers(ctx, hiddenTypesKeyPrefix+userHashKey(userID))
}

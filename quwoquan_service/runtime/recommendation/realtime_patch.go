package recommendation

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"
)

// 低风险首页推荐实时 patch（商用化阶段 7 · §G）服务端发射真相源。
//
// 单一真相源：services/content-service/contracts/content/post/projections/recommendation_realtime_patch.yaml。
// 本文件的常量 / 字段必须与该 metadata 逐项一致（由 realtime_patch_test.go 契约测试锁定），
// App 端强类型 DTO 由 codegen_app_metadata 从同一 metadata 生成，禁止第二套定义。
//
// 语义边界：这是「推荐 → 端」瞬时 pub/sub 提示通道，不是领域事件——不进 event_store、
// 不跨服务消费、不做持久化重放。服务端只在安全边界发射，绝不主动重排用户正在看的内容。

// feedPatchChannelTemplate 是 per-user 瞬时通道模板，必须等于 metadata 的 realtime_channel_template。
const feedPatchChannelTemplate = "rt:rec:feed:user:{userId}"

// FeedRealtimePatchSchema 是 wire envelope 的单一 schema 身份。
const FeedRealtimePatchSchema = "feed_realtime_patch"

// FeedPatchType 是 patch 类型闭集（metadata patch_types）。
type FeedPatchType string

const (
	// FeedPatchNewCandidateHint 有新候选可纳入推荐，提示可刷新（仅提示，不强插）。
	FeedPatchNewCandidateHint FeedPatchType = "new_candidate_hint"
	// FeedPatchNegativeFeedbackRemoval 用户负反馈后，对应内容从当前 feed 剔除。
	FeedPatchNegativeFeedbackRemoval FeedPatchType = "negative_feedback_removal"
	// FeedPatchRefreshSuggestion 疲劳 / 时效启发式触发，建议刷新。
	FeedPatchRefreshSuggestion FeedPatchType = "refresh_suggestion"
)

// FeedPatchReasonCode 是触发原因码闭集（metadata reason_codes）。
type FeedPatchReasonCode string

const (
	FeedPatchReasonNegativeDislike         FeedPatchReasonCode = "negative_dislike"
	FeedPatchReasonNegativeHideAuthor      FeedPatchReasonCode = "negative_hide_author"
	FeedPatchReasonNegativeHideContentType FeedPatchReasonCode = "negative_hide_content_type"
	FeedPatchReasonNegativeReport          FeedPatchReasonCode = "negative_report"
	FeedPatchReasonRelationshipExpanded    FeedPatchReasonCode = "relationship_expanded"
	FeedPatchReasonNewCandidatesAvailable  FeedPatchReasonCode = "new_candidates_available"
	FeedPatchReasonSessionFatigue          FeedPatchReasonCode = "session_fatigue"
	FeedPatchReasonFeedStaleness           FeedPatchReasonCode = "feed_staleness"
)

// FeedPatchRemovalDimension 是负反馈剔除维度闭集（metadata removal_dimensions）。
type FeedPatchRemovalDimension string

const (
	FeedPatchRemovalPost        FeedPatchRemovalDimension = "post"
	FeedPatchRemovalAuthor      FeedPatchRemovalDimension = "author"
	FeedPatchRemovalContentType FeedPatchRemovalDimension = "content_type"
)

// FeedRealtimePatch 是强类型 wire envelope，json tag 必须与 metadata envelope_fields 同名。
type FeedRealtimePatch struct {
	Schema                  string                    `json:"schema"`
	PatchID                 string                    `json:"patchId"`
	PatchType               FeedPatchType             `json:"patchType"`
	UserID                  string                    `json:"userId"`
	FeedRequestID           string                    `json:"feedRequestId,omitempty"`
	ChannelID               string                    `json:"channelId,omitempty"`
	TargetPostIDs           []string                  `json:"targetPostIds"`
	ReasonCode              FeedPatchReasonCode       `json:"reasonCode"`
	RemovalDimension        FeedPatchRemovalDimension `json:"removalDimension,omitempty"`
	RemovalDimensionValue   string                    `json:"removalDimensionValue,omitempty"`
	AffectedCount           int                       `json:"affectedCount"`
	PolicyDigest            string                    `json:"policyDigest,omitempty"`
	SafeToApplyWhileViewing bool                      `json:"safeToApplyWhileViewing"`
	EmittedAt               string                    `json:"emittedAt"`
}

// FeedPatchPublisher 发布一条序列化 patch 到 realtime 通道（由 runtime/redis.Client 满足）。
type FeedPatchPublisher interface {
	Publish(ctx context.Context, channel string, message string) error
}

// FeedPatchEmitter 在安全边界发射推荐实时 patch。nil 或无 publisher 时所有方法为安全 no-op。
type FeedPatchEmitter struct {
	publisher FeedPatchPublisher
	logger    *slog.Logger
	now       func() time.Time
	newID     func() string
}

// FeedPatchEmitterOption 配置 FeedPatchEmitter。
type FeedPatchEmitterOption func(*FeedPatchEmitter)

// WithFeedPatchLogger 注入结构化日志器（发射失败时记录）。
func WithFeedPatchLogger(logger *slog.Logger) FeedPatchEmitterOption {
	return func(e *FeedPatchEmitter) { e.logger = logger }
}

// WithFeedPatchClock 注入时钟（测试确定性）。
func WithFeedPatchClock(now func() time.Time) FeedPatchEmitterOption {
	return func(e *FeedPatchEmitter) { e.now = now }
}

// WithFeedPatchIDFunc 注入 patchId 生成器（测试确定性）。
func WithFeedPatchIDFunc(fn func() string) FeedPatchEmitterOption {
	return func(e *FeedPatchEmitter) { e.newID = fn }
}

// NewFeedPatchEmitter 构造 emitter。publisher 为 nil 时返回的 emitter 是安全 no-op。
func NewFeedPatchEmitter(publisher FeedPatchPublisher, opts ...FeedPatchEmitterOption) *FeedPatchEmitter {
	e := &FeedPatchEmitter{
		publisher: publisher,
		now:       func() time.Time { return time.Now().UTC() },
		newID:     defaultFeedPatchID,
	}
	for _, opt := range opts {
		if opt != nil {
			opt(e)
		}
	}
	if e.now == nil {
		e.now = func() time.Time { return time.Now().UTC() }
	}
	if e.newID == nil {
		e.newID = defaultFeedPatchID
	}
	return e
}

func defaultFeedPatchID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "fpat_" + time.Now().UTC().Format("20060102150405.000000000")
	}
	return "fpat_" + hex.EncodeToString(b[:])
}

// FeedPatchChannelFor 解析 per-user 通道（与端侧 feedRealtimePatchChannelFor 同源）。
func FeedPatchChannelFor(userID string) string {
	return strings.ReplaceAll(feedPatchChannelTemplate, "{userId}", userID)
}

// enabled 报告 emitter 是否可发射（非 nil 且有 publisher）。
func (e *FeedPatchEmitter) enabled() bool {
	return e != nil && e.publisher != nil
}

// NegativeFeedbackRemoval 描述一次负反馈剔除 patch 的输入。
type NegativeFeedbackRemoval struct {
	UserID                string
	FeedRequestID         string
	ChannelID             string
	PolicyDigest          string
	TargetPostIDs         []string
	ReasonCode            FeedPatchReasonCode
	RemovalDimension      FeedPatchRemovalDimension
	RemovalDimensionValue string
}

// NewCandidateHint 描述一次新候选提示 patch 的输入。
type NewCandidateHint struct {
	UserID        string
	FeedRequestID string
	ChannelID     string
	PolicyDigest  string
	ReasonCode    FeedPatchReasonCode
	AffectedCount int
}

// RefreshSuggestion 描述一次刷新建议 patch 的输入。
type RefreshSuggestion struct {
	UserID        string
	FeedRequestID string
	ChannelID     string
	PolicyDigest  string
	ReasonCode    FeedPatchReasonCode
	AffectedCount int
}

// EmitNegativeFeedbackRemoval 发射 negative_feedback_removal patch。
// 仅在 userID 非空（per-user 通道，游客不发）且有剔除目标时发射。
func (e *FeedPatchEmitter) EmitNegativeFeedbackRemoval(ctx context.Context, in NegativeFeedbackRemoval) error {
	if !e.enabled() {
		return nil
	}
	userID := strings.TrimSpace(in.UserID)
	if userID == "" {
		return nil
	}
	targets := dedupeNonEmpty(in.TargetPostIDs)
	// post 维度必须有具体目标；author/content_type 维度靠 removalDimensionValue 命中。
	if in.RemovalDimension == FeedPatchRemovalPost && len(targets) == 0 {
		return nil
	}
	patch := FeedRealtimePatch{
		PatchType:               FeedPatchNegativeFeedbackRemoval,
		UserID:                  userID,
		FeedRequestID:           strings.TrimSpace(in.FeedRequestID),
		ChannelID:               strings.TrimSpace(in.ChannelID),
		PolicyDigest:            strings.TrimSpace(in.PolicyDigest),
		TargetPostIDs:           targets,
		ReasonCode:              in.ReasonCode,
		RemovalDimension:        in.RemovalDimension,
		RemovalDimensionValue:   strings.TrimSpace(in.RemovalDimensionValue),
		AffectedCount:           len(targets),
		SafeToApplyWhileViewing: true,
	}
	return e.emit(ctx, patch)
}

// EmitNewCandidateHint 发射 new_candidate_hint patch（仅提示，不强插）。
func (e *FeedPatchEmitter) EmitNewCandidateHint(ctx context.Context, in NewCandidateHint) error {
	if !e.enabled() {
		return nil
	}
	userID := strings.TrimSpace(in.UserID)
	if userID == "" {
		return nil
	}
	affected := in.AffectedCount
	if affected <= 0 {
		affected = 1
	}
	patch := FeedRealtimePatch{
		PatchType:               FeedPatchNewCandidateHint,
		UserID:                  userID,
		FeedRequestID:           strings.TrimSpace(in.FeedRequestID),
		ChannelID:               strings.TrimSpace(in.ChannelID),
		PolicyDigest:            strings.TrimSpace(in.PolicyDigest),
		TargetPostIDs:           []string{},
		ReasonCode:              in.ReasonCode,
		AffectedCount:           affected,
		SafeToApplyWhileViewing: true,
	}
	return e.emit(ctx, patch)
}

// EmitRefreshSuggestion 发射 refresh_suggestion patch（仅建议，不自动刷新）。
func (e *FeedPatchEmitter) EmitRefreshSuggestion(ctx context.Context, in RefreshSuggestion) error {
	if !e.enabled() {
		return nil
	}
	userID := strings.TrimSpace(in.UserID)
	if userID == "" {
		return nil
	}
	patch := FeedRealtimePatch{
		PatchType:               FeedPatchRefreshSuggestion,
		UserID:                  userID,
		FeedRequestID:           strings.TrimSpace(in.FeedRequestID),
		ChannelID:               strings.TrimSpace(in.ChannelID),
		PolicyDigest:            strings.TrimSpace(in.PolicyDigest),
		TargetPostIDs:           []string{},
		ReasonCode:              in.ReasonCode,
		AffectedCount:           in.AffectedCount,
		SafeToApplyWhileViewing: true,
	}
	return e.emit(ctx, patch)
}

// sessionFatigueNegativeThreshold 是会话疲劳启发式阈值：单批负反馈达到该数即建议刷新。
const sessionFatigueNegativeThreshold = 3

// EmitForBehaviorBatch 在一批行为信号处理成功后，按安全启发式发射推荐 patch：
//   - 负反馈（dislike/report/hide_author/hide_content_type）→ negative_feedback_removal。
//   - 关系扩展（follow/join_circle/add_contact）→ new_candidate_hint。
//   - 单批负反馈累计达阈值 → session_fatigue 的 refresh_suggestion。
//
// best-effort：单条 patch 发射失败只记录指标/日志，不影响行为主链路。
func (e *FeedPatchEmitter) EmitForBehaviorBatch(ctx context.Context, signals []BehaviorSignal) {
	if !e.enabled() || len(signals) == 0 {
		return
	}
	var fatigueAnchor BehaviorSignal
	negativeCount := 0
	for _, signal := range signals {
		if reason, dimension, dimensionValue, ok := negativeRemovalMapping(signal); ok {
			negativeCount++
			fatigueAnchor = signal
			_ = e.EmitNegativeFeedbackRemoval(ctx, NegativeFeedbackRemoval{
				UserID:                signal.UserID,
				FeedRequestID:         signal.FeedRequestID,
				ChannelID:             signal.ChannelID,
				PolicyDigest:          signal.PolicyDigest,
				TargetPostIDs:         []string{signal.ContentID},
				ReasonCode:            reason,
				RemovalDimension:      dimension,
				RemovalDimensionValue: dimensionValue,
			})
			continue
		}
		if reason, ok := relationshipHintReason(signal); ok {
			_ = e.EmitNewCandidateHint(ctx, NewCandidateHint{
				UserID:        signal.UserID,
				FeedRequestID: signal.FeedRequestID,
				ChannelID:     signal.ChannelID,
				PolicyDigest:  signal.PolicyDigest,
				ReasonCode:    reason,
				AffectedCount: 1,
			})
		}
	}
	if negativeCount >= sessionFatigueNegativeThreshold && strings.TrimSpace(fatigueAnchor.UserID) != "" {
		_ = e.EmitRefreshSuggestion(ctx, RefreshSuggestion{
			UserID:        fatigueAnchor.UserID,
			FeedRequestID: fatigueAnchor.FeedRequestID,
			ChannelID:     fatigueAnchor.ChannelID,
			PolicyDigest:  fatigueAnchor.PolicyDigest,
			ReasonCode:    FeedPatchReasonSessionFatigue,
			AffectedCount: negativeCount,
		})
	}
}

// negativeRemovalMapping 把负反馈行为映射到剔除 patch 的原因码与维度。
// 与 normalizeFeedbackState 的 negative 闭集对齐（dislike/report/hide_author/hide_content_type）。
func negativeRemovalMapping(signal BehaviorSignal) (FeedPatchReasonCode, FeedPatchRemovalDimension, string, bool) {
	switch strings.TrimSpace(strings.ToLower(signal.Action)) {
	case "dislike":
		return FeedPatchReasonNegativeDislike, FeedPatchRemovalPost, "", true
	case "report":
		return FeedPatchReasonNegativeReport, FeedPatchRemovalPost, "", true
	case "hide_author":
		if author := strings.TrimSpace(signal.AuthorID); author != "" {
			return FeedPatchReasonNegativeHideAuthor, FeedPatchRemovalAuthor, author, true
		}
		// 缺 authorId 时退化为单条剔除，仍尊重负反馈。
		return FeedPatchReasonNegativeHideAuthor, FeedPatchRemovalPost, "", true
	case "hide_content_type":
		if contentType := strings.TrimSpace(signal.ContentType); contentType != "" {
			return FeedPatchReasonNegativeHideContentType, FeedPatchRemovalContentType, contentType, true
		}
		return FeedPatchReasonNegativeHideContentType, FeedPatchRemovalPost, "", true
	default:
		return "", "", "", false
	}
}

// relationshipHintReason 把关系扩展行为映射到新候选提示原因码。
func relationshipHintReason(signal BehaviorSignal) (FeedPatchReasonCode, bool) {
	switch strings.TrimSpace(strings.ToLower(signal.Action)) {
	case "follow", "join_circle", "add_contact":
		return FeedPatchReasonRelationshipExpanded, true
	default:
		return "", false
	}
}

// emit 填充契约不变字段、校验、序列化并发布到 per-user 通道，并登记可观测指标。
func (e *FeedPatchEmitter) emit(ctx context.Context, patch FeedRealtimePatch) error {
	if patch.Schema == "" {
		patch.Schema = FeedRealtimePatchSchema
	}
	if patch.PatchID == "" {
		patch.PatchID = e.newID()
	}
	if patch.EmittedAt == "" {
		patch.EmittedAt = e.now().UTC().Format(time.RFC3339)
	}
	if patch.TargetPostIDs == nil {
		patch.TargetPostIDs = []string{}
	}
	patchType := string(patch.PatchType)
	if err := patch.Validate(); err != nil {
		RecordFeedPatchEmitFailed(patchType, "validate")
		e.logEmitError("rec.feed_patch.invalid", patch, err)
		return err
	}
	encoded, err := json.Marshal(patch)
	if err != nil {
		RecordFeedPatchEmitFailed(patchType, "marshal")
		e.logEmitError("rec.feed_patch.marshal_failed", patch, err)
		return err
	}
	channel := FeedPatchChannelFor(patch.UserID)
	if err := e.publisher.Publish(ctx, channel, string(encoded)); err != nil {
		RecordFeedPatchEmitFailed(patchType, "publish")
		e.logEmitError("rec.feed_patch.publish_failed", patch, err)
		return err
	}
	RecordFeedPatchEmitted(patchType, string(patch.ReasonCode))
	return nil
}

func (e *FeedPatchEmitter) logEmitError(msg string, patch FeedRealtimePatch, err error) {
	if e.logger == nil {
		return
	}
	e.logger.Warn(msg,
		slog.String("patchType", string(patch.PatchType)),
		slog.String("reasonCode", string(patch.ReasonCode)),
		slog.String("userId", patch.UserID),
		slog.Any("error", err),
	)
}

// Validate 校验 envelope 满足契约不变量。
func (p FeedRealtimePatch) Validate() error {
	if strings.TrimSpace(p.PatchID) == "" {
		return fmt.Errorf("feed patch: patchId required")
	}
	if strings.TrimSpace(p.UserID) == "" {
		return fmt.Errorf("feed patch: userId required")
	}
	if strings.TrimSpace(p.EmittedAt) == "" {
		return fmt.Errorf("feed patch: emittedAt required")
	}
	switch p.PatchType {
	case FeedPatchNewCandidateHint, FeedPatchNegativeFeedbackRemoval, FeedPatchRefreshSuggestion:
	default:
		return fmt.Errorf("feed patch: unknown patchType %q", p.PatchType)
	}
	if !knownFeedPatchReason(p.ReasonCode) {
		return fmt.Errorf("feed patch: unknown reasonCode %q", p.ReasonCode)
	}
	if p.PatchType == FeedPatchNegativeFeedbackRemoval {
		switch p.RemovalDimension {
		case FeedPatchRemovalPost:
			if len(p.TargetPostIDs) == 0 {
				return fmt.Errorf("feed patch: removal(post) requires targetPostIds")
			}
		case FeedPatchRemovalAuthor, FeedPatchRemovalContentType:
			if strings.TrimSpace(p.RemovalDimensionValue) == "" {
				return fmt.Errorf("feed patch: removal(%s) requires removalDimensionValue", p.RemovalDimension)
			}
		default:
			return fmt.Errorf("feed patch: removal requires a valid removalDimension")
		}
	}
	return nil
}

func knownFeedPatchReason(reason FeedPatchReasonCode) bool {
	switch reason {
	case FeedPatchReasonNegativeDislike,
		FeedPatchReasonNegativeHideAuthor,
		FeedPatchReasonNegativeHideContentType,
		FeedPatchReasonNegativeReport,
		FeedPatchReasonRelationshipExpanded,
		FeedPatchReasonNewCandidatesAvailable,
		FeedPatchReasonSessionFatigue,
		FeedPatchReasonFeedStaleness:
		return true
	default:
		return false
	}
}

func dedupeNonEmpty(in []string) []string {
	if len(in) == 0 {
		return []string{}
	}
	seen := make(map[string]struct{}, len(in))
	out := make([]string, 0, len(in))
	for _, v := range in {
		v = strings.TrimSpace(v)
		if v == "" {
			continue
		}
		if _, ok := seen[v]; ok {
			continue
		}
		seen[v] = struct{}{}
		out = append(out, v)
	}
	return out
}

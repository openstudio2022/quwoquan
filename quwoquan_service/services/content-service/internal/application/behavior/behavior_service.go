package behavior

import (
	"context"
	"quwoquan_service/services/content-service/internal/application/identity"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtimpact "quwoquan_service/runtime/impact"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/repository"
	"quwoquan_service/services/content-service/internal/application/ports"
	"quwoquan_service/services/content-service/internal/domain/post/event"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/generated"
)

// supportedBehaviorActions derives from SignalWeights (single source of truth
// aligned with behaviors.yaml signal_weight). An action is supported iff it
// has a weight entry, preventing silent drift between the two maps.
var supportedBehaviorActions = func() map[string]struct{} {
	m := make(map[string]struct{}, len(rtrec.SignalWeights))
	for action := range rtrec.SignalWeights {
		m[action] = struct{}{}
	}
	return m
}()

type BehaviorEventInput struct {
	ClientEventID   string   `json:"clientEventId"`
	State           string   `json:"state"`
	UserID          string   `json:"userId"`
	DeviceActorID   string   `json:"deviceActorId"`
	SessionID       string   `json:"sessionId"`
	FeedSessionID   string   `json:"feedSessionId"`
	ContentID       string   `json:"contentId"`
	PostID          string   `json:"postId"`
	Action          string   `json:"action"`
	Type            string   `json:"type"`
	ContentType     string   `json:"contentType"`
	ObjectID        string   `json:"objectId"`
	ObjectKind      string   `json:"objectKind"`
	DisplayName     string   `json:"displayName"`
	SourceSurface   string   `json:"sourceSurface"`
	Tags            []string `json:"tagRefs"`
	Duration        float64  `json:"duration"`
	DwellMs         float64  `json:"dwellMs"`
	FeedPosition    int      `json:"feedPosition"`
	Position        int      `json:"position"`
	AuthorID        string   `json:"authorId"`
	ReferralSource  string   `json:"referralSource"`
	EngagementDepth int      `json:"engagementDepth"`
	ConsumedRatio   float64  `json:"consumedRatio"`
	TotalUnits      int      `json:"totalUnits"`
	EntityRefs      []string `json:"entityRefs"`
	FeedRequestID   string   `json:"feedRequestId"`
	CommentLength   int      `json:"commentLength"`
	// 阶段五归因：feed 下发频道与精排版本，全事件携带（behaviors.yaml common_fields），贯穿 HotPath / 事件存储 / 特征投影。
	ChannelID       string `json:"channelId"`
	RankingVersion  string `json:"rankingVersion"`
	ReasonVersion   string `json:"reasonVersion"`
	RecallPath      string `json:"recallPath"`
	ContentVertical string `json:"contentVertical"`
	SupplySource    string `json:"supplySource"`
	// 交集转化归因（S6）：触发交集行动（follow/join_circle/add_contact）的维度与路径制 tagRef。
	IntersectionDimension string   `json:"intersectionDimension"`
	IntersectionTagRefs   []string `json:"intersectionTagRefs"`
	// 交集来源 kind（§5.4 标准名）：驱动该曝光/点击/转化的事实交集 kind。
	// 喂 rm_recommend_feature.socialFeatures.intersection 的 viewer 级揭示偏好直方图（WP-4 特征回流）。
	IntersectionSourceRef string `json:"intersectionSourceRef"`
	// 交集漏斗归因（R08 端云对齐）：与 App BehaviorEvent.intersectionId/intersectionClass/
	// intersectionEvidenceId 对齐。此前服务端未声明这些字段，端侧上报被静默丢弃；现接收并贯穿
	// HotPath/事件存储，使「交集曝光 → 点击 → 转化」可按同一 intersectionId 与类别(fact|affinity)归因。
	IntersectionID         string `json:"intersectionId"`
	IntersectionClass      string `json:"intersectionClass"`
	IntersectionEvidenceID string `json:"intersectionEvidenceId"`
	// 交集负反馈闭环（F 推荐差异化）：intersection_feedback 事件专属。
	//   SubjectID    = 交集主体对象 id（person/circle/place…，与 reason.subjectId/actionTargetId 同源）；
	//   FeedbackKind = registry.feedbackKinds 闭集（notInterested/dismiss/rejectGreeting/leaveCircle）。
	// 二者驱动 IntersectionService 写 rec:ineg 交集负反馈冷却集（Feed 命中即过滤，不再推荐）。
	SubjectID    string `json:"subjectId"`
	FeedbackKind string `json:"feedbackKind"`
}

// IntersectionFeedbackSink 接收交集负反馈，驱动交集主体（subject）跨会话冷却（rec:ineg）。
// 由 content-service IntersectionService 实现；behavior 侧仅依赖该端口（DDD 依赖倒置，
// 避免 application 直接耦合 intersection application 实现）。
type IntersectionFeedbackSink interface {
	ReportNegativeFeedback(ctx context.Context, userID, subjectID, feedbackKind string) error
}

// intersectionFeedbackKindSupported 校验 feedbackKind ∈ registry.feedbackKinds 闭集
// （codegen 单一真相源 generated.IntersectionFeedbackKinds），端上报与云侧消费同源。
func intersectionFeedbackKindSupported(kind string) bool {
	for _, k := range generated.IntersectionFeedbackKinds {
		if k == kind {
			return true
		}
	}
	return false
}

func isWishlistAction(action string) bool {
	return action == "wishlist_add" || action == "wishlist_remove"
}

func firstString(values []string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func wishlistEventFromInput(input BehaviorEventInput, userID, contentID, action string, occurredAt time.Time) ports.WishlistEvent {
	status := "active"
	if action == "wishlist_remove" {
		status = "removed"
	}
	entityID := strings.TrimSpace(firstNonEmptyLocal(input.ObjectID, firstString(input.EntityRefs), contentID))
	objectType := strings.TrimSpace(firstNonEmptyLocal(input.ObjectKind, input.ContentType))
	return ports.WishlistEvent{
		UserID:         userID,
		EntityID:       entityID,
		ObjectType:     objectType,
		DisplayName:    strings.TrimSpace(input.DisplayName),
		Status:         status,
		SourceSurface:  strings.TrimSpace(input.SourceSurface),
		ReferralSource: strings.TrimSpace(input.ReferralSource),
		FeedRequestID:  strings.TrimSpace(input.FeedRequestID),
		SessionID:      strings.TrimSpace(input.SessionID),
		ClientEventID:  strings.TrimSpace(input.ClientEventID),
		CreatedAt:      occurredAt,
		UpdatedAt:      occurredAt,
	}
}

type BehaviorService struct {
	hotPath              rtrec.SignalProcessor
	feedbackIngestor     rtrec.FeedbackIngestor
	store                ports.PostRepository
	publisher            repository.EventPublisher
	projector            ports.Projector
	feedback             *rtrec.FeedbackRecorder
	eventStore           ports.BehaviorEventStore
	wishlistStore        ports.WishlistEventStore
	metricsStore         ports.DailyMetricsStore
	authorImpact         ports.AuthorImpactStore
	authorImpactEvidence ports.AuthorImpactEvidenceStore
	sessionInvalid       func(userID, sessionID string)
	patchEmitter         *rtrec.FeedPatchEmitter
	intersectionFeedback IntersectionFeedbackSink
}

type BehaviorServiceOption func(*BehaviorService)

func WithBehaviorEventPublisher(pub repository.EventPublisher) BehaviorServiceOption {
	return func(s *BehaviorService) { s.publisher = pub }
}

func WithBehaviorProjector(p ports.Projector) BehaviorServiceOption {
	return func(s *BehaviorService) { s.projector = p }
}

func WithBehaviorFeedbackRecorder(f *rtrec.FeedbackRecorder) BehaviorServiceOption {
	return func(s *BehaviorService) { s.feedback = f }
}

func WithSessionCacheInvalidator(fn func(userID, sessionID string)) BehaviorServiceOption {
	return func(s *BehaviorService) { s.sessionInvalid = fn }
}

func WithBehaviorEventStore(es ports.BehaviorEventStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.eventStore = es }
}

func WithWishlistEventStore(store ports.WishlistEventStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.wishlistStore = store }
}

func WithDailyMetricsStore(ms ports.DailyMetricsStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.metricsStore = ms }
}

func WithAuthorImpactStore(store ports.AuthorImpactStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.authorImpact = store }
}

func WithAuthorImpactEvidenceStore(store ports.AuthorImpactEvidenceStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.authorImpactEvidence = store }
}

// WithFeedPatchEmitter 注入低风险实时推荐 patch 发射器（阶段七 §G）。
// 未注入时行为处理不发任何 patch（emitter nil 即安全 no-op）。
func WithFeedPatchEmitter(emitter *rtrec.FeedPatchEmitter) BehaviorServiceOption {
	return func(s *BehaviorService) { s.patchEmitter = emitter }
}

// WithIntersectionFeedbackSink 注入交集负反馈冷却下沉端口（F 推荐差异化）。
// 未注入时 intersection_feedback 事件仍被采集/持久化，但不写交集冷却（安全降级）。
func WithIntersectionFeedbackSink(sink IntersectionFeedbackSink) BehaviorServiceOption {
	return func(s *BehaviorService) {
		if sink != nil {
			s.intersectionFeedback = sink
		}
	}
}

func NewBehaviorService(hotPath rtrec.SignalProcessor, store ports.PostRepository, opts ...BehaviorServiceOption) *BehaviorService {
	svc := &BehaviorService{
		hotPath: hotPath,
		store:   store,
	}
	if ingestor, ok := hotPath.(rtrec.FeedbackIngestor); ok {
		svc.feedbackIngestor = ingestor
	}
	for _, opt := range opts {
		if opt != nil {
			opt(svc)
		}
	}
	return svc
}

func (s *BehaviorService) ProcessBatch(ctx context.Context, events []BehaviorEventInput) error {
	if len(events) == 0 {
		return rterr.NewInvalidArgument(rterr.ModuleContent, "events 不能为空", "empty behavior events")
	}
	signals := make([]rtrec.BehaviorSignal, 0, len(events))
	projectedEvents := make([]map[string]any, 0, len(events))
	occurredAt := time.Now().UTC()
	batchUserID := ""
	batchSessionID := ""
	for _, eventInput := range events {
		action := normalizeBehaviorAction(eventInput)
		if _, ok := supportedBehaviorActions[action]; !ok {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "action 不支持", "unsupported action: "+firstNonEmptyLocal(eventInput.Action, eventInput.Type))
		}
		userID := identity.NormalizeAnonymousSubAccountID(eventInput.UserID)
		contentID := strings.TrimSpace(firstNonEmptyLocal(eventInput.ContentID, eventInput.PostID))
		if contentID == "" && isWishlistAction(action) {
			contentID = strings.TrimSpace(firstNonEmptyLocal(eventInput.ObjectID, firstString(eventInput.EntityRefs)))
		}
		// assistant_interest（仅 tagRefs）与 intersection_feedback（subjectId 承载对象）不绑定 post。
		if contentID == "" && action != "assistant_interest" && action != "intersection_feedback" && !isWishlistAction(action) {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "contentId 必填", "missing contentId")
		}
		if isWishlistAction(action) {
			if strings.TrimSpace(firstNonEmptyLocal(eventInput.ObjectID, firstString(eventInput.EntityRefs), contentID)) == "" {
				return rterr.NewInvalidArgument(rterr.ModuleContent, "objectId 必填", "wishlist event requires objectId")
			}
			if strings.TrimSpace(firstNonEmptyLocal(eventInput.ObjectKind, eventInput.ContentType)) == "" {
				return rterr.NewInvalidArgument(rterr.ModuleContent, "objectKind 必填", "wishlist event requires objectKind")
			}
		}
		if action == "intersection_feedback" {
			if strings.TrimSpace(eventInput.SubjectID) == "" {
				return rterr.NewInvalidArgument(rterr.ModuleContent, "subjectId 必填", "intersection_feedback requires subjectId")
			}
			if !intersectionFeedbackKindSupported(strings.TrimSpace(eventInput.FeedbackKind)) {
				return rterr.NewInvalidArgument(rterr.ModuleContent, "feedbackKind 非法", "intersection_feedback requires feedbackKind in registry.feedbackKinds")
			}
		}
		duration := eventInput.Duration
		if duration == 0 && eventInput.DwellMs > 0 {
			duration = eventInput.DwellMs / 1000
		}
		tags := eventInput.Tags
		var post *postmodel.Post
		if len(tags) == 0 {
			if foundPost, ok := s.store.FindByID(ctx, contentID); ok {
				post = foundPost
				tags = behaviorTagsFromAny(post.TagRefs)
			}
		}
		contentType := strings.TrimSpace(eventInput.ContentType)
		authorID := strings.TrimSpace(eventInput.AuthorID)
		if post == nil && (contentType == "" || authorID == "") && contentID != "" {
			if foundPost, ok := s.store.FindByID(ctx, contentID); ok {
				post = foundPost
			}
		}
		if post != nil {
			if contentType == "" {
				contentType = strings.TrimSpace(post.ContentType)
			}
			if authorID == "" {
				authorID = strings.TrimSpace(post.AuthorId)
			}
		}
		if action == "hide_author" && authorID == "" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "authorId 必填", "hide_author requires authorId")
		}
		if action == "hide_content_type" && contentType == "" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "contentType 必填", "hide_content_type requires contentType")
		}
		feedPos := eventInput.FeedPosition
		if feedPos == 0 && eventInput.Position > 0 {
			feedPos = eventInput.Position
		}
		signal := rtrec.BehaviorSignal{
			ClientEventID:          strings.TrimSpace(eventInput.ClientEventID),
			State:                  strings.TrimSpace(eventInput.State),
			UserID:                 userID,
			DeviceActorID:          strings.TrimSpace(eventInput.DeviceActorID),
			SessionID:              strings.TrimSpace(eventInput.SessionID),
			FeedSessionID:          strings.TrimSpace(eventInput.FeedSessionID),
			ContentID:              contentID,
			Action:                 action,
			ContentType:            contentType,
			Tags:                   tags,
			Duration:               duration,
			Timestamp:              occurredAt,
			AuthorID:               authorID,
			ReferralSource:         strings.TrimSpace(eventInput.ReferralSource),
			EngagementDepth:        eventInput.EngagementDepth,
			ConsumedRatio:          eventInput.ConsumedRatio,
			TotalUnits:             eventInput.TotalUnits,
			EntityRefs:             eventInput.EntityRefs,
			FeedRequestID:          strings.TrimSpace(eventInput.FeedRequestID),
			Position:               feedPos,
			CommentLength:          eventInput.CommentLength,
			ChannelID:              strings.TrimSpace(eventInput.ChannelID),
			RankingVersion:         strings.TrimSpace(eventInput.RankingVersion),
			ReasonVersion:          strings.TrimSpace(eventInput.ReasonVersion),
			RecallPath:             strings.TrimSpace(eventInput.RecallPath),
			ContentVertical:        strings.TrimSpace(eventInput.ContentVertical),
			SupplySource:           strings.TrimSpace(eventInput.SupplySource),
			IntersectionDimension:  strings.TrimSpace(eventInput.IntersectionDimension),
			IntersectionTagRefs:    eventInput.IntersectionTagRefs,
			IntersectionID:         strings.TrimSpace(eventInput.IntersectionID),
			IntersectionClass:      strings.TrimSpace(eventInput.IntersectionClass),
			IntersectionSourceRef:  strings.TrimSpace(eventInput.IntersectionSourceRef),
			IntersectionEvidenceID: strings.TrimSpace(eventInput.IntersectionEvidenceID),
		}
		if s.feedbackIngestor != nil {
			accepted, err := s.feedbackIngestor.AcceptEvent(ctx, signal)
			if err != nil {
				rtrec.RecordBehaviorIngestDropped("dedup_error")
				return err
			}
			if !accepted {
				rtrec.RecordBehaviorIngestDropped("duplicate_client_event")
				continue
			}
		}
		rtrec.RecordBehaviorIngest(signal)
		signals = append(signals, signal)
		projectedEvents = append(projectedEvents, map[string]any{
			"clientEventId":          signal.ClientEventID,
			"state":                  signal.State,
			"userId":                 userID,
			"deviceActorId":          signal.DeviceActorID,
			"sessionId":              signal.SessionID,
			"contentId":              contentID,
			"action":                 action,
			"contentType":            signal.ContentType,
			"objectId":               strings.TrimSpace(firstNonEmptyLocal(eventInput.ObjectID, contentID)),
			"objectKind":             strings.TrimSpace(firstNonEmptyLocal(eventInput.ObjectKind, contentType)),
			"displayName":            strings.TrimSpace(eventInput.DisplayName),
			"sourceSurface":          strings.TrimSpace(eventInput.SourceSurface),
			"tagRefs":                append([]string(nil), tags...),
			"duration":               duration,
			"timestamp":              occurredAt.Format(time.RFC3339),
			"authorId":               signal.AuthorID,
			"referralSource":         signal.ReferralSource,
			"engagementDepth":        signal.EngagementDepth,
			"consumedRatio":          signal.ConsumedRatio,
			"totalUnits":             signal.TotalUnits,
			"entityRefs":             signal.EntityRefs,
			"feedRequestId":          strings.TrimSpace(eventInput.FeedRequestID),
			"feedPosition":           feedPos,
			"commentLength":          eventInput.CommentLength,
			"channelId":              strings.TrimSpace(eventInput.ChannelID),
			"rankingVersion":         strings.TrimSpace(eventInput.RankingVersion),
			"reasonVersion":          strings.TrimSpace(eventInput.ReasonVersion),
			"recallPath":             strings.TrimSpace(eventInput.RecallPath),
			"contentVertical":        strings.TrimSpace(eventInput.ContentVertical),
			"supplySource":           strings.TrimSpace(eventInput.SupplySource),
			"intersectionDimension":  signal.IntersectionDimension,
			"intersectionTagRefs":    signal.IntersectionTagRefs,
			"intersectionSourceRef":  strings.TrimSpace(eventInput.IntersectionSourceRef),
			"intersectionId":         signal.IntersectionID,
			"intersectionClass":      signal.IntersectionClass,
			"intersectionEvidenceId": strings.TrimSpace(eventInput.IntersectionEvidenceID),
		})
		// 交集负反馈冷却（F 推荐差异化）：subjectId/feedbackKind 已在上文校验、dedup 已由
		// AcceptEvent 完成（重复事件在上方 continue 跳过），此处对唯一有效事件写交集冷却。
		// ReportNegativeFeedback 内部对 Redis 降级 → 返回 nil 不阻断（同 ReportExposure 语义）；
		// sink 未注入时安全跳过。
		if action == "intersection_feedback" && s.intersectionFeedback != nil {
			_ = s.intersectionFeedback.ReportNegativeFeedback(
				ctx,
				userID,
				strings.TrimSpace(eventInput.SubjectID),
				strings.TrimSpace(eventInput.FeedbackKind),
			)
		}
		if isWishlistAction(action) && s.wishlistStore != nil {
			if err := s.wishlistStore.UpsertWishlistEvent(ctx, wishlistEventFromInput(eventInput, userID, contentID, action, occurredAt)); err != nil {
				return err
			}
		}
		if batchUserID == "" {
			batchUserID = userID
		}
		if batchSessionID == "" {
			batchSessionID = signal.SessionID
		}
	}
	if err := s.hotPath.ProcessSignalBatch(ctx, signals); err != nil {
		return err
	}
	for _, signal := range signals {
		rtrec.RecordBehaviorMetric(signal)
	}
	if s.eventStore != nil {
		rawEvents := make([]ports.RawBehaviorEvent, len(signals))
		for i, sig := range signals {
			rawEvents[i] = ports.RawBehaviorEvent{
				ClientEventID:          sig.ClientEventID,
				State:                  sig.State,
				UserID:                 sig.UserID,
				DeviceActorID:          sig.DeviceActorID,
				SessionID:              sig.SessionID,
				ContentID:              sig.ContentID,
				Action:                 sig.Action,
				Tags:                   sig.Tags,
				Duration:               sig.Duration,
				AuthorID:               sig.AuthorID,
				ReferralSource:         sig.ReferralSource,
				EngagementDepth:        sig.EngagementDepth,
				ConsumedRatio:          sig.ConsumedRatio,
				TotalUnits:             sig.TotalUnits,
				EntityRefs:             sig.EntityRefs,
				FeedRequestID:          strings.TrimSpace(events[i].FeedRequestID),
				Position:               sig.Position,
				CommentLength:          sig.CommentLength,
				ChannelID:              sig.ChannelID,
				RankingVersion:         sig.RankingVersion,
				ReasonVersion:          sig.ReasonVersion,
				RecallPath:             sig.RecallPath,
				ContentVertical:        sig.ContentVertical,
				SupplySource:           sig.SupplySource,
				IntersectionDimension:  sig.IntersectionDimension,
				IntersectionTagRefs:    sig.IntersectionTagRefs,
				IntersectionID:         sig.IntersectionID,
				IntersectionClass:      sig.IntersectionClass,
				IntersectionSourceRef:  strings.TrimSpace(events[i].IntersectionSourceRef),
				IntersectionEvidenceID: strings.TrimSpace(events[i].IntersectionEvidenceID),
				OccurredAt:             occurredAt.Format(time.RFC3339),
				CreatedAt:              occurredAt,
			}
		}
		_ = s.eventStore.InsertBatch(ctx, rawEvents)
	}
	if s.metricsStore != nil {
		dateStr := occurredAt.Format("2006-01-02")
		for _, sig := range signals {
			dwellMs := int64(sig.Duration * 1000)
			_ = s.metricsStore.IncrementMetric(ctx, dateStr, ports.DailyMetricDimensionAction, sig.Action, sig.Action, dwellMs, sig.EngagementDepth)
			if sig.ContentID != "" {
				_ = s.metricsStore.IncrementMetric(ctx, dateStr, ports.DailyMetricDimensionContent, sig.ContentID, sig.Action, dwellMs, sig.EngagementDepth)
			}
			if sig.AuthorID != "" {
				_ = s.metricsStore.IncrementMetric(ctx, dateStr, ports.DailyMetricDimensionAuthor, sig.AuthorID, sig.Action, dwellMs, sig.EngagementDepth)
			}
			// 交集转化北极星（S6）：交集维度上有归因的行动（关注/进圈子/加联系人等）按维度累计，
			// 供「交集转化率 = 交集行动数 / 新增可解释交集数」按 dimension 下钻。
			if sig.IntersectionDimension != "" {
				_ = s.metricsStore.IncrementMetric(ctx, dateStr, ports.DailyMetricDimensionIntersection, sig.IntersectionDimension, sig.Action, dwellMs, sig.EngagementDepth)
			}
		}
	}
	if s.authorImpact != nil {
		for _, sig := range signals {
			if event := authorImpactEventFromSignal(sig, occurredAt); event.AuthorID != "" {
				_ = s.authorImpact.Record(ctx, event)
				s.recordAuthorImpactEvidence(ctx, sig, event, occurredAt)
			}
		}
	}
	if s.feedback != nil {
		for _, signal := range signals {
			_ = s.feedback.RecordEngagement(ctx, signal, 0)
		}
	}
	payload := map[string]any{
		"userId":     batchUserID,
		"sessionId":  batchSessionID,
		"events":     projectedEvents,
		"count":      len(projectedEvents),
		"reportedAt": occurredAt.Format(time.RFC3339),
		"source":     "content_behavior_tracker",
	}
	if s.publisher != nil {
		aggregateID := firstNonEmptyLocal(batchSessionID, batchUserID, occurredAt.Format(time.RFC3339Nano))
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          event.BehaviorBatchReported,
			AggregateType: "BehaviorBatch",
			AggregateID:   aggregateID,
			Payload:       payload,
			OccurredAt:    occurredAt.Format(time.RFC3339),
		})
	}
	if s.projector != nil {
		aggregateID := firstNonEmptyLocal(batchSessionID, batchUserID, occurredAt.Format(time.RFC3339Nano))
		if err := s.projector.Project(ctx, ports.ProjectorEvent{
			Type:          event.BehaviorBatchReported,
			AggregateType: "BehaviorBatch",
			AggregateID:   aggregateID,
			Payload:       payload,
			OccurredAt:    occurredAt,
		}); err != nil {
			return err
		}
	}
	if s.sessionInvalid != nil && batchUserID != "" && batchSessionID != "" {
		s.sessionInvalid(batchUserID, batchSessionID)
	}
	// 低风险实时推荐 patch（阶段七 §G）：在行为主链路全部成功后于安全边界发射。
	// best-effort，不影响行为写入结果；emitter 为 nil 时安全 no-op。
	s.patchEmitter.EmitForBehaviorBatch(ctx, signals)
	return nil
}

func normalizeBehaviorAction(input BehaviorEventInput) string {
	return strings.TrimSpace(strings.ToLower(firstNonEmptyLocal(input.Action, input.Type)))
}

// FootprintEntry 我的足迹单条记录：行为事件 + hydrate 后的内容（可能已删除为 nil）。
type FootprintEntry struct {
	PostID     string
	Action     string
	OccurredAt time.Time
	Post       *postmodel.Post
}

// footprintTypeActions 足迹 type → 行为 action 集合的云侧唯一映射；
// 端侧只传 type 枚举字符串，不解析 action 语义（计算与展示均在云侧）。
func footprintTypeActions(footprintType string) []string {
	switch strings.TrimSpace(strings.ToLower(footprintType)) {
	case "viewed":
		return []string{"click", "dwell", "content_depth", "play_progress"}
	case "liked":
		return []string{"like"}
	case "commented":
		return []string{"comment"}
	case "shared":
		return []string{"share"}
	default:
		return []string{"click", "dwell", "content_depth", "play_progress", "like", "comment", "share"}
	}
}

// GetMyFootprint 我的足迹只读查询：复用既有行为边（rm_behavior_events），
// 无新写路径；仅本人可见、不产生交集与影响事实。cursor 为 RFC3339Nano 时间。
func (s *BehaviorService) GetMyFootprint(ctx context.Context, userID, footprintType, cursor string, limit int) ([]FootprintEntry, string, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return nil, "", rterr.NewInvalidArgument(rterr.ModuleContent, "需要登录", "footprint requires authenticated user")
	}
	if s.eventStore == nil {
		return nil, "", nil
	}
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	var before time.Time
	if trimmed := strings.TrimSpace(cursor); trimmed != "" {
		parsed, err := time.Parse(time.RFC3339Nano, trimmed)
		if err != nil {
			return nil, "", rterr.NewInvalidArgument(rterr.ModuleContent, "无效的 cursor", "invalid footprint cursor")
		}
		before = parsed
	}
	actions := footprintTypeActions(footprintType)
	// 多取一些以覆盖同一内容的重复行为（去重后可能不足一页）。
	events, err := s.eventStore.ListUserFootprint(ctx, userID, actions, before, limit*3)
	if err != nil {
		return nil, "", err
	}
	entries := make([]FootprintEntry, 0, limit)
	seen := make(map[string]struct{}, len(events))
	var lastSeen time.Time
	for _, ev := range events {
		lastSeen = ev.CreatedAt
		contentID := strings.TrimSpace(ev.ContentID)
		if contentID == "" {
			continue
		}
		if _, dup := seen[contentID]; dup {
			continue
		}
		seen[contentID] = struct{}{}
		post, _ := s.store.FindByID(ctx, contentID)
		entries = append(entries, FootprintEntry{
			PostID:     contentID,
			Action:     ev.Action,
			OccurredAt: ev.CreatedAt,
			Post:       post,
		})
		if len(entries) >= limit {
			break
		}
	}
	nextCursor := ""
	if len(events) >= limit*3 && !lastSeen.IsZero() {
		nextCursor = lastSeen.UTC().Format(time.RFC3339Nano)
	} else if len(entries) >= limit && !lastSeen.IsZero() {
		nextCursor = lastSeen.UTC().Format(time.RFC3339Nano)
	}
	return entries, nextCursor, nil
}

func authorImpactEventFromSignal(signal rtrec.BehaviorSignal, occurredAt time.Time) ports.AuthorImpactEvent {
	// behavior action → helpType 反查 rtimpact.BehaviorActionToHelpType
	// （源 registry.helpTypes[].behaviorActions）。未登记动作不产生影响力事件。
	helpType, ok := rtimpact.BehaviorActionToHelpType[strings.TrimSpace(signal.Action)]
	if !ok {
		return ports.AuthorImpactEvent{}
	}
	return ports.AuthorImpactEvent{
		AuthorID:              strings.TrimSpace(signal.AuthorID),
		Action:                strings.TrimSpace(signal.Action),
		HelpType:              helpType,
		IntersectionDimension: strings.TrimSpace(signal.IntersectionDimension),
		IntersectionTagRefs:   signal.IntersectionTagRefs,
		Source:                "behavior",
		OccurredAt:            occurredAt,
	}
}

// authorImpactEvidenceSource is the canonical source tag for behavior-driven
// impact facts; it must match rm_author_impact's stored source so the per-tag
// impactId drill-down anchor stays identical across summary and evidence.
const authorImpactEvidenceSource = "behavior"

// recordAuthorImpactEvidence materializes one paginated evidence fact per
// (tagRef) for an impact-bearing behavior. impactId is derived identically to
// the rm_author_impact summary row so the app can drill from a count to its
// underlying facts. actorId is stored for dedupe only and never surfaced.
func (s *BehaviorService) recordAuthorImpactEvidence(ctx context.Context, sig rtrec.BehaviorSignal, event ports.AuthorImpactEvent, occurredAt time.Time) {
	if s.authorImpactEvidence == nil {
		return
	}
	authorID := strings.TrimSpace(event.AuthorID)
	if authorID == "" {
		return
	}
	tagRefs := ports.NormalizeImpactTags(event.IntersectionTagRefs)
	if len(tagRefs) == 0 {
		tagRefs = []string{""}
	}
	occur := occurredAt
	if !sig.Timestamp.IsZero() {
		occur = sig.Timestamp
	}
	for _, tagRef := range tagRefs {
		impactID := ports.StableImpactID(authorID, event.HelpType, event.Action, event.IntersectionDimension, tagRef, authorImpactEvidenceSource)
		_ = s.authorImpactEvidence.Record(ctx, ports.AuthorImpactEvidenceRecord{
			AuthorID:              authorID,
			ImpactID:              impactID,
			SourceEventID:         evidenceSourceEventID(sig, tagRef),
			ActorID:               strings.TrimSpace(sig.UserID),
			ContentID:             strings.TrimSpace(sig.ContentID),
			ContentType:           strings.TrimSpace(sig.ContentType),
			HelpType:              event.HelpType,
			Action:                event.Action,
			IntersectionDimension: event.IntersectionDimension,
			TagRef:                tagRef,
			Source:                authorImpactEvidenceSource,
			OccurredAt:            occur,
		})
	}
}

// evidenceSourceEventID makes the idempotency key unique per (clientEventId,
// tagRef). An empty client event id lets the store fall back to a deterministic
// synthetic key so replays still dedupe.
func evidenceSourceEventID(sig rtrec.BehaviorSignal, tagRef string) string {
	base := strings.TrimSpace(sig.ClientEventID)
	if base == "" {
		return ""
	}
	if strings.TrimSpace(tagRef) == "" {
		return base
	}
	return base + "|" + tagRef
}

func behaviorTagsFromAny(v any) []string {
	switch vv := v.(type) {
	case []string:
		return vv
	case []any:
		out := make([]string, 0, len(vv))
		for _, item := range vv {
			if s, ok := item.(string); ok && strings.TrimSpace(s) != "" {
				out = append(out, s)
			}
		}
		return out
	default:
		return nil
	}
}

func firstNonEmptyLocal(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

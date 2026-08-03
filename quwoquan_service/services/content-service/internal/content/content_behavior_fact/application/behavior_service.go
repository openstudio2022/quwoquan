package behavior

import (
	"context"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtimpact "quwoquan_service/runtime/impact"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/services/content-service/generated/content/post"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	behaviormodel "quwoquan_service/services/content-service/internal/content/content_behavior_fact/domain/model"
	behaviorports "quwoquan_service/services/content-service/internal/content/content_behavior_fact/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type BehaviorEventInput struct {
	ClientEventID string `json:"clientEventId"`
	OccurredAt    string `json:"occurredAt"`
	State         string `json:"state"`
	UserID        string `json:"userId"`
	// PersonaID 只由 HTTP verified principal 注入，禁止客户端通过行为 payload 伪造。
	PersonaID     string `json:"-"`
	DeviceActorID string `json:"deviceActorId"`
	SessionID     string `json:"sessionId"`
	FeedSessionID string `json:"feedSessionId"`
	// TaxonomyReleaseID 是 onboarding_interest 目录与 taxonomy snapshot 的
	// 唯一不可变发布身份；其他行为忽略。
	TaxonomyReleaseID string `json:"taxonomyReleaseId"`
	// 契约单轨：对象引用唯一键 contentId、动作唯一键 action、停留唯一键
	// duration（秒）、序位唯一键 position；旧键 postId/type/dwellMs/feedPosition
	// 已随 behaviors.yaml 收敛删除，服务端不再双读。
	ContentID       string   `json:"contentId"`
	Action          string   `json:"action"`
	ContentType     string   `json:"contentType"`
	ObjectID        string   `json:"objectId"`
	ObjectKind      string   `json:"objectKind"`
	DisplayName     string   `json:"displayName"`
	SourceSurface   string   `json:"sourceSurface"`
	Tags            []string `json:"tagRefs"`
	Duration        float64  `json:"duration"`
	Position        int      `json:"position"`
	AuthorID        string   `json:"authorId"`
	ReferralSource  string   `json:"referralSource"`
	EngagementDepth int      `json:"engagementDepth"`
	ConsumedRatio   float64  `json:"consumedRatio"`
	TotalUnits      int      `json:"totalUnits"`
	EffectivePlayMS int      `json:"effectivePlayMs"`
	EntityRefs      []string `json:"entityRefs"`
	FeedRequestID   string   `json:"feedRequestId"`
	CommentLength   int      `json:"commentLength"`
	// feed 下发频道与唯一策略摘要，全事件携带并贯穿 HotPath / 事件存储 / 特征投影。
	ChannelID       string `json:"channelId"`
	PolicyDigest    string `json:"policyDigest"`
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

// OnboardingInterestTaxonomyValidationInput carries one canonicalized
// onboarding_interest event into the request-level anti-forgery boundary.
type OnboardingInterestTaxonomyValidationInput struct {
	TaxonomyReleaseID string
	TagRefs           []string
}

// OnboardingInterestTaxonomyValidator validates every onboarding_interest event
// in a request together. Implementations must preflight the released catalog
// identity, dimension roots, quantity and active leaf status before any dedup,
// HotPath or raw-event side effect is written.
type OnboardingInterestTaxonomyValidator interface {
	ValidateOnboardingInterestBatch(
		ctx context.Context,
		inputs []OnboardingInterestTaxonomyValidationInput,
	) error
}

type BehaviorService struct {
	hotPath              rtrec.SignalProcessor
	feedbackIngestor     rtrec.FeedbackIngestor
	feedbackReplayReader rtrec.FeedbackReplayReader
	store                postports.DetailReader
	eventStore           behaviorports.FactStore
	wishlistStore        ports.WishlistEventStore
	wishlistReader       ports.WishlistStateReader
	metricsStore         behaviorports.DailyMetricsStore
	sessionInvalid       func(userID, sessionID string)
	patchEmitter         *rtrec.FeedPatchEmitter
	intersectionFeedback IntersectionFeedbackSink
	onboardingTaxonomy   OnboardingInterestTaxonomyValidator
}

type BehaviorServiceOption func(*BehaviorService)

func WithSessionCacheInvalidator(fn func(userID, sessionID string)) BehaviorServiceOption {
	return func(s *BehaviorService) { s.sessionInvalid = fn }
}

func WithBehaviorEventStore(es behaviorports.FactStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.eventStore = es }
}

func WithWishlistEventStore(store ports.WishlistEventStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.wishlistStore = store }
}

func WithWishlistStateReader(reader ports.WishlistStateReader) BehaviorServiceOption {
	return func(s *BehaviorService) { s.wishlistReader = reader }
}

func WithDailyMetricsStore(ms behaviorports.DailyMetricsStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.metricsStore = ms }
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

func WithOnboardingInterestTaxonomyValidator(
	validator OnboardingInterestTaxonomyValidator,
) BehaviorServiceOption {
	return func(s *BehaviorService) {
		if validator != nil {
			s.onboardingTaxonomy = validator
		}
	}
}

func NewBehaviorService(hotPath rtrec.SignalProcessor, store postports.DetailReader, opts ...BehaviorServiceOption) *BehaviorService {
	svc := &BehaviorService{
		hotPath: hotPath,
		store:   store,
	}
	if ingestor, ok := hotPath.(rtrec.FeedbackIngestor); ok {
		svc.feedbackIngestor = ingestor
	}
	if replayReader, ok := hotPath.(rtrec.FeedbackReplayReader); ok {
		svc.feedbackReplayReader = replayReader
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
	replayed, err := s.isFullyAcceptedOnboardingReplay(ctx, events)
	if err != nil {
		return err
	}
	if replayed {
		return nil
	}
	onboardingTagRefs, err := s.preflightOnboardingInterestBatch(ctx, events)
	if err != nil {
		return err
	}
	signals := make([]rtrec.BehaviorSignal, 0, len(events))
	batchObservedAt := time.Now().UTC()
	batchUserID := ""
	batchFeedSessionID := ""
	eventTimes := make([]time.Time, 0, len(events))
	acceptedInputs := make([]BehaviorEventInput, 0, len(events))
	for eventIndex, eventInput := range events {
		clientEventID := strings.TrimSpace(eventInput.ClientEventID)
		if clientEventID == "" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "clientEventId 必填", "clientEventId is required for idempotency")
		}
		occurredAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(eventInput.OccurredAt))
		if err != nil ||
			occurredAt.Before(batchObservedAt.Add(-72*time.Hour)) ||
			occurredAt.After(batchObservedAt.Add(5*time.Minute)) {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "occurredAt 非法", "occurredAt must be within the accepted replay window")
		}
		occurredAt = occurredAt.UTC()
		action := normalizeBehaviorAction(eventInput)
		if _, ok := supportedBehaviorActions[action]; !ok {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "action 不支持", "unsupported action: "+eventInput.Action)
		}
		if action == "impression" {
			state := strings.TrimSpace(eventInput.State)
			if state != "visible" && state != "impressed" {
				return rterr.NewInvalidArgument(
					rterr.ModuleContent,
					"曝光状态不完整",
					"impression requires canonical state visible or impressed",
				)
			}
		}
		userID := identity.NormalizeAnonymousPersonaID(eventInput.UserID)
		contentID := strings.TrimSpace(eventInput.ContentID)
		if contentID == "" && isWishlistAction(action) {
			contentID = strings.TrimSpace(firstNonEmptyLocal(eventInput.ObjectID, firstString(eventInput.EntityRefs)))
		}
		// assistant_interest / onboarding_interest（仅 tagRefs）与
		// intersection_feedback（subjectId 承载对象）不绑定 post。
		if contentID == "" && action != "assistant_interest" && action != "onboarding_interest" &&
			action != "intersection_feedback" && !isWishlistAction(action) {
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
		tags := eventInput.Tags
		if action == "onboarding_interest" {
			tags = onboardingTagRefs[eventIndex]
		}
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
		// 影响力计数只能由现存 Post 的权威 author/tag 事实驱动。行为 payload
		// 里的 authorId / intersectionTagRefs 仅是归因提示，绝不能用来增加他人的
		// 影响计数。关系、圈子和助手类 action 必须由各自确认事件/outbox 投影，不在
		// 这个 Post 行为入口伪造 AuthorImpact；其交集维度仍是本次行为的真实归因，
		// 必须继续进入转化指标与 raw event。
		impactDimension := strings.TrimSpace(eventInput.IntersectionDimension)
		impactTags := eventInput.IntersectionTagRefs
		if _, producesImpact := rtimpact.BehaviorActionToHelpType[action]; producesImpact {
			if authorImpactActionRequiresPost(action) {
				authoritativePost, found := s.store.FindByID(ctx, contentID)
				if !found || authoritativePost == nil {
					return rterr.NewInvalidArgument(
						rterr.ModuleContent,
						"影响力行为必须关联有效内容",
						"impact-bearing behavior requires an existing Post",
					)
				}
				post = authoritativePost
				authorID = strings.TrimSpace(post.AuthorId)
				contentType = strings.TrimSpace(post.ContentType)
				impactDimension = "content"
				impactTags = behaviorTagsFromAny(post.TagRefs)
			} else {
				authorID = ""
				impactTags = nil
			}
		}
		if action == "hide_author" && authorID == "" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "authorId 必填", "hide_author requires authorId")
		}
		if action == "hide_content_type" && contentType == "" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "contentType 必填", "hide_content_type requires contentType")
		}
		if action == "effective_play" {
			if strings.TrimSpace(eventInput.SessionID) == "" {
				return rterr.NewInvalidArgument(
					rterr.ModuleContent,
					"播放会话标识缺失",
					"effective_play requires sessionId",
				)
			}
			if strings.TrimSpace(eventInput.State) != "foreground_visible_playing" {
				return rterr.NewInvalidArgument(
					rterr.ModuleContent,
					"有效播放证据不完整",
					"effective_play requires foreground_visible_playing state",
				)
			}
			if eventInput.EffectivePlayMS < 5000 ||
				eventInput.TotalUnits <= 0 ||
				eventInput.EffectivePlayMS > eventInput.TotalUnits*1000 {
				return rterr.NewInvalidArgument(
					rterr.ModuleContent,
					"有效播放时长不合法",
					"effective_play duration is outside the trusted boundary",
				)
			}
			duration = float64(eventInput.EffectivePlayMS) / 1000
		}
		policyDigest := strings.TrimSpace(eventInput.PolicyDigest)
		if policyDigest != "" && !isCanonicalPolicyDigest(policyDigest) {
			return rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"推荐策略归因无效",
				"policyDigest must be a canonical sha256 digest",
			)
		}
		feedPos := eventInput.Position
		if action == "effective_play" {
			clientEventID = strings.Join(
				[]string{"effective_play", userID, eventInput.SessionID, contentID},
				":",
			)
		}
		signal := rtrec.BehaviorSignal{
			ClientEventID:          clientEventID,
			State:                  strings.TrimSpace(eventInput.State),
			UserID:                 userID,
			PersonaID:              strings.TrimSpace(eventInput.PersonaID),
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
			EffectivePlayMS:        eventInput.EffectivePlayMS,
			EntityRefs:             eventInput.EntityRefs,
			FeedRequestID:          strings.TrimSpace(eventInput.FeedRequestID),
			Position:               feedPos,
			CommentLength:          eventInput.CommentLength,
			ChannelID:              strings.TrimSpace(eventInput.ChannelID),
			PolicyDigest:           policyDigest,
			RecallPath:             strings.TrimSpace(eventInput.RecallPath),
			ContentVertical:        strings.TrimSpace(eventInput.ContentVertical),
			SupplySource:           strings.TrimSpace(eventInput.SupplySource),
			IntersectionDimension:  impactDimension,
			IntersectionTagRefs:    impactTags,
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
		eventTimes = append(eventTimes, occurredAt)
		acceptedInputs = append(acceptedInputs, eventInput)
		// 交集负反馈冷却（F 推荐差异化）：subjectId/feedbackKind 已在上文校验、dedup 已由
		// AcceptEvent 完成（重复事件在上方 continue 跳过），此处对唯一有效事件写交集冷却。
		// ReportNegativeFeedback 内部对 Redis 降级 → 返回 nil 不阻断（同 ReportExposure 语义）；
		// sink 未注入时安全跳过。
		if action == "intersection_feedback" && s.intersectionFeedback != nil {
			if err := s.intersectionFeedback.ReportNegativeFeedback(
				ctx,
				userID,
				strings.TrimSpace(eventInput.SubjectID),
				strings.TrimSpace(eventInput.FeedbackKind),
			); err != nil {
				return err
			}
		}
		if isWishlistAction(action) && s.wishlistStore != nil {
			if err := s.wishlistStore.UpsertWishlistEvent(ctx, wishlistEventFromInput(eventInput, userID, contentID, action, occurredAt)); err != nil {
				return err
			}
		}
		if batchUserID == "" {
			batchUserID = userID
		}
		if batchFeedSessionID == "" {
			batchFeedSessionID = strings.TrimSpace(eventInput.FeedSessionID)
		}
	}
	if err := s.hotPath.ProcessSignalBatch(ctx, signals); err != nil {
		return err
	}
	for _, signal := range signals {
		rtrec.RecordBehaviorMetric(signal)
	}
	if s.eventStore != nil {
		rawEvents := make([]behaviormodel.Fact, len(signals))
		for i, sig := range signals {
			eventOccurredAt := eventTimes[i]
			impactHelpType := ""
			if helpType, ok := rtimpact.BehaviorActionToHelpType[sig.Action]; ok && sig.AuthorID != "" {
				impactHelpType = helpType
			}
			rawEvents[i] = behaviormodel.Fact{
				ClientEventID:          sig.ClientEventID,
				State:                  sig.State,
				UserID:                 sig.UserID,
				DeviceActorID:          sig.DeviceActorID,
				SessionID:              sig.SessionID,
				ContentID:              sig.ContentID,
				Action:                 sig.Action,
				ContentType:            sig.ContentType,
				ObjectID:               strings.TrimSpace(acceptedInputs[i].ObjectID),
				ObjectKind:             strings.TrimSpace(acceptedInputs[i].ObjectKind),
				DisplayName:            strings.TrimSpace(acceptedInputs[i].DisplayName),
				SourceSurface:          strings.TrimSpace(acceptedInputs[i].SourceSurface),
				TaxonomyReleaseID:      strings.TrimSpace(acceptedInputs[i].TaxonomyReleaseID),
				Tags:                   sig.Tags,
				Duration:               sig.Duration,
				AuthorID:               sig.AuthorID,
				ImpactHelpType:         impactHelpType,
				ReferralSource:         sig.ReferralSource,
				EngagementDepth:        sig.EngagementDepth,
				ConsumedRatio:          sig.ConsumedRatio,
				TotalUnits:             sig.TotalUnits,
				EffectivePlayMS:        sig.EffectivePlayMS,
				EntityRefs:             sig.EntityRefs,
				FeedRequestID:          strings.TrimSpace(acceptedInputs[i].FeedRequestID),
				Position:               sig.Position,
				CommentLength:          sig.CommentLength,
				ChannelID:              sig.ChannelID,
				PolicyDigest:           sig.PolicyDigest,
				RecallPath:             sig.RecallPath,
				ContentVertical:        sig.ContentVertical,
				SupplySource:           sig.SupplySource,
				IntersectionDimension:  sig.IntersectionDimension,
				IntersectionTagRefs:    sig.IntersectionTagRefs,
				IntersectionID:         sig.IntersectionID,
				IntersectionClass:      sig.IntersectionClass,
				IntersectionSourceRef:  strings.TrimSpace(acceptedInputs[i].IntersectionSourceRef),
				IntersectionEvidenceID: strings.TrimSpace(acceptedInputs[i].IntersectionEvidenceID),
				OccurredAt:             eventOccurredAt.Format(time.RFC3339),
				CreatedAt:              eventOccurredAt,
			}
		}
		for _, fact := range rawEvents {
			if err := fact.Validate(); err != nil {
				return generated.AppErrorFromInvalidArgument(err.Error())
			}
		}
		if err := s.eventStore.InsertBatch(ctx, rawEvents); err != nil {
			return err
		}
	}
	if s.metricsStore != nil {
		for i, sig := range signals {
			dateStr := eventTimes[i].Format("2006-01-02")
			dwellMs := int64(sig.Duration * 1000)
			if err := s.metricsStore.IncrementMetric(ctx, dateStr, behaviorports.DailyMetricDimensionAction, sig.Action, sig.Action, dwellMs, sig.EngagementDepth); err != nil {
				return err
			}
			if sig.ContentID != "" {
				if err := s.metricsStore.IncrementMetric(ctx, dateStr, behaviorports.DailyMetricDimensionContent, sig.ContentID, sig.Action, dwellMs, sig.EngagementDepth); err != nil {
					return err
				}
			}
			if sig.AuthorID != "" {
				if err := s.metricsStore.IncrementMetric(ctx, dateStr, behaviorports.DailyMetricDimensionAuthor, sig.AuthorID, sig.Action, dwellMs, sig.EngagementDepth); err != nil {
					return err
				}
			}
			// 交集转化北极星（S6）：交集维度上有归因的行动（关注/进圈子/加联系人等）按维度累计，
			// 供「交集转化率 = 交集行动数 / 新增可解释交集数」按 dimension 下钻。
			if sig.IntersectionDimension != "" {
				if err := s.metricsStore.IncrementMetric(ctx, dateStr, behaviorports.DailyMetricDimensionIntersection, sig.IntersectionDimension, sig.Action, dwellMs, sig.EngagementDepth); err != nil {
					return err
				}
			}
		}
	}
	// ContentBehaviorFact 由对象存储与 typed stream 单轨发布；推荐反馈、长期
	// 特征与训练样本均由 recommendation-service 消费形成，Content 不再旁写。
	//
	// N0-4：SessionCache 的缓存 key 是 feed 读路径的 sessionId（FeedSession 滚动
	// UUID），signal.SessionID 是跨服务 trace sessionId（两套语义）。
	// 主动失效只能使用 feedSessionId；缺失时没有可命中的缓存身份，禁止以 trace
	// sessionId 猜测替代。
	if s.sessionInvalid != nil && batchUserID != "" && batchFeedSessionID != "" {
		s.sessionInvalid(batchUserID, batchFeedSessionID)
	}
	// 低风险实时推荐 patch（阶段七 §G）：在行为主链路全部成功后于安全边界发射。
	// best-effort，不影响行为写入结果；emitter 为 nil 时安全 no-op。
	s.patchEmitter.EmitForBehaviorBatch(ctx, signals)
	return nil
}

func isCanonicalPolicyDigest(value string) bool {
	const prefix = "sha256:"
	if !strings.HasPrefix(value, prefix) {
		return false
	}
	decoded, err := hex.DecodeString(strings.TrimPrefix(value, prefix))
	return err == nil && len(decoded) == 32
}

// isFullyAcceptedOnboardingReplay checks a complete batch against the same
// read-only idempotency receipts as AcceptEvent. A committed onboarding command
// must not be re-rejected merely because the taxonomy dependency later changes
// or becomes unavailable. Mixed/new batches continue to the fail-closed
// preflight below and cannot consume receipts before validation succeeds.
func (s *BehaviorService) isFullyAcceptedOnboardingReplay(
	ctx context.Context,
	events []BehaviorEventInput,
) (bool, error) {
	if s.feedbackReplayReader == nil {
		return false, nil
	}
	hasOnboardingInterest := false
	for _, event := range events {
		if normalizeBehaviorAction(event) == "onboarding_interest" {
			hasOnboardingInterest = true
			break
		}
	}
	if !hasOnboardingInterest {
		return false, nil
	}
	for _, event := range events {
		action := normalizeBehaviorAction(event)
		clientEventID := strings.TrimSpace(event.ClientEventID)
		if clientEventID == "" {
			return false, nil
		}
		userID := identity.NormalizeAnonymousPersonaID(event.UserID)
		contentID := strings.TrimSpace(event.ContentID)
		if contentID == "" && isWishlistAction(action) {
			contentID = strings.TrimSpace(
				firstNonEmptyLocal(event.ObjectID, firstString(event.EntityRefs)),
			)
		}
		if action == "effective_play" {
			clientEventID = strings.Join(
				[]string{"effective_play", userID, event.SessionID, contentID},
				":",
			)
		}
		accepted, err := s.feedbackReplayReader.HasAcceptedEvent(
			ctx,
			userID,
			clientEventID,
		)
		if err != nil {
			return false, err
		}
		if !accepted {
			return false, nil
		}
	}
	return true, nil
}

// preflightOnboardingInterestBatch is deliberately called before the event
// loop, whose first side effect is FeedbackIngestor.AcceptEvent. It ensures an
// invalid or unavailable taxonomy rejects the entire request without consuming
// idempotency keys, entering HotPath, or persisting raw facts.
func (s *BehaviorService) preflightOnboardingInterestBatch(
	ctx context.Context,
	events []BehaviorEventInput,
) (map[int][]string, error) {
	canonicalByEvent := make(map[int][]string)
	inputs := make([]OnboardingInterestTaxonomyValidationInput, 0)
	for index, event := range events {
		if normalizeBehaviorAction(event) != "onboarding_interest" {
			continue
		}
		tagRefs := canonicalOnboardingTagRefs(event.Tags)
		if len(tagRefs) == 0 {
			return nil, generated.AppErrorFromInvalidArgument(
				"onboarding_interest requires at least one canonical tagRef",
			)
		}
		canonicalByEvent[index] = tagRefs
		inputs = append(inputs, OnboardingInterestTaxonomyValidationInput{
			TaxonomyReleaseID: strings.TrimSpace(event.TaxonomyReleaseID),
			TagRefs:           tagRefs,
		})
	}
	if len(inputs) == 0 {
		return canonicalByEvent, nil
	}
	if s.onboardingTaxonomy == nil {
		return nil, generated.AppErrorFromRequiredDependencyUnavailable(
			"onboarding interest taxonomy validator is not configured",
		)
	}
	if err := s.onboardingTaxonomy.ValidateOnboardingInterestBatch(ctx, inputs); err != nil {
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return nil, appError
		}
		return nil, generated.AppErrorFromRequiredDependencyUnavailable(
			"onboarding interest taxonomy validator failed",
		)
	}
	return canonicalByEvent, nil
}

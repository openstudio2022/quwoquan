package application

import (
	"context"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/repository"
	"quwoquan_service/services/content-service/internal/domain/post/event"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
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
	UserID          string   `json:"userId"`
	DeviceActorID   string   `json:"deviceActorId"`
	SessionID       string   `json:"sessionId"`
	FeedSessionID   string   `json:"feedSessionId"`
	ContentID       string   `json:"contentId"`
	PostID          string   `json:"postId"`
	Action          string   `json:"action"`
	Type            string   `json:"type"`
	ContentType     string   `json:"contentType"`
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
	// 交集转化归因（S6）：触发交集行动（follow/join_circle/add_contact）的维度与路径制 tagRef。
	IntersectionDimension string   `json:"intersectionDimension"`
	IntersectionTagRefs   []string `json:"intersectionTagRefs"`
}

type BehaviorService struct {
	hotPath        rtrec.SignalProcessor
	store          persistence.PostRepository
	publisher      repository.EventPublisher
	projector      Projector
	feedback       *rtrec.FeedbackRecorder
	eventStore     persistence.BehaviorEventStore
	metricsStore   *persistence.DailyMetricsStore
	authorImpact   *persistence.AuthorImpactStore
	sessionInvalid func(userID, sessionID string)
}

type BehaviorServiceOption func(*BehaviorService)

func WithBehaviorEventPublisher(pub repository.EventPublisher) BehaviorServiceOption {
	return func(s *BehaviorService) { s.publisher = pub }
}

func WithBehaviorProjector(p Projector) BehaviorServiceOption {
	return func(s *BehaviorService) { s.projector = p }
}

func WithBehaviorFeedbackRecorder(f *rtrec.FeedbackRecorder) BehaviorServiceOption {
	return func(s *BehaviorService) { s.feedback = f }
}

func WithSessionCacheInvalidator(fn func(userID, sessionID string)) BehaviorServiceOption {
	return func(s *BehaviorService) { s.sessionInvalid = fn }
}

func WithBehaviorEventStore(es persistence.BehaviorEventStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.eventStore = es }
}

func WithDailyMetricsStore(ms *persistence.DailyMetricsStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.metricsStore = ms }
}

func WithAuthorImpactStore(store *persistence.AuthorImpactStore) BehaviorServiceOption {
	return func(s *BehaviorService) { s.authorImpact = store }
}

func NewBehaviorService(hotPath rtrec.SignalProcessor, store persistence.PostRepository, opts ...BehaviorServiceOption) *BehaviorService {
	svc := &BehaviorService{
		hotPath: hotPath,
		store:   store,
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
		userID := normalizeAnonymousSubAccountID(eventInput.UserID)
		contentID := strings.TrimSpace(firstNonEmptyLocal(eventInput.ContentID, eventInput.PostID))
		if contentID == "" && action != "assistant_interest" {
			return rterr.NewInvalidArgument(rterr.ModuleContent, "contentId 必填", "missing contentId")
		}
		duration := eventInput.Duration
		if duration == 0 && eventInput.DwellMs > 0 {
			duration = eventInput.DwellMs / 1000
		}
		tags := eventInput.Tags
		if len(tags) == 0 {
			if post, ok := s.store.FindByID(ctx, contentID); ok {
				tags = behaviorTagsFromAny(post.TagRefs)
			}
		}
		feedPos := eventInput.FeedPosition
		if feedPos == 0 && eventInput.Position > 0 {
			feedPos = eventInput.Position
		}
		signal := rtrec.BehaviorSignal{
			UserID:                userID,
			DeviceActorID:         strings.TrimSpace(eventInput.DeviceActorID),
			SessionID:             strings.TrimSpace(eventInput.SessionID),
			FeedSessionID:         strings.TrimSpace(eventInput.FeedSessionID),
			ContentID:             contentID,
			Action:                action,
			ContentType:           strings.TrimSpace(eventInput.ContentType),
			Tags:                  tags,
			Duration:              duration,
			Timestamp:             occurredAt,
			AuthorID:              strings.TrimSpace(eventInput.AuthorID),
			ReferralSource:        strings.TrimSpace(eventInput.ReferralSource),
			EngagementDepth:       eventInput.EngagementDepth,
			ConsumedRatio:         eventInput.ConsumedRatio,
			TotalUnits:            eventInput.TotalUnits,
			EntityRefs:            eventInput.EntityRefs,
			FeedRequestID:         strings.TrimSpace(eventInput.FeedRequestID),
			Position:              feedPos,
			CommentLength:         eventInput.CommentLength,
			IntersectionDimension: strings.TrimSpace(eventInput.IntersectionDimension),
			IntersectionTagRefs:   eventInput.IntersectionTagRefs,
		}
		signals = append(signals, signal)
		projectedEvents = append(projectedEvents, map[string]any{
			"userId":                userID,
			"deviceActorId":         signal.DeviceActorID,
			"sessionId":             signal.SessionID,
			"contentId":             contentID,
			"action":                action,
			"contentType":           signal.ContentType,
			"tagRefs":               append([]string(nil), tags...),
			"duration":              duration,
			"timestamp":             occurredAt.Format(time.RFC3339),
			"authorId":              signal.AuthorID,
			"referralSource":        signal.ReferralSource,
			"engagementDepth":       signal.EngagementDepth,
			"consumedRatio":         signal.ConsumedRatio,
			"totalUnits":            signal.TotalUnits,
			"entityRefs":            signal.EntityRefs,
			"feedRequestId":         strings.TrimSpace(eventInput.FeedRequestID),
			"feedPosition":          feedPos,
			"commentLength":         eventInput.CommentLength,
			"intersectionDimension": signal.IntersectionDimension,
			"intersectionTagRefs":   signal.IntersectionTagRefs,
		})
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
		rawEvents := make([]persistence.RawBehaviorEvent, len(signals))
		for i, sig := range signals {
			rawEvents[i] = persistence.RawBehaviorEvent{
				UserID:                sig.UserID,
				DeviceActorID:         sig.DeviceActorID,
				SessionID:             sig.SessionID,
				ContentID:             sig.ContentID,
				Action:                sig.Action,
				Tags:                  sig.Tags,
				Duration:              sig.Duration,
				AuthorID:              sig.AuthorID,
				ReferralSource:        sig.ReferralSource,
				EngagementDepth:       sig.EngagementDepth,
				ConsumedRatio:         sig.ConsumedRatio,
				TotalUnits:            sig.TotalUnits,
				EntityRefs:            sig.EntityRefs,
				FeedRequestID:         strings.TrimSpace(events[i].FeedRequestID),
				IntersectionDimension: sig.IntersectionDimension,
				IntersectionTagRefs:   sig.IntersectionTagRefs,
				OccurredAt:            occurredAt.Format(time.RFC3339),
				CreatedAt:             occurredAt,
			}
		}
		_ = s.eventStore.InsertBatch(ctx, rawEvents)
	}
	if s.metricsStore != nil {
		dateStr := occurredAt.Format("2006-01-02")
		for _, sig := range signals {
			dwellMs := int64(sig.Duration * 1000)
			_ = s.metricsStore.IncrementMetric(ctx, dateStr, persistence.DailyMetricDimensionAction, sig.Action, sig.Action, dwellMs, sig.EngagementDepth)
			if sig.ContentID != "" {
				_ = s.metricsStore.IncrementMetric(ctx, dateStr, persistence.DailyMetricDimensionContent, sig.ContentID, sig.Action, dwellMs, sig.EngagementDepth)
			}
			if sig.AuthorID != "" {
				_ = s.metricsStore.IncrementMetric(ctx, dateStr, persistence.DailyMetricDimensionAuthor, sig.AuthorID, sig.Action, dwellMs, sig.EngagementDepth)
			}
			// 交集转化北极星（S6）：交集维度上有归因的行动（关注/进圈子/加联系人等）按维度累计，
			// 供「交集转化率 = 交集行动数 / 新增可解释交集数」按 dimension 下钻。
			if sig.IntersectionDimension != "" {
				_ = s.metricsStore.IncrementMetric(ctx, dateStr, persistence.DailyMetricDimensionIntersection, sig.IntersectionDimension, sig.Action, dwellMs, sig.EngagementDepth)
			}
		}
	}
	if s.authorImpact != nil {
		for _, sig := range signals {
			if event := authorImpactEventFromSignal(sig, occurredAt); event.AuthorID != "" {
				_ = s.authorImpact.Record(ctx, event)
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
		if err := s.projector.Project(ctx, ProjectorEvent{
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

func authorImpactEventFromSignal(signal rtrec.BehaviorSignal, occurredAt time.Time) persistence.AuthorImpactEvent {
	helpType := ""
	switch signal.Action {
	case "follow", "add_contact":
		helpType = persistence.AuthorImpactHelpRelationship
	case "join_circle":
		helpType = persistence.AuthorImpactHelpCommunity
	case "author_view", "entity_page_view", "content_depth", "play_progress", "like", "comment":
		helpType = persistence.AuthorImpactHelpDecision
	case "share":
		helpType = persistence.AuthorImpactHelpSpread
	case "assistant_interest":
		helpType = persistence.AuthorImpactHelpKnowledge
	default:
		return persistence.AuthorImpactEvent{}
	}
	return persistence.AuthorImpactEvent{
		AuthorID:              strings.TrimSpace(signal.AuthorID),
		Action:                strings.TrimSpace(signal.Action),
		HelpType:              helpType,
		IntersectionDimension: strings.TrimSpace(signal.IntersectionDimension),
		IntersectionTagRefs:   signal.IntersectionTagRefs,
		Source:                "behavior",
		OccurredAt:            occurredAt,
	}
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

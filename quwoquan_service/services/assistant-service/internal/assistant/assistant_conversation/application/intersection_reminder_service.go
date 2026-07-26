package application

import (
	"context"
	"log/slog"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
)

type IntersectionReminderReason struct {
	ReasonID    string
	UserID      string
	TargetID    string
	TargetName  string
	Dimension   string
	PrimaryText string
	IsFact      bool
	CreatedAt   time.Time
}

type IntersectionInboxReader interface {
	ListNewIntersectionReasons(ctx context.Context, userID string, since time.Time, limit int) ([]IntersectionReminderReason, error)
}

type IntersectionReminderTickInput struct {
	UserID string `json:"userId"`
	Since  string `json:"since,omitempty"`
	Limit  int    `json:"limit,omitempty"`
}

type IntersectionReminderTickResult struct {
	ProcessedCount    int      `json:"processedCount"`
	CreatedMessageIDs []string `json:"createdMessageIds"`
}

type IntersectionReminderPolicy struct {
	DefaultLimit int `json:"defaultLimit"`
	MaxLimit     int `json:"maxLimit"`
}

func defaultIntersectionReminderPolicy() IntersectionReminderPolicy {
	return IntersectionReminderPolicy{DefaultLimit: 20, MaxLimit: 50}
}

func normalizeIntersectionReminderPolicy(policy IntersectionReminderPolicy) IntersectionReminderPolicy {
	if policy.DefaultLimit <= 0 {
		policy.DefaultLimit = 20
	}
	if policy.MaxLimit <= 0 {
		policy.MaxLimit = 50
	}
	if policy.DefaultLimit > policy.MaxLimit {
		policy.DefaultLimit = policy.MaxLimit
	}
	return policy
}

func (s *AssistantService) TickIntersectionReminders(ctx context.Context, input IntersectionReminderTickInput) (_ IntersectionReminderTickResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.TickIntersectionReminders",
		attribute.String("user.id", input.UserID),
		attribute.Int("list.limit", input.Limit))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.intersectionInbox == nil {
		return IntersectionReminderTickResult{}, rterr.NewUnavailable(rterr.ModuleAssistant, "交集收件箱不可用", "intersection inbox reader is not configured")
	}
	if s.notificationMessages == nil {
		return IntersectionReminderTickResult{}, rterr.NewUnavailable(rterr.ModuleAssistant, "应用消息通道不可用", "notification app message command writer is not configured")
	}
	userID := strings.TrimSpace(input.UserID)
	if userID == "" {
		return IntersectionReminderTickResult{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	limit := input.Limit
	policy := normalizeIntersectionReminderPolicy(s.intersectionReminderPolicy)
	if limit <= 0 {
		limit = policy.DefaultLimit
	}
	if limit > policy.MaxLimit {
		limit = policy.MaxLimit
	}
	since := time.Time{}
	if raw := strings.TrimSpace(input.Since); raw != "" {
		parsed, err := time.Parse(time.RFC3339, raw)
		if err != nil {
			return IntersectionReminderTickResult{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "since 无效", err.Error())
		}
		since = parsed.UTC()
	}
	reasons, err := s.intersectionInbox.ListNewIntersectionReasons(ctx, userID, since, limit)
	if err != nil {
		return IntersectionReminderTickResult{}, err
	}
	result := IntersectionReminderTickResult{CreatedMessageIDs: []string{}}
	for _, reason := range reasons {
		reason = normalizeIntersectionReminderReason(reason, userID)
		if reason.ReasonID == "" || !reason.IsFact || reason.PrimaryText == "" {
			continue
		}
		if !s.claimIntersectionReminder(ctx, reason.ReasonID) {
			continue
		}
		message, err := s.publishNotificationAppMessage(ctx, NotificationAppMessageCommand{
			IdempotencyKey: "assistant:intersection-reminder:" + reason.ReasonID,
			UserID:         userID,
			MessageType:    "assistant",
			Source:         "assistant/proactive_intersection",
			SourceID:       reason.ReasonID,
			Destination:    NotificationAppMessageDestination{Type: "user", ID: userID},
			Title:          "小趣提醒",
			Summary:        intersectionReminderSummary(reason),
			Target: NotificationAppMessageTarget{
				TargetType: "route",
				TargetID:   "myIntersections",
				RouteID:    "myIntersections",
				RoutePath:  "/profile/intersections",
				Dimension:  reason.Dimension,
			},
			Provenance: NotificationAppMessageProvenance{
				MatchedSegments: []string{reason.Dimension},
				LifecycleStage:  "intersection_new",
			},
		})
		if err != nil {
			return IntersectionReminderTickResult{}, err
		}
		result.ProcessedCount++
		result.CreatedMessageIDs = append(result.CreatedMessageIDs, message.MessageID)
	}
	return result, nil
}

func normalizeIntersectionReminderReason(reason IntersectionReminderReason, userID string) IntersectionReminderReason {
	reason.ReasonID = strings.TrimSpace(reason.ReasonID)
	reason.UserID = strings.TrimSpace(reason.UserID)
	if reason.UserID == "" {
		reason.UserID = userID
	}
	reason.TargetID = strings.TrimSpace(reason.TargetID)
	reason.TargetName = strings.TrimSpace(reason.TargetName)
	reason.Dimension = strings.TrimSpace(reason.Dimension)
	reason.PrimaryText = strings.TrimSpace(reason.PrimaryText)
	return reason
}

func intersectionReminderSummary(reason IntersectionReminderReason) string {
	name := reason.TargetName
	if name == "" {
		name = reason.TargetID
	}
	if name == "" {
		return "你有了新的交集：" + reason.PrimaryText
	}
	return "你和" + name + "有了新的交集：" + reason.PrimaryText
}

// claimIntersectionReminder 以 Redis SetNX + TTL 领取交集提醒租约
// （key 契约见 skill_subscription/storage.yaml）。语义同 claimSubscriptionTick。
func (s *AssistantService) claimIntersectionReminder(ctx context.Context, reasonID string) bool {
	key := strings.TrimSpace(reasonID)
	if key == "" || s.cache == nil {
		return false
	}
	acquired, err := s.cache.SetNX(ctx, "assistant:intersection:lease:"+key, "1", 5*time.Minute)
	if err != nil {
		slog.WarnContext(ctx, "assistant intersection reminder lease acquisition failed; skipping delivery",
			slog.String("reasonId", reasonID), slog.String("error", err.Error()))
		return false
	}
	return acquired
}

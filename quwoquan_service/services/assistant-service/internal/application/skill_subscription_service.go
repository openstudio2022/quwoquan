package application

import (
	"context"
	"strconv"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtid "quwoquan_service/runtime/id"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type SkillSubscriptionStore interface {
	CreateSkillSubscription(ctx context.Context, subscription assistant.SkillSubscription) (assistant.SkillSubscription, error)
	GetSkillSubscription(ctx context.Context, userID, subscriptionID string) (assistant.SkillSubscription, error)
	ListSkillSubscriptions(ctx context.Context, userID, status string, limit int) ([]assistant.SkillSubscription, error)
	UpdateSkillSubscriptionStatus(ctx context.Context, userID, subscriptionID, status string, updatedAt time.Time) (assistant.SkillSubscription, error)
}

func (s *AssistantService) CreateSkillSubscription(ctx context.Context, userID string, input assistant.CreateSkillSubscriptionInput) (_ assistant.SkillSubscription, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.CreateSkillSubscription",
		attribute.String("user.id", userID),
		attribute.String("skill.id", input.SkillID))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.subscriptions == nil {
		return assistant.SkillSubscription{}, rterr.NewUnavailable(rterr.ModuleAssistant, "订阅存储不可用", "skill subscription store is not configured")
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	normalized, err := s.normalizeSkillSubscriptionInput(userID, input)
	if err != nil {
		return assistant.SkillSubscription{}, err
	}
	return s.subscriptions.CreateSkillSubscription(ctx, normalized)
}

func (s *AssistantService) ListSkillSubscriptions(ctx context.Context, userID string, status string, limit int) (_ assistant.SkillSubscriptionListView, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ListSkillSubscriptions",
		attribute.String("user.id", userID),
		attribute.String("subscription.status", status))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.subscriptions == nil {
		return assistant.SkillSubscriptionListView{}, rterr.NewUnavailable(rterr.ModuleAssistant, "订阅存储不可用", "skill subscription store is not configured")
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return assistant.SkillSubscriptionListView{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	items, err := s.subscriptions.ListSkillSubscriptions(ctx, userID, strings.TrimSpace(status), limit)
	if err != nil {
		return assistant.SkillSubscriptionListView{}, err
	}
	return assistant.SkillSubscriptionListView{Items: items}, nil
}

func (s *AssistantService) GetSkillSubscription(ctx context.Context, userID, subscriptionID string) (_ assistant.SkillSubscription, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.GetSkillSubscription",
		attribute.String("subscription.id", subscriptionID))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.subscriptions == nil {
		return assistant.SkillSubscription{}, rterr.NewUnavailable(rterr.ModuleAssistant, "订阅存储不可用", "skill subscription store is not configured")
	}
	return s.subscriptions.GetSkillSubscription(ctx, strings.TrimSpace(userID), strings.TrimSpace(subscriptionID))
}

func (s *AssistantService) UpdateSkillSubscriptionStatus(ctx context.Context, userID, subscriptionID string, input assistant.UpdateSkillSubscriptionStatusInput) (_ assistant.SkillSubscription, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.UpdateSkillSubscriptionStatus",
		attribute.String("subscription.id", subscriptionID),
		attribute.String("subscription.status", input.Status))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.subscriptions == nil {
		return assistant.SkillSubscription{}, rterr.NewUnavailable(rterr.ModuleAssistant, "订阅存储不可用", "skill subscription store is not configured")
	}
	status, err := normalizeSubscriptionStatus(input.Status)
	if err != nil {
		return assistant.SkillSubscription{}, err
	}
	return s.subscriptions.UpdateSkillSubscriptionStatus(ctx, strings.TrimSpace(userID), strings.TrimSpace(subscriptionID), status, s.now())
}

func (s *AssistantService) TickSkillSubscriptionCron(ctx context.Context, input assistant.SkillSubscriptionCronTickInput) (_ assistant.SkillSubscriptionCronTickResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.TickSkillSubscriptionCron")
	defer func() { rtobs.EndSpan(span, err) }()

	if s.subscriptions == nil {
		return assistant.SkillSubscriptionCronTickResult{}, rterr.NewUnavailable(rterr.ModuleAssistant, "订阅存储不可用", "skill subscription store is not configured")
	}
	if s.appMessages == nil {
		return assistant.SkillSubscriptionCronTickResult{}, rterr.NewUnavailable(rterr.ModuleAssistant, "应用消息通道不可用", "app message store is not configured")
	}
	now := s.now()
	if raw := strings.TrimSpace(input.Now); raw != "" {
		parsed, err := time.Parse(time.RFC3339, raw)
		if err != nil {
			return assistant.SkillSubscriptionCronTickResult{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "now 无效", err.Error())
		}
		now = parsed.UTC()
	}
	items, err := s.subscriptions.ListSkillSubscriptions(ctx, "", assistant.SkillSubscriptionStatusActive, 100)
	if err != nil {
		return assistant.SkillSubscriptionCronTickResult{}, err
	}
	result := assistant.SkillSubscriptionCronTickResult{
		CreatedTurnIDs:    []string{},
		CreatedMessageIDs: []string{},
	}
	for _, subscription := range items {
		if !cronMatchesMinute(subscription.Trigger.Cron, now) {
			continue
		}
		if !s.claimSubscriptionTick(subscription.SubscriptionID, now) {
			continue
		}
		turn, message, err := s.createProactiveTurnMessage(ctx, subscription, now)
		if err != nil {
			return assistant.SkillSubscriptionCronTickResult{}, err
		}
		result.ProcessedCount++
		result.CreatedTurnIDs = append(result.CreatedTurnIDs, turn.TurnID)
		result.CreatedMessageIDs = append(result.CreatedMessageIDs, message.MessageID)
	}
	return result, nil
}

func (s *AssistantService) normalizeSkillSubscriptionInput(userID string, input assistant.CreateSkillSubscriptionInput) (assistant.SkillSubscription, error) {
	skillID := strings.TrimSpace(input.SkillID)
	if skillID == "" {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "skillId 不能为空", "missing skillId")
	}
	trigger := input.Trigger
	trigger.Type = strings.TrimSpace(trigger.Type)
	if trigger.Type == "" {
		trigger.Type = "cron"
	}
	if trigger.Type != "cron" {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "M8 仅支持 cron trigger", "unsupported trigger type")
	}
	trigger.Cron = strings.TrimSpace(trigger.Cron)
	if !isSupportedCron(trigger.Cron) {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "cron 表达式无效", "unsupported cron expression")
	}
	destination := input.Destination
	destination.DestinationType = strings.TrimSpace(destination.DestinationType)
	if destination.DestinationType == "" {
		destination.DestinationType = "user"
	}
	destination.DestinationID = strings.TrimSpace(destination.DestinationID)
	if destination.DestinationID == "" {
		destination.DestinationID = userID
	}
	if destination.DestinationType != "user" {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "M8 仅支持 user destination", "unsupported destination type")
	}
	searchPlan := input.SearchQueryPlan
	searchPlan.RawText = strings.TrimSpace(searchPlan.RawText)
	searchPlan.Queries = compactStrings(searchPlan.Queries)
	if len(searchPlan.Queries) == 0 && searchPlan.RawText != "" {
		searchPlan.Queries = []string{searchPlan.RawText}
	}
	subscriptionID, err := rtid.Generate(rtid.PrefixSkillSubscription)
	if err != nil {
		return assistant.SkillSubscription{}, rterr.NewUnavailable(rterr.ModuleAssistant, "生成订阅 ID 失败", err.Error())
	}
	now := s.now()
	return assistant.SkillSubscription{
		SubscriptionID:  subscriptionID,
		Owner:           assistant.SkillSubscriptionOwner{OwnerType: "user", OwnerID: userID},
		CreatedByUserID: userID,
		SkillID:         skillID,
		DomainID:        strings.TrimSpace(input.DomainID),
		TagRefs:         compactStrings(input.TagRefs),
		Status:          assistant.SkillSubscriptionStatusActive,
		SearchQueryPlan: searchPlan,
		Trigger:         trigger,
		Destination:     destination,
		CreatedAt:       now,
		UpdatedAt:       now,
	}, nil
}

func (s *AssistantService) createProactiveTurnMessage(ctx context.Context, subscription assistant.SkillSubscription, now time.Time) (assistant.AssistantTurn, assistant.AppMessage, error) {
	proactive := BuildP0ProactiveSkillResult(subscription, now)
	conversation, err := s.CreateConversation(ctx, subscription.Owner.OwnerID, assistant.CreateConversationInput{
		Summary: "主动订阅：" + displaySkillName(subscription.SkillID),
	})
	if err != nil {
		return assistant.AssistantTurn{}, assistant.AppMessage{}, err
	}
	prompt := proactive.Prompt
	turn, err := s.CreateTurn(ctx, subscription.Owner.OwnerID, conversation.ConversationID, assistant.CreateTurnInput{
		TurnType: "proactive",
		SkillID:  subscription.SkillID,
		DomainID: subscription.DomainID,
		Input:    assistant.AssistantTurnInput{Text: prompt},
		Trigger: assistant.AssistantTurnTrigger{
			Type: "cron",
		},
	})
	if err != nil {
		return assistant.AssistantTurn{}, assistant.AppMessage{}, err
	}
	if _, err := s.BuildFakeTurnStream(ctx, subscription.Owner.OwnerID, turn.TurnID); err != nil {
		return assistant.AssistantTurn{}, assistant.AppMessage{}, err
	}
	message, err := s.CreateAppMessage(ctx, assistant.CreateAppMessageInput{
		UserID:      subscription.Owner.OwnerID,
		MessageType: "assistant",
		Source:      "assistant_turn",
		SourceID:    turn.TurnID,
		Destination: assistant.AppMessageDestination{Type: "user", ID: subscription.Owner.OwnerID},
		Title:       proactive.Title,
		Summary:     proactive.Summary,
		Target:      assistant.AppMessageTarget{TargetType: "assistant_turn", TargetID: turn.TurnID},
	})
	if err != nil {
		return assistant.AssistantTurn{}, assistant.AppMessage{}, err
	}
	return turn, message, nil
}

func (s *AssistantService) claimSubscriptionTick(subscriptionID string, now time.Time) bool {
	key := subscriptionID + ":" + now.UTC().Format("200601021504")
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.cronClaims[key] {
		return false
	}
	s.cronClaims[key] = true
	return true
}

func normalizeSubscriptionStatus(raw string) (string, error) {
	status := strings.TrimSpace(raw)
	switch status {
	case assistant.SkillSubscriptionStatusActive, assistant.SkillSubscriptionStatusPaused, assistant.SkillSubscriptionStatusArchived:
		return status, nil
	default:
		return "", rterr.NewInvalidArgument(rterr.ModuleAssistant, "订阅状态无效", "unsupported subscription status")
	}
}

func compactStrings(items []string) []string {
	out := make([]string, 0, len(items))
	seen := map[string]bool{}
	for _, item := range items {
		item = strings.TrimSpace(item)
		if item == "" || seen[item] {
			continue
		}
		seen[item] = true
		out = append(out, item)
	}
	return out
}

func isSupportedCron(raw string) bool {
	parts := strings.Fields(raw)
	if len(parts) != 5 {
		return false
	}
	return cronFieldSupported(parts[0], 0, 59) && cronFieldSupported(parts[1], 0, 23) && parts[2] == "*" && parts[3] == "*" && parts[4] == "*"
}

func cronMatchesMinute(raw string, now time.Time) bool {
	parts := strings.Fields(raw)
	if len(parts) != 5 {
		return false
	}
	return cronPartMatches(parts[0], now.Minute(), 0, 59) && cronPartMatches(parts[1], now.Hour(), 0, 23) && parts[2] == "*" && parts[3] == "*" && parts[4] == "*"
}

func cronFieldSupported(raw string, min int, max int) bool {
	if raw == "*" {
		return true
	}
	value, err := strconv.Atoi(raw)
	return err == nil && value >= min && value <= max
}

func cronPartMatches(raw string, value int, min int, max int) bool {
	if raw == "*" {
		return true
	}
	parsed, err := strconv.Atoi(raw)
	return err == nil && parsed >= min && parsed <= max && parsed == value
}

package orchestration

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtid "quwoquan_service/runtime/id"
	rtobs "quwoquan_service/runtime/observability"
	rtredis "quwoquan_service/runtime/redis"
	skillgenerated "quwoquan_service/services/assistant-service/generated/assistant/skill_subscription"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

const (
	skillSubscriptionDeliveryLeaseTTL       = 5 * time.Minute
	skillSubscriptionDeliverySlotTTL        = 48 * time.Hour
	defaultSkillSubscriptionMaxPerDay       = 1
	defaultSkillSubscriptionCooldownMinutes = 60
	maxSkillSubscriptionDeliveriesPerDay    = 24
	maxSkillSubscriptionCooldownMinutes     = 7 * 24 * 60
	skillSubscriptionInitialRetryBackoff    = 5 * time.Minute
	skillSubscriptionMaximumRetryBackoff    = time.Hour
)

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
	normalized, err := s.normalizeSkillSubscriptionInput(userID, input, "")
	if err != nil {
		return assistant.SkillSubscription{}, err
	}
	if err := s.requireSkillSubscriptionDestinationAccess(
		ctx,
		normalized,
	); err != nil {
		return assistant.SkillSubscription{}, err
	}
	return s.subscriptions.CreateSkillSubscription(ctx, normalized)
}

func (s *AssistantService) UpsertSkillSubscription(ctx context.Context, userID string, input assistant.UpsertSkillSubscriptionInput) (_ assistant.SkillSubscription, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.UpsertSkillSubscription",
		attribute.String("user.id", userID),
		attribute.String("subscription.id", input.SubscriptionID),
		attribute.String("skill.id", input.SkillID))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.subscriptions == nil {
		return assistant.SkillSubscription{}, rterr.NewUnavailable(rterr.ModuleAssistant, "订阅存储不可用", "skill subscription store is not configured")
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	subscriptionID := strings.TrimSpace(input.SubscriptionID)
	if subscriptionID == "" {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "subscriptionId 不能为空", "missing subscriptionId")
	}
	status, err := normalizeSubscriptionStatus(input.Status)
	if err != nil {
		return assistant.SkillSubscription{}, err
	}
	normalized, err := s.normalizeSkillSubscriptionInput(userID, assistant.CreateSkillSubscriptionInput{
		SkillID:            input.SkillID,
		DomainID:           input.DomainID,
		TagRefs:            input.TagRefs,
		SearchQueryPlan:    input.SearchQueryPlan,
		Trigger:            input.Trigger,
		Destination:        input.Destination,
		CreatedByPersonaID: input.CreatedByPersonaID,
	}, subscriptionID)
	if err != nil {
		return assistant.SkillSubscription{}, err
	}
	normalized.Status = status
	if err := s.requireSkillSubscriptionDestinationAccess(
		ctx,
		normalized,
	); err != nil {
		return assistant.SkillSubscription{}, err
	}
	return s.subscriptions.UpsertSkillSubscription(ctx, normalized)
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
	userID = strings.TrimSpace(userID)
	subscriptionID = strings.TrimSpace(subscriptionID)
	current, err := s.subscriptions.GetSkillSubscription(
		ctx,
		userID,
		subscriptionID,
	)
	if err != nil {
		return assistant.SkillSubscription{}, err
	}
	now := s.now().UTC()
	var nextAttemptAt *time.Time
	if status == assistant.SkillSubscriptionStatusActive &&
		current.Status != assistant.SkillSubscriptionStatusActive {
		next, ok := nextCronTrigger(current.Trigger.Cron, now)
		if !ok {
			return assistant.SkillSubscription{}, rterr.NewInvalidArgument(
				rterr.ModuleAssistant,
				"cron 无法计算下一次触发时间",
				"cron has no trigger in the supported scheduling window",
			)
		}
		nextAttemptAt = &next
	}
	return s.subscriptions.UpdateSkillSubscriptionStatus(
		ctx,
		userID,
		subscriptionID,
		status,
		nextAttemptAt,
		now,
	)
}

func (s *AssistantService) TickSkillSubscriptionCron(ctx context.Context, input assistant.SkillSubscriptionCronTickInput) (_ assistant.SkillSubscriptionCronTickResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.TickSkillSubscriptionCron")
	defer func() { rtobs.EndSpan(span, err) }()
	defer func() { recordSubscriptionCronTick(err) }()

	if s.subscriptions == nil {
		return assistant.SkillSubscriptionCronTickResult{}, rterr.NewUnavailable(rterr.ModuleAssistant, "订阅存储不可用", "skill subscription store is not configured")
	}
	if s.cache == nil {
		return assistant.SkillSubscriptionCronTickResult{},
			skillgenerated.AppErrorFromSubscriptionDeliveryFailed(
				"redis is required for proactive delivery leases and frequency control",
			)
	}
	if s.deliveryPolicies == nil {
		return assistant.SkillSubscriptionCronTickResult{},
			skillgenerated.AppErrorFromSubscriptionDeliveryFailed(
				"assistant delivery policy reader is not configured",
			)
	}
	now := s.now()
	if raw := strings.TrimSpace(input.Now); raw != "" {
		parsed, err := time.Parse(time.RFC3339, raw)
		if err != nil {
			return assistant.SkillSubscriptionCronTickResult{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "now 无效", err.Error())
		}
		now = parsed.UTC()
	}
	items, err := s.subscriptions.ListActiveSkillSubscriptionsForDelivery(
		ctx,
		now,
		1000,
	)
	if err != nil {
		return assistant.SkillSubscriptionCronTickResult{}, err
	}
	result := assistant.SkillSubscriptionCronTickResult{
		CreatedTurnIDs:    []string{},
		CreatedMessageIDs: []string{},
	}
	for _, subscription := range items {
		isRetry := strings.TrimSpace(
			subscription.DeliveryState.PendingDeliveryID,
		) != ""
		deliveryID, due := skillSubscriptionDeliveryID(subscription, now)
		if !due {
			continue
		}
		turn, message, suppressed, began, deliveryErr :=
			s.deliverSkillSubscription(
				ctx,
				subscription,
				deliveryID,
				now,
			)
		if deliveryErr != nil {
			if !began {
				return assistant.SkillSubscriptionCronTickResult{},
					skillgenerated.AppErrorFromSubscriptionDeliveryFailed(
						deliveryErr.Error(),
					)
			}
			errorCode := skillSubscriptionDeliveryErrorCode(deliveryErr)
			nextAttemptAt := now.Add(
				skillSubscriptionRetryBackoff(
					subscription.DeliveryState.ConsecutiveFailures + 1,
				),
			)
			if _, recordErr := s.subscriptions.
				RecordSkillSubscriptionDeliveryFailure(
					ctx,
					subscription.Owner.OwnerID,
					subscription.SubscriptionID,
					deliveryID,
					errorCode,
					now,
					nextAttemptAt,
				); recordErr != nil {
				return assistant.SkillSubscriptionCronTickResult{},
					skillgenerated.AppErrorFromSubscriptionDeliveryFailed(
						fmt.Sprintf(
							"delivery failed (%s) and audit persistence failed: %v",
							errorCode,
							recordErr,
						),
					)
			}
			result.FailedCount++
			recordSubscriptionDeliveryAttempt("failed", isRetry)
			slog.WarnContext(
				ctx,
				"assistant proactive subscription delivery failed; retry scheduled",
				slog.String("subscriptionId", subscription.SubscriptionID),
				slog.String("deliveryId", deliveryID),
				slog.String("errorCode", errorCode),
			)
			continue
		}
		if suppressed {
			result.SuppressedCount++
			continue
		}
		result.ProcessedCount++
		recordSubscriptionDeliveryAttempt("delivered", isRetry)
		result.CreatedTurnIDs = append(result.CreatedTurnIDs, turn.TurnID)
		if message != nil {
			result.CreatedMessageIDs = append(
				result.CreatedMessageIDs,
				message.MessageID,
			)
		}
	}
	return result, nil
}

func (s *AssistantService) normalizeSkillSubscriptionInput(userID string, input assistant.CreateSkillSubscriptionInput, subscriptionID string) (assistant.SkillSubscription, error) {
	userID = strings.TrimSpace(userID)
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
	createdByPersonaID := strings.TrimSpace(input.CreatedByPersonaID)
	destination.DestinationType = assistant.SkillSubscriptionDestinationType(
		strings.TrimSpace(string(destination.DestinationType)),
	)
	if destination.DestinationType == "" {
		destination.DestinationType = assistant.SkillSubscriptionDestinationUser
	}
	destination.DestinationID = strings.TrimSpace(destination.DestinationID)
	if destination.DestinationType == assistant.SkillSubscriptionDestinationUser && destination.DestinationID == "" {
		destination.DestinationID = userID
	}
	if destination.DestinationID == "" {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"destinationId 不能为空",
			"missing destination id",
		)
	}
	if destination.DestinationType == assistant.SkillSubscriptionDestinationUser &&
		destination.DestinationID != userID {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"用户投递目标必须与订阅 owner 一致",
			"user destination must match the subscription owner",
		)
	}
	destination.QuietHoursPolicy = strings.TrimSpace(
		destination.QuietHoursPolicy,
	)
	if destination.QuietHoursPolicy == "" {
		destination.QuietHoursPolicy = "inherit_user_setting"
	}
	if destination.QuietHoursPolicy != "inherit_user_setting" {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"quietHoursPolicy 无效",
			"unsupported quiet hours policy",
		)
	}
	if destination.MaxPerDay == 0 {
		destination.MaxPerDay = defaultSkillSubscriptionMaxPerDay
	}
	if destination.MaxPerDay < 1 ||
		destination.MaxPerDay > maxSkillSubscriptionDeliveriesPerDay {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"maxPerDay 无效",
			"maxPerDay is outside the supported range",
		)
	}
	if destination.CooldownMinutes == 0 {
		destination.CooldownMinutes = defaultSkillSubscriptionCooldownMinutes
	}
	if destination.CooldownMinutes < 1 ||
		destination.CooldownMinutes > maxSkillSubscriptionCooldownMinutes {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"cooldownMinutes 无效",
			"cooldownMinutes is outside the supported range",
		)
	}
	switch destination.DestinationType {
	case assistant.SkillSubscriptionDestinationUser,
		assistant.SkillSubscriptionDestinationChatConversation:
	default:
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "destinationType 无效", "unsupported destination type")
	}
	if destination.DestinationType == assistant.SkillSubscriptionDestinationChatConversation && createdByPersonaID == "" {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"ChatConversation 投递缺少创建者 Persona",
			"chat conversation destination requires the creator persona",
		)
	}
	searchPlan := input.SearchQueryPlan
	searchPlan.RawText = strings.TrimSpace(searchPlan.RawText)
	searchPlan.Queries = compactStrings(searchPlan.Queries)
	if len(searchPlan.Queries) == 0 && searchPlan.RawText != "" {
		searchPlan.Queries = []string{searchPlan.RawText}
	}
	subscriptionID = strings.TrimSpace(subscriptionID)
	if subscriptionID == "" {
		generatedID, err := rtid.Generate(rtid.PrefixSkillSubscription)
		if err != nil {
			return assistant.SkillSubscription{}, rterr.NewUnavailable(rterr.ModuleAssistant, "生成订阅 ID 失败", err.Error())
		}
		subscriptionID = generatedID
	}
	now := s.now().UTC()
	nextAttemptAt, ok := nextCronTrigger(trigger.Cron, now)
	if !ok {
		return assistant.SkillSubscription{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"cron 无法计算下一次触发时间",
			"cron has no trigger in the supported scheduling window",
		)
	}
	return assistant.SkillSubscription{
		SubscriptionID:     subscriptionID,
		Owner:              assistant.SkillSubscriptionOwner{OwnerType: "user", OwnerID: userID},
		CreatedByUserID:    userID,
		CreatedByPersonaID: createdByPersonaID,
		SkillID:            skillID,
		DomainID:           strings.TrimSpace(input.DomainID),
		TagRefs:            compactStrings(input.TagRefs),
		Status:             assistant.SkillSubscriptionStatusActive,
		SearchQueryPlan:    searchPlan,
		Trigger:            trigger,
		Destination:        destination,
		DeliveryState: assistant.SkillSubscriptionDeliveryState{
			NextAttemptAt: &nextAttemptAt,
		},
		ClientRequestID: strings.TrimSpace(input.ClientRequestID),
		CreatedAt:       now,
		UpdatedAt:       now,
	}, nil
}

func skillSubscriptionDeliveryID(
	subscription assistant.SkillSubscription,
	now time.Time,
) (string, bool) {
	scheduledAt := now.UTC().Truncate(time.Minute)
	if next := subscription.DeliveryState.NextAttemptAt; next != nil {
		if now.Before(*next) {
			return "", false
		}
		scheduledAt = next.UTC()
	}
	if pending := strings.TrimSpace(
		subscription.DeliveryState.PendingDeliveryID,
	); pending != "" {
		if subscription.DeliveryState.NextAttemptAt == nil &&
			subscription.DeliveryState.LastAttemptAt != nil &&
			now.Before(subscription.DeliveryState.LastAttemptAt.Add(
				skillSubscriptionRetryBackoff(
					subscription.DeliveryState.ConsecutiveFailures,
				),
			)) {
			return "", false
		}
		return pending, true
	}
	if subscription.DeliveryState.NextAttemptAt == nil &&
		!cronMatchesMinute(subscription.Trigger.Cron, now) {
		return "", false
	}
	return "assistant-proactive-" + subscription.SubscriptionID + "-" +
		scheduledAt.Format("200601021504"), true
}

func skillSubscriptionRetryBackoff(failureCount int) time.Duration {
	backoff := skillSubscriptionInitialRetryBackoff
	for attempt := 1; attempt < failureCount; attempt++ {
		if backoff >= skillSubscriptionMaximumRetryBackoff/2 {
			backoff = skillSubscriptionMaximumRetryBackoff
			break
		}
		backoff *= 2
	}
	return backoff
}

func (s *AssistantService) deliverSkillSubscription(
	ctx context.Context,
	subscription assistant.SkillSubscription,
	deliveryID string,
	now time.Time,
) (
	assistant.AssistantTurn,
	*ports.NotificationAppMessageReceipt,
	bool,
	bool,
	error,
) {
	acquired, err := s.claimSubscriptionDelivery(
		ctx,
		subscription.SubscriptionID,
		deliveryID,
	)
	if err != nil {
		return assistant.AssistantTurn{}, nil, false, false, err
	}
	if !acquired {
		recordSubscriptionDeliverySuppressed("lease_held")
		return assistant.AssistantTurn{}, nil, true, false, nil
	}
	current, err := s.subscriptions.GetSkillSubscription(
		ctx,
		subscription.Owner.OwnerID,
		subscription.SubscriptionID,
	)
	if err != nil {
		return assistant.AssistantTurn{}, nil, false, false, err
	}
	current, began, err := s.subscriptions.BeginSkillSubscriptionDelivery(
		ctx,
		current.Owner.OwnerID,
		current.SubscriptionID,
		deliveryID,
		now,
	)
	if err != nil {
		return assistant.AssistantTurn{}, nil, false, false, err
	}
	if !began {
		recordSubscriptionDeliverySuppressed("inactive")
		return assistant.AssistantTurn{}, nil, true, false, nil
	}
	suppress := func(reason string) (
		assistant.AssistantTurn,
		*ports.NotificationAppMessageReceipt,
		bool,
		bool,
		error,
	) {
		nextAttemptAt, ok := nextSkillSubscriptionScheduledAttempt(
			current,
			now,
			false,
		)
		if !ok {
			return assistant.AssistantTurn{}, nil, false, true, fmt.Errorf(
				"calculate next proactive subscription attempt",
			)
		}
		if err := s.subscriptions.ClearPendingSkillSubscriptionDelivery(
			ctx,
			current.Owner.OwnerID,
			current.SubscriptionID,
			deliveryID,
			now,
			nextAttemptAt,
		); err != nil {
			return assistant.AssistantTurn{}, nil, false, true, err
		}
		recordSubscriptionDeliverySuppressed(reason)
		return assistant.AssistantTurn{}, nil, true, true, nil
	}
	if skillSubscriptionCooldownActive(current, now) {
		return suppress("cooldown")
	}
	if err := s.requireSkillConsent(
		ctx,
		current.Owner.OwnerID,
		current.SkillID,
	); err != nil {
		if skillSubscriptionConsentMissing(err) {
			return suppress("consent_missing")
		}
		return assistant.AssistantTurn{}, nil, false, true, err
	}
	policy, err := s.deliveryPolicies.ResolveAssistantDeliveryPolicy(
		ctx,
		current.Owner.OwnerID,
	)
	if err != nil {
		return assistant.AssistantTurn{}, nil, false, true, err
	}
	if !policy.AssistantEnabled {
		return suppress("assistant_disabled")
	}
	if assistantDeliveryQuietHoursActive(now, policy) {
		return suppress("quiet_hours")
	}
	member, err := s.subscriptionDestinationMembershipIsCurrent(
		ctx,
		current,
	)
	if err != nil {
		return assistant.AssistantTurn{}, nil, false, true, err
	}
	if !member {
		return suppress("destination_membership")
	}
	reserved, err := s.reserveSkillSubscriptionDailySlot(
		ctx,
		current,
		deliveryID,
		now,
	)
	if err != nil {
		return assistant.AssistantTurn{}, nil, false, true, err
	}
	if !reserved {
		return suppress("daily_limit")
	}
	turn, message, err := s.createProactiveTurnMessage(
		ctx,
		current,
		deliveryID,
		now,
	)
	if err != nil {
		return assistant.AssistantTurn{}, nil, false, true, err
	}
	nextAttemptAt, ok := nextSkillSubscriptionScheduledAttempt(
		current,
		now,
		true,
	)
	if !ok {
		return assistant.AssistantTurn{}, nil, false, true, fmt.Errorf(
			"calculate next proactive subscription attempt",
		)
	}
	if _, err := s.subscriptions.CompleteSkillSubscriptionDelivery(
		ctx,
		current.Owner.OwnerID,
		current.SubscriptionID,
		deliveryID,
		now,
		nextAttemptAt,
	); err != nil {
		return assistant.AssistantTurn{}, nil, false, true, err
	}
	return turn, &message, false, true, nil
}

func nextSkillSubscriptionScheduledAttempt(
	subscription assistant.SkillSubscription,
	now time.Time,
	afterDelivery bool,
) (time.Time, bool) {
	after := now.UTC()
	var earliest time.Time
	if afterDelivery {
		earliest = after.Add(
			time.Duration(subscription.Destination.CooldownMinutes) *
				time.Minute,
		)
	} else if subscription.DeliveryState.LastDeliveredAt != nil {
		earliest = subscription.DeliveryState.LastDeliveredAt.Add(
			time.Duration(subscription.Destination.CooldownMinutes) *
				time.Minute,
		)
	}
	if earliest.After(after) {
		after = earliest.Add(-time.Minute)
	}
	return nextCronTrigger(subscription.Trigger.Cron, after)
}

func skillSubscriptionCooldownActive(
	subscription assistant.SkillSubscription,
	now time.Time,
) bool {
	if subscription.DeliveryState.LastDeliveredAt == nil {
		return false
	}
	cooldown := time.Duration(subscription.Destination.CooldownMinutes) *
		time.Minute
	return now.Before(subscription.DeliveryState.LastDeliveredAt.Add(cooldown))
}

func skillSubscriptionConsentMissing(err error) bool {
	var appErr *rterr.AppError
	return errors.As(err, &appErr) &&
		appErr.Code.Reason == "skill_consent_required"
}

func assistantDeliveryQuietHoursActive(
	now time.Time,
	policy ports.AssistantDeliveryPolicy,
) bool {
	if policy.QuietHoursStart == nil || policy.QuietHoursEnd == nil {
		return false
	}
	start := *policy.QuietHoursStart
	end := *policy.QuietHoursEnd
	current := time.Duration(now.UTC().Hour())*time.Hour +
		time.Duration(now.UTC().Minute())*time.Minute
	if start == end {
		return true
	}
	if start < end {
		return current >= start && current < end
	}
	return current >= start || current < end
}

func (s *AssistantService) subscriptionDestinationMembershipIsCurrent(
	ctx context.Context,
	subscription assistant.SkillSubscription,
) (bool, error) {
	switch subscription.Destination.DestinationType {
	case "user":
		if strings.TrimSpace(subscription.Destination.DestinationID) !=
			strings.TrimSpace(subscription.Owner.OwnerID) {
			RecordAssistantWrongDestinationIncident()
			return false, nil
		}
		return true, nil
	case assistant.SkillSubscriptionDestinationChatConversation:
		if s.chatGrounding == nil {
			return false, fmt.Errorf(
				"chat grounding client is required for proactive destination",
			)
		}
		current, err := s.chatGrounding.
			ResolveAssistantDeliveryMembership(
				ctx,
				subscription.Destination.DestinationID,
				subscription.CreatedByPersonaID,
				"",
				subscription.SkillID,
			)
		if err != nil {
			return false, fmt.Errorf(
				"resolve proactive destination membership: %w",
				err,
			)
		}
		return current, nil
	default:
		return false, fmt.Errorf(
			"unsupported proactive destination type %q",
			subscription.Destination.DestinationType,
		)
	}
}

func (s *AssistantService) requireSkillSubscriptionDestinationAccess(
	ctx context.Context,
	subscription assistant.SkillSubscription,
) error {
	current, err := s.subscriptionDestinationMembershipIsCurrent(
		ctx,
		subscription,
	)
	if err != nil {
		return skillgenerated.
			AppErrorFromSubscriptionDestinationValidationUnavailable(
				err.Error(),
			)
	}
	if !current {
		return skillgenerated.AppErrorFromSubscriptionDestinationForbidden(
			"subscription creator or assistant skill is not a current chat conversation member",
		)
	}
	return nil
}

func (s *AssistantService) reserveSkillSubscriptionDailySlot(
	ctx context.Context,
	subscription assistant.SkillSubscription,
	deliveryID string,
	now time.Time,
) (bool, error) {
	for slot := 1; slot <= subscription.Destination.MaxPerDay; slot++ {
		key := fmt.Sprintf(
			"assistant:subscription:delivery_slot:%s:%s:%d",
			subscription.SubscriptionID,
			now.UTC().Format("20060102"),
			slot,
		)
		holder, err := s.cache.Get(ctx, key)
		switch {
		case err == nil && holder == deliveryID:
			return true, nil
		case err == nil:
			continue
		case !errors.Is(err, rtredis.ErrKeyNotFound):
			return false, fmt.Errorf(
				"read proactive delivery quota slot: %w",
				err,
			)
		}
		acquired, err := s.cache.SetNX(
			ctx,
			key,
			deliveryID,
			skillSubscriptionDeliverySlotTTL,
		)
		if err != nil {
			return false, fmt.Errorf(
				"reserve proactive delivery quota slot: %w",
				err,
			)
		}
		if acquired {
			return true, nil
		}
		holder, err = s.cache.Get(ctx, key)
		if err == nil && holder == deliveryID {
			return true, nil
		}
		if err != nil && !errors.Is(err, rtredis.ErrKeyNotFound) {
			return false, fmt.Errorf(
				"verify proactive delivery quota slot: %w",
				err,
			)
		}
	}
	return false, nil
}

func skillSubscriptionDeliveryErrorCode(err error) string {
	var appErr *rterr.AppError
	if errors.As(err, &appErr) {
		return appErr.Code.String()
	}
	return skillgenerated.AppErrorFromSubscriptionDeliveryFailed(
		err.Error(),
	).Code.String()
}

func (s *AssistantService) createProactiveTurnMessage(
	ctx context.Context,
	subscription assistant.SkillSubscription,
	deliveryID string,
	now time.Time,
) (assistant.AssistantTurn, ports.NotificationAppMessageReceipt, error) {
	manifest, found := proactiveSkillManifest(subscription.SkillID)
	if !found {
		return assistant.AssistantTurn{}, ports.NotificationAppMessageReceipt{}, fmt.Errorf(
			"proactive skill %q has no activated package",
			subscription.SkillID,
		)
	}
	session, err := s.CreateSession(ctx, subscription.Owner.OwnerID, assistant.CreateSessionInput{
		Summary:         manifest.DisplayName,
		ClientRequestID: deliveryID + ":session",
	})
	if err != nil {
		return assistant.AssistantTurn{}, ports.NotificationAppMessageReceipt{}, err
	}
	// The scheduler forwards only user-authored subscription input. Domain copy,
	// evidence collection and final presentation are owned by the same Skill ->
	// Context -> AgentLoop pipeline used by reactive runs.
	userInput := strings.TrimSpace(subscription.SearchQueryPlan.RawText)
	if userInput == "" {
		userInput = strings.Join(compactStrings(subscription.SearchQueryPlan.Queries), " ")
	}
	run, err := s.startCanonicalRunAndWait(
		ctx,
		subscription.Owner.OwnerID,
		session.SessionID,
		canonicalRunInput{
			SkillID:  subscription.SkillID,
			DomainID: subscription.DomainID,
			Text:     userInput,
			Trigger: assistant.AssistantTurnTrigger{
				Type: "cron",
				Envelope: &assistant.AssistantTriggerEnvelope{
					Kind:              "schedule",
					TriggerID:         deliveryID,
					OccurredAt:        now.UTC(),
					SubscriptionRef:   subscription.SubscriptionID,
					Reason:            "subscription_due",
					DedupeKey:         deliveryID,
					DeliveryPolicyRef: subscription.Destination.QuietHoursPolicy,
				},
			},
			ClientRequestID: deliveryID + ":run",
		},
	)
	if err != nil {
		return assistant.AssistantTurn{}, ports.NotificationAppMessageReceipt{}, err
	}
	turn := projectCanonicalRunAsTurnView(run)
	answer := ""
	if raw, ok := run.TerminalSnapshot["answerText"].(string); ok {
		answer = strings.TrimSpace(raw)
	}
	if run.State.WireName() != "completed" || answer == "" {
		return assistant.AssistantTurn{}, ports.NotificationAppMessageReceipt{}, fmt.Errorf(
			"proactive assistant run %s produced no completed answer",
			run.RunID,
		)
	}
	title := strings.TrimSpace(manifest.DisplayName)
	switch subscription.Destination.DestinationType {
	case assistant.SkillSubscriptionDestinationChatConversation:
		if s.chatGrounding == nil {
			return assistant.AssistantTurn{}, ports.NotificationAppMessageReceipt{}, rterr.NewUnavailable(rterr.ModuleAssistant, "会话投递通道不可用", "chat grounding client is not configured")
		}
		clientMsgID := deliveryID + ":chat"
		if err := s.chatGrounding.SendMessage(ctx, ports.ChatGroundingSendMessageRequest{
			ChatConversationID: subscription.Destination.DestinationID,
			CreatorPersonaID:   subscription.CreatedByPersonaID,
			AssistantSkillID:   subscription.SkillID,
			Type:               "text",
			Content:            title + "\n" + answer,
			ClientMsgID:        clientMsgID,
		}); err != nil {
			return assistant.AssistantTurn{}, ports.NotificationAppMessageReceipt{}, err
		}
		return turn, ports.NotificationAppMessageReceipt{MessageID: clientMsgID}, nil
	default:
		message, err := s.publishNotificationAppMessage(ctx, ports.NotificationAppMessageCommand{
			IdempotencyKey: deliveryID + ":notification",
			UserID:         subscription.Owner.OwnerID,
			MessageType:    "assistant",
			Source:         "assistant_run",
			SourceID:       run.RunID,
			Destination:    ports.NotificationAppMessageDestination{Type: "user", ID: subscription.Owner.OwnerID},
			Title:          title,
			Summary:        answer,
			Target:         ports.NotificationAppMessageTarget{TargetType: "assistant_run", TargetID: run.RunID},
		})
		if err != nil {
			return assistant.AssistantTurn{}, ports.NotificationAppMessageReceipt{}, err
		}
		return turn, message, nil
	}
}

func (s *AssistantService) claimSubscriptionDelivery(
	ctx context.Context,
	subscriptionID string,
	deliveryID string,
) (bool, error) {
	key := "assistant:subscription:lease:" + subscriptionID + ":" +
		deliveryID
	acquired, err := s.cache.SetNX(
		ctx,
		key,
		deliveryID,
		skillSubscriptionDeliveryLeaseTTL,
	)
	if err != nil {
		return false, fmt.Errorf(
			"acquire proactive subscription delivery lease: %w",
			err,
		)
	}
	return acquired, nil
}

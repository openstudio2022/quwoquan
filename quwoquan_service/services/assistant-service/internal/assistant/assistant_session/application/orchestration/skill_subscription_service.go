package orchestration

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	rtredis "quwoquan_service/runtime/redis"
	skillgenerated "quwoquan_service/services/assistant-service/generated/assistant/skill_subscription"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

const (
	skillSubscriptionDeliveryLeaseTTL    = 5 * time.Minute
	skillSubscriptionDeliverySlotTTL     = 48 * time.Hour
	skillSubscriptionInitialRetryBackoff = 5 * time.Minute
	skillSubscriptionMaximumRetryBackoff = time.Hour
)

func (s *AssistantService) TickSkillSubscriptionCron(ctx context.Context, input skillmodel.SkillSubscriptionCronTickInput) (_ skillmodel.SkillSubscriptionCronTickResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.TickSkillSubscriptionCron")
	defer func() { rtobs.EndSpan(span, err) }()
	defer func() { recordSubscriptionCronTick(err) }()

	if s.subscriptions == nil {
		return skillmodel.SkillSubscriptionCronTickResult{}, rterr.NewUnavailable(rterr.ModuleAssistant, "订阅存储不可用", "skill subscription store is not configured")
	}
	if s.cache == nil {
		return skillmodel.SkillSubscriptionCronTickResult{},
			skillgenerated.AppErrorFromSubscriptionDeliveryFailed(
				"redis is required for proactive delivery leases and frequency control",
			)
	}
	if s.deliveryPolicies == nil {
		return skillmodel.SkillSubscriptionCronTickResult{},
			skillgenerated.AppErrorFromSubscriptionDeliveryFailed(
				"assistant delivery policy reader is not configured",
			)
	}
	now := s.now()
	if raw := strings.TrimSpace(input.Now); raw != "" {
		parsed, err := time.Parse(time.RFC3339, raw)
		if err != nil {
			return skillmodel.SkillSubscriptionCronTickResult{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "now 无效", err.Error())
		}
		now = parsed.UTC()
	}
	items, err := s.subscriptions.ListActiveSkillSubscriptionsForDelivery(
		ctx,
		now,
		1000,
	)
	if err != nil {
		return skillmodel.SkillSubscriptionCronTickResult{}, err
	}
	result := skillmodel.SkillSubscriptionCronTickResult{
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
				return skillmodel.SkillSubscriptionCronTickResult{},
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
				return skillmodel.SkillSubscriptionCronTickResult{},
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

func skillSubscriptionDeliveryID(
	subscription skillmodel.SkillSubscription,
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
		!subscriptionapplication.CronMatchesMinute(
			subscription.Trigger.Cron,
			subscription.Trigger.Timezone,
			now,
		) {
		return "", false
	}
	return "assistant-proactive-" + subscription.SubscriptionID + "-" +
		scheduledAt.Format("200601021504"), true
}

func skillSubscriptionDeliveryOccurredAt(deliveryID string) (time.Time, error) {
	deliveryID = strings.TrimSpace(deliveryID)
	separator := strings.LastIndex(deliveryID, "-")
	if separator < 0 || separator == len(deliveryID)-1 {
		return time.Time{}, fmt.Errorf("proactive delivery id has no scheduled coordinate")
	}
	occurredAt, err := time.Parse("200601021504", deliveryID[separator+1:])
	if err != nil {
		return time.Time{}, fmt.Errorf("parse proactive delivery scheduled coordinate: %w", err)
	}
	return occurredAt.UTC(), nil
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
	subscription skillmodel.SkillSubscription,
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
	subscription skillmodel.SkillSubscription,
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
	return subscriptionapplication.NextCronTrigger(
		subscription.Trigger.Cron,
		subscription.Trigger.Timezone,
		after,
	)
}

func skillSubscriptionCooldownActive(
	subscription skillmodel.SkillSubscription,
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
	subscription skillmodel.SkillSubscription,
) (bool, error) {
	switch subscription.Destination.DestinationType {
	case "user":
		if strings.TrimSpace(subscription.Destination.DestinationID) !=
			strings.TrimSpace(subscription.Owner.OwnerID) {
			RecordAssistantWrongDestinationIncident()
			return false, nil
		}
		return true, nil
	case skillmodel.SkillSubscriptionDestinationChatConversation:
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

func (s *AssistantService) reserveSkillSubscriptionDailySlot(
	ctx context.Context,
	subscription skillmodel.SkillSubscription,
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
	subscription skillmodel.SkillSubscription,
	deliveryID string,
) (assistant.AssistantTurn, ports.NotificationAppMessageReceipt, error) {
	triggerOccurredAt, err := skillSubscriptionDeliveryOccurredAt(deliveryID)
	if err != nil {
		return assistant.AssistantTurn{}, ports.NotificationAppMessageReceipt{}, err
	}
	manifest, found, manifestErr := s.resolveSkillManifest(ctx, subscription.SkillID)
	if manifestErr != nil {
		return assistant.AssistantTurn{}, ports.NotificationAppMessageReceipt{}, manifestErr
	}
	found = found && manifest.IsProactive()
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
		userInput = strings.Join(subscriptionapplication.CompactStrings(subscription.SearchQueryPlan.Queries), " ")
	}
	run, err := s.startCanonicalRunAndWait(
		ctx,
		subscription.Owner.OwnerID,
		session.SessionID,
		canonicalRunInput{
			SkillID:     subscription.SkillID,
			DomainID:    subscription.DomainID,
			Text:        userInput,
			PersonaID:   subscription.CreatedByPersonaID,
			SurfaceKind: proactiveSurfaceKind(subscription),
			SurfaceID:   proactiveSurfaceID(subscription),
			Trigger: assistant.AssistantTurnTrigger{
				Type: "cron",
				Envelope: &assistant.AssistantTriggerEnvelope{
					Kind:              "schedule",
					TriggerID:         deliveryID,
					OccurredAt:        triggerOccurredAt,
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
	case skillmodel.SkillSubscriptionDestinationChatConversation:
		if s.chatGrounding == nil {
			return assistant.AssistantTurn{}, ports.NotificationAppMessageReceipt{}, rterr.NewUnavailable(rterr.ModuleAssistant, "会话投递通道不可用", "chat grounding client is not configured")
		}
		clientMsgID := deliveryID + ":chat"
		if err := s.chatGrounding.SendMessage(ctx, ports.ChatGroundingSendMessageRequest{
			ChatConversationID: subscription.Destination.DestinationID,
			CreatorPersonaID:   subscription.CreatedByPersonaID,
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

func proactiveSurfaceKind(subscription skillmodel.SkillSubscription) string {
	if subscription.Destination.DestinationType ==
		skillmodel.SkillSubscriptionDestinationChatConversation {
		return "conversation"
	}
	return ""
}

func proactiveSurfaceID(subscription skillmodel.SkillSubscription) string {
	if proactiveSurfaceKind(subscription) == "" {
		return ""
	}
	return strings.TrimSpace(subscription.Destination.DestinationID)
}

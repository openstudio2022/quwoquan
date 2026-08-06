package application

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"

	userevent "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/event"
	greetingrepo "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/ports"
)

// GreetingOutboxRelay 把 greeting_request_outbox 中已提交的事实投递到
// realtime 用户事件与 durable Redis Stream。两个通道都成功才推进
// checkpoint；消费者按 eventId 去重。
type GreetingOutboxRelay struct {
	outbox    greetingrepo.GreetingOutbox
	publisher GreetingPublisher
	ownerID   string
}

type GreetingPublisher interface {
	PublishGreeting(context.Context, greetingrepo.GreetingOutboxEvent) error
}

type greetingPublisher struct {
	events UserEventPublisher
	stream GreetingEventStream
}

const (
	greetingOutboxLease        = time.Minute
	greetingOutboxRetryBackoff = 5 * time.Second
)

func NewGreetingOutboxRelay(
	outbox greetingrepo.GreetingOutbox,
	events UserEventPublisher,
	stream GreetingEventStream,
) *GreetingOutboxRelay {
	if outbox == nil || events == nil || stream == nil {
		panic("greeting outbox relay requires outbox, events and stream")
	}
	return &GreetingOutboxRelay{
		outbox: outbox,
		publisher: &greetingPublisher{
			events: events,
			stream: stream,
		},
		ownerID: uuid.NewString(),
	}
}

func (r *GreetingOutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	events, err := r.outbox.ClaimPendingOutbox(ctx, r.ownerID, greetingOutboxLease, limit)
	if err != nil {
		return 0, err
	}
	for _, event := range events {
		if err := r.publisher.PublishGreeting(ctx, event); err != nil {
			nextAttemptAt := time.Now().UTC().Add(greetingOutboxRetryBackoff)
			if retryErr := r.outbox.ScheduleOutboxRetry(
				ctx, event.EventID, r.ownerID, greetingOutboxLease, nextAttemptAt,
			); retryErr != nil {
				err = errors.Join(err, retryErr)
			}
			return 0, fmt.Errorf("deliver greeting outbox event %s: %w", event.EventID, err)
		}
		if err := r.outbox.MarkOutboxPublished(ctx, event.EventID, r.ownerID); err != nil {
			if errors.Is(err, greetingrepo.ErrGreetingOutboxClaimLost) {
				continue
			}
			return 0, err
		}
	}
	return len(events), nil
}

func (publisher *greetingPublisher) PublishGreeting(ctx context.Context, event greetingrepo.GreetingOutboxEvent) error {
	greetingID, _ := event.Payload["id"].(string)
	requesterID, _ := event.Payload["requesterPersonaId"].(string)
	targetID, _ := event.Payload["targetPersonaId"].(string)
	source, _ := event.Payload["source"].(string)
	conversationID, _ := event.Payload["promotedConversationId"].(string)
	expireAt, _ := event.Payload["expireAt"].(string)
	decisionAt, _ := event.Payload["decisionAt"].(string)
	if greetingID == "" || greetingID != event.AggregateID || requesterID == "" || targetID == "" {
		return fmt.Errorf("greeting event %s has invalid canonical identity", event.EventID)
	}
	allows, ok := event.Payload["targetAllowsStrangerGreeting"].(bool)
	if !ok {
		allows = true
	}

	canonicalPayload := map[string]any{
		"id": greetingID, "requesterPersonaId": requesterID, "targetPersonaId": targetID,
	}
	switch event.EventName {
	case userevent.GreetingRequestSent:
		if source == "" || expireAt == "" {
			return fmt.Errorf("GreetingRequestSent payload is incomplete")
		}
		canonicalPayload["source"] = source
		canonicalPayload["expireAt"] = expireAt
	case userevent.GreetingRequestReplied:
		if conversationID == "" {
			return fmt.Errorf("GreetingRequestReplied payload is incomplete")
		}
		canonicalPayload["promotedConversationId"] = conversationID
	case userevent.GreetingRequestIgnored:
		if decisionAt == "" {
			return fmt.Errorf("GreetingRequestIgnored payload is incomplete")
		}
		canonicalPayload["decisionAt"] = decisionAt
	case userevent.GreetingRequestCancelled:
	default:
		return fmt.Errorf("greeting event type %q is not canonical", event.EventName)
	}
	realtimePayload := make(map[string]any, len(canonicalPayload)+1)
	for name, value := range canonicalPayload {
		realtimePayload[name] = value
	}
	realtimePayload["targetAllowsStrangerGreeting"] = allows

	// realtime 用户事件（在线红点/推送路由）：Sent/Cancelled 收件人是 target，
	// Replied/Ignored 收件人是 requester。
	recipient, actor := targetID, requesterID
	if event.EventName == userevent.GreetingRequestReplied ||
		event.EventName == userevent.GreetingRequestIgnored {
		recipient, actor = requesterID, targetID
	}
	if err := publisher.events.PublishUserEvent(ctx, event.EventName, recipient, actor, realtimePayload); err != nil {
		return err
	}
	return publisher.stream.PublishGreetingEvent(ctx, GreetingStreamEvent{
		EventID:                      event.EventID,
		EventName:                    event.EventName,
		GreetingID:                   event.AggregateID,
		RequesterPersonaID:           requesterID,
		TargetPersonaID:              targetID,
		Source:                       source,
		PromotedConversationID:       conversationID,
		ExpireAt:                     expireAt,
		DecisionAt:                   decisionAt,
		TargetAllowsStrangerGreeting: allows,
		OccurredAt:                   event.OccurredAt,
	})
}

func (r *GreetingOutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := r.Drain(ctx, 100); err != nil && ctx.Err() == nil {
			slog.ErrorContext(ctx, "greeting outbox drain failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}

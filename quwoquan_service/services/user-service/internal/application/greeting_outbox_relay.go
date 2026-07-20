package application

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"

	userevent "quwoquan_service/services/user-service/internal/domain/user/event"
	greetingrepo "quwoquan_service/services/user-service/internal/domain/user/ports"
)

// GreetingOutboxRelay 把 greeting_request_outbox 中已提交的事实投递到
// realtime 用户事件与 durable Redis Stream。两个通道都成功才推进
// checkpoint；消费者按 eventId 去重。
type GreetingOutboxRelay struct {
	outbox  greetingrepo.GreetingOutbox
	events  UserEventPublisher
	stream  GreetingEventStream
	ownerID string
}

func NewGreetingOutboxRelay(
	outbox greetingrepo.GreetingOutbox,
	events UserEventPublisher,
	stream GreetingEventStream,
) *GreetingOutboxRelay {
	if outbox == nil || events == nil || stream == nil {
		panic("greeting outbox relay requires outbox, events and stream")
	}
	return &GreetingOutboxRelay{
		outbox:  outbox,
		events:  events,
		stream:  stream,
		ownerID: uuid.NewString(),
	}
}

func (r *GreetingOutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	events, err := r.outbox.ClaimPendingOutbox(ctx, r.ownerID, time.Minute, limit)
	if err != nil {
		return 0, err
	}
	for _, event := range events {
		if err := r.deliver(ctx, event); err != nil {
			_ = r.outbox.ReleaseOutboxClaim(ctx, event.EventID, r.ownerID)
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

func (r *GreetingOutboxRelay) deliver(ctx context.Context, event greetingrepo.GreetingOutboxEvent) error {
	requesterID, _ := event.Payload["requesterSubAccountId"].(string)
	targetID, _ := event.Payload["targetSubAccountId"].(string)
	source, _ := event.Payload["source"].(string)
	conversationID, _ := event.Payload["promotedConversationId"].(string)
	allows, ok := event.Payload["targetAllowsStrangerGreeting"].(bool)
	if !ok {
		allows = true
	}

	// realtime 用户事件（在线红点/推送路由）：Sent/Cancelled 收件人是 target，
	// Replied/Ignored 收件人是 requester。
	recipient, actor := targetID, requesterID
	if event.EventName == userevent.GreetingRequestReplied ||
		event.EventName == userevent.GreetingRequestIgnored {
		recipient, actor = requesterID, targetID
	}
	if err := r.events.PublishUserEvent(ctx, event.EventName, recipient, actor, event.Payload); err != nil {
		return err
	}
	return r.stream.PublishGreetingEvent(ctx, GreetingStreamEvent{
		EventID:                      event.EventID,
		EventName:                    event.EventName,
		GreetingID:                   event.AggregateID,
		RequesterSubAccountID:        requesterID,
		TargetSubAccountID:           targetID,
		Source:                       source,
		PromotedConversationID:       conversationID,
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

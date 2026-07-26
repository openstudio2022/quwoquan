package application

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// CallOutboxRelay 是 CallSession 事实的唯一发布主线。
//
// 聚合 state/receipt/outbox 已同事务提交；relay 成功发布 persona realtime 与 durable
// downstream stream 后才标记 publishedAt，进程重启可继续补偿。
type CallOutboxRelay struct {
	store     CallOutboxStore
	publisher CallRealtimePublisher
}

func NewCallOutboxRelay(
	store CallOutboxStore,
	publisher CallRealtimePublisher,
) *CallOutboxRelay {
	return &CallOutboxRelay{store: store, publisher: publisher}
}

func (r *CallOutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if r == nil || r.store == nil || r.publisher == nil {
		return 0, errors.New("rtc call outbox relay is not fully configured")
	}
	if limit <= 0 {
		limit = 100
	}
	events, err := r.store.ReadPendingOutbox(ctx, limit)
	if err != nil {
		return 0, fmt.Errorf("read rtc call outbox: %w", err)
	}
	for index, event := range events {
		recipients := decodeRecipients(event)
		if err := r.publisher.PublishToPersonas(
			ctx,
			recipients,
			signalWireType(event.EventType),
			event,
		); err != nil {
			return index, fmt.Errorf("publish rtc outbox %s: %w", event.EventID, err)
		}
		if err := r.store.MarkOutboxPublished(
			ctx,
			event.EventID,
			time.Now().UTC(),
		); err != nil {
			return index, fmt.Errorf("mark rtc outbox %s published: %w", event.EventID, err)
		}
	}
	return len(events), nil
}

func (r *CallOutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = 100 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := r.Drain(ctx, 100); err != nil {
			return err
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}

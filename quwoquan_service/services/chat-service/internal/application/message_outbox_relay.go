package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"
)

const defaultMessageOutboxConsumer = "chat-runtime-fanout"

// MessageOutboxRelay 是 Message 事件的唯一投递主线。命令只提交聚合、回执
// 与 outbox；relay 在发布被 transport 接受且 dispatched 状态落盘后才推进
// consumer checkpoint，进程重启会从最后水位继续。
type MessageOutboxRelay struct {
	reader      MessageOutboxReader
	dispatch    MessageOutboxDispatchStore
	checkpoints MessageOutboxCheckpointStore
	publisher   EventPublisher
	consumer    string

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewMessageOutboxRelay(
	reader MessageOutboxReader,
	dispatch MessageOutboxDispatchStore,
	checkpoints MessageOutboxCheckpointStore,
	publisher EventPublisher,
	consumer string,
) *MessageOutboxRelay {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = defaultMessageOutboxConsumer
	}
	return &MessageOutboxRelay{
		reader:      reader,
		dispatch:    dispatch,
		checkpoints: checkpoints,
		publisher:   publisher,
		consumer:    consumer,
	}
}

func (r *MessageOutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if r == nil || r.reader == nil || r.dispatch == nil || r.checkpoints == nil || r.publisher == nil {
		return 0, errors.New("message outbox relay is not fully configured")
	}
	checkpoint, err := r.checkpoints.LoadMessageOutboxCheckpoint(ctx, r.consumer)
	if err != nil {
		return 0, fmt.Errorf("load message outbox checkpoint: %w", err)
	}
	events, err := r.reader.ReadMessageOutboxAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, fmt.Errorf("read message outbox: %w", err)
	}
	for index, event := range events {
		if strings.TrimSpace(event.Checkpoint) == "" {
			return index, fmt.Errorf("message outbox event %s has no checkpoint", event.EventID)
		}
		if err := r.publisher.PublishRecordedDomainEvent(
			ctx,
			event.EventID,
			event.EventType,
			event.ConversationID,
			event.ActorID,
			event.Payload,
		); err != nil {
			return index, fmt.Errorf("publish message outbox event %s: %w", event.EventID, err)
		}
		if err := r.dispatch.MarkMessageOutboxDispatched(ctx, event.EventID, time.Now().UTC()); err != nil {
			return index, fmt.Errorf("mark message outbox event %s dispatched: %w", event.EventID, err)
		}
		if err := r.checkpoints.SaveMessageOutboxCheckpoint(ctx, r.consumer, event.Checkpoint); err != nil {
			return index, fmt.Errorf("save message outbox checkpoint for %s: %w", event.EventID, err)
		}
	}
	return len(events), nil
}

func (r *MessageOutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = 100 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := r.Drain(ctx, 100); err != nil {
			r.recordFailure(err)
		} else {
			r.recordSuccess()
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (r *MessageOutboxRelay) Healthy(maxStaleness time.Duration) error {
	if r == nil {
		return errors.New("message outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	r.mu.RLock()
	defer r.mu.RUnlock()
	if r.lastSuccess.IsZero() {
		return errors.New("message outbox relay has not completed a scan")
	}
	if r.lastFailure != nil {
		return fmt.Errorf("message outbox relay last failure: %w", r.lastFailure)
	}
	if time.Since(r.lastSuccess) > maxStaleness {
		return fmt.Errorf("message outbox relay heartbeat is stale")
	}
	return nil
}

func (r *MessageOutboxRelay) recordSuccess() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastSuccess = time.Now().UTC()
	r.lastFailure = nil
}

func (r *MessageOutboxRelay) recordFailure(err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastFailure = err
}

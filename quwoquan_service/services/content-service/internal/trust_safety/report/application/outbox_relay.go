package report

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

const defaultReportOutboxConsumer = "content-report-runtime-fanout"

// OutboxRelay 是 Report 事实的唯一异步投递路径。它只读取已经完成 aggregate
// transaction 的 outbox；请求 command 不会在事务内 best-effort 发布。
//
// 一个 Drain 在同一 consumer checkpoint lease 内完成。publisher 或 checkpoint
// commit 任一步失败都会回滚 lease，因此该批事实保持可重放（至少一次投递）。
type OutboxRelay struct {
	reader      reportports.OutboxReader
	checkpoints reportports.ProjectionCheckpointStore
	publisher   reportports.OutboxPublisher
	consumer    string

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewOutboxRelay(
	reader reportports.OutboxReader,
	checkpoints reportports.ProjectionCheckpointStore,
	publisher reportports.OutboxPublisher,
	consumer string,
) *OutboxRelay {
	return &OutboxRelay{
		reader:      reader,
		checkpoints: checkpoints,
		publisher:   publisher,
		consumer:    defaultReportOutboxConsumerIfEmpty(consumer),
	}
}

func defaultReportOutboxConsumerIfEmpty(consumer string) string {
	if consumer = strings.TrimSpace(consumer); consumer != "" {
		return consumer
	}
	return defaultReportOutboxConsumer
}

// Drain publishes at most limit committed Report facts. It returns a count only
// after their checkpoint advances durably. A failure rolls back the entire
// checkpoint lease, so even facts already accepted by the publisher are replayed
// safely on the next run.
func (r *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if r == nil || r.reader == nil || r.checkpoints == nil || r.publisher == nil {
		return 0, fmt.Errorf("report outbox relay is not fully configured")
	}

	lease, acquired, err := r.checkpoints.AcquireCheckpoint(ctx, r.consumer)
	if err != nil {
		return 0, fmt.Errorf("acquire report outbox checkpoint: %w", err)
	}
	if !acquired {
		return 0, nil
	}
	if lease == nil {
		return 0, fmt.Errorf("report outbox checkpoint lease is nil")
	}

	committed := false
	defer func() {
		if !committed {
			_ = lease.Rollback()
		}
	}()

	events, err := r.reader.ReadAfter(ctx, lease.Checkpoint(), limit)
	if err != nil {
		return 0, fmt.Errorf("read report outbox: %w", err)
	}
	for _, event := range events {
		if strings.TrimSpace(string(event.Checkpoint)) == "" {
			return 0, fmt.Errorf("report outbox event %q has no checkpoint", event.EventID)
		}
		if err := r.publisher.Publish(ctx, event); err != nil {
			return 0, fmt.Errorf("publish report outbox event %q: %w", event.EventID, err)
		}
		if err := lease.SaveCheckpoint(ctx, event.Checkpoint); err != nil {
			return 0, fmt.Errorf(
				"save report outbox checkpoint for event %q: %w",
				event.EventID,
				err,
			)
		}
	}
	if err := lease.Commit(ctx); err != nil {
		return 0, fmt.Errorf("commit report outbox checkpoint: %w", err)
	}
	committed = true
	return len(events), nil
}

// Run scans the durable outbox until the application context ends. A transient
// publisher or checkpoint failure does not consume its batch and is retried on
// the next interval.
func (r *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = 250 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		if _, err := r.Drain(ctx, 100); err != nil {
			r.recordFailure(err)
			if ctx.Err() != nil {
				return ctx.Err()
			}
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-ticker.C:
				continue
			}
		}
		r.recordSuccess()
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

// Healthy reports whether the background relay has completed a recent durable
// scan and has not observed a later delivery failure. It never triggers delivery
// work, so readiness cannot become a request-path best-effort publisher.
func (r *OutboxRelay) Healthy(maxStaleness time.Duration) error {
	if r == nil {
		return fmt.Errorf("report outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}

	r.mu.RLock()
	defer r.mu.RUnlock()
	if r.lastSuccess.IsZero() {
		return fmt.Errorf("report outbox relay has not completed a scan")
	}
	if r.lastFailure != nil {
		return fmt.Errorf("report outbox relay last failure: %w", r.lastFailure)
	}
	if time.Since(r.lastSuccess) > maxStaleness {
		return fmt.Errorf(
			"report outbox relay heartbeat is stale: %s",
			time.Since(r.lastSuccess).Round(time.Millisecond),
		)
	}
	return nil
}

func (r *OutboxRelay) recordSuccess() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastSuccess = time.Now().UTC()
	r.lastFailure = nil
}

func (r *OutboxRelay) recordFailure(err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastFailure = err
}

package persistence

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

type OutboxDispatcher struct {
	pool      *pgxpool.Pool
	publisher runtimemessaging.EventPublisher
	owner     string
	interval  time.Duration
	batchSize int
}

type outboxEvent struct {
	ID            string
	Type          string
	AggregateType string
	AggregateID   string
	Payload       []byte
	OccurredAt    time.Time
	RetryCount    int
}

func NewOutboxDispatcher(
	pool *pgxpool.Pool,
	publisher runtimemessaging.EventPublisher,
) (*OutboxDispatcher, error) {
	if pool == nil || publisher == nil {
		return nil, fmt.Errorf("product ops outbox requires postgres pool and publisher")
	}
	host, _ := os.Hostname()
	return &OutboxDispatcher{
		pool: pool, publisher: publisher,
		owner:    fmt.Sprintf("%s-%d", host, time.Now().UnixNano()),
		interval: time.Second, batchSize: 100,
	}, nil
}

func (d *OutboxDispatcher) Run(ctx context.Context) {
	ticker := time.NewTicker(d.interval)
	defer ticker.Stop()
	for {
		if _, err := d.DispatchOnce(ctx); err != nil && ctx.Err() == nil {
			slog.Error("product ops outbox dispatch failed", "error", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (d *OutboxDispatcher) DispatchOnce(ctx context.Context) (int, error) {
	rows, err := d.pool.Query(ctx, `
WITH candidates AS (
  SELECT event_id FROM product_ops_outbox
  WHERE dispatched_at IS NULL
    AND next_attempt_at <= NOW()
    AND (leased_until IS NULL OR leased_until < NOW())
  ORDER BY occurred_at, event_id
  FOR UPDATE SKIP LOCKED
  LIMIT $1
)
UPDATE product_ops_outbox AS outbox
SET lease_owner=$2, leased_until=NOW() + INTERVAL '30 seconds'
FROM candidates
WHERE outbox.event_id=candidates.event_id
RETURNING outbox.event_id, outbox.event_type, outbox.aggregate_type,
  outbox.aggregate_id, outbox.payload, outbox.occurred_at, outbox.retry_count`,
		d.batchSize, d.owner)
	if err != nil {
		return 0, err
	}
	events := make([]outboxEvent, 0)
	for rows.Next() {
		var event outboxEvent
		if err := rows.Scan(
			&event.ID, &event.Type, &event.AggregateType, &event.AggregateID,
			&event.Payload, &event.OccurredAt, &event.RetryCount,
		); err != nil {
			rows.Close()
			return 0, err
		}
		events = append(events, event)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return 0, err
	}
	rows.Close()

	dispatched := 0
	for _, event := range events {
		var payload map[string]any
		if err := json.Unmarshal(event.Payload, &payload); err != nil {
			if markErr := d.markFailed(ctx, event, err); markErr != nil {
				return dispatched, markErr
			}
			continue
		}
		err := d.publisher.Publish(ctx, runtimemessaging.DomainEvent{
			EventID: event.ID, Type: event.Type, AggregateType: event.AggregateType,
			AggregateID: event.AggregateID, Payload: payload,
			OccurredAt: event.OccurredAt.UTC().Format(time.RFC3339),
		})
		if err != nil {
			if markErr := d.markFailed(ctx, event, err); markErr != nil {
				return dispatched, markErr
			}
			continue
		}
		commandTag, err := d.pool.Exec(ctx, `
UPDATE product_ops_outbox
SET dispatched_at=NOW(), lease_owner=NULL, leased_until=NULL, last_error=''
WHERE event_id=$1 AND lease_owner=$2 AND dispatched_at IS NULL`, event.ID, d.owner)
		if err != nil {
			return dispatched, err
		}
		if commandTag.RowsAffected() == 1 {
			dispatched++
		}
	}
	return dispatched, nil
}

func (d *OutboxDispatcher) markFailed(ctx context.Context, event outboxEvent, cause error) error {
	retryDelay := time.Second * time.Duration(1<<min(event.RetryCount, 6))
	_, err := d.pool.Exec(ctx, `
UPDATE product_ops_outbox
SET retry_count=retry_count+1, next_attempt_at=NOW()+$3::interval,
    last_error=$4, lease_owner=NULL, leased_until=NULL
WHERE event_id=$1 AND lease_owner=$2 AND dispatched_at IS NULL`,
		event.ID, d.owner, retryDelay.String(), cause.Error())
	return err
}

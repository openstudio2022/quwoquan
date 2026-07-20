// Package pgoutbox 提供 PostgreSQL 事务 outbox 的通用租约投递器。
// 表结构契约（与各对象 storage.yaml 声明一致）：
//
//	event_id / event_type / aggregate_type / aggregate_id / payload(JSONB) /
//	occurred_at / dispatched_at / retry_count / next_attempt_at / last_error /
//	lease_owner / leased_until
//
// 每个业务对象仍拥有自己的 outbox 表（对象专属 packet）；本包只统一
// 「租约领取 → 发布 → 标记/退避」这段横切机制（R25），不做任何业务解释。
package pgoutbox

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"regexp"
	"sync"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/prometheus/client_golang/prometheus"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

var validTableName = regexp.MustCompile(`^[a-z][a-z0-9_]*$`)

var (
	outboxMetricsOnce      sync.Once
	outboxDispatchedTotal  *prometheus.CounterVec
	outboxDispatchFailures *prometheus.CounterVec
)

// registerOutboxMetrics 注册跨服务共享的 outbox 投递指标（按表分维度），
// 供 PgOutboxDispatchFailuresSustained 等告警消费。
func registerOutboxMetrics() {
	outboxMetricsOnce.Do(func() {
		outboxDispatchedTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "pg_outbox_dispatched_total",
			Help: "Outbox events successfully published and marked dispatched.",
		}, []string{"table"})
		outboxDispatchFailures = prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "pg_outbox_dispatch_failures_total",
			Help: "Outbox publish or decode failures that scheduled a retry.",
		}, []string{"table"})
		registerOutboxCollector(&outboxDispatchedTotal)
		registerOutboxCollector(&outboxDispatchFailures)
	})
}

func registerOutboxCollector(collector **prometheus.CounterVec) {
	if err := prometheus.Register(*collector); err != nil {
		if registered, ok := err.(prometheus.AlreadyRegisteredError); ok {
			if existing, ok := registered.ExistingCollector.(*prometheus.CounterVec); ok {
				*collector = existing
			}
		}
	}
}

type Dispatcher struct {
	pool      *pgxpool.Pool
	publisher runtimemessaging.EventPublisher
	table     string
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

func NewDispatcher(
	pool *pgxpool.Pool,
	publisher runtimemessaging.EventPublisher,
	table string,
) (*Dispatcher, error) {
	if pool == nil || publisher == nil {
		return nil, fmt.Errorf("pg outbox dispatcher requires postgres pool and publisher")
	}
	if !validTableName.MatchString(table) {
		return nil, fmt.Errorf("pg outbox dispatcher table name %q is invalid", table)
	}
	registerOutboxMetrics()
	host, _ := os.Hostname()
	return &Dispatcher{
		pool: pool, publisher: publisher, table: table,
		owner:    fmt.Sprintf("%s-%d", host, time.Now().UnixNano()),
		interval: time.Second, batchSize: 100,
	}, nil
}

func (d *Dispatcher) Run(ctx context.Context) {
	ticker := time.NewTicker(d.interval)
	defer ticker.Stop()
	for {
		if _, err := d.DispatchOnce(ctx); err != nil && ctx.Err() == nil {
			slog.Error("pg outbox dispatch failed", "table", d.table, "error", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (d *Dispatcher) DispatchOnce(ctx context.Context) (int, error) {
	rows, err := d.pool.Query(ctx, fmt.Sprintf(`
WITH candidates AS (
  SELECT event_id FROM %[1]s
  WHERE dispatched_at IS NULL
    AND next_attempt_at <= NOW()
    AND (leased_until IS NULL OR leased_until < NOW())
  ORDER BY occurred_at, event_id
  FOR UPDATE SKIP LOCKED
  LIMIT $1
)
UPDATE %[1]s AS outbox
SET lease_owner=$2, leased_until=NOW() + INTERVAL '30 seconds'
FROM candidates
WHERE outbox.event_id=candidates.event_id
RETURNING outbox.event_id, outbox.event_type, outbox.aggregate_type,
  outbox.aggregate_id, outbox.payload, outbox.occurred_at, outbox.retry_count`, d.table),
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
		commandTag, err := d.pool.Exec(ctx, fmt.Sprintf(`
UPDATE %s
SET dispatched_at=NOW(), lease_owner=NULL, leased_until=NULL, last_error=''
WHERE event_id=$1 AND lease_owner=$2 AND dispatched_at IS NULL`, d.table), event.ID, d.owner)
		if err != nil {
			return dispatched, err
		}
		if commandTag.RowsAffected() == 1 {
			dispatched++
			outboxDispatchedTotal.WithLabelValues(d.table).Inc()
		}
	}
	return dispatched, nil
}

func (d *Dispatcher) markFailed(ctx context.Context, event outboxEvent, cause error) error {
	outboxDispatchFailures.WithLabelValues(d.table).Inc()
	retryDelay := time.Second * time.Duration(1<<min(event.RetryCount, 6))
	_, err := d.pool.Exec(ctx, fmt.Sprintf(`
UPDATE %s
SET retry_count=retry_count+1, next_attempt_at=NOW()+$3::interval,
    last_error=$4, lease_owner=NULL, leased_until=NULL
WHERE event_id=$1 AND lease_owner=$2 AND dispatched_at IS NULL`, d.table),
		event.ID, d.owner, retryDelay.String(), cause.Error())
	return err
}

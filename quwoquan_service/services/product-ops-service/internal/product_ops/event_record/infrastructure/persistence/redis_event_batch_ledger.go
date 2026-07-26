package persistence

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

type eventLedgerRedis interface {
	Get(context.Context, string) (string, error)
	Set(context.Context, string, string, time.Duration) error
	SetNX(context.Context, string, string, time.Duration) (bool, error)
}

type RedisEventBatchLedger struct{ redis eventLedgerRedis }

func NewRedisEventBatchLedger(redis eventLedgerRedis) *RedisEventBatchLedger {
	return &RedisEventBatchLedger{redis: redis}
}

func (l *RedisEventBatchLedger) Begin(ctx context.Context, batchKey string, count int) (application.BatchLedgerState, error) {
	key := "ops:telemetry:batch:" + batchKey
	created, err := l.redis.SetNX(ctx, key, ledgerValue(application.BatchLedgerPending, count), 72*time.Hour)
	if err != nil {
		return "", fmt.Errorf("begin telemetry batch ledger: %w", err)
	}
	if created {
		return application.BatchLedgerNew, nil
	}
	raw, err := l.redis.Get(ctx, key)
	if err != nil {
		return "", fmt.Errorf("read telemetry batch ledger: %w", err)
	}
	state, recordedCount, err := parseLedgerValue(raw)
	if err != nil || recordedCount != count {
		return "", fmt.Errorf("telemetry batch ledger conflict")
	}
	return state, nil
}

func (l *RedisEventBatchLedger) MarkAccepted(ctx context.Context, batchKey string, count int) error {
	if err := l.redis.Set(ctx, "ops:telemetry:batch:"+batchKey, ledgerValue(application.BatchLedgerAccepted, count), 72*time.Hour); err != nil {
		return fmt.Errorf("accept telemetry batch ledger: %w", err)
	}
	return nil
}

func ledgerValue(state application.BatchLedgerState, count int) string {
	return string(state) + ":" + strconv.Itoa(count)
}

func parseLedgerValue(raw string) (application.BatchLedgerState, int, error) {
	parts := strings.Split(raw, ":")
	if len(parts) != 2 {
		return "", 0, fmt.Errorf("invalid ledger state")
	}
	count, err := strconv.Atoi(parts[1])
	if err != nil {
		return "", 0, err
	}
	state := application.BatchLedgerState(parts[0])
	if state != application.BatchLedgerPending && state != application.BatchLedgerAccepted {
		return "", 0, fmt.Errorf("invalid ledger state")
	}
	return state, count, nil
}

var _ application.EventBatchLedger = (*RedisEventBatchLedger)(nil)

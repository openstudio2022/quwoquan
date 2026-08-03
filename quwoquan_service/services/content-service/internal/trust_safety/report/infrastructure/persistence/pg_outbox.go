package persistence

import (
	"context"
	"database/sql"
	"fmt"
	"strconv"
	"strings"
	"sync"

	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

const (
	defaultReportOutboxBatchSize = 100
	maxReportOutboxBatchSize     = 1000
)

// ReadAfter 按唯一重放顺序 outbox_sequence ASC 返回 Report 自有不可变事实。
// PostgreSQL 会在写入事实的同一 aggregate transaction 中分配该序号，因此
// 后提交的事务不会先于更早的重放位置可见。
func (s *PGReportStore) ReadAfter(
	ctx context.Context,
	checkpoint reportports.OutboxCheckpoint,
	limit int,
) ([]reportports.OutboxEvent, error) {
	if s == nil || s.db == nil {
		return nil, fmt.Errorf("report outbox reader is not configured")
	}
	limit = normalizedReportOutboxLimit(limit)

	var (
		rows *sql.Rows
		err  error
	)
	if strings.TrimSpace(string(checkpoint)) == "" {
		rows, err = s.db.QueryContext(ctx, `
SELECT outbox_sequence, event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
FROM report_outbox
ORDER BY outbox_sequence ASC
LIMIT $1`, limit)
	} else {
		outboxSequence, parseErr := parseReportOutboxCheckpoint(checkpoint)
		if parseErr != nil {
			return nil, parseErr
		}
		rows, err = s.db.QueryContext(ctx, `
SELECT outbox_sequence, event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
FROM report_outbox
WHERE outbox_sequence > $1
ORDER BY outbox_sequence ASC
LIMIT $2`, outboxSequence, limit)
	}
	if err != nil {
		return nil, fmt.Errorf("read report outbox: %w", err)
	}
	defer rows.Close()

	events := make([]reportports.OutboxEvent, 0, limit)
	for rows.Next() {
		var event reportports.OutboxEvent
		var outboxSequence int64
		var payload []byte
		if err := rows.Scan(
			&outboxSequence,
			&event.EventID,
			&event.AggregateID,
			&event.AggregateVersion,
			&event.EventType,
			&payload,
			&event.OccurredAt,
		); err != nil {
			return nil, fmt.Errorf("scan report outbox: %w", err)
		}
		event.OccurredAt = event.OccurredAt.UTC()
		event.Payload = append([]byte(nil), payload...)
		event.Checkpoint = reportOutboxCheckpoint(outboxSequence)
		events = append(events, event)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate report outbox: %w", err)
	}
	return events, nil
}

// AcquireCheckpoint 在完整的发布与水位提交期间串行化一个具名 consumer。
// 它用 FOR UPDATE SKIP LOCKED 锁 consumer 行，而不锁不可变 event 行：
// 跳过被锁住的早期 event 行会让另一个 consumer 越过它推进水位并破坏重放顺序。
// acquired=false 是同一 consumer 已有 relay 实例在运行的正常信号。
func (s *PGReportStore) AcquireCheckpoint(
	ctx context.Context,
	consumer string,
) (reportports.ProjectionCheckpointLease, bool, error) {
	if s == nil || s.db == nil {
		return nil, false, fmt.Errorf("report checkpoint store is not configured")
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, false, fmt.Errorf("report projection consumer is required")
	}

	if _, err := s.db.ExecContext(ctx, `
INSERT INTO report_outbox_checkpoints (consumer, checkpoint, updated_at)
VALUES ($1, '', NOW())
ON CONFLICT (consumer) DO NOTHING`, consumer); err != nil {
		return nil, false, fmt.Errorf("ensure report outbox checkpoint: %w", err)
	}

	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return nil, false, fmt.Errorf("begin report outbox checkpoint transaction: %w", err)
	}
	var checkpoint string
	err = tx.QueryRowContext(ctx, `
SELECT checkpoint
FROM report_outbox_checkpoints
WHERE consumer = $1
FOR UPDATE SKIP LOCKED`, consumer).Scan(&checkpoint)
	switch {
	case err == sql.ErrNoRows:
		_ = tx.Rollback()
		return nil, false, nil
	case err != nil:
		_ = tx.Rollback()
		return nil, false, fmt.Errorf("lock report outbox checkpoint: %w", err)
	}

	return &pgReportCheckpointLease{
		tx:         tx,
		consumer:   consumer,
		checkpoint: reportports.OutboxCheckpoint(checkpoint),
	}, true, nil
}

type pgReportCheckpointLease struct {
	mu sync.Mutex

	tx         *sql.Tx
	consumer   string
	checkpoint reportports.OutboxCheckpoint
	closed     bool
}

func (l *pgReportCheckpointLease) Checkpoint() reportports.OutboxCheckpoint {
	if l == nil {
		return ""
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.checkpoint
}

func (l *pgReportCheckpointLease) SaveCheckpoint(
	ctx context.Context,
	checkpoint reportports.OutboxCheckpoint,
) error {
	if l == nil || l.tx == nil {
		return fmt.Errorf("report checkpoint lease is not configured")
	}
	checkpoint = reportports.OutboxCheckpoint(strings.TrimSpace(string(checkpoint)))
	if _, err := parseReportOutboxCheckpoint(checkpoint); err != nil {
		return err
	}

	l.mu.Lock()
	defer l.mu.Unlock()
	if l.closed {
		return fmt.Errorf("report checkpoint lease is closed")
	}
	if l.checkpoint != "" {
		order, err := compareReportOutboxCheckpoints(l.checkpoint, checkpoint)
		if err != nil {
			return err
		}
		if order > 0 {
			return fmt.Errorf("report checkpoint cannot move backward")
		}
		if order == 0 {
			return nil
		}
	}
	result, err := l.tx.ExecContext(ctx, `
UPDATE report_outbox_checkpoints
SET checkpoint = $2, updated_at = NOW()
WHERE consumer = $1`, l.consumer, checkpoint)
	if err != nil {
		return fmt.Errorf("save report outbox checkpoint: %w", err)
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("count report outbox checkpoint update: %w", err)
	}
	if affected != 1 {
		return fmt.Errorf("report outbox checkpoint consumer %q disappeared", l.consumer)
	}
	l.checkpoint = checkpoint
	return nil
}

func (l *pgReportCheckpointLease) Commit(_ context.Context) error {
	if l == nil || l.tx == nil {
		return fmt.Errorf("report checkpoint lease is not configured")
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.closed {
		return fmt.Errorf("report checkpoint lease is closed")
	}
	if err := l.tx.Commit(); err != nil {
		return fmt.Errorf("commit report outbox checkpoint: %w", err)
	}
	l.closed = true
	return nil
}

func (l *pgReportCheckpointLease) Rollback() error {
	if l == nil || l.tx == nil {
		return nil
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.closed {
		return nil
	}
	l.closed = true
	if err := l.tx.Rollback(); err != nil && err != sql.ErrTxDone {
		return fmt.Errorf("rollback report outbox checkpoint: %w", err)
	}
	return nil
}

func normalizedReportOutboxLimit(limit int) int {
	if limit <= 0 {
		return defaultReportOutboxBatchSize
	}
	if limit > maxReportOutboxBatchSize {
		return maxReportOutboxBatchSize
	}
	return limit
}

func reportOutboxCheckpoint(
	outboxSequence int64,
) reportports.OutboxCheckpoint {
	return reportports.OutboxCheckpoint(strconv.FormatInt(outboxSequence, 10))
}

func parseReportOutboxCheckpoint(
	checkpoint reportports.OutboxCheckpoint,
) (int64, error) {
	outboxSequence, err := strconv.ParseInt(
		strings.TrimSpace(string(checkpoint)),
		10,
		64,
	)
	if err != nil || outboxSequence <= 0 {
		return 0, fmt.Errorf("invalid report outbox checkpoint")
	}
	return outboxSequence, nil
}

// compareReportOutboxCheckpoints 按 ReadAfter 的精确顺序比较不可变重放位置。
func compareReportOutboxCheckpoints(
	left reportports.OutboxCheckpoint,
	right reportports.OutboxCheckpoint,
) (int, error) {
	leftSequence, err := parseReportOutboxCheckpoint(left)
	if err != nil {
		return 0, err
	}
	rightSequence, err := parseReportOutboxCheckpoint(right)
	if err != nil {
		return 0, err
	}
	switch {
	case leftSequence < rightSequence:
		return -1, nil
	case leftSequence > rightSequence:
		return 1, nil
	default:
		return 0, nil
	}
}

var (
	_ reportports.OutboxReader              = (*PGReportStore)(nil)
	_ reportports.ProjectionCheckpointStore = (*PGReportStore)(nil)
)

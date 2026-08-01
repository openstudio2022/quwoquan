package persistence

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	_ "github.com/lib/pq"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

type PGReportStore struct {
	db *sql.DB
}

type reportRecord struct {
	ID                string     `json:"id"`
	Version           int64      `json:"version"`
	ReporterID        string     `json:"reporterId"`
	ReporterAccountID string     `json:"reporterAccountId"`
	TargetType        string     `json:"targetType"`
	TargetID          string     `json:"targetId"`
	Reason            string     `json:"reason"`
	Description       string     `json:"description,omitempty"`
	Status            string     `json:"status"`
	ReviewerID        string     `json:"reviewerId,omitempty"`
	Resolution        string     `json:"resolution,omitempty"`
	CreatedAt         time.Time  `json:"createdAt"`
	UpdatedAt         time.Time  `json:"updatedAt"`
	ResolvedAt        *time.Time `json:"resolvedAt,omitempty"`
}

type rowScanner interface {
	Scan(dest ...any) error
}

func NewPGReportStore(
	db *sql.DB,
) (*PGReportStore, error) {
	store := &PGReportStore{db: db}
	if err := store.ensureSchema(context.Background()); err != nil {
		return nil, err
	}
	return store, nil
}

func (s *PGReportStore) ensureSchema(ctx context.Context) error {
	const ddl = `
CREATE TABLE IF NOT EXISTS reports (
  id VARCHAR(36) PRIMARY KEY,
  version BIGINT NOT NULL DEFAULT 1,
  reporter_id VARCHAR(64) NOT NULL,
  reporter_account_id VARCHAR(64) NOT NULL,
  target_type VARCHAR(16) NOT NULL,
  target_id VARCHAR(64) NOT NULL,
  reason VARCHAR(32) NOT NULL,
  description TEXT,
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  reviewer_id VARCHAR(64),
  resolution VARCHAR(32),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at TIMESTAMPTZ
);
ALTER TABLE reports ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 1;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE reports ADD COLUMN IF NOT EXISTS reporter_account_id VARCHAR(64);
ALTER TABLE reports ALTER COLUMN reporter_id TYPE VARCHAR(64);
ALTER TABLE reports ALTER COLUMN reporter_account_id TYPE VARCHAR(64);
ALTER TABLE reports ALTER COLUMN reviewer_id TYPE VARCHAR(64);
CREATE TABLE IF NOT EXISTS report_command_receipts (
  idempotency_key VARCHAR(128) PRIMARY KEY,
  aggregate_id VARCHAR(36) NOT NULL,
  aggregate_version BIGINT NOT NULL,
  command_name VARCHAR(64) NOT NULL,
  command_digest VARCHAR(64) NOT NULL,
  result_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS report_outbox (
  event_id VARCHAR(128) PRIMARY KEY,
  outbox_sequence BIGINT NOT NULL,
  aggregate_id VARCHAR(36) NOT NULL,
  aggregate_version BIGINT NOT NULL,
  event_type VARCHAR(128) NOT NULL,
  payload_json JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE report_outbox ADD COLUMN IF NOT EXISTS outbox_sequence BIGINT;
WITH existing_max AS (
  SELECT COALESCE(MAX(outbox_sequence), 0) AS value
  FROM report_outbox
),
missing_sequence AS (
  SELECT
    event_id,
    (SELECT value FROM existing_max)
      + ROW_NUMBER() OVER (ORDER BY occurred_at ASC, event_id ASC) AS value
  FROM report_outbox
  WHERE outbox_sequence IS NULL
)
UPDATE report_outbox AS target
SET outbox_sequence = missing_sequence.value
FROM missing_sequence
WHERE target.event_id = missing_sequence.event_id;
ALTER TABLE report_outbox ALTER COLUMN outbox_sequence SET NOT NULL;
CREATE TABLE IF NOT EXISTS report_outbox_sequence (
  name VARCHAR(64) PRIMARY KEY,
  value BIGINT NOT NULL
);
INSERT INTO report_outbox_sequence (name, value)
SELECT 'report_outbox', COALESCE(MAX(outbox_sequence), 0)
FROM report_outbox
ON CONFLICT (name) DO NOTHING;
CREATE OR REPLACE FUNCTION assign_report_outbox_sequence()
RETURNS trigger AS $$
BEGIN
  IF NEW.outbox_sequence IS NULL THEN
    UPDATE report_outbox_sequence
    SET value = value + 1
    WHERE name = 'report_outbox'
    RETURNING value INTO NEW.outbox_sequence;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS report_outbox_assign_sequence ON report_outbox;
CREATE TRIGGER report_outbox_assign_sequence
BEFORE INSERT ON report_outbox
FOR EACH ROW
EXECUTE FUNCTION assign_report_outbox_sequence();
CREATE TABLE IF NOT EXISTS report_outbox_checkpoints (
  consumer VARCHAR(128) PRIMARY KEY,
  checkpoint TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reports_target ON reports(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status, created_at);
CREATE INDEX IF NOT EXISTS idx_reports_reporter ON reports(reporter_id);
CREATE INDEX IF NOT EXISTS idx_report_receipts_expires ON report_command_receipts(expires_at);
DROP INDEX IF EXISTS idx_report_outbox_unpublished;
CREATE UNIQUE INDEX IF NOT EXISTS idx_report_outbox_replay_order
  ON report_outbox(outbox_sequence ASC);`
	if _, err := s.db.ExecContext(ctx, ddl); err != nil {
		return err
	}
	_, err := s.db.ExecContext(ctx, `
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM reports
    WHERE reporter_account_id IS NULL OR BTRIM(reporter_account_id) = ''
  ) THEN
    RAISE EXCEPTION
      'reports.reporter_account_id must be canonical before startup';
  END IF;
END;
$$;
ALTER TABLE reports ALTER COLUMN reporter_account_id SET NOT NULL;`)
	return err
}

func (s *PGReportStore) Load(
	ctx context.Context,
	reportID string,
) (*reportmodel.Report, bool, error) {
	row := s.db.QueryRowContext(ctx, reportSelectByID, strings.TrimSpace(reportID))
	record, err := scanReportRecord(row)
	if err == sql.ErrNoRows {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	aggregate, err := record.aggregate()
	if err != nil {
		return nil, false, err
	}
	return aggregate, true, nil
}

func (s *PGReportStore) FindReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (reportports.CommitResult, bool, error) {
	replayed, found, err := loadReportReceipt(
		ctx,
		s.db,
		idempotencyKey,
		commandName,
		commandDigest,
	)
	if err != nil || !found {
		return reportports.CommitResult{}, found, err
	}
	return reportports.CommitResult{
		Aggregate: replayed,
		Replayed:  true,
	}, true, nil
}

// RecordNoopReceipt 持久化目标状态已满足的命名迁移回执：INSERT ON CONFLICT
// DO NOTHING 与既有 receipt 语义共存，并发首插以先者为准并回放先者结果。
func (s *PGReportStore) RecordNoopReceipt(
	ctx context.Context,
	noop reportports.NoopReceipt,
) (reportports.CommitResult, error) {
	if noop.Aggregate == nil ||
		strings.TrimSpace(noop.IdempotencyKey) == "" ||
		strings.TrimSpace(noop.CommandName) == "" ||
		strings.TrimSpace(noop.CommandDigest) == "" {
		return reportports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict(
				"report no-op receipt is incomplete",
			)
	}
	if replayed, found, err := s.FindReceipt(
		ctx,
		noop.IdempotencyKey,
		noop.CommandName,
		noop.CommandDigest,
	); err != nil || found {
		return replayed, err
	}
	record := recordFromSnapshot(noop.Aggregate.Snapshot())
	resultJSON, err := json.Marshal(record)
	if err != nil {
		return reportports.CommitResult{}, err
	}
	expiresAt := noop.ReceiptExpiresAt.UTC()
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	result, err := s.db.ExecContext(ctx, `
INSERT INTO report_command_receipts (
  idempotency_key, aggregate_id, aggregate_version, command_name, command_digest,
  result_json, created_at, expires_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
ON CONFLICT (idempotency_key) DO NOTHING`,
		strings.TrimSpace(noop.IdempotencyKey),
		record.ID,
		record.Version,
		strings.TrimSpace(noop.CommandName),
		strings.TrimSpace(noop.CommandDigest),
		resultJSON,
		time.Now().UTC(),
		expiresAt,
	)
	if err != nil {
		return reportports.CommitResult{}, err
	}
	if rows, rowsErr := result.RowsAffected(); rowsErr == nil && rows == 1 {
		return reportports.CommitResult{Aggregate: noop.Aggregate}, nil
	}
	replayed, found, err := s.FindReceipt(
		ctx,
		noop.IdempotencyKey,
		noop.CommandName,
		noop.CommandDigest,
	)
	if err != nil {
		return reportports.CommitResult{}, err
	}
	if !found {
		return reportports.CommitResult{},
			contentgenerated.AppErrorFromStorageWriteFailed(
				"report no-op receipt lost a concurrent insert",
			)
	}
	return replayed, nil
}

func (s *PGReportStore) Commit(
	ctx context.Context,
	commit reportports.Commit,
) (reportports.CommitResult, error) {
	if commit.Aggregate == nil || commit.Aggregate.ID() == "" {
		return reportports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict(
				"report commit requires aggregate",
			)
	}
	if strings.TrimSpace(commit.IdempotencyKey) == "" {
		return reportports.CommitResult{},
			contentgenerated.AppErrorFromIdempotencyConflict(
				"report command requires idempotency key",
			)
	}
	snapshot := commit.Aggregate.Snapshot()
	if snapshot.Version != commit.ExpectedVersion+1 {
		return reportports.CommitResult{},
			contentgenerated.AppErrorFromVersionConflict(
				"report aggregate version does not follow expected version",
			)
	}
	for _, event := range commit.Events {
		if event.AggregateID != snapshot.ID ||
			event.AggregateVersion != snapshot.Version {
			return reportports.CommitResult{},
				contentgenerated.AppErrorFromVersionConflict(
					"report outbox fact does not match aggregate version",
				)
		}
	}

	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return reportports.CommitResult{}, err
	}
	defer func() { _ = tx.Rollback() }()

	replayed, found, err := loadReportReceipt(
		ctx,
		tx,
		commit.IdempotencyKey,
		commit.CommandName,
		commit.CommandDigest,
	)
	if err != nil {
		return reportports.CommitResult{}, err
	}
	if found {
		if err := tx.Commit(); err != nil {
			return reportports.CommitResult{}, err
		}
		return reportports.CommitResult{
			Aggregate: replayed,
			Replayed:  true,
		}, nil
	}

	record := recordFromSnapshot(snapshot)
	if commit.ExpectedVersion == 0 {
		err = insertReport(ctx, tx, record)
	} else {
		err = updateReport(ctx, tx, record, commit.ExpectedVersion)
	}
	if err != nil {
		return reportports.CommitResult{}, err
	}
	if err := insertReportEvents(ctx, tx, commit.Events); err != nil {
		return reportports.CommitResult{}, err
	}
	if err := insertReportReceipt(ctx, tx, commit, record); err != nil {
		return reportports.CommitResult{}, err
	}
	if err := tx.Commit(); err != nil {
		return reportports.CommitResult{}, err
	}
	return reportports.CommitResult{Aggregate: commit.Aggregate}, nil
}

func (s *PGReportStore) FindByID(
	ctx context.Context,
	reportID string,
) (reportapp.ReportDetailSlice, bool, error) {
	row := s.db.QueryRowContext(ctx, reportSelectByID, strings.TrimSpace(reportID))
	record, err := scanReportRecord(row)
	if err == sql.ErrNoRows {
		return reportapp.ReportDetailSlice{}, false, nil
	}
	if err != nil {
		return reportapp.ReportDetailSlice{}, false, err
	}
	return record.detailSlice(), true, nil
}

func (s *PGReportStore) List(
	ctx context.Context,
	limit int,
) (reportapp.ReportQueueSlice, error) {
	if limit <= 0 {
		limit = 20
	}
	rows, err := s.db.QueryContext(ctx, `
SELECT id, version, reporter_id, reporter_account_id, target_type, target_id, reason, description, status,
       reviewer_id, resolution, created_at, updated_at, resolved_at
FROM reports
ORDER BY created_at DESC
LIMIT $1`, limit)
	if err != nil {
		return reportapp.ReportQueueSlice{}, err
	}
	defer rows.Close()

	items := make([]reportapp.ReportQueueItemSlice, 0, limit)
	for rows.Next() {
		record, err := scanReportRecord(rows)
		if err != nil {
			return reportapp.ReportQueueSlice{}, err
		}
		items = append(items, record.queueItemSlice())
	}
	if err := rows.Err(); err != nil {
		return reportapp.ReportQueueSlice{}, err
	}
	return reportapp.ReportQueueSlice{Items: items, Total: len(items)}, nil
}

func (s *PGReportStore) ListByReporter(
	ctx context.Context,
	reporterID string,
	cursor *reportapp.MyReportCursor,
	limit int,
) ([]reportapp.MyReportItemSlice, error) {
	if limit <= 0 {
		limit = 20
	}
	var (
		rows *sql.Rows
		err  error
	)
	if cursor == nil {
		rows, err = s.db.QueryContext(ctx, `
SELECT id, version, reporter_id, reporter_account_id, target_type, target_id, reason, description, status,
       reviewer_id, resolution, created_at, updated_at, resolved_at
FROM reports
WHERE reporter_id = $1
ORDER BY created_at DESC, id DESC
LIMIT $2`, strings.TrimSpace(reporterID), limit)
	} else {
		rows, err = s.db.QueryContext(ctx, `
SELECT id, version, reporter_id, reporter_account_id, target_type, target_id, reason, description, status,
       reviewer_id, resolution, created_at, updated_at, resolved_at
FROM reports
WHERE reporter_id = $1
  AND (created_at < $2 OR (created_at = $2 AND id < $3))
ORDER BY created_at DESC, id DESC
LIMIT $4`,
			strings.TrimSpace(reporterID),
			cursor.CreatedAt.UTC(),
			strings.TrimSpace(cursor.ID),
			limit,
		)
	}
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]reportapp.MyReportItemSlice, 0, limit)
	for rows.Next() {
		record, scanErr := scanReportRecord(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		items = append(items, record.myReportItemSlice())
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return items, nil
}

const reportSelectByID = `
SELECT id, version, reporter_id, reporter_account_id, target_type, target_id, reason, description, status,
       reviewer_id, resolution, created_at, updated_at, resolved_at
FROM reports
WHERE id = $1`

type reportReceiptQueryer interface {
	QueryRowContext(ctx context.Context, query string, args ...any) *sql.Row
	ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error)
}

func loadReportReceipt(
	ctx context.Context,
	queryer reportReceiptQueryer,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (*reportmodel.Report, bool, error) {
	var storedCommandName string
	var storedCommandDigest string
	var resultJSON []byte
	var expiresAt time.Time
	err := queryer.QueryRowContext(ctx, `
SELECT command_name, command_digest, result_json, expires_at
FROM report_command_receipts
WHERE idempotency_key = $1`, idempotencyKey).Scan(
		&storedCommandName,
		&storedCommandDigest,
		&resultJSON,
		&expiresAt,
	)
	if err == sql.ErrNoRows {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	if !expiresAt.After(time.Now().UTC()) {
		if _, err := queryer.ExecContext(
			ctx,
			`DELETE FROM report_command_receipts WHERE idempotency_key = $1`,
			idempotencyKey,
		); err != nil {
			return nil, false, err
		}
		return nil, false, nil
	}
	if storedCommandName != commandName || storedCommandDigest != commandDigest {
		return nil, false, contentgenerated.AppErrorFromIdempotencyConflict(
			"idempotency key was reused with a different report command",
		)
	}
	var record reportRecord
	if err := json.Unmarshal(resultJSON, &record); err != nil {
		return nil, false, err
	}
	aggregate, err := record.aggregate()
	if err != nil {
		return nil, false, err
	}
	return aggregate, true, nil
}

func insertReport(
	ctx context.Context,
	tx *sql.Tx,
	record reportRecord,
) error {
	_, err := tx.ExecContext(ctx, `
INSERT INTO reports (
  id, version, reporter_id, reporter_account_id, target_type, target_id, reason, description, status,
  reviewer_id, resolution, created_at, updated_at, resolved_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)`,
		record.ID,
		record.Version,
		record.ReporterID,
		record.ReporterAccountID,
		record.TargetType,
		record.TargetID,
		record.Reason,
		nullString(record.Description),
		record.Status,
		nullString(record.ReviewerID),
		nullString(record.Resolution),
		record.CreatedAt,
		record.UpdatedAt,
		record.ResolvedAt,
	)
	return err
}

func updateReport(
	ctx context.Context,
	tx *sql.Tx,
	record reportRecord,
	expectedVersion int64,
) error {
	result, err := tx.ExecContext(ctx, `
UPDATE reports
SET version = $3,
    reporter_id = $4,
    reporter_account_id = $5,
    target_type = $6,
    target_id = $7,
    reason = $8,
    description = $9,
    status = $10,
    reviewer_id = $11,
    resolution = $12,
    created_at = $13,
    updated_at = $14,
    resolved_at = $15
WHERE id = $1 AND version = $2`,
		record.ID,
		expectedVersion,
		record.Version,
		record.ReporterID,
		record.ReporterAccountID,
		record.TargetType,
		record.TargetID,
		record.Reason,
		nullString(record.Description),
		record.Status,
		nullString(record.ReviewerID),
		nullString(record.Resolution),
		record.CreatedAt,
		record.UpdatedAt,
		record.ResolvedAt,
	)
	if err != nil {
		return err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if affected != 1 {
		return contentgenerated.AppErrorFromVersionConflict(
			"report version changed before commit",
		)
	}
	return nil
}

func insertReportEvents(
	ctx context.Context,
	tx *sql.Tx,
	events []reportports.OutboxEvent,
) error {
	for _, event := range events {
		if _, err := tx.ExecContext(ctx, `
INSERT INTO report_outbox (
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,$4,$5,$6)`,
			event.EventID,
			event.AggregateID,
			event.AggregateVersion,
			event.EventType,
			event.Payload,
			event.OccurredAt,
		); err != nil {
			return err
		}
	}
	return nil
}

func insertReportReceipt(
	ctx context.Context,
	tx *sql.Tx,
	commit reportports.Commit,
	record reportRecord,
) error {
	resultJSON, err := json.Marshal(record)
	if err != nil {
		return err
	}
	expiresAt := commit.ReceiptExpiresAt
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO report_command_receipts (
  idempotency_key, aggregate_id, aggregate_version, command_name, command_digest,
  result_json, created_at, expires_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
		commit.IdempotencyKey,
		record.ID,
		record.Version,
		commit.CommandName,
		commit.CommandDigest,
		resultJSON,
		time.Now().UTC(),
		expiresAt,
	)
	return err
}

func scanReportRecord(scanner rowScanner) (reportRecord, error) {
	var record reportRecord
	var description sql.NullString
	var reviewerID sql.NullString
	var resolution sql.NullString
	var resolvedAt sql.NullTime
	err := scanner.Scan(
		&record.ID,
		&record.Version,
		&record.ReporterID,
		&record.ReporterAccountID,
		&record.TargetType,
		&record.TargetID,
		&record.Reason,
		&description,
		&record.Status,
		&reviewerID,
		&resolution,
		&record.CreatedAt,
		&record.UpdatedAt,
		&resolvedAt,
	)
	if err != nil {
		return reportRecord{}, err
	}
	record.Description = description.String
	record.ReviewerID = reviewerID.String
	record.Resolution = resolution.String
	if resolvedAt.Valid {
		value := resolvedAt.Time.UTC()
		record.ResolvedAt = &value
	}
	return record, nil
}

func recordFromSnapshot(snapshot reportmodel.Snapshot) reportRecord {
	return reportRecord{
		ID:                snapshot.ID,
		Version:           snapshot.Version,
		ReporterID:        snapshot.ReporterID,
		ReporterAccountID: snapshot.ReporterAccountID,
		TargetType:        string(snapshot.TargetType),
		TargetID:          snapshot.TargetID,
		Reason:            string(snapshot.Reason),
		Description:       snapshot.Description,
		Status:            string(snapshot.Status),
		ReviewerID:        snapshot.ReviewerID,
		Resolution:        string(snapshot.Resolution),
		CreatedAt:         snapshot.CreatedAt,
		UpdatedAt:         snapshot.UpdatedAt,
		ResolvedAt:        snapshot.ResolvedAt,
	}
}

func (r reportRecord) aggregate() (*reportmodel.Report, error) {
	aggregate, err := reportmodel.Restore(reportmodel.Snapshot{
		ID:                r.ID,
		Version:           r.Version,
		ReporterID:        r.ReporterID,
		ReporterAccountID: r.ReporterAccountID,
		TargetType:        reportmodel.TargetType(r.TargetType),
		TargetID:          r.TargetID,
		Reason:            reportmodel.Reason(r.Reason),
		Description:       r.Description,
		Status:            reportmodel.Status(r.Status),
		ReviewerID:        r.ReviewerID,
		Resolution:        reportmodel.Resolution(r.Resolution),
		CreatedAt:         r.CreatedAt,
		UpdatedAt:         r.UpdatedAt,
		ResolvedAt:        r.ResolvedAt,
	})
	if err != nil {
		return nil, fmt.Errorf("restore report %q: %w", r.ID, err)
	}
	return aggregate, nil
}

func (r reportRecord) detailSlice() reportapp.ReportDetailSlice {
	return reportapp.ReportDetailSlice{
		ID:          r.ID,
		Version:     r.Version,
		ReporterID:  r.ReporterID,
		TargetType:  reportmodel.TargetType(r.TargetType),
		TargetID:    r.TargetID,
		Reason:      reportmodel.Reason(r.Reason),
		Description: r.Description,
		Status:      reportmodel.Status(r.Status),
		ReviewerID:  r.ReviewerID,
		Resolution:  reportmodel.Resolution(r.Resolution),
		CreatedAt:   r.CreatedAt,
		UpdatedAt:   r.UpdatedAt,
		ResolvedAt:  r.ResolvedAt,
	}
}

func (r reportRecord) queueItemSlice() reportapp.ReportQueueItemSlice {
	return reportapp.ReportQueueItemSlice{
		ID:         r.ID,
		Version:    r.Version,
		TargetType: reportmodel.TargetType(r.TargetType),
		TargetID:   r.TargetID,
		Reason:     reportmodel.Reason(r.Reason),
		Status:     reportmodel.Status(r.Status),
		CreatedAt:  r.CreatedAt,
		UpdatedAt:  r.UpdatedAt,
	}
}

func (r reportRecord) myReportItemSlice() reportapp.MyReportItemSlice {
	return reportapp.MyReportItemSlice{
		ID:          r.ID,
		TargetType:  reportmodel.TargetType(r.TargetType),
		TargetID:    r.TargetID,
		Reason:      reportmodel.Reason(r.Reason),
		Description: r.Description,
		Status:      reportmodel.Status(r.Status),
		CreatedAt:   r.CreatedAt,
		UpdatedAt:   r.UpdatedAt,
		ResolvedAt:  r.ResolvedAt,
	}
}

func nullString(value string) any {
	if value == "" {
		return nil
	}
	return value
}

package persistence

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
)

const reporterAccountBackfillKind = "content.reporter_account_backfill"

// ReporterAccountBackfill is a reviewed, deployment-time identity mapping for
// legacy Report rows that predate trusted account ownership persistence.
type ReporterAccountBackfill struct {
	ReporterID string `json:"reporterId"`
	AccountID  string `json:"accountId"`
}

type reporterAccountBackfillDocument struct {
	Kind    string                    `json:"kind"`
	Entries []ReporterAccountBackfill `json:"entries"`
}

// ReporterAccountBackfillResult contains migration counters only. Identity
// values are deliberately excluded from runtime logs and diagnostics.
type ReporterAccountBackfillResult struct {
	ReportsBackfilled        int64
	OutboxPayloadsBackfilled int64
	ReceiptsBackfilled       int64
}

// PGReportStoreOption keeps migration input at the infrastructure composition
// boundary; application and domain code never receive deployment identity data.
type PGReportStoreOption func(*PGReportStore) error

// WithReporterAccountBackfills supplies a verified persona-to-account snapshot
// for the one-way legacy migration. Missing or contradictory mappings fail
// closed before the Report store starts serving requests.
func WithReporterAccountBackfills(
	entries []ReporterAccountBackfill,
) PGReportStoreOption {
	return func(store *PGReportStore) error {
		mappings, err := NormalizeReporterAccountBackfills(entries)
		if err != nil {
			return err
		}
		store.reporterAccountBackfills = mappings
		return nil
	}
}

// LoadReporterAccountBackfills reads the explicit deployment artifact. An
// absent path means no legacy mapping was supplied; startup remains fail-closed
// if the database actually contains unresolved Report rows.
func LoadReporterAccountBackfills(
	path string,
) ([]ReporterAccountBackfill, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return nil, nil
	}
	body, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read report account backfill artifact: %w", err)
	}
	var document reporterAccountBackfillDocument
	if err := json.Unmarshal(body, &document); err != nil {
		return nil, fmt.Errorf("decode report account backfill artifact: %w", err)
	}
	if document.Kind != reporterAccountBackfillKind {
		return nil, fmt.Errorf("invalid report account backfill artifact kind")
	}
	if _, err := NormalizeReporterAccountBackfills(document.Entries); err != nil {
		return nil, err
	}
	return document.Entries, nil
}

func NormalizeReporterAccountBackfills(
	entries []ReporterAccountBackfill,
) (map[string]string, error) {
	mappings := make(map[string]string, len(entries))
	for _, entry := range entries {
		reporterID := strings.TrimSpace(entry.ReporterID)
		accountID := strings.TrimSpace(entry.AccountID)
		if reporterID == "" || accountID == "" {
			return nil, fmt.Errorf("report account backfill entry is incomplete")
		}
		if current, exists := mappings[reporterID]; exists && current != accountID {
			return nil, fmt.Errorf("report account backfill has conflicting reporter mapping")
		}
		mappings[reporterID] = accountID
	}
	return mappings, nil
}

func (s *PGReportStore) applyReporterAccountBackfills(
	ctx context.Context,
) (ReporterAccountBackfillResult, error) {
	result := ReporterAccountBackfillResult{}
	if len(s.reporterAccountBackfills) == 0 {
		return result, nil
	}

	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return result, err
	}
	defer func() { _ = tx.Rollback() }()

	reporterIDs := make([]string, 0, len(s.reporterAccountBackfills))
	for reporterID := range s.reporterAccountBackfills {
		reporterIDs = append(reporterIDs, reporterID)
	}
	sort.Strings(reporterIDs)

	for _, reporterID := range reporterIDs {
		accountID := s.reporterAccountBackfills[reporterID]
		if err := assertReporterAccountBackfillCompatible(
			ctx,
			tx,
			reporterID,
			accountID,
		); err != nil {
			return result, err
		}

		reportRows, err := tx.ExecContext(ctx, `
UPDATE reports
SET reporter_account_id = $2
WHERE reporter_id = $1
  AND COALESCE(BTRIM(reporter_account_id), '') = ''`,
			reporterID,
			accountID,
		)
		if err != nil {
			return result, err
		}
		if count, err := reportRows.RowsAffected(); err == nil {
			result.ReportsBackfilled += count
		}

		outboxRows, err := tx.ExecContext(ctx, `
UPDATE report_outbox AS outbox
SET payload_json = jsonb_set(
  outbox.payload_json,
  '{reporterAccountId}',
  to_jsonb($2::text),
  true
)
FROM reports
WHERE reports.id = outbox.aggregate_id
  AND reports.reporter_id = $1
  AND outbox.event_type IN (
    'content.report.created',
    'content.report.resolved',
    'content.report.dismissed'
  )
  AND COALESCE(BTRIM(outbox.payload_json ->> 'reporterAccountId'), '') = ''`,
			reporterID,
			accountID,
		)
		if err != nil {
			return result, err
		}
		if count, err := outboxRows.RowsAffected(); err == nil {
			result.OutboxPayloadsBackfilled += count
		}

		receiptRows, err := tx.ExecContext(ctx, `
UPDATE report_command_receipts AS receipt
SET result_json = jsonb_set(
  receipt.result_json,
  '{reporterAccountId}',
  to_jsonb($2::text),
  true
)
FROM reports
WHERE reports.id = receipt.aggregate_id
  AND reports.reporter_id = $1
  AND COALESCE(BTRIM(receipt.result_json ->> 'reporterAccountId'), '') = ''`,
			reporterID,
			accountID,
		)
		if err != nil {
			return result, err
		}
		if count, err := receiptRows.RowsAffected(); err == nil {
			result.ReceiptsBackfilled += count
		}
	}

	if err := tx.Commit(); err != nil {
		return result, err
	}
	return result, nil
}

func assertReporterAccountBackfillCompatible(
	ctx context.Context,
	tx *sql.Tx,
	reporterID string,
	accountID string,
) error {
	var reportConflicts int
	if err := tx.QueryRowContext(ctx, `
SELECT COUNT(*)
FROM reports
WHERE reporter_id = $1
  AND COALESCE(BTRIM(reporter_account_id), '') <> ''
  AND reporter_account_id <> $2`,
		reporterID,
		accountID,
	).Scan(&reportConflicts); err != nil {
		return err
	}
	if reportConflicts > 0 {
		return fmt.Errorf("report account backfill conflicts with persisted report ownership")
	}

	var outboxConflicts int
	if err := tx.QueryRowContext(ctx, `
SELECT COUNT(*)
FROM report_outbox AS outbox
JOIN reports ON reports.id = outbox.aggregate_id
WHERE reports.reporter_id = $1
  AND outbox.event_type IN (
    'content.report.created',
    'content.report.resolved',
    'content.report.dismissed'
  )
  AND COALESCE(BTRIM(outbox.payload_json ->> 'reporterAccountId'), '') <> ''
  AND outbox.payload_json ->> 'reporterAccountId' <> $2`,
		reporterID,
		accountID,
	).Scan(&outboxConflicts); err != nil {
		return err
	}
	if outboxConflicts > 0 {
		return fmt.Errorf("report account backfill conflicts with persisted outbox payload")
	}

	var receiptConflicts int
	if err := tx.QueryRowContext(ctx, `
SELECT COUNT(*)
FROM report_command_receipts AS receipt
JOIN reports ON reports.id = receipt.aggregate_id
WHERE reports.reporter_id = $1
  AND COALESCE(BTRIM(receipt.result_json ->> 'reporterAccountId'), '') <> ''
  AND receipt.result_json ->> 'reporterAccountId' <> $2`,
		reporterID,
		accountID,
	).Scan(&receiptConflicts); err != nil {
		return err
	}
	if receiptConflicts > 0 {
		return fmt.Errorf("report account backfill conflicts with persisted receipt")
	}
	return nil
}

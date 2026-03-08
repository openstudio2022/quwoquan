package persistence

import (
	"context"
	"database/sql"
	"fmt"

	_ "github.com/lib/pq"

	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
)

type PGReportStore struct {
	db *sql.DB
}

func NewPGReportStore(db *sql.DB) (*PGReportStore, error) {
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
  reporter_id VARCHAR(36) NOT NULL,
  target_type VARCHAR(16) NOT NULL,
  target_id VARCHAR(64) NOT NULL,
  reason VARCHAR(32) NOT NULL,
  description TEXT,
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  reviewer_id VARCHAR(36),
  resolution VARCHAR(32),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_reports_target ON reports(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status, created_at);
CREATE INDEX IF NOT EXISTS idx_reports_reporter ON reports(reporter_id);`
	_, err := s.db.ExecContext(ctx, ddl)
	return err
}

func (s *PGReportStore) Create(ctx context.Context, report *reportmodel.Report) error {
	_, err := s.db.ExecContext(ctx, `
INSERT INTO reports (
  id, reporter_id, target_type, target_id, reason, description, status, reviewer_id, resolution, created_at, resolved_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
		report.ID,
		report.ReporterID,
		report.TargetType,
		report.TargetID,
		report.Reason,
		report.Description,
		report.Status,
		nullString(report.ReviewerID),
		nullString(report.Resolution),
		report.CreatedAt,
		report.ResolvedAt,
	)
	return err
}

func (s *PGReportStore) FindByID(ctx context.Context, id string) (*reportmodel.Report, bool, error) {
	row := s.db.QueryRowContext(ctx, `
SELECT id, reporter_id, target_type, target_id, reason, description, status, reviewer_id, resolution, created_at, resolved_at
FROM reports WHERE id = $1`, id)

	var report reportmodel.Report
	var description sql.NullString
	var reviewerID sql.NullString
	var resolution sql.NullString
	var resolvedAt sql.NullTime
	err := row.Scan(
		&report.ID,
		&report.ReporterID,
		&report.TargetType,
		&report.TargetID,
		&report.Reason,
		&description,
		&report.Status,
		&reviewerID,
		&resolution,
		&report.CreatedAt,
		&resolvedAt,
	)
	if err == sql.ErrNoRows {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	report.Description = description.String
	report.ReviewerID = reviewerID.String
	report.Resolution = resolution.String
	if resolvedAt.Valid {
		t := resolvedAt.Time
		report.ResolvedAt = &t
	}
	return &report, true, nil
}

func (s *PGReportStore) Update(ctx context.Context, report *reportmodel.Report) error {
	result, err := s.db.ExecContext(ctx, `
UPDATE reports
SET reporter_id = $2,
    target_type = $3,
    target_id = $4,
    reason = $5,
    description = $6,
    status = $7,
    reviewer_id = $8,
    resolution = $9,
    created_at = $10,
    resolved_at = $11
WHERE id = $1`,
		report.ID,
		report.ReporterID,
		report.TargetType,
		report.TargetID,
		report.Reason,
		nullString(report.Description),
		report.Status,
		nullString(report.ReviewerID),
		nullString(report.Resolution),
		report.CreatedAt,
		report.ResolvedAt,
	)
	if err != nil {
		return err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if affected == 0 {
		return fmt.Errorf("report %s not found", report.ID)
	}
	return nil
}

func (s *PGReportStore) List(ctx context.Context, limit int) ([]*reportmodel.Report, error) {
	if limit <= 0 {
		limit = 50
	}
	rows, err := s.db.QueryContext(ctx, `
SELECT id, reporter_id, target_type, target_id, reason, description, status, reviewer_id, resolution, created_at, resolved_at
FROM reports
ORDER BY created_at DESC
LIMIT $1`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]*reportmodel.Report, 0, limit)
	for rows.Next() {
		var report reportmodel.Report
		var description sql.NullString
		var reviewerID sql.NullString
		var resolution sql.NullString
		var resolvedAt sql.NullTime
		if err := rows.Scan(
			&report.ID,
			&report.ReporterID,
			&report.TargetType,
			&report.TargetID,
			&report.Reason,
			&description,
			&report.Status,
			&reviewerID,
			&resolution,
			&report.CreatedAt,
			&resolvedAt,
		); err != nil {
			return nil, err
		}
		report.Description = description.String
		report.ReviewerID = reviewerID.String
		report.Resolution = resolution.String
		if resolvedAt.Valid {
			t := resolvedAt.Time
			report.ResolvedAt = &t
		}
		items = append(items, &report)
	}
	return items, rows.Err()
}

func nullString(value string) any {
	if value == "" {
		return nil
	}
	return value
}

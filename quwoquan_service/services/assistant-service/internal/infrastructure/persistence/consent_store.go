package persistence

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type PgConsentStore struct {
	pool *pgxpool.Pool
}

const (
	assistantConsentSchemaVersion = 1
	assistantConsentMigrationLock = int64(0x617373697374)
)

func NewPgConsentStore(pool *pgxpool.Pool) *PgConsentStore {
	return &PgConsentStore{pool: pool}
}

func (s *PgConsentStore) EnsureSchema(ctx context.Context) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin assistant consent migration: %w", err)
	}
	defer func() {
		_ = tx.Rollback(ctx)
	}()

	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, assistantConsentMigrationLock); err != nil {
		return fmt.Errorf("lock assistant consent migration: %w", err)
	}
	if _, err := tx.Exec(ctx, `
CREATE TABLE IF NOT EXISTS assistant_schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)`); err != nil {
		return fmt.Errorf("create assistant migration ledger: %w", err)
	}

	var applied bool
	if err := tx.QueryRow(
		ctx,
		`SELECT EXISTS (SELECT 1 FROM assistant_schema_migrations WHERE version = $1)`,
		assistantConsentSchemaVersion,
	).Scan(&applied); err != nil {
		return fmt.Errorf("read assistant consent migration version: %w", err)
	}
	if !applied {
		query := `
CREATE TABLE IF NOT EXISTS skill_consents (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  granted_scope TEXT NOT NULL,
  granted_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_consents_user_skill_active
  ON skill_consents(user_id, skill_id)
  WHERE revoked_at IS NULL;
DROP INDEX IF EXISTS idx_skill_consents_user_active;
CREATE INDEX idx_skill_consents_user_active
  ON skill_consents(user_id, granted_at DESC)
  WHERE revoked_at IS NULL;
`
		if _, err := tx.Exec(ctx, query); err != nil {
			return fmt.Errorf("apply assistant consent schema v%d: %w", assistantConsentSchemaVersion, err)
		}
		if _, err := tx.Exec(
			ctx,
			`INSERT INTO assistant_schema_migrations(version) VALUES ($1)`,
			assistantConsentSchemaVersion,
		); err != nil {
			return fmt.Errorf("record assistant consent schema v%d: %w", assistantConsentSchemaVersion, err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit assistant consent migration: %w", err)
	}
	return nil
}

func (s *PgConsentStore) ListActiveConsents(ctx context.Context, userID string) ([]assistant.SkillConsent, error) {
	rows, err := s.pool.Query(ctx, `SELECT id, user_id, skill_id, granted_scope, granted_at, revoked_at FROM skill_consents WHERE user_id = $1 AND revoked_at IS NULL ORDER BY granted_at DESC`, userID)
	if err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleAssistant, "读取授权失败", err.Error())
	}
	defer rows.Close()
	items := []assistant.SkillConsent{}
	for rows.Next() {
		var item assistant.SkillConsent
		if err := rows.Scan(&item.ID, &item.UserID, &item.SkillID, &item.GrantedScope, &item.GrantedAt, &item.RevokedAt); err != nil {
			return nil, rterr.NewUnavailable(rterr.ModuleAssistant, "解析授权失败", err.Error())
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

// UpsertConsent 以版本化流水语义授权：已有 active 行时幂等返回现有事实
// （不覆盖 granted_at，保留审计真相）；无 active 行时插入新行，历史撤权行
// 永久保留。并发重复授权由 partial unique index 兜底后读回。
func (s *PgConsentStore) UpsertConsent(ctx context.Context, consent assistant.SkillConsent) (assistant.SkillConsent, error) {
	if existing, found, err := s.findActiveConsent(ctx, consent.UserID, consent.SkillID); err != nil {
		return assistant.SkillConsent{}, err
	} else if found {
		return existing, nil
	}
	query := `
INSERT INTO skill_consents (id, user_id, skill_id, granted_scope, granted_at, revoked_at)
VALUES ($1, $2, $3, $4, $5, NULL)
ON CONFLICT (user_id, skill_id) WHERE revoked_at IS NULL DO NOTHING
RETURNING id, user_id, skill_id, granted_scope, granted_at, revoked_at`
	var out assistant.SkillConsent
	err := s.pool.QueryRow(ctx, query, consent.ID, consent.UserID, consent.SkillID, consent.GrantedScope, consent.GrantedAt).Scan(
		&out.ID,
		&out.UserID,
		&out.SkillID,
		&out.GrantedScope,
		&out.GrantedAt,
		&out.RevokedAt,
	)
	if err == nil {
		return out, nil
	}
	// DO NOTHING 命中（并发已授权）时 RETURNING 无行，读回现有 active 事实。
	existing, found, findErr := s.findActiveConsent(ctx, consent.UserID, consent.SkillID)
	if findErr != nil {
		return assistant.SkillConsent{}, findErr
	}
	if found {
		return existing, nil
	}
	return assistant.SkillConsent{}, rterr.NewUnavailable(rterr.ModuleAssistant, "写入授权失败", err.Error())
}

func (s *PgConsentStore) findActiveConsent(ctx context.Context, userID, skillID string) (assistant.SkillConsent, bool, error) {
	var out assistant.SkillConsent
	err := s.pool.QueryRow(ctx, `
SELECT id, user_id, skill_id, granted_scope, granted_at, revoked_at
FROM skill_consents
WHERE user_id = $1 AND skill_id = $2 AND revoked_at IS NULL`, userID, skillID).Scan(
		&out.ID,
		&out.UserID,
		&out.SkillID,
		&out.GrantedScope,
		&out.GrantedAt,
		&out.RevokedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return assistant.SkillConsent{}, false, nil
		}
		return assistant.SkillConsent{}, false, rterr.NewUnavailable(rterr.ModuleAssistant, "读取授权失败", err.Error())
	}
	return out, true, nil
}

func (s *PgConsentStore) RevokeConsent(ctx context.Context, userID string, skillID string, revokedAt time.Time) error {
	cmd, err := s.pool.Exec(ctx, `UPDATE skill_consents SET revoked_at = $3 WHERE user_id = $1 AND skill_id = $2 AND revoked_at IS NULL`, userID, skillID, revokedAt)
	if err != nil {
		return rterr.NewUnavailable(rterr.ModuleAssistant, "撤销授权失败", err.Error())
	}
	if cmd.RowsAffected() == 0 {
		return nil
	}
	return nil
}

type MemoryConsentStore struct {
	items map[string]assistant.SkillConsent
}

func NewMemoryConsentStore() *MemoryConsentStore {
	return &MemoryConsentStore{items: map[string]assistant.SkillConsent{}}
}

func (s *MemoryConsentStore) ListActiveConsents(_ context.Context, userID string) ([]assistant.SkillConsent, error) {
	items := []assistant.SkillConsent{}
	for _, item := range s.items {
		if item.UserID == userID && item.RevokedAt == nil {
			items = append(items, item)
		}
	}
	return items, nil
}

func (s *MemoryConsentStore) UpsertConsent(_ context.Context, consent assistant.SkillConsent) (assistant.SkillConsent, error) {
	// 与 PgConsentStore 同语义：已有 active 事实时幂等返回，不覆盖历史。
	for _, item := range s.items {
		if item.UserID == consent.UserID && item.SkillID == consent.SkillID && item.RevokedAt == nil {
			return item, nil
		}
	}
	consent.RevokedAt = nil
	s.items[consent.ID] = consent
	return consent, nil
}

func (s *MemoryConsentStore) RevokeConsent(_ context.Context, userID string, skillID string, revokedAt time.Time) error {
	for key, item := range s.items {
		if item.UserID == userID && item.SkillID == skillID && item.RevokedAt == nil {
			at := revokedAt
			item.RevokedAt = &at
			s.items[key] = item
		}
	}
	return nil
}

func (s *MemoryConsentStore) EnsureSchema(_ context.Context) error { return nil }

func IsNoRows(err error) bool {
	return errors.Is(err, sql.ErrNoRows)
}

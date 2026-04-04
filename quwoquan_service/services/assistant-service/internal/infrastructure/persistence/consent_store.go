package persistence

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type PgConsentStore struct {
	pool *pgxpool.Pool
}

func NewPgConsentStore(pool *pgxpool.Pool) *PgConsentStore {
	return &PgConsentStore{pool: pool}
}

func (s *PgConsentStore) EnsureSchema(ctx context.Context) error {
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
CREATE INDEX IF NOT EXISTS idx_skill_consents_user_active
  ON skill_consents(user_id, granted_at DESC);
`
	_, err := s.pool.Exec(ctx, query)
	return err
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

func (s *PgConsentStore) UpsertConsent(ctx context.Context, consent assistant.SkillConsent) (assistant.SkillConsent, error) {
	query := `
INSERT INTO skill_consents (id, user_id, skill_id, granted_scope, granted_at, revoked_at)
VALUES ($1, $2, $3, $4, $5, NULL)
ON CONFLICT (id) DO UPDATE SET
  granted_scope = EXCLUDED.granted_scope,
  granted_at = EXCLUDED.granted_at,
  revoked_at = NULL
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
	if err != nil {
		return assistant.SkillConsent{}, rterr.NewUnavailable(rterr.ModuleAssistant, "写入授权失败", err.Error())
	}
	return out, nil
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
	consent.RevokedAt = nil
	s.items[consent.ID] = consent
	return consent, nil
}

func (s *MemoryConsentStore) RevokeConsent(_ context.Context, userID string, skillID string, revokedAt time.Time) error {
	key := userID + ":" + skillID
	item, ok := s.items[key]
	if !ok {
		return nil
	}
	item.RevokedAt = &revokedAt
	s.items[key] = item
	return nil
}

func (s *MemoryConsentStore) EnsureSchema(_ context.Context) error { return nil }

func IsNoRows(err error) bool {
	return errors.Is(err, sql.ErrNoRows)
}

var _ = fmt.Sprintf

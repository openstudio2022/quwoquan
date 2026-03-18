package persistence

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

// PgPersonaStore extends pgPersonaStoreBase with domain-specific methods.
type PgPersonaStore struct{ pgPersonaStoreBase }

var _ repository.PersonaRepository = (*PgPersonaStore)(nil)

const personaNullableSafeCols = `id, user_id, display_name, COALESCE(avatar_url, ''), COALESCE(caller_ringtone_id, ''), COALESCE(theme_mode_override, ''), COALESCE(font_size_preset_override, ''), appearance_override_updated_at, is_primary, is_private, is_active, COALESCE(sub_account_id, ''), COALESCE(isolation_level, ''), COALESCE(purpose_hint, ''), invite_count, created_at, updated_at`

func NewPgPersonaStore(pool *pgxpool.Pool) *PgPersonaStore {
	return &PgPersonaStore{pgPersonaStoreBase{pool: pool}}
}

func (s *PgPersonaStore) FindByID(ctx context.Context, id string) (*model.Persona, error) {
	return scanPersona(s.pool.QueryRow(ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE id = $1`, id))
}

// FindByUserID delegates to the generated ListByUserID (FK-based list).
func (s *PgPersonaStore) FindByUserID(ctx context.Context, userID string) ([]model.Persona, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE user_id = $1 ORDER BY created_at DESC`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []model.Persona
	for rows.Next() {
		var e model.Persona
		if err := rows.Scan(
			&e.ID,
			&e.UserID,
			&e.DisplayName,
			&e.AvatarURL,
			&e.CallerRingtoneID,
			&e.ThemeModeOverride,
			&e.FontSizePresetOverride,
			&e.AppearanceOverrideUpdatedAt,
			&e.IsPrimary,
			&e.IsPrivate,
			&e.IsActive,
			&e.SubAccountID,
			&e.IsolationLevel,
			&e.PurposeHint,
			&e.InviteCount,
			&e.CreatedAt,
			&e.UpdatedAt,
		); err != nil {
			return nil, err
		}
		result = append(result, e)
	}
	return result, rows.Err()
}

// Update delegates to the generated full-column update.
func (s *PgPersonaStore) Update(ctx context.Context, p *model.Persona) error {
	return s.pgPersonaStoreBase.Update(ctx, p)
}

func (s *PgPersonaStore) FindActiveByUserID(ctx context.Context, userID string) (*model.Persona, error) {
	return scanPersona(s.pool.QueryRow(ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE user_id = $1 AND is_active = true`, userID))
}

func (s *PgPersonaStore) DeactivateAll(ctx context.Context, userID string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE personas SET is_active = false, updated_at = NOW() WHERE user_id = $1 AND is_active = true`, userID)
	return err
}

func (s *PgPersonaStore) ActivateOne(ctx context.Context, id string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE personas SET is_active = true, updated_at = NOW() WHERE id = $1`, id)
	return err
}

// FindBySubAccountID looks up a persona by its public sub_account_id.
func (s *PgPersonaStore) FindBySubAccountID(ctx context.Context, subAccountID string) (*model.Persona, error) {
	return scanPersona(s.pool.QueryRow(ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE sub_account_id = $1`, subAccountID))
}

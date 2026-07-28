package persistence

import (
	"context"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	generated "quwoquan_service/services/user-service/generated/persona_management/persona/persistence/user/persistence"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	repository "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

// PgPersonaStore 在生成的对象级 PostgreSQL Store 上补充领域查询。
type PgPersonaStore struct {
	*generated.PGPersonaStoreBase
	pool *pgxpool.Pool
}

var (
	_ repository.PersonaReader             = (*PgPersonaStore)(nil)
	_ repository.PersonaOwnerAccountReader = (*PgPersonaStore)(nil)
	_ repository.PersonaWriter             = (*PgPersonaStore)(nil)
)

const personaNullableSafeCols = `sub_account_id, user_id, display_name, COALESCE(user_handle, ''), COALESCE(phone, ''), COALESCE(email, ''), COALESCE(bio, ''), COALESCE(avatar_media_asset_id, ''), COALESCE(avatar_url, ''), avatar_version, COALESCE(background_media_asset_id, ''), COALESCE(background_url, ''), COALESCE(caller_ringtone_id, ''), COALESCE(theme_mode_override, ''), COALESCE(font_size_preset_override, ''), appearance_override_updated_at, is_primary, is_private, is_active, COALESCE(isolation_level, ''), COALESCE(purpose_hint, ''), COALESCE(status, 'active'), retired_at, COALESCE(inherits_profile_from_owner, false), COALESCE(overridden_profile_fields, ARRAY[]::text[]), last_profile_sync_at, COALESCE(last_profile_sync_source, ''), last_activated_at, version, created_at, updated_at`

func NewPgPersonaStore(pool *pgxpool.Pool) *PgPersonaStore {
	return &PgPersonaStore{
		PGPersonaStoreBase: generated.NewPGPersonaStoreBase(pool),
		pool:               pool,
	}
}

func (s *PgPersonaStore) FindByID(
	ctx context.Context,
	id string,
) (*model.Persona, error) {
	persona, err := generated.ScanPersona(s.pool.QueryRow(
		ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE sub_account_id = $1`,
		id,
	))
	return persona, mapPersonaPersistenceError(err)
}

func (s *PgPersonaStore) FindByUserID(
	ctx context.Context,
	userID string,
) ([]model.Persona, error) {
	rows, err := s.pool.Query(
		ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE user_id = $1 ORDER BY created_at DESC`,
		userID,
	)
	if err != nil {
		return nil, mapPersonaPersistenceError(err)
	}
	defer rows.Close()

	result := make([]model.Persona, 0)
	for rows.Next() {
		persona, scanErr := generated.ScanPersona(rows)
		if scanErr != nil {
			return nil, mapPersonaPersistenceError(scanErr)
		}
		result = append(result, *persona)
	}
	return result, mapPersonaPersistenceError(rows.Err())
}

func (s *PgPersonaStore) Create(
	ctx context.Context,
	persona *model.Persona,
) error {
	return mapPersonaPersistenceError(s.PGPersonaStoreBase.Create(ctx, persona))
}

func (s *PgPersonaStore) Update(
	ctx context.Context,
	persona *model.Persona,
) error {
	return mapPersonaPersistenceError(s.PGPersonaStoreBase.Update(ctx, persona))
}

func (s *PgPersonaStore) FindActiveByUserID(
	ctx context.Context,
	userID string,
) (*model.Persona, error) {
	persona, err := generated.ScanPersona(s.pool.QueryRow(
		ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE user_id = $1 AND is_active = true AND COALESCE(status, 'active') <> 'retired'`,
		userID,
	))
	return persona, mapPersonaPersistenceError(err)
}

func (s *PgPersonaStore) FindByUserHandle(
	ctx context.Context,
	userHandle string,
) (*model.Persona, error) {
	persona, err := generated.ScanPersona(s.pool.QueryRow(
		ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE user_handle = $1`,
		userHandle,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return persona, mapPersonaPersistenceError(err)
}

func (s *PgPersonaStore) FindBySubAccountID(
	ctx context.Context,
	subAccountID string,
) (*model.Persona, error) {
	persona, err := generated.ScanPersona(s.pool.QueryRow(
		ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE sub_account_id = $1`,
		subAccountID,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return persona, mapPersonaPersistenceError(err)
}

func (s *PgPersonaStore) ResolveOwnerAccountID(
	ctx context.Context,
	subAccountID string,
) (string, bool, error) {
	var accountID string
	err := s.pool.QueryRow(
		ctx,
		`SELECT user_id
		 FROM personas
		 WHERE sub_account_id = $1
		   AND COALESCE(status, 'active') <> 'retired'`,
		subAccountID,
	).Scan(&accountID)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", false, nil
	}
	if err != nil {
		return "", false, mapPersonaPersistenceError(err)
	}
	return accountID, true, nil
}

func mapPersonaPersistenceError(err error) error {
	if err == nil {
		return nil
	}
	var pgErr *pgconn.PgError
	if !errors.As(err, &pgErr) {
		return err
	}
	if pgErr.ConstraintName == "uq_personas_user_handle" {
		return repository.ErrPersonaHandleConflict
	}
	return repository.ErrPersonaPersistence
}

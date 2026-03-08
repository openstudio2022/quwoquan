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

func NewPgPersonaStore(pool *pgxpool.Pool) *PgPersonaStore {
	return &PgPersonaStore{pgPersonaStoreBase{pool: pool}}
}

// FindByUserID delegates to the generated ListByUserID (FK-based list).
func (s *PgPersonaStore) FindByUserID(ctx context.Context, userID string) ([]model.Persona, error) {
	return s.ListByUserID(ctx, userID)
}

// Update delegates to the generated full-column update.
func (s *PgPersonaStore) Update(ctx context.Context, p *model.Persona) error {
	return s.pgPersonaStoreBase.Update(ctx, p)
}

func (s *PgPersonaStore) FindActiveByUserID(ctx context.Context, userID string) (*model.Persona, error) {
	return scanPersona(s.pool.QueryRow(ctx,
		`SELECT `+personaCols+` FROM personas WHERE user_id = $1 AND is_active = true`, userID))
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

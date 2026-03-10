package persistence

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

// PgCredentialBindingStore extends pgCredentialBindingStoreBase with domain-specific queries.
type PgCredentialBindingStore struct{ pgCredentialBindingStoreBase }

var _ repository.CredentialRepository = (*PgCredentialBindingStore)(nil)

func NewPgCredentialBindingStore(pool *pgxpool.Pool) *PgCredentialBindingStore {
	return &PgCredentialBindingStore{pgCredentialBindingStoreBase{pool: pool}}
}

func (s *PgCredentialBindingStore) FindByOwner(ctx context.Context, ownerID string) ([]model.CredentialBinding, error) {
	// Override generated ListByOwnerID which incorrectly uses created_at; credential_bindings uses bound_at.
	rows, err := s.pool.Query(ctx,
		`SELECT `+credentialBindingCols+` FROM credential_bindings WHERE owner_id = $1 AND is_active = true ORDER BY bound_at DESC`,
		ownerID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var result []model.CredentialBinding
	for rows.Next() {
		var e model.CredentialBinding
		if err := rows.Scan(&e.ID, &e.OwnerID, &e.CredentialType, &e.CredentialKey, &e.DisplayLabel, &e.IsActive, &e.BoundAt, &e.LastUsedAt); err != nil {
			return nil, err
		}
		result = append(result, e)
	}
	return result, rows.Err()
}

func (s *PgCredentialBindingStore) FindByTypeAndKey(ctx context.Context, credentialType, credentialKey string) (*model.CredentialBinding, error) {
	return scanCredentialBinding(s.pool.QueryRow(ctx,
		`SELECT `+credentialBindingCols+` FROM credential_bindings WHERE credential_type = $1 AND credential_key = $2 AND is_active = true`,
		credentialType, credentialKey))
}

func (s *PgCredentialBindingStore) FindByOwnerAndType(ctx context.Context, ownerID, credentialType string) (*model.CredentialBinding, error) {
	return scanCredentialBinding(s.pool.QueryRow(ctx,
		`SELECT `+credentialBindingCols+` FROM credential_bindings WHERE owner_id = $1 AND credential_type = $2 AND is_active = true`,
		ownerID, credentialType))
}

func (s *PgCredentialBindingStore) Deactivate(ctx context.Context, ownerID, credentialType string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE credential_bindings SET is_active = false WHERE owner_id = $1 AND credential_type = $2`,
		ownerID, credentialType)
	return err
}

func (s *PgCredentialBindingStore) CountActive(ctx context.Context, ownerID string) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM credential_bindings WHERE owner_id = $1 AND is_active = true`, ownerID).Scan(&n)
	return n, err
}

func (s *PgCredentialBindingStore) UpdateLastUsed(ctx context.Context, id string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE credential_bindings SET last_used_at = $2 WHERE id = $1`, id, time.Now().UTC())
	return err
}

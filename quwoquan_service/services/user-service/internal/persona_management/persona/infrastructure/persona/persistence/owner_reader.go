package persistence

import (
	"context"
	"errors"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// OwnerReader is Persona's object-local authority for resolving its owning
// account. Consumers must not reach into UserAccount persistence for this fact.
type OwnerReader struct {
	pool *pgxpool.Pool
}

func NewOwnerReader(pool *pgxpool.Pool) *OwnerReader {
	if pool == nil {
		panic("Persona owner reader requires PostgreSQL")
	}
	return &OwnerReader{pool: pool}
}

func (r *OwnerReader) ResolveOwnerAccountID(
	ctx context.Context,
	personaID string,
) (string, bool, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return "", false, nil
	}
	var accountID string
	err := r.pool.QueryRow(ctx, `
SELECT user_id
FROM personas
WHERE persona_id=$1 AND COALESCE(status, 'active') <> 'retired'`, personaID).Scan(&accountID)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", false, nil
	}
	if err != nil {
		return "", false, err
	}
	return strings.TrimSpace(accountID), true, nil
}

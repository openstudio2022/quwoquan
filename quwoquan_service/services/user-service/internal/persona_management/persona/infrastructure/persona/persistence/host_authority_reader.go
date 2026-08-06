package persistence

import (
	"context"
	"errors"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
)

type HostAuthorityReader struct {
	pool *pgxpool.Pool
}

func NewHostAuthorityReader(pool *pgxpool.Pool) *HostAuthorityReader {
	if pool == nil {
		panic("Persona Host authority reader requires PostgreSQL")
	}
	return &HostAuthorityReader{pool: pool}
}

func (reader *HostAuthorityReader) ReadHostAuthoritySnapshot(
	ctx context.Context,
	personaID string,
) (personaapp.HostAuthoritySnapshot, bool, error) {
	var snapshot personaapp.HostAuthoritySnapshot
	err := reader.pool.QueryRow(ctx, `
SELECT persona_id, version, COALESCE(status, 'active')
FROM personas
WHERE persona_id = $1`, strings.TrimSpace(personaID)).Scan(
		&snapshot.PersonaID,
		&snapshot.Version,
		&snapshot.Status,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return personaapp.HostAuthoritySnapshot{}, false, nil
	}
	if err != nil {
		return personaapp.HostAuthoritySnapshot{}, false, err
	}
	return snapshot, true, nil
}

var _ personaapp.HostAuthoritySnapshotReader = (*HostAuthorityReader)(nil)

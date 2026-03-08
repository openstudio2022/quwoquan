package persistence

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	blockmodel "quwoquan_service/services/user-service/internal/domain/block/model"
	blockrepo "quwoquan_service/services/user-service/internal/domain/block/repository"
)

// PgBlockStore extends pgBlockStoreBase with domain-specific methods.
type PgBlockStore struct{ pgBlockStoreBase }

var _ blockrepo.BlockRepository = (*PgBlockStore)(nil)

func NewPgBlockStore(pool *pgxpool.Pool) *PgBlockStore {
	return &PgBlockStore{pgBlockStoreBase{pool: pool}}
}

// Create inserts a block edge with idempotent ON CONFLICT handling.
func (s *PgBlockStore) Create(ctx context.Context, edge *blockmodel.BlockEdge) (bool, error) {
	edge.CreatedAt = time.Now().UTC()
	tag, err := s.pool.Exec(ctx, `
		INSERT INTO block_edges (id, blocker_id, blocked_id, reason, created_at)
		VALUES ($1,$2,$3,$4,$5) ON CONFLICT (blocker_id, blocked_id) DO NOTHING`,
		edge.ID, edge.BlockerID, edge.BlockedID, edge.Reason, edge.CreatedAt)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}

// Delete removes a block edge by blocker/blocked pair.
func (s *PgBlockStore) Delete(ctx context.Context, blockerID, blockedID string) (bool, error) {
	tag, err := s.pool.Exec(ctx,
		`DELETE FROM block_edges WHERE blocker_id = $1 AND blocked_id = $2`, blockerID, blockedID)
	if err != nil {
		return false, err
	}
	return tag.RowsAffected() > 0, nil
}

func (s *PgBlockStore) Exists(ctx context.Context, blockerID, blockedID string) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx,
		`SELECT EXISTS(SELECT 1 FROM block_edges WHERE blocker_id=$1 AND blocked_id=$2)`,
		blockerID, blockedID).Scan(&exists)
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil
	}
	return exists, err
}

func (s *PgBlockStore) ListByBlocker(ctx context.Context, blockerID string, cursor string, limit int) ([]blockmodel.BlockEdge, string, error) {
	if limit <= 0 {
		limit = 20
	}
	var rows pgx.Rows
	var err error
	if cursor == "" {
		rows, err = s.pool.Query(ctx, `
			SELECT `+blockEdgeCols+`
			FROM block_edges WHERE blocker_id = $1
			ORDER BY created_at DESC LIMIT $2`, blockerID, limit+1)
	} else {
		rows, err = s.pool.Query(ctx, `
			SELECT `+blockEdgeCols+`
			FROM block_edges WHERE blocker_id = $1 AND id < $2
			ORDER BY created_at DESC LIMIT $3`, blockerID, cursor, limit+1)
	}
	if err != nil {
		return nil, "", err
	}
	defer rows.Close()

	var result []blockmodel.BlockEdge
	for rows.Next() {
		var e blockmodel.BlockEdge
		if err := rows.Scan(&e.ID, &e.BlockerID, &e.BlockedID, &e.Reason, &e.CreatedAt); err != nil {
			return nil, "", err
		}
		result = append(result, e)
	}
	if err := rows.Err(); err != nil {
		return nil, "", err
	}
	var nextCursor string
	if len(result) > limit {
		nextCursor = result[limit].ID
		result = result[:limit]
	}
	return result, nextCursor, nil
}

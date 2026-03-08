package persistence

import (
	"context"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

type PgWorkStore struct {
	pool *pgxpool.Pool
}

var _ repository.WorkRepository = (*PgWorkStore)(nil)

func NewPgWorkStore(pool *pgxpool.Pool) *PgWorkStore {
	return &PgWorkStore{pool: pool}
}

func (s *PgWorkStore) ListByUserID(ctx context.Context, userID string, cursor string, limit int) ([]model.UserWork, string, error) {
	if limit <= 0 {
		limit = 20
	}
	var rows pgx.Rows
	var err error
	if cursor == "" {
		rows, err = s.pool.Query(ctx, `
			SELECT id, user_id, title, cover_url, work_type, ref_id, sort_order, created_at, updated_at
			FROM user_works WHERE user_id = $1 ORDER BY sort_order, created_at DESC LIMIT $2`,
			userID, limit+1)
	} else {
		rows, err = s.pool.Query(ctx, `
			SELECT id, user_id, title, cover_url, work_type, ref_id, sort_order, created_at, updated_at
			FROM user_works WHERE user_id = $1 AND id < $2 ORDER BY sort_order, created_at DESC LIMIT $3`,
			userID, cursor, limit+1)
	}
	if err != nil {
		return nil, "", err
	}
	defer rows.Close()

	var result []model.UserWork
	for rows.Next() {
		var w model.UserWork
		if err := rows.Scan(&w.ID, &w.UserID, &w.Title, &w.CoverURL, &w.WorkType,
			&w.RefID, &w.SortOrder, &w.CreatedAt, &w.UpdatedAt); err != nil {
			return nil, "", err
		}
		result = append(result, w)
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

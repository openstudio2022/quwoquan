package persistence

import (
	"context"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

type PgLifeItemStore struct {
	pool *pgxpool.Pool
}

var _ repository.LifeItemRepository = (*PgLifeItemStore)(nil)

func NewPgLifeItemStore(pool *pgxpool.Pool) *PgLifeItemStore {
	return &PgLifeItemStore{pool: pool}
}

func (s *PgLifeItemStore) ListByUserID(ctx context.Context, userID string, category string, cursor string, limit int) ([]model.UserLifeItem, string, error) {
	if limit <= 0 {
		limit = 20
	}
	var rows pgx.Rows
	var err error
	if category != "" && cursor == "" {
		rows, err = s.pool.Query(ctx, `
			SELECT id, user_id, category, title, subtitle, image_url, ref_id, sort_order, created_at, updated_at
			FROM user_life_items WHERE user_id=$1 AND category=$2 ORDER BY sort_order, created_at DESC LIMIT $3`,
			userID, category, limit+1)
	} else if category != "" && cursor != "" {
		rows, err = s.pool.Query(ctx, `
			SELECT id, user_id, category, title, subtitle, image_url, ref_id, sort_order, created_at, updated_at
			FROM user_life_items WHERE user_id=$1 AND category=$2 AND id < $3 ORDER BY sort_order, created_at DESC LIMIT $4`,
			userID, category, cursor, limit+1)
	} else if cursor == "" {
		rows, err = s.pool.Query(ctx, `
			SELECT id, user_id, category, title, subtitle, image_url, ref_id, sort_order, created_at, updated_at
			FROM user_life_items WHERE user_id=$1 ORDER BY sort_order, created_at DESC LIMIT $2`,
			userID, limit+1)
	} else {
		rows, err = s.pool.Query(ctx, `
			SELECT id, user_id, category, title, subtitle, image_url, ref_id, sort_order, created_at, updated_at
			FROM user_life_items WHERE user_id=$1 AND id < $2 ORDER BY sort_order, created_at DESC LIMIT $3`,
			userID, cursor, limit+1)
	}
	if err != nil {
		return nil, "", err
	}
	defer rows.Close()

	var result []model.UserLifeItem
	for rows.Next() {
		var item model.UserLifeItem
		if err := rows.Scan(&item.ID, &item.UserID, &item.Category, &item.Title, &item.Subtitle,
			&item.ImageURL, &item.RefID, &item.SortOrder, &item.CreatedAt, &item.UpdatedAt); err != nil {
			return nil, "", err
		}
		result = append(result, item)
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

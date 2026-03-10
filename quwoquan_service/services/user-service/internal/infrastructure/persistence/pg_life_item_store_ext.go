package persistence

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

// PgLifeItemStore extends pgLifeItemStoreBase with cursor-based pagination.
type PgLifeItemStore struct{ pgLifeItemStoreBase }

var _ repository.LifeItemRepository = (*PgLifeItemStore)(nil)

func NewPgLifeItemStore(pool *pgxpool.Pool) *PgLifeItemStore {
	return &PgLifeItemStore{pgLifeItemStoreBase{pool: pool}}
}

// ListByUserID returns life items for a user with optional category filter and cursor-based pagination.
func (s *PgLifeItemStore) ListByUserID(ctx context.Context, userID, category, cursor string, limit int) ([]model.UserLifeItem, string, error) {
	if limit <= 0 {
		limit = 20
	}

	var (
		rows interface {
			Next() bool
			Scan(...any) error
			Err() error
			Close()
		}
		err error
	)

	cols := userLifeItemCols
	base := `SELECT ` + cols + ` FROM user_life_items WHERE user_id = $1`

	switch {
	case category != "" && cursor != "":
		rows, err = s.pool.Query(ctx, base+` AND category = $2 AND id < $3 ORDER BY sort_order, created_at DESC LIMIT $4`,
			userID, category, cursor, limit+1)
	case category != "":
		rows, err = s.pool.Query(ctx, base+` AND category = $2 ORDER BY sort_order, created_at DESC LIMIT $3`,
			userID, category, limit+1)
	case cursor != "":
		rows, err = s.pool.Query(ctx, base+` AND id < $2 ORDER BY sort_order, created_at DESC LIMIT $3`,
			userID, cursor, limit+1)
	default:
		rows, err = s.pool.Query(ctx, base+` ORDER BY sort_order, created_at DESC LIMIT $2`,
			userID, limit+1)
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

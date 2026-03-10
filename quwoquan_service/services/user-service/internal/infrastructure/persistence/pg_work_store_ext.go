package persistence

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

// PgWorkStore extends pgWorkStoreBase with cursor-based pagination.
type PgWorkStore struct{ pgWorkStoreBase }

var _ repository.WorkRepository = (*PgWorkStore)(nil)

func NewPgWorkStore(pool *pgxpool.Pool) *PgWorkStore {
	return &PgWorkStore{pgWorkStoreBase{pool: pool}}
}

// ListByUserID returns works for a user with cursor-based pagination.
func (s *PgWorkStore) ListByUserID(ctx context.Context, userID, cursor string, limit int) ([]model.UserWork, string, error) {
	if limit <= 0 {
		limit = 20
	}

	cols := userWorkCols
	base := `SELECT ` + cols + ` FROM user_works WHERE user_id = $1`

	var rows interface {
		Next() bool
		Scan(...any) error
		Err() error
		Close()
	}
	var err error

	if cursor != "" {
		rows, err = s.pool.Query(ctx, base+` AND id < $2 ORDER BY sort_order, created_at DESC LIMIT $3`,
			userID, cursor, limit+1)
	} else {
		rows, err = s.pool.Query(ctx, base+` ORDER BY sort_order, created_at DESC LIMIT $2`,
			userID, limit+1)
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

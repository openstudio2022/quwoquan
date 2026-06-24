package persistence

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

type PgProfileQrTokenStore struct{ pgProfileQrTokenStoreBase }

var _ repository.ProfileQrTokenRepository = (*PgProfileQrTokenStore)(nil)

func NewPgProfileQrTokenStore(pool *pgxpool.Pool) *PgProfileQrTokenStore {
	return &PgProfileQrTokenStore{pgProfileQrTokenStoreBase{pool: pool}}
}

func (s *PgProfileQrTokenStore) FindActiveByOwnerAndHandle(ctx context.Context, ownerUserID, userHandle, styleVersion string) (*model.ProfileQrToken, error) {
	return scanProfileQrToken(s.pool.QueryRow(ctx,
		`SELECT `+profileQrTokenCols+` FROM profile_qr_tokens
		 WHERE owner_user_id = $1 AND user_handle = $2 AND style_version = $3 AND status = 'active' AND revoked_at IS NULL
		 ORDER BY created_at DESC
		 LIMIT 1`,
		ownerUserID, userHandle, styleVersion))
}

func (s *PgProfileQrTokenStore) FindByTokenHash(ctx context.Context, tokenHash string) (*model.ProfileQrToken, error) {
	return scanProfileQrToken(s.pool.QueryRow(ctx,
		`SELECT `+profileQrTokenCols+` FROM profile_qr_tokens WHERE token_hash = $1`,
		tokenHash))
}

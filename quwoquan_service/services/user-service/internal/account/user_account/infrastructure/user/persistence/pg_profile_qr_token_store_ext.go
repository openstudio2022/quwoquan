package persistence

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"

	generated "quwoquan_service/services/user-service/generated/account/user_account/persistence/user/persistence"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	repository "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

type PgProfileQrTokenStore struct {
	*generated.PGProfileQrTokenStoreBase
	pool *pgxpool.Pool
}

var _ repository.ProfileQrTokenStore = (*PgProfileQrTokenStore)(nil)

func NewPgProfileQrTokenStore(pool *pgxpool.Pool) *PgProfileQrTokenStore {
	return &PgProfileQrTokenStore{
		PGProfileQrTokenStoreBase: generated.NewPGProfileQrTokenStoreBase(pool),
		pool:                      pool,
	}
}

func (s *PgProfileQrTokenStore) FindActiveByOwnerAndHandle(ctx context.Context, ownerUserID, userHandle, styleVersion string) (*model.ProfileQrToken, error) {
	return generated.ScanProfileQrToken(s.pool.QueryRow(ctx,
		`SELECT `+generated.ProfileQrTokenCols+` FROM profile_qr_tokens
		 WHERE owner_user_id = $1 AND user_handle = $2 AND style_version = $3 AND status = 'active' AND revoked_at IS NULL
		 ORDER BY created_at DESC
		 LIMIT 1`,
		ownerUserID, userHandle, styleVersion))
}

func (s *PgProfileQrTokenStore) FindByTokenHash(ctx context.Context, tokenHash string) (*model.ProfileQrToken, error) {
	return generated.ScanProfileQrToken(s.pool.QueryRow(ctx,
		`SELECT `+generated.ProfileQrTokenCols+` FROM profile_qr_tokens WHERE token_hash = $1`,
		tokenHash))
}

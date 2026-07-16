package persistence

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	repository "quwoquan_service/services/user-service/internal/domain/user/ports"
)

// PgUserAuthStore extends pgUserAuthStoreBase with refresh-token operations.
type PgUserAuthStore struct{ pgUserAuthStoreBase }

var _ repository.AccountSessionStore = (*PgUserAuthStore)(nil)

func NewPgUserAuthStore(pool *pgxpool.Pool) *PgUserAuthStore {
	return &PgUserAuthStore{pgUserAuthStoreBase{pool: pool}}
}

func (s *PgUserAuthStore) FindByRefreshToken(ctx context.Context, refreshToken string) (*model.UserAuth, error) {
	return scanUserAuth(s.pool.QueryRow(ctx,
		`SELECT `+userAuthCols+` FROM user_auth WHERE refresh_token = $1`,
		refreshToken,
	))
}

func (s *PgUserAuthStore) UpsertRefreshToken(ctx context.Context, ownerID, refreshToken string, expiresAt time.Time) error {
	now := time.Now().UTC()
	_, err := s.pool.Exec(ctx, `
		INSERT INTO user_auth (
			user_id, password_hash, otp_secret, refresh_token, refresh_token_expires_at,
			last_login_at, last_login_ip, login_fail_count, locked_until, created_at, updated_at
		)
		VALUES ($1, '', '', $2, $3, $4, '', 0, NULL, $4, $4)
		ON CONFLICT (user_id) DO UPDATE SET
			refresh_token = EXCLUDED.refresh_token,
			refresh_token_expires_at = EXCLUDED.refresh_token_expires_at,
			last_login_at = EXCLUDED.last_login_at,
			login_fail_count = 0,
			locked_until = NULL,
			updated_at = EXCLUDED.updated_at
	`, ownerID, refreshToken, expiresAt.UTC(), now)
	return err
}

func (s *PgUserAuthStore) RevokeRefreshToken(ctx context.Context, ownerID string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE user_auth SET refresh_token = '', refresh_token_expires_at = NULL, updated_at = $2 WHERE user_id = $1`,
		ownerID,
		time.Now().UTC(),
	)
	return err
}

func (s *PgUserAuthStore) RevokeRefreshTokenValue(ctx context.Context, refreshToken string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE user_auth SET refresh_token = '', refresh_token_expires_at = NULL, updated_at = $2 WHERE refresh_token = $1`,
		refreshToken,
		time.Now().UTC(),
	)
	return err
}

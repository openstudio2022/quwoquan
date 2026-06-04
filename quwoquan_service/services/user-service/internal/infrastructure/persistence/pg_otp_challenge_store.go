package persistence

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/application"
)

type PgOtpChallengeStore struct {
	pool *pgxpool.Pool
}

func NewPgOtpChallengeStore(pool *pgxpool.Pool) *PgOtpChallengeStore {
	return &PgOtpChallengeStore{pool: pool}
}

func (s *PgOtpChallengeStore) CreateChallenge(ctx context.Context, challenge application.OtpChallenge) (application.OtpChallenge, error) {
	now := time.Now().UTC()
	if challenge.CreatedAt.IsZero() {
		challenge.CreatedAt = now
	}
	challenge.UpdatedAt = now
	_, err := s.pool.Exec(ctx, `
		INSERT INTO otp_challenges (
			challenge_id, request_id, phone, phone_hash, code_hash, status,
			idempotency_key, expires_at, consumed_at, created_at, updated_at
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NULL, $9, $10)
		ON CONFLICT (idempotency_key) DO UPDATE SET
			updated_at = EXCLUDED.updated_at
	`, challenge.ChallengeID, challenge.RequestID, challenge.Phone, challenge.PhoneHash, challenge.CodeHash, challenge.Status,
		challenge.IdempotencyKey, challenge.ExpiresAt.UTC(), challenge.CreatedAt, challenge.UpdatedAt)
	return challenge, err
}

func (s *PgOtpChallengeStore) FindLatestChallenge(ctx context.Context, phone string, now time.Time) (*application.OtpChallenge, error) {
	row := s.pool.QueryRow(ctx, `
		SELECT challenge_id, request_id, phone, phone_hash, code_hash, status,
		       idempotency_key, expires_at, consumed_at, created_at, updated_at
		FROM otp_challenges
		WHERE phone = $1 AND expires_at > $2 AND consumed_at IS NULL
		ORDER BY created_at DESC
		LIMIT 1
	`, phone, now.UTC())
	return scanOtpChallenge(row)
}

func (s *PgOtpChallengeStore) MarkChallengeDelivered(ctx context.Context, requestID string, status string) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE otp_challenges
		SET status = $2, updated_at = $3
		WHERE request_id = $1 AND consumed_at IS NULL
	`, requestID, status, time.Now().UTC())
	return err
}

func (s *PgOtpChallengeStore) MarkChallengeFailed(ctx context.Context, requestID string, reason string) error {
	_ = reason
	_, err := s.pool.Exec(ctx, `
		UPDATE otp_challenges
		SET status = $2, updated_at = $3
		WHERE request_id = $1 AND consumed_at IS NULL
	`, requestID, application.OtpChallengeStatusFailed, time.Now().UTC())
	return err
}

func (s *PgOtpChallengeStore) ConsumeChallenge(ctx context.Context, challengeID string, now time.Time) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE otp_challenges
		SET status = $2, consumed_at = $3, updated_at = $3
		WHERE challenge_id = $1 AND consumed_at IS NULL
	`, challengeID, application.OtpChallengeStatusConsumed, now.UTC())
	return err
}

func scanOtpChallenge(row pgx.Row) (*application.OtpChallenge, error) {
	var challenge application.OtpChallenge
	var consumedAt *time.Time
	err := row.Scan(
		&challenge.ChallengeID,
		&challenge.RequestID,
		&challenge.Phone,
		&challenge.PhoneHash,
		&challenge.CodeHash,
		&challenge.Status,
		&challenge.IdempotencyKey,
		&challenge.ExpiresAt,
		&consumedAt,
		&challenge.CreatedAt,
		&challenge.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	challenge.ConsumedAt = consumedAt
	return &challenge, nil
}

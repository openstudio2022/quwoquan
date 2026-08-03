package api_integration

import (
	"context"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengepersistence "quwoquan_service/services/user-service/internal/account/authentication_challenge/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestAuthenticationChallengePostgresCreateIsIdempotent(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store, err := challengepersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		facade := challengeapp.NewAuthenticationChallengeCommandFacade(store, challengeapp.OTPCredentialVerifier{})
		command := challengeapp.CreateChallengeCommand{
			ID: "challenge-pg-1", AccountID: "account-pg-1", Purpose: "phone_login",
			Channel: "sms", DestinationHash: "destination-hash", SecretRef: "otp-secret-ref",
			IdempotencyKey: "challenge-create-key", ExpiresAt: time.Now().UTC().Add(5 * time.Minute),
		}
		first, err := facade.CreateChallenge(ctx, command)
		if err != nil {
			t.Fatal(err)
		}
		command.ID = "challenge-pg-retry"
		replayed, err := facade.CreateChallenge(ctx, command)
		if err != nil || !replayed.IdempotentReplay || replayed.Challenge.ID != first.Challenge.ID {
			t.Fatalf("AuthenticationChallenge replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var count int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM authentication_challenges WHERE idempotency_key=$1`, command.IdempotencyKey).Scan(&count); err != nil || count != 1 {
			t.Fatalf("AuthenticationChallenge row count=%d err=%v", count, err)
		}
	})
}

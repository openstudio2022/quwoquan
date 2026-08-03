package api_integration

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	sessionpersistence "quwoquan_service/services/user-service/internal/account/account_session/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestAccountSessionPostgresPersistsOnlyTokenHashAndOutbox(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store, err := sessionpersistence.NewAccountSessionPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		facade := sessionapp.NewAccountSessionCommandFacade(store)
		plaintext := "object-session-refresh-token"
		result, err := facade.Issue(ctx, sessionapp.IssueCommand{
			AccountID: "account-session-owner", DeviceID: "device-1",
			AuthenticationSubject: "phone:hash", IdentityOrigin: "phone",
			RefreshToken: []byte(plaintext), ExpiresAt: time.Now().UTC().Add(time.Hour),
		})
		if err != nil || result.SessionID == "" || result.LineageID == "" {
			t.Fatalf("issue AccountSession: result=%+v err=%v", result, err)
		}
		var tokenHash string
		if err := pool.QueryRow(ctx, `SELECT refresh_token_hash FROM account_sessions WHERE session_id=$1`, result.SessionID).Scan(&tokenHash); err != nil {
			t.Fatal(err)
		}
		if tokenHash == "" || tokenHash == plaintext || strings.Contains(tokenHash, plaintext) {
			t.Fatalf("AccountSession persisted plaintext token: %q", tokenHash)
		}
		var events int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM account_sessions_outbox WHERE aggregate_id=$1`, result.SessionID).Scan(&events); err != nil || events != 1 {
			t.Fatalf("AccountSession outbox mismatch: count=%d err=%v", events, err)
		}
	})
}

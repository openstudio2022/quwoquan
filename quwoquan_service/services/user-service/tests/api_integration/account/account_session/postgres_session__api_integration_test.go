// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/auth-token-lifecycle/spec.md#gwt-002
// readiness_case: refresh-token-api
// readiness_case: logout-api
package api_integration

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	rtauth "quwoquan_service/runtime/auth"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	sessionports "quwoquan_service/services/user-service/internal/account/account_session/domain/ports"
	sessionpersistence "quwoquan_service/services/user-service/internal/account/account_session/infrastructure/persistence"
	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	accountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	userpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/user/persistence"
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

func TestRefreshAndLogoutUseCanonicalPostgresAccountSession(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		const (
			ownerID       = "account-session-readiness-owner"
			personaID     = "account-session-readiness-persona"
			originalToken = "account-session-readiness-refresh"
		)
		if err := usersupport.SeedAccountPersona(ctx, pool, ownerID, personaID); err != nil {
			t.Fatalf("seed AccountSession owner: %v", err)
		}
		store, err := sessionpersistence.NewAccountSessionPostgresStore(pool)
		if err != nil {
			t.Fatalf("account session store: %v", err)
		}
		sessions := sessionapp.NewAccountSessionCommandFacade(store)
		issued, err := sessions.Issue(ctx, sessionapp.IssueCommand{
			AccountID:             ownerID,
			DeviceID:              "session-device-1",
			AuthenticationSubject: "session-subject-1",
			IdentityOrigin:        "phone",
			RefreshToken:          []byte(originalToken),
			ExpiresAt:             time.Now().UTC().Add(24 * time.Hour),
		})
		if err != nil {
			t.Fatalf("seed AccountSession: %v", err)
		}
		security, err := accountpersistence.NewEnforcementStore(pool)
		if err != nil {
			t.Fatalf("account security reader: %v", err)
		}
		signer, err := rtauth.NewHS256Signer(rtauth.TokenConfig{
			Secret:       []byte("account-session-api-secret-32bytes"),
			Issuer:       "https://auth.quwoquan.test",
			Audience:     "quwoquan-api",
			Type:         rtauth.TokenTypeAccess,
			TokenVersion: 1,
			TTL:          30 * time.Minute,
		})
		if err != nil {
			t.Fatalf("access signer: %v", err)
		}
		service := accountapp.NewAuthService(
			accountpersistence.NewPgProfileStore(pool),
			userpersistence.NewPgPersonaStore(pool),
			nil,
			nil,
			nil,
			accountapp.WithAccountSessionCommands(sessions),
			accountapp.WithAccountSecurityReader(security),
			accountapp.WithAccessTokenSigner(signer),
		)

		rotated, err := service.RefreshToken(ctx, originalToken)
		if err != nil {
			t.Fatalf("RefreshToken: %v", err)
		}
		if rotated.OwnerID != ownerID || rotated.RefreshToken == "" ||
			rotated.RefreshToken == originalToken || rotated.AccessToken == "" {
			t.Fatalf("rotated AccountSession grant=%+v", rotated)
		}
		if err := service.Logout(ctx, ownerID, rotated.RefreshToken); err != nil {
			t.Fatalf("Logout: %v", err)
		}
		var activeCount, outboxCount, authenticatedCount, rotatedCount, revokedCount int
		if err := pool.QueryRow(
			ctx,
			`SELECT COUNT(*) FROM account_sessions WHERE lineage_id=$1 AND status='active'`,
			issued.LineageID,
		).Scan(&activeCount); err != nil {
			t.Fatalf("count active AccountSessions: %v", err)
		}
		if err := pool.QueryRow(
			ctx,
			`SELECT COUNT(*) FROM account_sessions_outbox WHERE aggregate_id IN (SELECT session_id FROM account_sessions WHERE lineage_id=$1)`,
			issued.LineageID,
		).Scan(&outboxCount); err != nil {
			t.Fatalf("count AccountSession outbox: %v", err)
		}
		if activeCount != 0 {
			t.Fatalf("AccountSession lifecycle active=%d outbox=%d", activeCount, outboxCount)
		}
		if err := pool.QueryRow(ctx, `
SELECT COUNT(*) FILTER (WHERE event_type='AccountSessionAuthenticated'),
       COUNT(*) FILTER (WHERE event_type='AccountSessionRotated'),
       COUNT(*) FILTER (WHERE event_type='AccountSessionRevoked')
FROM account_sessions_outbox
WHERE aggregate_id IN (
  SELECT session_id FROM account_sessions WHERE lineage_id=$1
)`, issued.LineageID).Scan(&authenticatedCount, &rotatedCount, &revokedCount); err != nil {
			t.Fatalf("count AccountSession lifecycle facts: %v", err)
		}
		if outboxCount != 3 || authenticatedCount != 1 || rotatedCount != 1 || revokedCount != 1 {
			t.Fatalf(
				"AccountSession lifecycle facts total=%d authenticated=%d rotated=%d revoked=%d",
				outboxCount,
				authenticatedCount,
				rotatedCount,
				revokedCount,
			)
		}
		var (
			authenticatedAggregateVersion int64
			authenticatedSessionID        string
			authenticatedSubject          string
			authenticatedOrigin           string
			authenticatedDevice           string
			authenticatedAt               time.Time
		)
		if err := pool.QueryRow(ctx, `
SELECT aggregate_version,
       payload_json->>'sessionId',
       payload_json->>'authenticationSubject',
       payload_json->>'identityOrigin',
       payload_json->>'deviceId',
       (payload_json->>'issuedAt')::timestamptz
FROM account_sessions_outbox
WHERE event_type='AccountSessionAuthenticated' AND aggregate_id=$1`, issued.SessionID).Scan(
			&authenticatedAggregateVersion,
			&authenticatedSessionID,
			&authenticatedSubject,
			&authenticatedOrigin,
			&authenticatedDevice,
			&authenticatedAt,
		); err != nil {
			t.Fatalf("read AccountSessionAuthenticated fact: %v", err)
		}
		if authenticatedAggregateVersion != 1 ||
			authenticatedSessionID != issued.SessionID ||
			authenticatedSubject != "session-subject-1" ||
			authenticatedOrigin != "phone" ||
			authenticatedDevice != "session-device-1" ||
			authenticatedAt.IsZero() {
			t.Fatalf(
				"AccountSessionAuthenticated payload/version mismatch: version=%d session=%q subject=%q origin=%q device=%q issuedAt=%v",
				authenticatedAggregateVersion,
				authenticatedSessionID,
				authenticatedSubject,
				authenticatedOrigin,
				authenticatedDevice,
				authenticatedAt,
			)
		}
		var rotatedSessionID string
		if err := pool.QueryRow(ctx, `
SELECT session_id
FROM account_sessions
WHERE lineage_id=$1 AND session_id<>$2`, issued.LineageID, issued.SessionID).Scan(
			&rotatedSessionID,
		); err != nil {
			t.Fatalf("read rotated AccountSession: %v", err)
		}
		var (
			rotatedAggregateVersion int64
			rotatedAccountID        string
			rotatedDeviceID         string
			rotatedLineageID        string
			rotatedToSessionID      string
			rotatedAt               time.Time
		)
		if err := pool.QueryRow(ctx, `
SELECT aggregate_version,
       payload_json->>'accountId',
       payload_json->>'deviceId',
       payload_json->>'lineageId',
       payload_json->>'rotatedToSessionId',
       (payload_json->>'rotatedAt')::timestamptz
FROM account_sessions_outbox
WHERE event_type='AccountSessionRotated' AND aggregate_id=$1`, issued.SessionID).Scan(
			&rotatedAggregateVersion,
			&rotatedAccountID,
			&rotatedDeviceID,
			&rotatedLineageID,
			&rotatedToSessionID,
			&rotatedAt,
		); err != nil {
			t.Fatalf("read AccountSessionRotated fact: %v", err)
		}
		if rotatedAggregateVersion != 2 ||
			rotatedAccountID != ownerID ||
			rotatedDeviceID != "session-device-1" ||
			rotatedLineageID != issued.LineageID ||
			rotatedToSessionID != rotatedSessionID ||
			rotatedAt.IsZero() {
			t.Fatalf(
				"AccountSessionRotated payload/version mismatch: version=%d account=%q device=%q lineage=%q rotatedTo=%q rotatedAt=%v",
				rotatedAggregateVersion,
				rotatedAccountID,
				rotatedDeviceID,
				rotatedLineageID,
				rotatedToSessionID,
				rotatedAt,
			)
		}
		var (
			revokedAggregateVersion int64
			revokedSessionID        string
			revokedAccountID        string
			revokedDeviceID         string
			revokedReason           string
			revokedAt               time.Time
		)
		if err := pool.QueryRow(ctx, `
SELECT aggregate_version,
       payload_json->>'sessionId',
       payload_json->>'accountId',
       payload_json->>'deviceId',
       payload_json->>'reason',
       (payload_json->>'revokedAt')::timestamptz
FROM account_sessions_outbox
WHERE event_type='AccountSessionRevoked' AND aggregate_id=$1`, rotatedSessionID).Scan(
			&revokedAggregateVersion,
			&revokedSessionID,
			&revokedAccountID,
			&revokedDeviceID,
			&revokedReason,
			&revokedAt,
		); err != nil {
			t.Fatalf("read AccountSessionRevoked fact: %v", err)
		}
		if revokedAggregateVersion != 2 ||
			revokedSessionID != rotatedSessionID ||
			revokedAccountID != ownerID ||
			revokedDeviceID != "session-device-1" ||
			revokedReason != sessionports.RevokeReasonLogout ||
			revokedAt.IsZero() {
			t.Fatalf(
				"AccountSessionRevoked payload/version mismatch: version=%d session=%q account=%q device=%q reason=%q revokedAt=%v",
				revokedAggregateVersion,
				revokedSessionID,
				revokedAccountID,
				revokedDeviceID,
				revokedReason,
				revokedAt,
			)
		}
		if _, err := service.RefreshToken(ctx, rotated.RefreshToken); err == nil {
			t.Fatal("logged-out refresh token was accepted")
		}
	})
}

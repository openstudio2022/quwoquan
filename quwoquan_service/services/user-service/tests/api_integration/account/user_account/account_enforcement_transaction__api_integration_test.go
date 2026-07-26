package api_integration

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	sessionports "quwoquan_service/services/user-service/internal/account/account_session/domain/ports"
	sessionpersistence "quwoquan_service/services/user-service/internal/account/account_session/infrastructure/persistence"
	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
)

func TestAccountEnforcementTransactionSuspendsRevokesAndRestores(t *testing.T) {
	cleanAll(t)
	const (
		accountID = "enforcement-owner"
		personaID = "enforcement-persona"
	)
	createTestProfile(t, accountID, "Enforcement Owner")
	createTestPersonaFull(
		t,
		"",
		accountID,
		personaID,
		"Enforcement Persona",
		"open",
		true,
	)
	_, err := pgPool.Exec(context.Background(), `
INSERT INTO account_sessions(
  session_id, account_id, device_id, refresh_token_hash, lineage_id,
  status, issued_at, expires_at, version, created_at, updated_at
) VALUES (
  'enforcement-session', $1, 'device-1', $2,
  'enforcement-lineage', 'active', NOW(), NOW() + INTERVAL '1 day', 1, NOW(), NOW()
)`, accountID, integrationRefreshTokenHash("enforcement-refresh-token"))
	if err != nil {
		t.Fatalf("create active refresh session: %v", err)
	}

	store, err := useraccountpersistence.NewEnforcementStore(pgPool)
	if err != nil {
		t.Fatalf("construct enforcement store: %v", err)
	}
	facade := useraccountapp.NewAccountEnforcementCommandFacade(store)
	suspendDecision := accountports.EnforcementDecision{
		DecisionID:     "enforcement-suspend-decision",
		CaseRef:        "case-opaque-suspend",
		DecisionDigest: "digest-suspend",
		ApprovedAt:     time.Date(2026, time.July, 21, 0, 0, 0, 0, time.UTC),
	}
	suspended, err := facade.SuspendAccount(
		context.Background(),
		useraccountapp.EnforcementCommand{
			AccountID: accountID,
			Decision:  suspendDecision,
		},
	)
	if err != nil {
		t.Fatalf("suspend account: %v", err)
	}
	if suspended.AccountState != "suspended" || suspended.AuthEpoch != 2 ||
		suspended.IdempotentReplay {
		t.Fatalf("unexpected first suspend outcome: %+v", suspended)
	}

	var (
		accountState string
		authEpoch    int64
		sessionState string
		eventType    string
		payloadRaw   []byte
	)
	if err := pgPool.QueryRow(context.Background(), `
SELECT account_state, auth_epoch
FROM user_profiles
WHERE user_id=$1`, accountID).Scan(&accountState, &authEpoch); err != nil {
		t.Fatalf("read suspended account: %v", err)
	}
	if err := pgPool.QueryRow(context.Background(), `
SELECT status
FROM account_sessions
WHERE session_id='enforcement-session'`).Scan(&sessionState); err != nil {
		t.Fatalf("read revoked refresh session: %v", err)
	}
	if err := pgPool.QueryRow(context.Background(), `
SELECT event_type, payload_json
FROM user_account_outbox
WHERE aggregate_id=$1
ORDER BY occurred_at
LIMIT 1`, accountID).Scan(&eventType, &payloadRaw); err != nil {
		t.Fatalf("read suspend outbox: %v", err)
	}
	if accountState != "suspended" || authEpoch != 2 || sessionState != "revoked" ||
		eventType != useraccountapp.UserSuspendedEventName {
		t.Fatalf(
			"suspend must atomically restrict account/session/outbox: state=%s epoch=%d session=%s event=%s",
			accountState,
			authEpoch,
			sessionState,
			eventType,
		)
	}
	sessionStore, err := sessionpersistence.NewAccountSessionPostgresStore(pgPool)
	if err != nil {
		t.Fatalf("construct account session store: %v", err)
	}
	if _, err := sessionStore.RotateSession(
		context.Background(),
		integrationRefreshTokenHash("enforcement-refresh-token"),
		integrationRefreshTokenHash("enforcement-next-refresh-token"),
		time.Now().UTC().Add(time.Hour),
	); !errors.Is(err, sessionports.ErrSessionAccountSuspended) {
		t.Fatalf("suspended refresh session must retain structured reason, got %v", err)
	}
	var payload map[string]any
	if err := json.Unmarshal(payloadRaw, &payload); err != nil {
		t.Fatalf("decode suspend payload: %v", err)
	}
	if _, leaked := payload["caseRef"]; leaked {
		t.Fatalf("suspend event leaked case reference: %#v", payload)
	}
	if _, leaked := payload["decisionDigest"]; leaked {
		t.Fatalf("suspend event leaked decision digest: %#v", payload)
	}
	if payload["decisionRef"] != suspendDecision.DecisionID {
		t.Fatalf("suspend event must carry opaque decision reference: %#v", payload)
	}
	staleToken, err := testAccessSigner.Sign(rtauth.TokenSubject{
		AccountID: accountID,
		PersonaID: personaID,
		AuthEpoch: 1,
	})
	if err != nil {
		t.Fatalf("issue pre-suspension token: %v", err)
	}
	staleHeaders := map[string]string{"Authorization": "Bearer " + staleToken}
	if response := doRequest(t, http.MethodGet, "/me", "", staleHeaders); response.Code != http.StatusForbidden {
		t.Fatalf(
			"suspended account must be rejected before owner handler: code=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}

	replayed, err := facade.SuspendAccount(
		context.Background(),
		useraccountapp.EnforcementCommand{
			AccountID: accountID,
			Decision:  suspendDecision,
		},
	)
	if err != nil {
		t.Fatalf("replay suspend account: %v", err)
	}
	if !replayed.IdempotentReplay || replayed.AuthEpoch != 2 {
		t.Fatalf("same decision must return stable receipt: %+v", replayed)
	}

	restored, err := facade.RestoreAccount(
		context.Background(),
		useraccountapp.EnforcementCommand{
			AccountID: accountID,
			Decision: accountports.EnforcementDecision{
				DecisionID:     "enforcement-restore-decision",
				CaseRef:        "appeal-opaque-restore",
				DecisionDigest: "digest-restore",
				ApprovedAt:     time.Date(2026, time.July, 21, 1, 0, 0, 0, time.UTC),
			},
		},
	)
	if err != nil {
		t.Fatalf("restore account: %v", err)
	}
	if restored.AccountState != "active" || restored.AuthEpoch != 3 {
		t.Fatalf("restore must advance epoch without resurrecting old sessions: %+v", restored)
	}
	if err := pgPool.QueryRow(context.Background(), `
SELECT status
FROM account_sessions
WHERE session_id='enforcement-session'`).Scan(&sessionState); err != nil {
		t.Fatalf("read session after restore: %v", err)
	}
	if sessionState != "revoked" {
		t.Fatalf("restore must not revive the pre-suspension refresh session: %s", sessionState)
	}
	if response := doRequest(t, http.MethodGet, "/me", "", staleHeaders); response.Code != http.StatusUnauthorized {
		t.Fatalf(
			"restore must not accept pre-suspension token: code=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}
	freshToken, err := testAccessSigner.Sign(rtauth.TokenSubject{
		AccountID: accountID,
		PersonaID: personaID,
		AuthEpoch: restored.AuthEpoch,
	})
	if err != nil {
		t.Fatalf("issue restored account token: %v", err)
	}
	if response := doRequest(
		t,
		http.MethodGet,
		"/me",
		"",
		map[string]string{"Authorization": "Bearer " + freshToken},
	); response.Code != http.StatusOK {
		t.Fatalf(
			"only a current-epoch token may access after restore: code=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}
}

func integrationRefreshTokenHash(token string) string {
	digest := sha256.Sum256([]byte(token))
	return fmt.Sprintf("%x", digest)
}

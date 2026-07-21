package persistence

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	sessionports "quwoquan_service/services/user-service/internal/domain/account/account_session/ports"
)

// AccountSessionPostgresStore 实现 AccountSession 聚合的对象专属端口：
// 每个会话一行，refresh token 只保存 SHA-256 哈希；轮换保持 lineage，
// 旧 hash 重放触发整条 lineage 吊销；状态与 outbox 同事务提交。
type AccountSessionPostgresStore struct {
	pool *pgxpool.Pool
}

func NewAccountSessionPostgresStore(pool *pgxpool.Pool) (*AccountSessionPostgresStore, error) {
	if pool == nil {
		return nil, errors.New("AccountSession PostgreSQL pool is required")
	}
	return &AccountSessionPostgresStore{pool: pool}, nil
}

var _ sessionports.AccountSessionStore = (*AccountSessionPostgresStore)(nil)

func (s *AccountSessionPostgresStore) IssueSession(
	ctx context.Context,
	accountID string,
	deviceID string,
	authenticationSubject string,
	identityOrigin string,
	refreshTokenHash string,
	expiresAt time.Time,
) (sessionports.IssuedSession, error) {
	accountID = strings.TrimSpace(accountID)
	refreshTokenHash = strings.TrimSpace(refreshTokenHash)
	deviceID = strings.TrimSpace(deviceID)
	authenticationSubject = strings.TrimSpace(authenticationSubject)
	identityOrigin = strings.TrimSpace(identityOrigin)
	if accountID == "" ||
		deviceID == "" ||
		authenticationSubject == "" ||
		identityOrigin == "" ||
		refreshTokenHash == "" {
		return sessionports.IssuedSession{},
			errors.New(
				"account session requires account, device, authentication subject, identity origin and token hash",
			)
	}
	sessionID, err := randomSessionID()
	if err != nil {
		return sessionports.IssuedSession{}, err
	}
	lineageID, err := randomSessionID()
	if err != nil {
		return sessionports.IssuedSession{}, err
	}
	issued := sessionports.IssuedSession{
		SessionID: sessionID,
		AccountID: accountID,
		DeviceID:  deviceID,
		LineageID: lineageID,
		ExpiresAt: expiresAt.UTC(),
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return sessionports.IssuedSession{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `
INSERT INTO account_sessions (
  session_id, account_id, device_id, refresh_token_hash, lineage_id,
  status, issued_at, expires_at
) VALUES ($1,$2,$3,$4,$5,'active',NOW(),$6)`,
		sessionID, accountID, issued.DeviceID, refreshTokenHash, lineageID,
		issued.ExpiresAt,
	); err != nil {
		return sessionports.IssuedSession{}, err
	}
	issuedAt := time.Now().UTC()
	if err := appendSessionEvent(ctx, tx, sessionID, 1,
		sessionports.AccountSessionAuthenticatedEvent, sessionEventPayload{
			SessionID: sessionID, AccountID: accountID,
			DeviceID: issued.DeviceID, LineageID: lineageID,
			AuthenticationSubject: authenticationSubject,
			IdentityOrigin:        identityOrigin,
			IssuedAt:              &issuedAt,
		}); err != nil {
		return sessionports.IssuedSession{}, err
	}
	return issued, tx.Commit(ctx)
}

func (s *AccountSessionPostgresStore) RotateSession(
	ctx context.Context,
	currentTokenHash string,
	nextTokenHash string,
	expiresAt time.Time,
) (sessionports.IssuedSession, error) {
	currentTokenHash = strings.TrimSpace(currentTokenHash)
	nextTokenHash = strings.TrimSpace(nextTokenHash)
	if currentTokenHash == "" || nextTokenHash == "" {
		return sessionports.IssuedSession{},
			errors.New("session rotation requires current and next token hashes")
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return sessionports.IssuedSession{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var (
		sessionID    string
		accountID    string
		deviceID     string
		lineageID    string
		status       string
		revokeReason string
		expiresDB    time.Time
		version      int64
	)
	err = tx.QueryRow(ctx, `
SELECT session_id, account_id, device_id, lineage_id, status,
       COALESCE(revoke_reason, ''), expires_at, version
FROM account_sessions
WHERE refresh_token_hash=$1
FOR UPDATE`, currentTokenHash).Scan(
		&sessionID,
		&accountID,
		&deviceID,
		&lineageID,
		&status,
		&revokeReason,
		&expiresDB,
		&version,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return sessionports.IssuedSession{}, sessionports.ErrSessionNotFound
	}
	if err != nil {
		return sessionports.IssuedSession{}, err
	}
	now := time.Now().UTC()
	switch status {
	case "active":
		if expiresDB.Before(now) {
			if _, err := tx.Exec(ctx, `
UPDATE account_sessions SET status='expired', updated_at=NOW(), version=version+1
WHERE session_id=$1`, sessionID); err != nil {
				return sessionports.IssuedSession{}, err
			}
			if err := tx.Commit(ctx); err != nil {
				return sessionports.IssuedSession{}, err
			}
			return sessionports.IssuedSession{}, sessionports.ErrSessionExpired
		}
	case "rotated":
		// 旧 token 重放：吊销整条 lineage 并提交事实，然后拒绝。
		if err := s.revokeLineage(ctx, tx, lineageID, accountID, deviceID,
			sessionports.RevokeReasonReplay); err != nil {
			return sessionports.IssuedSession{}, err
		}
		if err := tx.Commit(ctx); err != nil {
			return sessionports.IssuedSession{}, err
		}
		return sessionports.IssuedSession{}, sessionports.ErrSessionReplayed
	case "revoked":
		if strings.TrimSpace(revokeReason) == "account_suspended" {
			return sessionports.IssuedSession{},
				sessionports.ErrSessionAccountSuspended
		}
		return sessionports.IssuedSession{}, sessionports.ErrSessionRevoked
	default:
		return sessionports.IssuedSession{}, sessionports.ErrSessionExpired
	}

	if _, err := tx.Exec(ctx, `
UPDATE account_sessions SET status='rotated', updated_at=NOW(), version=version+1
WHERE session_id=$1`, sessionID); err != nil {
		return sessionports.IssuedSession{}, err
	}
	nextSessionID, err := randomSessionID()
	if err != nil {
		return sessionports.IssuedSession{}, err
	}
	issued := sessionports.IssuedSession{
		SessionID: nextSessionID,
		AccountID: accountID,
		DeviceID:  deviceID,
		LineageID: lineageID,
		ExpiresAt: expiresAt.UTC(),
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO account_sessions (
  session_id, account_id, device_id, refresh_token_hash, lineage_id,
  rotated_from_hash, status, issued_at, expires_at
) VALUES ($1,$2,$3,$4,$5,$6,'active',NOW(),$7)`,
		nextSessionID, accountID, deviceID, nextTokenHash, lineageID,
		currentTokenHash, issued.ExpiresAt,
	); err != nil {
		return sessionports.IssuedSession{}, err
	}
	return issued, tx.Commit(ctx)
}

func (s *AccountSessionPostgresStore) RevokeByTokenHash(
	ctx context.Context,
	refreshTokenHash string,
	reason string,
) error {
	refreshTokenHash = strings.TrimSpace(refreshTokenHash)
	if refreshTokenHash == "" {
		return nil
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var (
		sessionID string
		accountID string
		deviceID  string
		status    string
		version   int64
	)
	err = tx.QueryRow(ctx, `
SELECT session_id, account_id, device_id, status, version
FROM account_sessions
WHERE refresh_token_hash=$1
FOR UPDATE`, refreshTokenHash).Scan(&sessionID, &accountID, &deviceID, &status, &version)
	if errors.Is(err, pgx.ErrNoRows) {
		// logout 对未知 token 幂等：可能从未签发或已被清理。
		return tx.Commit(ctx)
	}
	if err != nil {
		return err
	}
	if status == "revoked" {
		return tx.Commit(ctx)
	}
	nextVersion := version + 1
	if _, err := tx.Exec(ctx, `
UPDATE account_sessions
SET status='revoked', revoked_at=NOW(), revoke_reason=$2, updated_at=NOW(), version=$3
WHERE session_id=$1`, sessionID, strings.TrimSpace(reason), nextVersion); err != nil {
		return err
	}
	if err := appendSessionEvent(ctx, tx, sessionID, nextVersion,
		sessionports.AccountSessionRevokedEvent, sessionEventPayload{
			SessionID: sessionID, AccountID: accountID, DeviceID: deviceID,
			Reason: strings.TrimSpace(reason), RevokedAt: timePtr(time.Now().UTC()),
		}); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func (s *AccountSessionPostgresStore) RevokeAllForAccount(
	ctx context.Context,
	accountID string,
	reason string,
) error {
	accountID = strings.TrimSpace(accountID)
	if accountID == "" {
		return nil
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	rows, err := tx.Query(ctx, `
SELECT session_id, device_id, version
FROM account_sessions
WHERE account_id=$1 AND status IN ('active','rotated')
FOR UPDATE`, accountID)
	if err != nil {
		return err
	}
	type target struct {
		sessionID string
		deviceID  string
		version   int64
	}
	targets := make([]target, 0, 4)
	for rows.Next() {
		var item target
		if err := rows.Scan(&item.sessionID, &item.deviceID, &item.version); err != nil {
			rows.Close()
			return err
		}
		targets = append(targets, item)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return err
	}
	for _, item := range targets {
		nextVersion := item.version + 1
		if _, err := tx.Exec(ctx, `
UPDATE account_sessions
SET status='revoked', revoked_at=NOW(), revoke_reason=$2, updated_at=NOW(), version=$3
WHERE session_id=$1`, item.sessionID, strings.TrimSpace(reason), nextVersion); err != nil {
			return err
		}
		if err := appendSessionEvent(ctx, tx, item.sessionID, nextVersion,
			sessionports.AccountSessionRevokedEvent, sessionEventPayload{
				SessionID: item.sessionID, AccountID: accountID,
				DeviceID: item.deviceID, Reason: strings.TrimSpace(reason),
				RevokedAt: timePtr(time.Now().UTC()),
			}); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

// revokeLineage 在已开启事务内吊销同 lineage 全部会话并记录一条重放事实。
func (s *AccountSessionPostgresStore) revokeLineage(
	ctx context.Context,
	tx pgx.Tx,
	lineageID string,
	accountID string,
	deviceID string,
	reason string,
) error {
	var maxVersion int64
	if err := tx.QueryRow(ctx, `
UPDATE account_sessions
SET status='revoked', revoked_at=NOW(), revoke_reason=$2, updated_at=NOW(), version=version+1
WHERE lineage_id=$1 AND status <> 'revoked'
RETURNING (SELECT COALESCE(MAX(version),0)+1 FROM account_sessions WHERE lineage_id=$1)`,
		lineageID, reason,
	).Scan(&maxVersion); err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return err
	}
	return appendSessionEvent(ctx, tx, lineageID, maxVersion,
		sessionports.AccountSessionRevokedEvent, sessionEventPayload{
			AccountID: accountID, DeviceID: deviceID,
			LineageID: lineageID, Reason: reason,
			RevokedAt: timePtr(time.Now().UTC()),
		})
}

type sessionEventPayload struct {
	SessionID             string     `json:"sessionId,omitempty"`
	AccountID             string     `json:"accountId"`
	DeviceID              string     `json:"deviceId,omitempty"`
	LineageID             string     `json:"lineageId,omitempty"`
	AuthenticationSubject string     `json:"authenticationSubject,omitempty"`
	IdentityOrigin        string     `json:"identityOrigin,omitempty"`
	IssuedAt              *time.Time `json:"issuedAt,omitempty"`
	RevokedAt             *time.Time `json:"revokedAt,omitempty"`
	Reason                string     `json:"reason,omitempty"`
}

func timePtr(value time.Time) *time.Time {
	return &value
}

func appendSessionEvent(
	ctx context.Context,
	tx pgx.Tx,
	aggregateID string,
	aggregateVersion int64,
	eventType string,
	payload sessionEventPayload,
) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	eventID, err := randomSessionID()
	if err != nil {
		return err
	}
	_, err = tx.Exec(ctx, `
INSERT INTO account_sessions_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,$4,$5,NOW())
ON CONFLICT (aggregate_id, aggregate_version) DO NOTHING`,
		eventID, aggregateID, aggregateVersion, eventType, body)
	return err
}

func randomSessionID() (string, error) {
	buffer := make([]byte, 16)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return hex.EncodeToString(buffer), nil
}

package persistence

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

type sessionCloseTarget struct {
	sessionID       string
	deviceID        string
	refreshHash     string
	lineageID       string
	rotatedFromHash *string
	status          string
	revokedAt       *time.Time
	revokeReason    *string
	version         int64
}

func closeAccountSessions(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	closedAt time.Time,
) error {
	// 历史 session outbox 可能包含 authentication subject/device id；保留
	// 事件元数据作安全审计，擦除 payload 并阻止旧事件在注销后继续投递。
	if _, err := tx.Exec(ctx, `
UPDATE account_sessions_outbox
SET payload_json=jsonb_build_object('accountId',$1,'redacted',true),
    published_at=COALESCE(published_at,$2),
    last_error=''
WHERE payload_json->>'accountId'=$1`, accountID, closedAt); err != nil {
		return fmt.Errorf("redact account session outbox on close: %w", err)
	}

	rows, err := tx.Query(ctx, `
SELECT session_id, device_id, refresh_token_hash, lineage_id,
       rotated_from_hash, status, revoked_at, revoke_reason, version
FROM account_sessions
WHERE account_id=$1
ORDER BY session_id
FOR UPDATE`, accountID)
	if err != nil {
		return fmt.Errorf("load account sessions for close: %w", err)
	}
	targets := make([]sessionCloseTarget, 0)
	for rows.Next() {
		var target sessionCloseTarget
		if err := rows.Scan(
			&target.sessionID,
			&target.deviceID,
			&target.refreshHash,
			&target.lineageID,
			&target.rotatedFromHash,
			&target.status,
			&target.revokedAt,
			&target.revokeReason,
			&target.version,
		); err != nil {
			rows.Close()
			return fmt.Errorf("scan account session for close: %w", err)
		}
		targets = append(targets, target)
	}
	rowsErr := rows.Err()
	rows.Close()
	if rowsErr != nil {
		return fmt.Errorf("iterate account sessions for close: %w", rowsErr)
	}

	for _, target := range targets {
		erasedRefreshHash := stableCloseEventID(
			"AccountSessionRefreshErased",
			target.sessionID,
		)
		erasedLineageID := stableCloseEventID(
			"AccountSessionLineageErased",
			target.sessionID,
		)
		reasonClosed := target.revokeReason != nil &&
			*target.revokeReason == "account_closed"
		if target.status == "revoked" &&
			target.deviceID == "" &&
			target.refreshHash == erasedRefreshHash &&
			target.lineageID == erasedLineageID &&
			target.rotatedFromHash == nil &&
			reasonClosed {
			continue
		}
		revokedAt := closedAt
		if target.revokedAt != nil {
			revokedAt = target.revokedAt.UTC()
		}
		nextVersion := target.version + 1
		tag, err := tx.Exec(ctx, `
UPDATE account_sessions
SET device_id='',
    refresh_token_hash=$3,
    lineage_id=$4,
    rotated_from_hash=NULL,
    status='revoked',
    revoked_at=$5,
    revoke_reason='account_closed',
    version=$6,
    updated_at=$7
WHERE session_id=$1 AND account_id=$2 AND version=$8`,
			target.sessionID,
			accountID,
			erasedRefreshHash,
			erasedLineageID,
			revokedAt,
			nextVersion,
			closedAt,
			target.version,
		)
		if err != nil {
			return fmt.Errorf("revoke and scrub account session: %w", err)
		}
		if tag.RowsAffected() != 1 {
			return fmt.Errorf("account session changed concurrently during close")
		}
		payload, err := json.Marshal(struct {
			AccountID string    `json:"accountId"`
			Reason    string    `json:"reason"`
			RevokedAt time.Time `json:"revokedAt"`
		}{
			AccountID: accountID,
			Reason:    "account_closed",
			RevokedAt: revokedAt,
		})
		if err != nil {
			return fmt.Errorf("encode close session outbox: %w", err)
		}
		if _, err := tx.Exec(ctx, `
INSERT INTO account_sessions_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,'AccountSessionRevoked',$4,$5)
ON CONFLICT (aggregate_id, aggregate_version) DO NOTHING`,
			stableCloseEventID("AccountSessionRevoked", target.sessionID),
			target.sessionID,
			nextVersion,
			payload,
			closedAt,
		); err != nil {
			return fmt.Errorf("append close session outbox: %w", err)
		}
	}
	return nil
}

package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
)

type credentialCloseTarget struct {
	id             string
	credentialType string
	credentialKey  string
	displayLabel   *string
	lastUsedAt     *time.Time
	active         bool
	version        int64
}

func loadCredentialCloseTargets(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
) ([]credentialCloseTarget, error) {
	rows, err := tx.Query(ctx, `
SELECT id, credential_type, credential_key, display_label,
       last_used_at, is_active, version
FROM credential_bindings
WHERE owner_id=$1
ORDER BY id
FOR UPDATE`, accountID)
	if err != nil {
		return nil, fmt.Errorf("load credentials for account close: %w", err)
	}
	defer rows.Close()
	targets := make([]credentialCloseTarget, 0)
	for rows.Next() {
		var target credentialCloseTarget
		if err := rows.Scan(
			&target.id,
			&target.credentialType,
			&target.credentialKey,
			&target.displayLabel,
			&target.lastUsedAt,
			&target.active,
			&target.version,
		); err != nil {
			return nil, fmt.Errorf("scan credential for account close: %w", err)
		}
		targets = append(targets, target)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate credentials for account close: %w", err)
	}
	return targets, nil
}

func authenticationDestinations(
	accountPhone string,
	credentials []credentialCloseTarget,
) ([]string, []string) {
	seen := make(map[string]struct{}, len(credentials)+1)
	phones := make([]string, 0, len(credentials)+1)
	appendPhone := func(value string) {
		value = strings.TrimSpace(value)
		if value == "" {
			return
		}
		if _, exists := seen[value]; exists {
			return
		}
		seen[value] = struct{}{}
		phones = append(phones, value)
	}
	appendPhone(accountPhone)
	for _, credential := range credentials {
		switch credential.credentialType {
		case "phone", "carrier_phone":
			appendPhone(credential.credentialKey)
		}
	}
	hashes := make([]string, 0, len(phones))
	for _, phone := range phones {
		digest := sha256.Sum256([]byte(phone))
		hashes = append(hashes, hex.EncodeToString(digest[:]))
	}
	return phones, hashes
}

func closeCredentialBindings(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	targets []credentialCloseTarget,
	closedAt time.Time,
) error {
	for _, target := range targets {
		erasedKey := erasedCredentialKey(target.id)
		if !target.active &&
			target.credentialKey == erasedKey &&
			target.displayLabel == nil &&
			target.lastUsedAt == nil {
			continue
		}
		nextVersion := target.version + 1
		tag, err := tx.Exec(ctx, `
UPDATE credential_bindings
SET credential_key=$3,
    display_label=NULL,
    is_active=false,
    last_used_at=NULL,
    version=$4
WHERE id=$1 AND owner_id=$2 AND version=$5`,
			target.id,
			accountID,
			erasedKey,
			nextVersion,
			target.version,
		)
		if err != nil {
			return fmt.Errorf("scrub credential on account close: %w", err)
		}
		if tag.RowsAffected() != 1 {
			return fmt.Errorf("credential changed concurrently during account close")
		}
		payload, err := json.Marshal(struct {
			ID string `json:"id"`
		}{ID: target.id})
		if err != nil {
			return fmt.Errorf("encode close credential outbox: %w", err)
		}
		if _, err := tx.Exec(ctx, `
INSERT INTO credential_bindings_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,'CredentialRevoked',$4,$5)
ON CONFLICT (aggregate_id, aggregate_version) DO NOTHING`,
			stableCloseEventID("CredentialRevoked", target.id),
			target.id,
			nextVersion,
			payload,
			closedAt,
		); err != nil {
			return fmt.Errorf("append close credential outbox: %w", err)
		}
	}
	return nil
}

func erasedCredentialKey(credentialID string) string {
	return "erased:" + stableCloseEventID("CredentialKey", credentialID)
}

func stableCloseEventID(eventType, aggregateID string) string {
	digest := sha256.Sum256([]byte(eventType + ":" + aggregateID))
	return hex.EncodeToString(digest[:])
}

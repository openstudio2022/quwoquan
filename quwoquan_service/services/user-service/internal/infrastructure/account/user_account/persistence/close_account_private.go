package persistence

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

func eraseAccountPrivateState(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	phoneCredentialKeys []string,
	destinationHashes []string,
	closedAt time.Time,
) error {
	if _, err := tx.Exec(ctx, `
UPDATE user_settings_outbox
SET payload_json=jsonb_build_object('accountId',$1,'redacted',true),
    published_at=COALESCE(published_at,$2),
    next_attempt_at=$2,
    last_error=''
WHERE aggregate_id=$1`, accountID, closedAt); err != nil {
		return fmt.Errorf("redact settings audit on account close: %w", err)
	}
	if err := execCloseStep(
		ctx,
		tx,
		"delete account settings",
		`DELETE FROM user_settings WHERE user_id=$1`,
		accountID,
	); err != nil {
		return err
	}
	if err := execCloseStep(
		ctx,
		tx,
		"delete account authentication secrets",
		`DELETE FROM user_auth WHERE user_id=$1`,
		accountID,
	); err != nil {
		return err
	}
	if err := execCloseStep(
		ctx,
		tx,
		"delete account device registrations",
		`DELETE FROM user_devices WHERE account_id=$1`,
		accountID,
	); err != nil {
		return err
	}
	if err := execCloseStep(
		ctx,
		tx,
		"delete anonymous device bindings",
		`DELETE FROM anonymous_device_bindings WHERE owner_id=$1`,
		accountID,
	); err != nil {
		return err
	}
	if err := execCloseStep(
		ctx,
		tx,
		"delete profile QR tokens",
		`DELETE FROM profile_qr_tokens WHERE owner_user_id=$1`,
		accountID,
	); err != nil {
		return err
	}
	if err := execCloseStep(
		ctx,
		tx,
		"delete owned contact discovery records",
		`DELETE FROM contact_discovery_records WHERE owner_account_id=$1`,
		accountID,
	); err != nil {
		return err
	}
	if err := execCloseStep(
		ctx,
		tx,
		"delete account authentication challenges",
		`DELETE FROM authentication_challenges
		 WHERE account_id=$1
		    OR phone=ANY($2::text[])
		    OR phone_hash=ANY($3::text[])`,
		accountID,
		phoneCredentialKeys,
		destinationHashes,
	); err != nil {
		return err
	}
	// 同意事实用于证明当时适用的协议版本与接受时间，具有合规审计价值；
	// 仅保留 account id、版本、时间与 operation，擦除设备和平台 PII。
	if err := execCloseStep(
		ctx,
		tx,
		"minimize consent audit records",
		`UPDATE consent_records
		    SET device_id=NULL, platform=NULL
		  WHERE owner_id=$1`,
		accountID,
	); err != nil {
		return err
	}
	return nil
}

func execCloseStep(
	ctx context.Context,
	tx pgx.Tx,
	step string,
	query string,
	args ...any,
) error {
	if _, err := tx.Exec(ctx, query, args...); err != nil {
		return fmt.Errorf("%s: %w", step, err)
	}
	return nil
}

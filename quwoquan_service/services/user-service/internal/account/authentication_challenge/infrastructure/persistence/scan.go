package persistence

import (
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"

	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
)

type rowScanner interface {
	Scan(dest ...any) error
}

func scanChallenge(
	row rowScanner,
) (challengemodel.AuthenticationChallenge, bool, error) {
	var (
		state             challengemodel.State
		status            string
		completionReceipt string
	)
	err := row.Scan(
		&state.ID,
		&state.AccountID,
		&state.Purpose,
		&state.Channel,
		&state.DestinationHash,
		&state.SecretRef,
		&status,
		&state.AttemptCount,
		&state.ExpiresAt,
		&state.CreatedAt,
		&state.CompletedAt,
		&completionReceipt,
		&state.Version,
		&state.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return challengemodel.AuthenticationChallenge{}, false, nil
	}
	if err != nil {
		return challengemodel.AuthenticationChallenge{}, false, fmt.Errorf(
			"scan authentication challenge: %w",
			err,
		)
	}
	state.Status = challengemodel.Status(status)
	state.CompletionFingerprint = completionReceipt
	challenge, err := challengemodel.Restore(state)
	if err != nil {
		return challengemodel.AuthenticationChallenge{}, false, fmt.Errorf(
			"restore authentication challenge: %w",
			err,
		)
	}
	return challenge, true, nil
}

const challengeSelectColumns = `
challenge_id,
COALESCE(account_id, ''),
purpose,
channel,
COALESCE(phone_hash, ''),
code_hash,
status,
failed_attempts,
expires_at,
created_at,
consumed_at,
COALESCE(completion_fingerprint, ''),
version,
updated_at`

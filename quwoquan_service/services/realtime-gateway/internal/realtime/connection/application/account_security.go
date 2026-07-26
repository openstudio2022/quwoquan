package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
)

var (
	// ErrAccountSecurityDenied is deliberately identifier-free. Transports map
	// it to their canonical unauthenticated/session-invalid result.
	ErrAccountSecurityDenied = errors.New("realtime account security denied")
	// ErrAccountSecurityUnavailable is a fail-closed result. It never permits
	// a ticket, a websocket upgrade, or a new long-poll session.
	ErrAccountSecurityUnavailable = errors.New(
		"realtime account security authority unavailable",
	)
)

// VerifyAccountSecurity reuses the same authority instance supplied to HTTP
// middleware. Ticket issuance/consumption and Hub attachment call it again so
// a credential issued before a terminal account event cannot open a session.
func VerifyAccountSecurity(
	ctx context.Context,
	authority rtauth.AccountSecurityAuthority,
	accountID string,
	authEpoch int64,
) error {
	if authority == nil {
		return ErrAccountSecurityUnavailable
	}
	if strings.TrimSpace(accountID) == "" || authEpoch <= 0 {
		return ErrAccountSecurityDenied
	}
	snapshot, err := authority.ReadAccountSecurity(ctx, strings.TrimSpace(accountID))
	if errors.Is(err, rtauth.ErrAccountSecurityNotFound) {
		return ErrAccountSecurityDenied
	}
	if err != nil {
		return ErrAccountSecurityUnavailable
	}
	if strings.TrimSpace(snapshot.AccountState) != "active" ||
		snapshot.AuthEpoch <= 0 ||
		snapshot.AuthEpoch != authEpoch {
		return ErrAccountSecurityDenied
	}
	return nil
}

// ErrorDigest permits a caller to correlate a runtime failure without placing
// a source payload, account identifier, ticket, or provider error in logs.
func ErrorDigest(err error) string {
	if err == nil {
		return ""
	}
	sum := sha256.Sum256([]byte(strings.TrimSpace(err.Error())))
	return hex.EncodeToString(sum[:])
}

func (event AccountSecurityEvent) Validate() error {
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.AccountID) == "" ||
		event.OccurredAt.IsZero() {
		return errors.New("realtime account security event is incomplete")
	}
	switch strings.TrimSpace(event.AccountState) {
	case "closed":
		return nil
	case "suspended", "active":
		if event.AuthEpoch <= 0 {
			return errors.New("realtime account security event has invalid auth epoch")
		}
		return nil
	default:
		return errors.New("realtime account security event has invalid state")
	}
}

// Package account_session 提供 AccountSession 对象专属、强类型 command Facet。
package account_session

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"

	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	"quwoquan_service/services/user-service/generated/account/user_account"
	sessionports "quwoquan_service/services/user-service/internal/account/account_session/domain/ports"
)

// CommandFacet 只暴露 AccountSession 的四个对象命令，不接收客户端
// If-Match、expectedVersion 或 idempotency key。
type CommandFacet interface {
	Issue(context.Context, IssueCommand) (SessionResult, error)
	Rotate(context.Context, RotateCommand) (SessionResult, error)
	Logout(context.Context, LogoutCommand) error
	Revoke(context.Context, RevokeCommand) error
}

type AccountSessionCommandFacade struct {
	store sessionports.AccountSessionStore
}

func NewAccountSessionCommandFacade(
	store sessionports.AccountSessionStore,
) *AccountSessionCommandFacade {
	if store == nil {
		panic("AccountSessionCommandFacade requires an object-specific AccountSessionStore")
	}
	return &AccountSessionCommandFacade{store: store}
}

var _ CommandFacet = (*AccountSessionCommandFacade)(nil)

func (facade *AccountSessionCommandFacade) Issue(
	ctx context.Context,
	command IssueCommand,
) (SessionResult, error) {
	accountID := strings.TrimSpace(command.AccountID)
	deviceID := strings.TrimSpace(command.DeviceID)
	authenticationSubject := strings.TrimSpace(command.AuthenticationSubject)
	identityOrigin := strings.TrimSpace(command.IdentityOrigin)
	if accountID == "" ||
		deviceID == "" ||
		authenticationSubject == "" ||
		identityOrigin == "" ||
		command.ExpiresAt.IsZero() {
		return SessionResult{}, generated.AppErrorFromInvalidArgument(
			"account session issue command is incomplete",
		)
	}
	refreshTokenHash, ok := hashTransientRefreshToken(command.RefreshToken)
	if !ok {
		return SessionResult{}, generated.AppErrorFromInvalidArgument(
			"account session issue requires a refresh token",
		)
	}
	issued, err := facade.store.IssueSession(
		ctx,
		accountID,
		deviceID,
		authenticationSubject,
		identityOrigin,
		refreshTokenHash,
		command.ExpiresAt.UTC(),
	)
	if err != nil {
		return SessionResult{}, mapSessionStoreError(err)
	}
	return sessionResult(issued)
}

func (facade *AccountSessionCommandFacade) Rotate(
	ctx context.Context,
	command RotateCommand,
) (SessionResult, error) {
	if command.ExpiresAt.IsZero() {
		return SessionResult{}, generated.AppErrorFromInvalidArgument(
			"account session rotation requires expiresAt",
		)
	}
	currentTokenHash, currentOK := hashTransientRefreshToken(
		command.CurrentRefreshToken,
	)
	nextTokenHash, nextOK := hashTransientRefreshToken(command.NextRefreshToken)
	if !currentOK || !nextOK {
		return SessionResult{}, generated.AppErrorFromInvalidArgument(
			"account session rotation requires current and next refresh tokens",
		)
	}
	if currentTokenHash == nextTokenHash {
		return SessionResult{}, generated.AppErrorFromInvalidArgument(
			"account session rotation requires a distinct next refresh token",
		)
	}
	issued, err := facade.store.RotateSession(
		ctx,
		currentTokenHash,
		nextTokenHash,
		command.ExpiresAt.UTC(),
	)
	if err != nil {
		return SessionResult{}, mapSessionStoreError(err)
	}
	return sessionResult(issued)
}

func (facade *AccountSessionCommandFacade) Logout(
	ctx context.Context,
	command LogoutCommand,
) error {
	refreshTokenHash, ok := hashTransientRefreshToken(command.RefreshToken)
	if !ok {
		return generated.AppErrorFromInvalidArgument(
			"account session logout requires a refresh token",
		)
	}
	err := facade.store.RevokeByTokenHash(
		ctx,
		refreshTokenHash,
		sessionports.RevokeReasonLogout,
	)
	if err == nil || revocationAlreadyComplete(err) {
		return nil
	}
	return mapSessionStoreError(err)
}

func (facade *AccountSessionCommandFacade) Revoke(
	ctx context.Context,
	command RevokeCommand,
) error {
	accountID := strings.TrimSpace(command.AccountID)
	reason := strings.TrimSpace(command.Reason)
	if accountID == "" || !validRevokeReason(reason) {
		return generated.AppErrorFromInvalidArgument(
			"account session revoke requires an account and known reason",
		)
	}
	err := facade.store.RevokeAllForAccount(ctx, accountID, reason)
	if err == nil || revocationAlreadyComplete(err) {
		return nil
	}
	return mapSessionStoreError(err)
}

func hashTransientRefreshToken(value []byte) (string, bool) {
	secret := append([]byte(nil), value...)
	defer clearBytes(secret)
	trimmed := bytes.TrimSpace(secret)
	if len(trimmed) == 0 {
		return "", false
	}
	digest := sha256.Sum256(trimmed)
	return hex.EncodeToString(digest[:]), true
}

func clearBytes(value []byte) {
	for index := range value {
		value[index] = 0
	}
}

func sessionResult(
	issued sessionports.IssuedSession,
) (SessionResult, error) {
	result := SessionResult{
		SessionID: strings.TrimSpace(issued.SessionID),
		AccountID: strings.TrimSpace(issued.AccountID),
		DeviceID:  strings.TrimSpace(issued.DeviceID),
		LineageID: strings.TrimSpace(issued.LineageID),
		ExpiresAt: issued.ExpiresAt.UTC(),
	}
	if result.SessionID == "" ||
		result.AccountID == "" ||
		result.DeviceID == "" ||
		result.LineageID == "" ||
		result.ExpiresAt.IsZero() {
		return SessionResult{}, generated.AppErrorFromInternalError(
			"account session store returned an invalid issued session",
		)
	}
	return result, nil
}

func validRevokeReason(reason string) bool {
	switch reason {
	case sessionports.RevokeReasonLogout,
		sessionports.RevokeReasonReplay,
		sessionports.RevokeReasonExpired,
		sessionports.RevokeReasonSecuritySalt:
		return true
	default:
		return false
	}
}

func revocationAlreadyComplete(err error) bool {
	return errors.Is(err, sessionports.ErrSessionNotFound) ||
		errors.Is(err, sessionports.ErrSessionExpired) ||
		errors.Is(err, sessionports.ErrSessionReplayed) ||
		errors.Is(err, sessionports.ErrSessionRevoked)
}

func mapSessionStoreError(err error) error {
	switch {
	case errors.Is(err, sessionports.ErrSessionAccountSuspended):
		return sessiongenerated.AppErrorFromAccountSuspended(
			"account session was revoked because the account is suspended",
		)
	case errors.Is(err, sessionports.ErrSessionNotFound),
		errors.Is(err, sessionports.ErrSessionRevoked):
		return generated.AppErrorFromUnauthorized(
			"account session refresh token is invalid",
		)
	case errors.Is(err, sessionports.ErrSessionExpired),
		errors.Is(err, sessionports.ErrSessionReplayed):
		return sessiongenerated.AppErrorFromTokenExpired(
			"account session refresh token is no longer usable",
		)
	default:
		return generated.AppErrorFromInternalError(
			"account session persistence failed",
		)
	}
}

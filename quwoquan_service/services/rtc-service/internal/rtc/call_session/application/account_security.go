package application

import (
	"context"
	"errors"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	generated "quwoquan_service/services/rtc-service/generated/rtc/call_session"
)

var (
	// ErrCallAccountSecurityDenied intentionally carries no account, persona,
	// credential, or authority response data. Call transports map it to the
	// canonical account-security rejection.
	ErrCallAccountSecurityDenied = errors.New("rtc call account security denied")
	// ErrCallAccountSecurityUnavailable is fail-closed. It is returned for
	// missing wiring, a failed authority read, or an unusable direct-signalling
	// principal, so no media access can be issued optimistically.
	ErrCallAccountSecurityUnavailable = errors.New(
		"rtc call account security authority unavailable",
	)
)

// CallAccountSecurityGate is enforced by CallOrchestrator before any
// user-initiated mutation or media-access issuance. HTTP middleware remains the
// first guard, while this gate makes non-HTTP/direct-signalling callers obey
// the same synchronous authority check.
type CallAccountSecurityGate interface {
	AuthorizeCallActor(ctx context.Context, personaID string) error
}

type runtimeCallAccountSecurityGate struct {
	authority rtauth.AccountSecurityAuthority
}

// NewCallAccountSecurityGate reuses the same authority instance registered in
// HTTP middleware. It deliberately has no cache: a successful pre-close read
// must never reopen the terminal-account window.
func NewCallAccountSecurityGate(
	authority rtauth.AccountSecurityAuthority,
) CallAccountSecurityGate {
	return &runtimeCallAccountSecurityGate{authority: authority}
}

func (gate *runtimeCallAccountSecurityGate) AuthorizeCallActor(
	ctx context.Context,
	personaID string,
) error {
	if gate == nil || gate.authority == nil {
		return ErrCallAccountSecurityUnavailable
	}
	personaID = strings.TrimSpace(personaID)
	principal, found := rtauth.PrincipalFromContext(ctx)
	if !found ||
		principal.TokenType != rtauth.TokenTypeAccess ||
		strings.TrimSpace(principal.Actor.AccountID) == "" ||
		strings.TrimSpace(principal.Actor.PersonaID) != personaID ||
		principal.AuthEpoch <= 0 ||
		isNonEndUserPrincipal(principal) {
		return ErrCallAccountSecurityDenied
	}
	snapshot, err := gate.authority.ReadAccountSecurity(
		ctx,
		principal.Actor.AccountID,
	)
	if errors.Is(err, rtauth.ErrAccountSecurityNotFound) {
		return ErrCallAccountSecurityDenied
	}
	if err != nil {
		return ErrCallAccountSecurityUnavailable
	}
	if strings.TrimSpace(snapshot.AccountState) != "active" ||
		snapshot.AuthEpoch <= 0 ||
		snapshot.AuthEpoch != principal.AuthEpoch {
		return ErrCallAccountSecurityDenied
	}
	return nil
}

func isNonEndUserPrincipal(principal rtauth.Principal) bool {
	for _, role := range principal.Roles {
		switch strings.TrimSpace(role) {
		case "service", "operator", "admin":
			return true
		}
	}
	return false
}

type allowCallAccountSecurityGate struct{}

func (allowCallAccountSecurityGate) AuthorizeCallActor(
	context.Context,
	string,
) error {
	return nil
}

// AllowCallAccountSecurityForTest is limited to isolated service tests. Runtime
// composition never uses it: absent production wiring is a fail-closed error.
func AllowCallAccountSecurityForTest() CallAccountSecurityGate {
	return allowCallAccountSecurityGate{}
}

func accountSecurityCallError(cause error) error {
	if errors.Is(cause, ErrCallAccountSecurityDenied) {
		return generated.AppErrorFromAccountSecurityDenied(
			"rtc call account security authority denied the credential",
		)
	}
	return generated.AppErrorFromAccountSecurityUnavailable(
		"rtc call account security authority is unavailable",
	)
}

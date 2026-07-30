package account_session

import (
	"errors"
	"strings"
)

const (
	FederatedLoginAuthenticated        = "authenticated"
	FederatedLoginPhoneBindingRequired = "phoneBindingRequired"
)

// AuthSessionGrant is the canonical successful authentication response.
// RefreshToken is returned once and must never be persisted in plaintext.
type AuthSessionGrant struct {
	AccessToken               string         `json:"accessToken"`
	RefreshToken              string         `json:"refreshToken"`
	OwnerID                   string         `json:"ownerId"`
	ActivePersona             map[string]any `json:"activePersona"`
	PersonaCount              int            `json:"personaCount"`
	AccountState              string         `json:"accountState"`
	IdentityOrigin            string         `json:"identityOrigin"`
	LogicalShard              int            `json:"logicalShard"`
	AnonymousRetentionPolicy  string         `json:"anonymousRetentionPolicy"`
	AccountHint               map[string]any `json:"accountHint,omitempty"`
	SessionRememberTTLSeconds int            `json:"sessionRememberTtlSeconds"`
}

// FederatedLoginOutcome has exactly two wire states. Constructors are the only
// supported creation path so irrelevant state fields are absent, not null.
type FederatedLoginOutcome struct {
	Status           string            `json:"status"`
	Session          *AuthSessionGrant `json:"session,omitempty"`
	BindingTicket    string            `json:"bindingTicket,omitempty"`
	Provider         string            `json:"provider,omitempty"`
	ExpiresInSeconds int               `json:"expiresInSeconds,omitempty"`
}

func NewAuthenticatedFederatedLogin(
	session *AuthSessionGrant,
) (*FederatedLoginOutcome, error) {
	outcome := &FederatedLoginOutcome{
		Status:  FederatedLoginAuthenticated,
		Session: session,
	}
	return outcome, outcome.Validate()
}

func NewPhoneBindingRequiredFederatedLogin(
	bindingTicket string,
	provider string,
	expiresInSeconds int,
) (*FederatedLoginOutcome, error) {
	outcome := &FederatedLoginOutcome{
		Status:           FederatedLoginPhoneBindingRequired,
		BindingTicket:    strings.TrimSpace(bindingTicket),
		Provider:         strings.TrimSpace(provider),
		ExpiresInSeconds: expiresInSeconds,
	}
	return outcome, outcome.Validate()
}

func (outcome FederatedLoginOutcome) Validate() error {
	switch outcome.Status {
	case FederatedLoginAuthenticated:
		if outcome.Session == nil || outcome.BindingTicket != "" ||
			outcome.Provider != "" || outcome.ExpiresInSeconds != 0 {
			return errors.New("authenticated federated outcome is invalid")
		}
	case FederatedLoginPhoneBindingRequired:
		if outcome.Session != nil || strings.TrimSpace(outcome.BindingTicket) == "" ||
			!validFederatedProviderSlot(outcome.Provider) || outcome.ExpiresInSeconds <= 0 {
			return errors.New("phone-binding federated outcome is invalid")
		}
	default:
		return errors.New("federated login outcome status is invalid")
	}
	return nil
}

func validFederatedProviderSlot(provider string) bool {
	switch strings.TrimSpace(provider) {
	case "federated_slot_a", "federated_slot_b", "federated_slot_c":
		return true
	default:
		return false
	}
}

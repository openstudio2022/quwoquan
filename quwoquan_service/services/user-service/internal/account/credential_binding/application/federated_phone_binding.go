package credential_binding

import (
	"context"
	"errors"
	"time"

	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

const FederatedPhoneBindingTicketTTL = 3 * time.Minute

var (
	ErrFederatedBindingTicketInvalid  = errors.New("federated binding ticket invalid")
	ErrFederatedBindingTicketExpired  = errors.New("federated binding ticket expired")
	ErrFederatedBindingTicketConsumed = errors.New("federated binding ticket consumed")
	ErrFederatedBindingContext        = errors.New("federated binding context mismatch")
	ErrFederatedBindingConflict       = errors.New("federated binding credential conflict")
	ErrFederatedBindingAccountClosed  = errors.New("federated binding account closed")
	ErrFederatedBindingAccountPaused  = errors.New("federated binding account suspended")
	ErrFederatedBindingOTPMismatch    = errors.New("federated binding otp mismatch")
	ErrFederatedBindingOTPLocked      = errors.New("federated binding otp locked")
	ErrFederatedBindingOTPExpired     = errors.New("federated binding otp expired")
	ErrFederatedBindingOTPConsumed    = errors.New("federated binding otp consumed")
	ErrFederatedBindingVersion        = errors.New("federated binding version conflict")
)

type IssueFederatedPhoneBindingTicket struct {
	Provider         bindingmodel.FederatedProvider
	CredentialType   bindingmodel.CredentialType
	CredentialKey    string
	DisplayName      string
	AvatarURL        string
	DeviceID         string
	Platform         string
	AppVersion       string
	AgreementVersion string
	PrivacyVersion   string
	ExpiresAt        time.Time
}

type IssuedFederatedPhoneBindingTicket struct {
	Opaque           string
	Provider         bindingmodel.FederatedProvider
	ExpiresInSeconds int
}

type CompletionSession struct {
	SessionID             string
	LineageID             string
	RefreshTokenHash      string
	AuthenticationSubject string
	IdentityOrigin        string
	ExpiresAt             time.Time
	OutboxEventID         string
}

type NewFederatedAccount struct {
	Profile *usermodel.UserProfile
	Persona *usermodel.Persona
}

type CompleteFederatedPhoneBindingPacket struct {
	OpaqueTicket         string
	ExpectedTicket       bindingmodel.FederatedPhoneBindingTicket
	ChallengeID          string
	Phone                string
	PhoneDestinationHash string
	OTPSecretRef         string
	OTPCompletionDigest  string
	OTPMaxAttempts       int
	DeviceID             string
	Platform             string
	AppVersion           string
	AgreementVersion     string
	PrivacyVersion       string
	ExpectedOwnerID      string
	ExpectedAuthEpoch    int64
	ExpectedPersonaID    string
	ExpectedPersonaVer   int64
	NewAccount           *NewFederatedAccount
	PhoneBinding         *bindingmodel.ChangeSet
	SocialBinding        bindingmodel.ChangeSet
	ConsentID            string
	DeviceRegistrationID string
	Session              CompletionSession
	OccurredAt           time.Time
}

type FederatedPhoneBindingCompletion struct {
	OwnerID        string
	PersonaID      string
	PersonaVersion int64
}

type FederatedPhoneBindingStore interface {
	IssueFederatedPhoneBindingTicket(
		context.Context,
		IssueFederatedPhoneBindingTicket,
	) (IssuedFederatedPhoneBindingTicket, error)
	ResolveFederatedPhoneBindingTicket(
		context.Context,
		string,
	) (bindingmodel.FederatedPhoneBindingTicket, error)
	CommitFederatedPhoneBinding(
		context.Context,
		CompleteFederatedPhoneBindingPacket,
	) (FederatedPhoneBindingCompletion, error)
}

type CompleteFederatedPhoneBindingCommand struct {
	BindingTicket    string
	Phone            string
	OTPCode          string
	ChallengeID      string
	DeviceID         string
	Platform         string
	AppVersion       string
	AgreementVersion string
	PrivacyVersion   string
}

type FederatedPhoneBindingCompleter interface {
	CompleteFederatedPhoneBinding(
		context.Context,
		CompleteFederatedPhoneBindingCommand,
	) (*sessionapp.AuthSessionGrant, error)
}

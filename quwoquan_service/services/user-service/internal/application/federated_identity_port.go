package application

import (
	"context"
	"strings"
	"time"

	credentialmodel "quwoquan_service/services/user-service/internal/domain/account/credential_binding/model"
)

// FederatedIdentityVerifier verifies one opaque authorization assertion and
// returns the normalized account material required by the login workflow.
// Adapter selection, protocol details, endpoints, credentials, and upstream
// payloads remain outside the application layer.
type FederatedIdentityVerifier interface {
	Verify(
		ctx context.Context,
		authorizationCode string,
	) (VerifiedFederatedIdentity, error)
}

// FederatedAuthorizationIssuer creates an opaque, short-lived authorization
// request when a bound adapter requires one before the client can obtain an
// assertion. Its payload must never be inspected by application code.
type FederatedAuthorizationIssuer interface {
	IssueAuthorizationRequest(
		ctx context.Context,
	) (FederatedAuthorizationRequest, error)
}

// VerifiedFederatedIdentity is provider-neutral identity material produced by
// a verified infrastructure adapter. CredentialKey and identity-class fields
// are opaque to this layer; only the adapter may derive them.
type VerifiedFederatedIdentity struct {
	CredentialType credentialmodel.CredentialType
	CredentialKey  string
	DisplayName    string
	AvatarURL      string
}

func (identity VerifiedFederatedIdentity) valid() bool {
	return identity.CredentialType.Valid() &&
		strings.TrimSpace(identity.CredentialKey) != ""
}

// FederatedAuthorizationRequest is an opaque, expiring request payload.
type FederatedAuthorizationRequest struct {
	Payload   string
	ExpiresAt time.Time
}

// CarrierPhoneResolver resolves a short-lived, opaque carrier assertion to a
// verified phone identity. Concrete provider behavior belongs to infrastructure.
type CarrierPhoneResolver interface {
	ResolvePhone(
		ctx context.Context,
		carrierToken string,
	) (VerifiedCarrierPhone, error)
}

// VerifiedCarrierPhone is the normalized carrier assertion result.
type VerifiedCarrierPhone struct {
	Phone        string
	DisplayLabel string
}

func (phone VerifiedCarrierPhone) valid() bool {
	return strings.TrimSpace(phone.Phone) != ""
}

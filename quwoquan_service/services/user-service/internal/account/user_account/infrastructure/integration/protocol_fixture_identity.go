package integration

import (
	"context"
	"strings"

	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
)

// ProtocolFixtureCarrierPhoneResolver is the non-prod CarrierOneTapPort substitute.
type ProtocolFixtureCarrierPhoneResolver struct{}

func NewProtocolFixtureCarrierPhoneResolver() application.CarrierPhoneResolver {
	return ProtocolFixtureCarrierPhoneResolver{}
}

func (ProtocolFixtureCarrierPhoneResolver) ResolvePhone(
	_ context.Context,
	carrierToken string,
) (application.VerifiedCarrierPhone, error) {
	token := strings.TrimSpace(carrierToken)
	if token == "" {
		token = "fixture"
	}
	return application.VerifiedCarrierPhone{
		Phone:        "+8600000000000",
		DisplayLabel: "fixture-" + token,
	}, nil
}

// ProtocolFixtureFederatedIdentityVerifier is the non-prod FederatedIdentityPort substitute.
type ProtocolFixtureFederatedIdentityVerifier struct {
	credentialType credentialmodel.CredentialType
}

func NewProtocolFixtureFederatedIdentityVerifier(
	credentialType credentialmodel.CredentialType,
) application.FederatedIdentityVerifier {
	return ProtocolFixtureFederatedIdentityVerifier{credentialType: credentialType}
}

func (v ProtocolFixtureFederatedIdentityVerifier) Verify(
	_ context.Context,
	authorizationCode string,
) (application.VerifiedFederatedIdentity, error) {
	code := strings.TrimSpace(authorizationCode)
	if code == "" {
		code = "fixture"
	}
	return application.VerifiedFederatedIdentity{
		CredentialType: v.credentialType,
		CredentialKey:  "fixture-" + code,
		DisplayName:    "Fixture User",
		AvatarURL:      "",
	}, nil
}

package application

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	bindinggenerated "quwoquan_service/services/user-service/generated/account/credential_binding"
	"quwoquan_service/services/user-service/generated/account/user_account"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
)

// FederatedLoginFacade is the application capability exposed to a transport
// binding. Each bound instance verifies one opaque authorization format; the
// facade never selects an external adapter at runtime.
type FederatedLoginFacade struct {
	auth                *AuthService
	identityVerifier    FederatedIdentityVerifier
	authorizationIssuer FederatedAuthorizationIssuer
}

func NewFederatedLoginFacade(
	auth *AuthService,
	identityVerifier FederatedIdentityVerifier,
	authorizationIssuer FederatedAuthorizationIssuer,
) *FederatedLoginFacade {
	return &FederatedLoginFacade{
		auth:                auth,
		identityVerifier:    identityVerifier,
		authorizationIssuer: authorizationIssuer,
	}
}

func (f *FederatedLoginFacade) IssueAuthorizationRequest(
	ctx context.Context,
) (FederatedAuthorizationRequest, error) {
	if f == nil || f.authorizationIssuer == nil {
		return FederatedAuthorizationRequest{}, sessiongenerated.AppErrorFromSocialProviderUnavailable(
			"federated authorization capability unavailable",
		)
	}
	request, err := f.authorizationIssuer.IssueAuthorizationRequest(ctx)
	if err != nil {
		return FederatedAuthorizationRequest{}, err
	}
	if strings.TrimSpace(request.Payload) == "" || request.ExpiresAt.IsZero() {
		return FederatedAuthorizationRequest{}, sessiongenerated.AppErrorFromSocialProviderUnavailable(
			"federated authorization request unavailable",
		)
	}
	return request, nil
}

func (f *FederatedLoginFacade) Login(
	ctx context.Context,
	authorizationCode string,
	deviceID string,
	platform string,
	appVersion string,
	agreementVersion string,
	privacyVersion string,
) (_ *sessionapp.FederatedLoginOutcome, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.LoginWithFederatedIdentity")
	defer func() { rtobs.EndSpan(span, err) }()

	if f == nil || f.auth == nil || f.identityVerifier == nil {
		return nil, sessiongenerated.AppErrorFromSocialProviderUnavailable(
			"federated identity capability unavailable",
		)
	}
	if strings.TrimSpace(deviceID) == "" ||
		strings.TrimSpace(platform) == "" ||
		strings.TrimSpace(appVersion) == "" {
		return nil, generated.AppErrorFromInvalidArgument(
			"federated login device context required",
		)
	}
	if strings.TrimSpace(agreementVersion) == "" ||
		strings.TrimSpace(privacyVersion) == "" {
		return nil, sessiongenerated.AppErrorFromConsentRequired(
			"federated login consent context required",
		)
	}
	authorizationCode = strings.TrimSpace(authorizationCode)
	if authorizationCode == "" {
		return nil, generated.AppErrorFromInvalidArgument("authCode is required")
	}
	identity, err := f.identityVerifier.Verify(ctx, authorizationCode)
	if err != nil {
		return nil, err
	}
	if !identity.valid() {
		return nil, sessiongenerated.AppErrorFromSocialProviderUnavailable(
			"federated identity verification returned incomplete identity",
		)
	}
	return f.auth.loginWithVerifiedFederatedIdentity(
		ctx,
		identity,
		deviceID,
		platform,
		appVersion,
		agreementVersion,
		privacyVersion,
	)
}

func (s *AuthService) loginWithVerifiedFederatedIdentity(
	ctx context.Context,
	identity VerifiedFederatedIdentity,
	deviceID string,
	platform string,
	appVersion string,
	agreementVersion string,
	privacyVersion string,
) (_ *sessionapp.FederatedLoginOutcome, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"user.LoginWithVerifiedFederatedIdentity",
		attribute.String("credential.type", string(identity.CredentialType)),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	existing, found, err := s.credentials.FindByTypeAndKey(
		ctx,
		identity.CredentialType,
		identity.CredentialKey,
	)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(
			fmt.Sprintf("federated credential lookup: %v", err),
		)
	}
	if found {
		state := existing.State()
		if state.Status != credentialmodel.StatusActive {
			return nil, bindinggenerated.AppErrorFromCredentialConflict(
				"federated credential is not active",
			)
		}
		ownerID := state.OwnerID
		_ = s.credentials.MarkUsed(ctx, state.ID, time.Now().UTC())
		if err := s.persistLoginDevice(
			ctx,
			ownerID,
			deviceID,
			platform,
			appVersion,
		); err != nil {
			return nil, generated.AppErrorFromInternalError(
				fmt.Sprintf("persist federated login device: %v", err),
			)
		}
		if err := s.persistConsentRecord(
			ctx,
			ownerID,
			agreementVersion,
			privacyVersion,
			deviceID,
			platform,
			"LoginWithFederatedIdentity",
		); err != nil {
			return nil, generated.AppErrorFromInternalError(
				fmt.Sprintf("persist federated consent: %v", err),
			)
		}
		session, issueErr := s.issueLoginResult(
			ctx,
			ownerID,
			string(identity.CredentialType),
			identity.CredentialKey,
			deviceID,
		)
		if issueErr != nil {
			return nil, issueErr
		}
		outcome, outcomeErr := sessionapp.NewAuthenticatedFederatedLogin(session)
		if outcomeErr != nil {
			return nil, generated.AppErrorFromInternalError(
				"build authenticated federated login outcome",
			)
		}
		return outcome, nil
	}

	if s.federatedBindingTickets == nil {
		return nil, generated.AppErrorFromInternalError(
			"federated phone binding ticket store unavailable",
		)
	}
	provider, err := credentialmodel.ProviderForCredentialType(identity.CredentialType)
	if err != nil {
		return nil, sessiongenerated.AppErrorFromSocialProviderUnavailable(
			"federated identity provider mapping unavailable",
		)
	}
	issued, err := s.federatedBindingTickets.IssueFederatedPhoneBindingTicket(
		ctx,
		credentialapp.IssueFederatedPhoneBindingTicket{
			Provider:         provider,
			CredentialType:   identity.CredentialType,
			CredentialKey:    identity.CredentialKey,
			DisplayName:      sanitizeFederatedDisplayName(identity.DisplayName),
			AvatarURL:        strings.TrimSpace(identity.AvatarURL),
			DeviceID:         strings.TrimSpace(deviceID),
			Platform:         strings.TrimSpace(platform),
			AppVersion:       strings.TrimSpace(appVersion),
			AgreementVersion: strings.TrimSpace(agreementVersion),
			PrivacyVersion:   strings.TrimSpace(privacyVersion),
			ExpiresAt: time.Now().UTC().Add(
				credentialapp.FederatedPhoneBindingTicketTTL,
			),
		},
	)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(
			"issue federated phone binding ticket",
		)
	}
	outcome, outcomeErr := sessionapp.NewPhoneBindingRequiredFederatedLogin(
		issued.Opaque,
		string(issued.Provider),
		issued.ExpiresInSeconds,
	)
	if outcomeErr != nil {
		return nil, generated.AppErrorFromInternalError(
			"build federated phone binding outcome",
		)
	}
	return outcome, nil
}

func (s *AuthService) CompleteFederatedPhoneBinding(
	ctx context.Context,
	command credentialapp.CompleteFederatedPhoneBindingCommand,
) (_ *sessionapp.AuthSessionGrant, err error) {
	return s.completeFederatedPhoneBinding(ctx, command)
}

func sanitizeFederatedDisplayName(name string) string {
	trimmed := strings.TrimSpace(name)
	if len([]rune(trimmed)) > 32 {
		return string([]rune(trimmed)[:32])
	}
	return trimmed
}

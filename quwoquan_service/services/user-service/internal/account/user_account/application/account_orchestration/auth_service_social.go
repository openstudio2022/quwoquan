package application

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	"quwoquan_service/services/user-service/generated/account/user_account"
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
) (_ *LoginResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.LoginWithFederatedIdentity")
	defer func() { rtobs.EndSpan(span, err) }()

	if f == nil || f.auth == nil || f.identityVerifier == nil {
		return nil, sessiongenerated.AppErrorFromSocialProviderUnavailable(
			"federated identity capability unavailable",
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
	)
}

func (s *AuthService) loginWithVerifiedFederatedIdentity(
	ctx context.Context,
	identity VerifiedFederatedIdentity,
	deviceID string,
	platform string,
	appVersion string,
) (_ *LoginResult, err error) {
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
	var ownerID string
	if found {
		state := existing.State()
		ownerID = state.OwnerID
		_ = s.credentials.MarkUsed(ctx, state.ID, time.Now().UTC())
	} else {
		ownerID, err = s.createOwnerAccountForFederatedIdentity(ctx, identity)
		if err != nil {
			return nil, err
		}
		if syncErr := s.syncFederatedProfileOnFirstLogin(ctx, ownerID, identity); syncErr != nil {
			slog.WarnContext(
				ctx,
				"federated identity profile first-sync failed",
				"owner.id", ownerID,
				"error", syncErr.Error(),
			)
		}
	}
	if err := s.persistLoginDevice(ctx, ownerID, deviceID, platform, appVersion); err != nil {
		return nil, generated.AppErrorFromInternalError(
			fmt.Sprintf("persist federated login device: %v", err),
		)
	}
	return s.issueLoginResult(
		ctx,
		ownerID,
		string(identity.CredentialType),
		identity.CredentialKey,
		deviceID,
	)
}

func (s *AuthService) syncFederatedProfileOnFirstLogin(
	ctx context.Context,
	ownerID string,
	identity VerifiedFederatedIdentity,
) error {
	profile, err := s.profiles.FindByID(ctx, ownerID)
	if err != nil || profile == nil {
		return err
	}
	updated := false
	if displayName := sanitizeFederatedDisplayName(identity.DisplayName); displayName != "" {
		profile.OwnerDisplayName = displayName
		profile.Nickname = displayName
		profile.NicknameCustomized = true
		updated = true
	}
	if avatar := strings.TrimSpace(identity.AvatarURL); avatar != "" &&
		avatar != strings.TrimSpace(profile.AvatarURL) {
		profile.AvatarURL = avatar
		profile.AvatarVersion++
		if profile.AvatarVersion <= 0 {
			profile.AvatarVersion = 1
		}
		profile.AvatarAssetID = fmt.Sprintf("ua_%s", ownerID)
		updated = true
	}
	if updated {
		if err := s.profiles.Update(ctx, profile); err != nil {
			return err
		}
	}
	activeSub, err := s.personas.FindActiveByUserID(ctx, ownerID)
	if err != nil || activeSub == nil {
		return err
	}
	personaUpdated := false
	if name := strings.TrimSpace(profile.Nickname); name != "" && activeSub.DisplayName != name {
		activeSub.DisplayName = name
		personaUpdated = true
	}
	if avatar := strings.TrimSpace(profile.AvatarURL); avatar != "" &&
		(activeSub.AvatarURL != avatar || activeSub.AvatarVersion != profile.AvatarVersion) {
		activeSub.AvatarURL = avatar
		activeSub.AvatarVersion = profile.AvatarVersion
		personaUpdated = true
	}
	if personaUpdated {
		normalizePersonaPersistence(activeSub)
		return s.personas.Update(ctx, activeSub)
	}
	return nil
}

func sanitizeFederatedDisplayName(name string) string {
	trimmed := strings.TrimSpace(name)
	if len([]rune(trimmed)) > 32 {
		return string([]rune(trimmed)[:32])
	}
	return trimmed
}

package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	challengegenerated "quwoquan_service/services/user-service/generated/account/authentication_challenge"
	bindinggenerated "quwoquan_service/services/user-service/generated/account/credential_binding"
	"quwoquan_service/services/user-service/generated/account/user_account"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	bindingapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	registrationmodel "quwoquan_service/services/user-service/internal/account/device_registration/domain/model"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

const federatedBindingOTPMaxAttempts = 5

func (s *AuthService) completeFederatedPhoneBinding(
	ctx context.Context,
	command bindingapp.CompleteFederatedPhoneBindingCommand,
) (_ *sessionapp.AuthSessionGrant, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"user.CompleteFederatedPhoneBinding",
		attribute.String("platform", strings.TrimSpace(command.Platform)),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	phone := normalizePhoneCredentialKey(command.Phone)
	otpCode := strings.TrimSpace(command.OTPCode)
	command.BindingTicket = strings.TrimSpace(command.BindingTicket)
	command.ChallengeID = strings.TrimSpace(command.ChallengeID)
	command.DeviceID = strings.TrimSpace(command.DeviceID)
	command.Platform = strings.TrimSpace(command.Platform)
	command.AppVersion = strings.TrimSpace(command.AppVersion)
	command.AgreementVersion = strings.TrimSpace(command.AgreementVersion)
	command.PrivacyVersion = strings.TrimSpace(command.PrivacyVersion)
	if len(phone) < 5 || command.BindingTicket == "" || otpCode == "" ||
		command.ChallengeID == "" || command.DeviceID == "" ||
		command.Platform == "" || command.AppVersion == "" {
		return nil, generated.AppErrorFromInvalidArgument(
			"federated phone binding request is incomplete",
		)
	}
	if command.AgreementVersion == "" || command.PrivacyVersion == "" {
		return nil, sessiongenerated.AppErrorFromConsentRequired(
			"agreementVersion and privacyVersion required",
		)
	}
	if s.federatedBindingTickets == nil {
		return nil, generated.AppErrorFromInternalError(
			"federated phone binding packet unavailable",
		)
	}
	ticket, err := s.federatedBindingTickets.ResolveFederatedPhoneBindingTicket(
		ctx,
		command.BindingTicket,
	)
	if err != nil {
		return nil, mapFederatedPhoneBindingError(err)
	}
	if !ticket.MatchesContext(
		command.DeviceID,
		command.Platform,
		command.AppVersion,
		command.AgreementVersion,
		command.PrivacyVersion,
	) {
		return nil, generated.AppErrorFromInvalidArgument(
			"federated phone binding context does not match authorization",
		)
	}

	prepared, err := s.prepareFederatedPhoneBindingAccount(ctx, ticket, phone)
	if err != nil {
		return nil, err
	}
	now := time.Now().UTC()
	accessToken, err := s.issueAccessToken(
		prepared.ownerID,
		prepared.persona,
		command.DeviceID,
		prepared.authEpoch,
	)
	if err != nil {
		return nil, err
	}
	refreshToken, err := generateToken()
	if err != nil {
		return nil, generated.AppErrorFromInternalError(
			"generate federated refresh token",
		)
	}
	refreshDigest := sha256.Sum256([]byte(strings.TrimSpace(refreshToken)))
	authenticationSubject := sha256.Sum256([]byte(
		string(ticket.CredentialType) + "\x00" + ticket.CredentialKey,
	))

	socialBinding, err := newFederatedCredentialBindingChange(
		prepared.ownerID,
		ticket.CredentialType,
		ticket.CredentialKey,
		trimRunes(ticket.DisplayName, 32),
		now,
	)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(
			"prepare federated credential binding",
		)
	}
	var phoneBinding *bindingmodel.ChangeSet
	if prepared.newAccount != nil {
		change, changeErr := newFederatedCredentialBindingChange(
			prepared.ownerID,
			bindingmodel.CredentialTypePhone,
			phone,
			maskPhoneForDisplay(phone),
			now,
		)
		if changeErr != nil {
			return nil, generated.AppErrorFromInternalError(
				"prepare phone credential binding",
			)
		}
		phoneBinding = &change
	}
	registration, err := registrationmodel.New(
		registrationmodel.RegisterParams{
			AccountID:    prepared.ownerID,
			DeviceID:     command.DeviceID,
			AppVersion:   command.AppVersion,
			RegisteredAt: now,
		},
	)
	if err != nil {
		return nil, generated.AppErrorFromInvalidArgument(
			"federated binding device context is invalid",
		)
	}
	otpBytes := []byte(otpCode)
	defer clearFederatedBindingSecret(otpBytes)
	packet := bindingapp.CompleteFederatedPhoneBindingPacket{
		OpaqueTicket:         command.BindingTicket,
		ExpectedTicket:       ticket,
		ChallengeID:          command.ChallengeID,
		Phone:                phone,
		PhoneDestinationHash: hashOTPPhone(phone),
		OTPSecretRef: challengeapp.OTPSecretReference(
			command.ChallengeID,
			hashOTPPhone(phone),
			otpBytes,
		),
		OTPCompletionDigest: challengeapp.OTPCompletionFingerprint(
			command.ChallengeID,
			otpBytes,
		),
		OTPMaxAttempts:       federatedBindingOTPMaxAttempts,
		DeviceID:             command.DeviceID,
		Platform:             command.Platform,
		AppVersion:           command.AppVersion,
		AgreementVersion:     command.AgreementVersion,
		PrivacyVersion:       command.PrivacyVersion,
		ExpectedOwnerID:      prepared.ownerID,
		ExpectedAuthEpoch:    prepared.authEpoch,
		ExpectedPersonaID:    prepared.persona.PersonaID,
		ExpectedPersonaVer:   int64(prepared.persona.Version),
		NewAccount:           prepared.newAccount,
		PhoneBinding:         phoneBinding,
		SocialBinding:        socialBinding,
		ConsentID:            uuid.NewString(),
		DeviceRegistrationID: registration.State().ID,
		Session: bindingapp.CompletionSession{
			SessionID:             uuid.NewString(),
			LineageID:             uuid.NewString(),
			RefreshTokenHash:      hex.EncodeToString(refreshDigest[:]),
			AuthenticationSubject: hex.EncodeToString(authenticationSubject[:]),
			IdentityOrigin:        prepared.profile.IdentityOrigin,
			ExpiresAt: now.Add(
				refreshTokenTTLHours * time.Hour,
			),
			OutboxEventID: uuid.NewString(),
		},
		OccurredAt: now,
	}
	completion, err := s.federatedBindingTickets.CommitFederatedPhoneBinding(
		ctx,
		packet,
	)
	if err != nil {
		return nil, mapFederatedPhoneBindingError(err)
	}
	if completion.OwnerID != prepared.ownerID {
		return nil, generated.AppErrorFromInternalError(
			"federated binding packet returned another owner",
		)
	}
	if s.personaProfileProjector == nil {
		return nil, generated.AppErrorFromInternalError(
			"Persona bootstrap projector unavailable",
		)
	}
	if _, err := s.personaProfileProjector.Project(
		ctx,
		completion.PersonaID,
		completion.PersonaVersion,
	); err != nil {
		return nil, generated.AppErrorFromInternalError(
			fmt.Sprintf("project federated Persona profile: %v", err),
		)
	}
	return &sessionapp.AuthSessionGrant{
		AccessToken:               accessToken,
		RefreshToken:              refreshToken,
		OwnerID:                   prepared.ownerID,
		ActivePersona:             buildActivePersonaEnvelope(prepared.persona),
		PersonaCount:              prepared.personaCount,
		AccountState:              prepared.profile.AccountState,
		IdentityOrigin:            prepared.profile.IdentityOrigin,
		LogicalShard:              prepared.profile.LogicalShard,
		AnonymousRetentionPolicy:  prepared.profile.AnonymousRetentionPolicy,
		AccountHint:               buildLoginAccountHint(prepared.profile, ""),
		SessionRememberTTLSeconds: refreshTokenTTLHours * 60 * 60,
	}, nil
}

type preparedFederatedBindingAccount struct {
	ownerID      string
	profile      *model.UserProfile
	persona      *model.Persona
	authEpoch    int64
	personaCount int
	newAccount   *bindingapp.NewFederatedAccount
}

func (s *AuthService) prepareFederatedPhoneBindingAccount(
	ctx context.Context,
	ticket bindingmodel.FederatedPhoneBindingTicket,
	phone string,
) (preparedFederatedBindingAccount, error) {
	identityOrigin, originCode := identityOriginForCredentialType(
		string(ticket.CredentialType),
	)
	identity, err := buildOwnerIdentityForOrigin(identityOrigin, originCode)
	if err != nil {
		return preparedFederatedBindingAccount{}, generated.AppErrorFromInternalError(
			"build federated account identity",
		)
	}
	if _, err := s.resolvePhysicalShard(identity.OwnerID); err != nil {
		return preparedFederatedBindingAccount{}, err
	}
	personaID, err := buildPersonaIdentity(identity.RootPrefix)
	if err != nil {
		return preparedFederatedBindingAccount{}, generated.AppErrorFromInternalError(
			"build federated persona identity",
		)
	}
	now := time.Now().UTC()
	displayName := sanitizeFederatedDisplayName(ticket.DisplayName)
	nicknameCustomized := displayName != ""
	if displayName == "" {
		displayName = s.buildDefaultNickname()
	}
	avatarURL := strings.TrimSpace(ticket.AvatarURL)
	avatarVersion := 0
	avatarAssetID := ""
	if avatarURL != "" {
		avatarVersion = 1
		avatarAssetID = "ua_" + identity.OwnerID
	}
	profile := &model.UserProfile{
		UserID:                   identity.OwnerID,
		AccountState:             accountStateActive,
		AuthEpoch:                1,
		IdentityOrigin:           identityOriginFederated,
		LogicalShard:             identity.LogicalShard,
		AnonymousRetentionPolicy: retentionPolicyPreserve,
		Phone:                    phone,
		Nickname:                 displayName,
		NicknameCustomized:       nicknameCustomized,
		AvatarURL:                avatarURL,
		AvatarAssetID:            avatarAssetID,
		AvatarVersion:            avatarVersion,
		IdentityTags:             "{}",
		ProfileVersion:           1,
		OwnerDisplayName:         displayName,
		PersonaCount:             1,
		CreatedAt:                now,
		UpdatedAt:                now,
	}
	persona := &model.Persona{
		PersonaID:                personaID,
		UserID:                   identity.OwnerID,
		DisplayName:              displayName,
		NicknameCustomized:       nicknameCustomized,
		IdentityTags:             []string{},
		UserHandle:               systemUserHandleForPersona(personaID),
		AvatarMediaAssetID:       avatarAssetID,
		AvatarURL:                avatarURL,
		AvatarVersion:            avatarVersion,
		IsPrimary:                true,
		IsActive:                 true,
		IsolationLevel:           defaultIsolationLevel,
		Status:                   personaStatusActive,
		InheritsProfileFromOwner: false,
		OverriddenProfileFields:  []string{},
		Version:                  1,
		CreatedAt:                now,
		UpdatedAt:                now,
	}
	normalizePersonaPersistence(persona)
	return preparedFederatedBindingAccount{
		ownerID:      identity.OwnerID,
		profile:      profile,
		persona:      persona,
		authEpoch:    1,
		personaCount: 1,
		newAccount: &bindingapp.NewFederatedAccount{
			Profile: profile,
			Persona: persona,
		},
	}, nil
}

func newFederatedCredentialBindingChange(
	ownerID string,
	credentialType bindingmodel.CredentialType,
	credentialKey string,
	displayLabel string,
	boundAt time.Time,
) (bindingmodel.ChangeSet, error) {
	return bindingmodel.Bind(bindingmodel.BindParams{
		ID:             uuid.NewString(),
		OwnerID:        ownerID,
		CredentialType: credentialType,
		CredentialKey:  credentialKey,
		DisplayLabel:   displayLabel,
		EventID:        uuid.NewString(),
		BoundAt:        boundAt,
	})
}

func mapFederatedPhoneBindingError(err error) error {
	switch {
	case errors.Is(err, bindingapp.ErrFederatedBindingTicketInvalid),
		errors.Is(err, bindingapp.ErrFederatedBindingContext):
		return generated.AppErrorFromInvalidArgument(
			"federated phone binding ticket or context is invalid",
		)
	case errors.Is(err, bindingapp.ErrFederatedBindingTicketExpired),
		errors.Is(err, bindingapp.ErrFederatedBindingOTPExpired):
		return challengegenerated.AppErrorFromOtpExpired(
			"federated phone binding authorization expired",
		)
	case errors.Is(err, bindingapp.ErrFederatedBindingTicketConsumed),
		errors.Is(err, bindingapp.ErrFederatedBindingOTPConsumed),
		errors.Is(err, bindingapp.ErrFederatedBindingVersion):
		return challengegenerated.AppErrorFromChallengeConsumed(
			"federated phone binding authorization was consumed",
		)
	case errors.Is(err, bindingapp.ErrFederatedBindingOTPMismatch):
		return challengegenerated.AppErrorFromOtpMismatch(
			"federated phone binding otp did not match",
		)
	case errors.Is(err, bindingapp.ErrFederatedBindingOTPLocked):
		return challengegenerated.AppErrorFromOtpAttemptsExceeded(
			"federated phone binding otp attempts exceeded",
		)
	case errors.Is(err, bindingapp.ErrFederatedBindingConflict):
		return bindinggenerated.AppErrorFromCredentialConflict(
			"federated phone credential identity is already owned",
		)
	case errors.Is(err, bindingapp.ErrFederatedBindingAccountPaused):
		return sessiongenerated.AppErrorFromAccountSuspended("account suspended")
	case errors.Is(err, bindingapp.ErrFederatedBindingAccountClosed):
		return sessiongenerated.AppErrorFromAccountDeleted("account closed")
	default:
		return generated.AppErrorFromInternalError(
			fmt.Sprintf("federated phone binding packet failed: %v", err),
		)
	}
}

func clearFederatedBindingSecret(secret []byte) {
	for index := range secret {
		secret[index] = 0
	}
}

func trimRunes(value string, max int) string {
	value = strings.TrimSpace(value)
	for len(value) > max {
		runes := []rune(value)
		if len(runes) <= 1 {
			return ""
		}
		value = string(runes[:len(runes)-1])
	}
	return value
}

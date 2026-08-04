package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	"quwoquan_service/services/user-service/generated/account/user_account"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

func (s *AuthService) LoginWithOneTap(
	ctx context.Context,
	carrierToken string,
	deviceID string,
	platform string,
	appVersion string,
	agreementVersion string,
	privacyVersion string,
) (_ *sessionapp.AuthSessionGrant, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.LoginWithOneTap",
		attribute.String("platform", strings.TrimSpace(platform)))
	defer func() { rtobs.EndSpan(span, err) }()

	resolver := s.carrierPhoneResolver
	if resolver == nil {
		return nil, sessiongenerated.AppErrorFromCarrierUnavailable("carrier identity capability unavailable")
	}
	verifiedPhone, err := resolver.ResolvePhone(ctx, carrierToken)
	if err != nil {
		return nil, err
	}
	phone := normalizePhoneCredentialKey(verifiedPhone.Phone)
	if phone == "" {
		return nil, sessiongenerated.AppErrorFromCarrierTokenInvalid("carrier identity is empty")
	}
	displayLabel := strings.TrimSpace(verifiedPhone.DisplayLabel)
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = maskPhoneForDisplay(phone)
	}
	if strings.TrimSpace(agreementVersion) == "" || strings.TrimSpace(privacyVersion) == "" {
		return nil, sessiongenerated.AppErrorFromConsentRequired("agreementVersion and privacyVersion required")
	}
	result, err := s.LoginWithCredentialOnDevice(ctx, credentialCarrierPhone, phone, displayLabel, deviceID)
	if err != nil {
		return nil, err
	}
	if err := s.persistLoginDevice(ctx, result.OwnerID, deviceID, platform, appVersion); err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("persist login device: %v", err))
	}
	if err := s.persistConsentRecord(ctx, result.OwnerID, agreementVersion, privacyVersion, deviceID, platform, "LoginOneTap"); err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("persist consent record: %v", err))
	}
	return result, nil
}

func (s *AuthService) ResolveOneTapLoginHint(
	ctx context.Context,
	carrierToken string,
	deviceID string,
	platform string,
	appVersion string,
) (_ *OneTapLoginHint, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.ResolveOneTapLoginHint",
		attribute.String("platform", strings.TrimSpace(platform)))
	defer func() { rtobs.EndSpan(span, err) }()

	resolver := s.carrierPhoneResolver
	if resolver == nil {
		return nil, sessiongenerated.AppErrorFromCarrierUnavailable("carrier identity capability unavailable")
	}
	verifiedPhone, err := resolver.ResolvePhone(ctx, carrierToken)
	if err != nil {
		return nil, err
	}
	phone := normalizePhoneCredentialKey(verifiedPhone.Phone)
	if phone == "" {
		return nil, sessiongenerated.AppErrorFromCarrierTokenInvalid("carrier identity is empty")
	}
	displayLabel := strings.TrimSpace(verifiedPhone.DisplayLabel)
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = maskPhoneForDisplay(phone)
	}
	hint := &OneTapLoginHint{
		State:            "new_phone",
		MaskedPhone:      displayLabel,
		Registered:       false,
		ExpiresInSeconds: 60,
	}
	existing, found, err := s.credentials.FindByTypeAndKey(
		ctx,
		credentialmodel.CredentialTypeCarrierPhone,
		phone,
	)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("one tap credential lookup: %v", err))
	}
	if !found {
		existing, found, err = s.credentials.FindByTypeAndKey(
			ctx,
			credentialmodel.CredentialTypePhone,
			phone,
		)
		if err != nil {
			return nil, generated.AppErrorFromInternalError(fmt.Sprintf("phone credential lookup: %v", err))
		}
	}
	if !found {
		return hint, nil
	}
	profile, err := s.profiles.FindByID(ctx, existing.State().OwnerID)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("load one tap account hint: %v", err))
	}
	if err := ensureProfileCanLogin(profile); err != nil {
		return nil, err
	}
	hint.State = "registered"
	hint.Registered = true
	hint.AccountHint = buildLoginAccountHint(profile, displayLabel)
	return hint, nil
}

func (s *AuthService) LoginAnonymously(
	ctx context.Context,
	installID string,
	deviceFingerprintHash string,
	platform string,
	appVersion string,
) (_ *sessionapp.AuthSessionGrant, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.LoginAnonymously",
		attribute.String("platform", platform))
	defer func() { rtobs.EndSpan(span, err) }()

	installIDHash := hashInstallID(installID)
	deviceFingerprintHash = normalizeAnonymousCredentialKey(deviceFingerprintHash)
	if installIDHash == "" {
		return nil, generated.AppErrorFromInvalidArgument("installId is required")
	}
	if deviceFingerprintHash == "" {
		return nil, generated.AppErrorFromInvalidArgument("deviceFingerprintHash is required")
	}
	platform, appVersion, err = validateAnonymousDeviceMetadata(platform, appVersion)
	if err != nil {
		return nil, err
	}

	var ownerID string
	if s.anonymousDevices != nil {
		binding, err := s.anonymousDevices.FindByDeviceFingerprintHash(ctx, deviceFingerprintHash)
		if err != nil {
			return nil, generated.AppErrorFromInternalError(fmt.Sprintf("lookup anonymous device binding: %v", err))
		}
		if binding != nil {
			ownerID = strings.TrimSpace(binding.OwnerID)
			_ = s.anonymousDevices.Touch(ctx, binding.ID, installIDHash, platform, appVersion)
		}
	}
	if ownerID == "" {
		existing, found, err := s.credentials.FindByTypeAndKey(
			ctx,
			credentialmodel.CredentialTypeAnonymousDevice,
			deviceFingerprintHash,
		)
		if err != nil {
			return nil, generated.AppErrorFromInternalError(fmt.Sprintf("anonymous credential lookup: %v", err))
		}
		if found {
			state := existing.State()
			ownerID = state.OwnerID
			_ = s.credentials.MarkUsed(ctx, state.ID, time.Now().UTC())
		}
	}
	if ownerID == "" {
		displayLabel := anonymousDisplayLabel(platform)
		created, err := s.createOwnerAccount(ctx, credentialAnonymousDevice, deviceFingerprintHash, displayLabel)
		if err != nil {
			return nil, generated.AppErrorFromInternalError(fmt.Sprintf("create anonymous owner account: %v", err))
		}
		ownerID = created
	}
	if err := s.ensureAnonymousDeviceBinding(
		ctx,
		ownerID,
		installIDHash,
		deviceFingerprintHash,
		platform,
		appVersion,
	); err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("persist anonymous device binding: %v", err))
	}
	return s.issueLoginResult(ctx, ownerID, credentialAnonymousDevice, "", deviceFingerprintHash)
}

func validateAnonymousDeviceMetadata(platform, appVersion string) (string, string, error) {
	normalizedPlatform := strings.TrimSpace(platform)
	if normalizedPlatform == "" {
		normalizedPlatform = "unknown"
	}
	if utf8.RuneCountInString(normalizedPlatform) > anonymousDevicePlatformMaxRunes {
		return "", "", generated.AppErrorFromInvalidArgument("platform exceeds 16 characters")
	}

	normalizedAppVersion := strings.TrimSpace(appVersion)
	if utf8.RuneCountInString(normalizedAppVersion) > anonymousDeviceAppVersionMaxRunes {
		return "", "", generated.AppErrorFromInvalidArgument("appVersion exceeds 32 characters")
	}
	return normalizedPlatform, normalizedAppVersion, nil
}

func (s *AuthService) BindPhoneCredential(
	ctx context.Context,
	ownerID, phone, otpCode, displayLabel string,
) (result credentialapp.CommandResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"user.BindPhoneCredential",
		attribute.String("owner.id", ownerID),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	normalized := normalizePhoneCredentialKey(phone)
	if normalized == "" {
		return credentialapp.CommandResult{},
			generated.AppErrorFromInvalidArgument("phone is required")
	}
	if err := s.verifyOtp(ctx, normalized, otpCode, "bind_phone"); err != nil {
		return credentialapp.CommandResult{}, err
	}
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = maskPhoneForDisplay(normalized)
	}
	if s.credentialCommands == nil {
		return credentialapp.CommandResult{}, generated.AppErrorFromInternalError(
			"credential command facet unavailable",
		)
	}
	result, err = s.credentialCommands.BindVerifiedCredential(
		ctx,
		ownerID,
		credentialapp.BindCredentialCommand{
			CredentialType: credentialmodel.CredentialTypePhone,
			CredentialKey:  normalized,
			DisplayLabel:   displayLabel,
		},
	)
	if err != nil {
		return credentialapp.CommandResult{}, err
	}
	if err := s.promoteCredentialOwner(
		ctx,
		ownerID,
		credentialPhone,
		normalized,
	); err != nil {
		return credentialapp.CommandResult{}, err
	}
	return result, nil
}

func (s *AuthService) BindCarrierPhoneCredential(
	ctx context.Context,
	ownerID, carrierToken, deviceID, platform, displayLabel string,
) (result credentialapp.CommandResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"user.BindCarrierPhoneCredential",
		attribute.String("owner.id", ownerID),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	resolver := s.carrierPhoneResolver
	if resolver == nil {
		return credentialapp.CommandResult{},
			sessiongenerated.AppErrorFromCarrierUnavailable("carrier identity capability unavailable")
	}
	verifiedPhone, err := resolver.ResolvePhone(ctx, carrierToken)
	if err != nil {
		return credentialapp.CommandResult{}, err
	}
	normalized := normalizePhoneCredentialKey(verifiedPhone.Phone)
	if normalized == "" {
		return credentialapp.CommandResult{},
			sessiongenerated.AppErrorFromCarrierTokenInvalid("carrier identity is empty")
	}
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = strings.TrimSpace(verifiedPhone.DisplayLabel)
	}
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = maskPhoneForDisplay(normalized)
	}
	if err := s.persistLoginDevice(ctx, ownerID, deviceID, platform, ""); err != nil {
		return credentialapp.CommandResult{}, generated.AppErrorFromInternalError(
			fmt.Sprintf("persist carrier bind device: %v", err),
		)
	}
	if s.credentialCommands == nil {
		return credentialapp.CommandResult{}, generated.AppErrorFromInternalError(
			"credential command facet unavailable",
		)
	}
	result, err = s.credentialCommands.BindVerifiedCredential(
		ctx,
		ownerID,
		credentialapp.BindCredentialCommand{
			CredentialType: credentialmodel.CredentialTypeCarrierPhone,
			CredentialKey:  normalized,
			DisplayLabel:   displayLabel,
		},
	)
	if err != nil {
		return credentialapp.CommandResult{}, err
	}
	if err := s.promoteCredentialOwner(
		ctx,
		ownerID,
		credentialCarrierPhone,
		normalized,
	); err != nil {
		return credentialapp.CommandResult{}, err
	}
	return result, nil
}

func (s *AuthService) persistLoginDevice(ctx context.Context, ownerID, deviceID, platform, appVersion string) error {
	if s.deviceRegistration == nil {
		return generated.AppErrorFromInternalError(
			"device registration packet unavailable",
		)
	}
	deviceID = strings.TrimSpace(deviceID)
	if strings.TrimSpace(ownerID) == "" || deviceID == "" {
		return generated.AppErrorFromInvalidArgument(
			"login requires accountId and deviceId",
		)
	}
	_, err := s.deviceRegistration.Register(
		ctx,
		registrationapp.RegisterCommand{
			AccountID:  strings.TrimSpace(ownerID),
			DeviceID:   deviceID,
			AppVersion: strings.TrimSpace(appVersion),
		},
	)
	return err
}

func (s *AuthService) persistConsentRecord(ctx context.Context, ownerID, agreementVersion, privacyVersion, deviceID, platform, sourceOperation string) error {
	if s.consents == nil {
		return nil
	}
	if strings.TrimSpace(agreementVersion) == "" || strings.TrimSpace(privacyVersion) == "" {
		return sessiongenerated.AppErrorFromConsentRequired("agreementVersion and privacyVersion required")
	}
	return s.consents.Create(ctx, &userrepo.ConsentRecord{
		OwnerID:          strings.TrimSpace(ownerID),
		AgreementVersion: strings.TrimSpace(agreementVersion),
		PrivacyVersion:   strings.TrimSpace(privacyVersion),
		AcceptedAt:       time.Now().UTC(),
		DeviceID:         strings.TrimSpace(deviceID),
		Platform:         strings.TrimSpace(platform),
		SourceOperation:  strings.TrimSpace(sourceOperation),
	})
}

func hashInstallID(installID string) string {
	normalized := strings.TrimSpace(strings.ToLower(installID))
	if normalized == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(normalized))
	return hex.EncodeToString(sum[:])
}

func normalizePhoneCredentialKey(phone string) string {
	return credentialmodel.NormalizePhoneCredentialKey(phone)
}

var canonicalE164PhonePattern = regexp.MustCompile(`^\+[1-9][0-9]{7,14}$`)

func canonicalE164Phone(phone string) (string, bool) {
	normalized := normalizePhoneCredentialKey(phone)
	return normalized, canonicalE164PhonePattern.MatchString(normalized)
}

func maskPhoneForDisplay(phone string) string {
	normalized := normalizePhoneCredentialKey(phone)
	if strings.HasPrefix(normalized, "+86") && len(normalized) == 14 {
		normalized = normalized[3:]
	}
	if len(normalized) <= 7 {
		return normalized
	}
	return normalized[:3] + "****" + normalized[len(normalized)-4:]
}

func anonymousDisplayLabel(platform string) string {
	label := strings.TrimSpace(strings.ToLower(platform))
	if label == "" {
		label = "anonymous_device"
	}
	if len(label) > 32 {
		return label[:32]
	}
	return label
}

func generateAnonymousDeviceBindingID() (string, error) {
	entropyBody, err := generateIdentityEntropyBody()
	if err != nil {
		return "", err
	}
	return "adb_" + entropyBody, nil
}

func (s *AuthService) ensureAnonymousDeviceBinding(
	ctx context.Context,
	ownerID, installIDHash, deviceFingerprintHash, platform, appVersion string,
) error {
	if s.anonymousDevices == nil {
		return nil
	}
	existing, err := s.anonymousDevices.FindByDeviceFingerprintHash(ctx, deviceFingerprintHash)
	if err != nil {
		return err
	}
	if existing != nil {
		return s.anonymousDevices.Touch(ctx, existing.ID, installIDHash, platform, appVersion)
	}
	bindingID, err := generateAnonymousDeviceBindingID()
	if err != nil {
		return err
	}
	return s.anonymousDevices.Create(ctx, &model.AnonymousDeviceBinding{
		ID:                    bindingID,
		OwnerID:               strings.TrimSpace(ownerID),
		InstallIDHash:         strings.TrimSpace(installIDHash),
		DeviceFingerprintHash: strings.TrimSpace(deviceFingerprintHash),
		Platform:              platform,
		AppVersion:            appVersion,
		LastSeenAt:            time.Now().UTC(),
	})
}

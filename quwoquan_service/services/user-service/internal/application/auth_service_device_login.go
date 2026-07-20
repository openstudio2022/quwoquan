package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"
	"unicode/utf8"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	credentialapp "quwoquan_service/services/user-service/internal/application/account/credential_binding"
	registrationapp "quwoquan_service/services/user-service/internal/application/account/device_registration"
	credentialmodel "quwoquan_service/services/user-service/internal/domain/account/credential_binding/model"
	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

func (s *AuthService) LoginWithOneTap(
	ctx context.Context,
	vendor string,
	carrierToken string,
	deviceID string,
	platform string,
	appVersion string,
	agreementVersion string,
	privacyVersion string,
) (_ *LoginResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.LoginWithOneTap",
		attribute.String("one_tap.vendor", strings.TrimSpace(vendor)),
		attribute.String("platform", strings.TrimSpace(platform)))
	defer func() { rtobs.EndSpan(span, err) }()

	resolver := s.oneTapResolver
	if resolver == nil {
		return nil, generated.AppErrorFromInternalError("one tap resolver unavailable")
	}
	phone, displayLabel, err := resolver.ResolvePhone(ctx, vendor, carrierToken)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("resolve one tap phone: %v", err))
	}
	phone = normalizePhoneCredentialKey(phone)
	if phone == "" {
		return nil, generated.AppErrorFromInvalidArgument("one tap phone is empty")
	}
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = maskPhoneForDisplay(phone)
	}
	if strings.TrimSpace(agreementVersion) == "" || strings.TrimSpace(privacyVersion) == "" {
		return nil, generated.AppErrorFromConsentRequired("agreementVersion and privacyVersion required")
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
	vendor string,
	carrierToken string,
	deviceID string,
	platform string,
	appVersion string,
) (_ *OneTapLoginHint, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.ResolveOneTapLoginHint",
		attribute.String("one_tap.vendor", strings.TrimSpace(vendor)),
		attribute.String("platform", strings.TrimSpace(platform)))
	defer func() { rtobs.EndSpan(span, err) }()

	resolver := s.oneTapResolver
	if resolver == nil {
		return nil, generated.AppErrorFromCarrierUnavailable("one tap resolver unavailable")
	}
	phone, displayLabel, err := resolver.ResolvePhone(ctx, vendor, carrierToken)
	if err != nil {
		return nil, mapCarrierResolverError(err)
	}
	phone = normalizePhoneCredentialKey(phone)
	if phone == "" {
		return nil, generated.AppErrorFromCarrierTokenInvalid("one tap phone is empty")
	}
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
) (_ *LoginResult, err error) {
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
	ownerID, vendor, carrierToken, deviceID, platform, displayLabel string,
) (result credentialapp.CommandResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"user.BindCarrierPhoneCredential",
		attribute.String("owner.id", ownerID),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	resolver := s.oneTapResolver
	if resolver == nil {
		return credentialapp.CommandResult{},
			generated.AppErrorFromCarrierUnavailable("one tap resolver unavailable")
	}
	phone, resolvedLabel, err := resolver.ResolvePhone(ctx, vendor, carrierToken)
	if err != nil {
		return credentialapp.CommandResult{}, mapCarrierResolverError(err)
	}
	normalized := normalizePhoneCredentialKey(phone)
	if normalized == "" {
		return credentialapp.CommandResult{},
			generated.AppErrorFromCarrierTokenInvalid("one tap phone is empty")
	}
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = strings.TrimSpace(resolvedLabel)
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
		return generated.AppErrorFromConsentRequired("agreementVersion and privacyVersion required")
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

func mapCarrierResolverError(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return generated.AppErrorFromCarrierProviderTimeout(err.Error())
	}
	text := strings.ToLower(err.Error())
	switch {
	case strings.Contains(text, "timeout"):
		return generated.AppErrorFromCarrierProviderTimeout(err.Error())
	case strings.Contains(text, "unavailable"):
		return generated.AppErrorFromCarrierUnavailable(err.Error())
	case strings.Contains(text, "invalid"), strings.Contains(text, "not recognized"):
		return generated.AppErrorFromCarrierTokenInvalid(err.Error())
	default:
		return generated.AppErrorFromCarrierUnavailable(err.Error())
	}
}

// TokenEncodedOneTapPhoneResolver is a local/dev resolver boundary. Production
// deployments should replace it with a carrier vendor resolver through
// WithOneTapPhoneResolver; the App still only receives AuthLoginResult.
type TokenEncodedOneTapPhoneResolver struct{}

func (TokenEncodedOneTapPhoneResolver) ResolvePhone(_ context.Context, _ string, carrierToken string) (string, string, error) {
	token := strings.TrimSpace(carrierToken)
	if token == "" {
		return "", "", generated.AppErrorFromInvalidArgument("carrierToken is required")
	}
	if strings.HasPrefix(token, "phone:") {
		phone := normalizePhoneCredentialKey(strings.TrimPrefix(token, "phone:"))
		return phone, maskPhoneForDisplay(phone), nil
	}
	return "", "", generated.AppErrorFromInternalError("one tap resolver requires carrier server exchange")
}

// UnavailableOneTapPhoneResolver 在尚未接入真实运营商置换的环境（如 prod 过渡期、gamma 无沙箱号段）
// 统一返回结构化不可用，杜绝 dev 解码后门进入生产。
type UnavailableOneTapPhoneResolver struct{}

func (UnavailableOneTapPhoneResolver) ResolvePhone(_ context.Context, _ string, _ string) (string, string, error) {
	return "", "", generated.AppErrorFromCarrierUnavailable("one tap carrier resolver not provisioned")
}

type StaticOneTapPhoneResolver map[string]string

func (r StaticOneTapPhoneResolver) ResolvePhone(_ context.Context, _ string, carrierToken string) (string, string, error) {
	phone := normalizePhoneCredentialKey(r[strings.TrimSpace(carrierToken)])
	if phone == "" {
		return "", "", generated.AppErrorFromInvalidArgument("carrierToken not recognized")
	}
	return phone, maskPhoneForDisplay(phone), nil
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
	trimmed := strings.TrimSpace(phone)
	if trimmed == "" {
		return ""
	}
	replacer := strings.NewReplacer(" ", "", "-", "", "(", "", ")", "")
	return replacer.Replace(trimmed)
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

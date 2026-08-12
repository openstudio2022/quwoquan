package application

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"math/big"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/otpseal"
	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	challengegenerated "quwoquan_service/services/user-service/generated/account/authentication_challenge"
	"quwoquan_service/services/user-service/generated/account/user_account"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

const otpReadinessRetryAfterSeconds = 5

var otpClientPlatforms = map[string]struct{}{
	"ios":        {},
	"android":    {},
	"web":        {},
	"acceptance": {},
}

// GetOtpDeliveryReadiness exposes only the business-safe availability enum.
// Provider names, dependency checks, response bodies and transport errors stay
// inside the service boundary.
func (s *AuthService) GetOtpDeliveryReadiness(ctx context.Context) OtpDeliveryReadiness {
	checker, ok := s.externalClient.(SMSOTPReadinessChecker)
	if !ok || checker == nil {
		return OtpDeliveryReadiness{
			Availability:      "temporarily_unavailable",
			RetryAfterSeconds: otpReadinessRetryAfterSeconds,
		}
	}
	probeCtx, cancel := context.WithTimeout(ctx, 1200*time.Millisecond)
	defer cancel()
	if err := checker.CheckSMSOTPReadiness(probeCtx); err != nil {
		return OtpDeliveryReadiness{
			Availability:      "temporarily_unavailable",
			RetryAfterSeconds: otpReadinessRetryAfterSeconds,
		}
	}
	return OtpDeliveryReadiness{Availability: "ready", RetryAfterSeconds: 0}
}

// SendOtp 校验号码、限频后创建 OTP challenge，并通过 integration-service 提交短信发送。
func (s *AuthService) SendOtp(
	ctx context.Context,
	phone string,
	deviceID string,
	platform string,
	appVersion string,
	sourceOperation string,
	bindingTicket string,
	idempotencyKey string,
) (_ *OtpSendResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.SendOtp",
		attribute.String("platform", strings.TrimSpace(platform)),
		attribute.String("source.operation", strings.TrimSpace(sourceOperation)))
	defer func() { rtobs.EndSpan(span, err) }()

	normalized, validPhone := canonicalE164Phone(phone)
	if !validPhone {
		return nil, generated.AppErrorFromInvalidArgument(
			"phone must use canonical E.164 format",
		)
	}
	platform = strings.ToLower(strings.TrimSpace(platform))
	if _, ok := otpClientPlatforms[platform]; !ok {
		return nil, generated.AppErrorFromInvalidArgument(
			"platform must be one of ios, android, web, acceptance",
		)
	}
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if len(idempotencyKey) < 16 || len(idempotencyKey) > 128 {
		return nil, generated.AppErrorFromInvalidArgument(
			"Idempotency-Key must be a 128-bit opaque identifier",
		)
	}
	if s.otp == nil {
		return nil, generated.AppErrorFromInternalError("otp store unavailable")
	}
	if s.authenticationChallenges == nil {
		return nil, generated.AppErrorFromInternalError(
			"authentication challenge facade unavailable",
		)
	}
	if s.otpCodeSealer == nil {
		return nil, generated.AppErrorFromInternalError("otp code reference sealer unavailable")
	}
	purpose := otpChallengePurpose(sourceOperation)
	bindingTicketRef := ""
	if purpose == "bind_phone" && strings.TrimSpace(bindingTicket) != "" {
		if s.federatedBindingTickets == nil {
			return nil, generated.AppErrorFromInternalError(
				"federated phone binding ticket store unavailable",
			)
		}
		ticket, ticketErr := s.federatedBindingTickets.ResolveFederatedPhoneBindingTicket(
			ctx,
			bindingTicket,
		)
		if ticketErr != nil {
			return nil, mapFederatedPhoneBindingError(ticketErr)
		}
		if ticket.DeviceID != strings.TrimSpace(deviceID) ||
			ticket.Platform != strings.TrimSpace(platform) ||
			ticket.AppVersion != strings.TrimSpace(appVersion) {
			return nil, generated.AppErrorFromInvalidArgument(
				"federated phone binding otp context does not match authorization",
			)
		}
		bindingTicketRef = ticket.ID
	}
	commandFingerprint := otpSendCommandFingerprint(
		normalized,
		purpose,
		bindingTicketRef,
	)
	admission, err := s.otp.AllowSend(
		ctx,
		normalized,
		idempotencyKey,
		commandFingerprint,
	)
	if err != nil {
		if errors.Is(err, ErrOtpIdempotencyConflict) {
			span.SetAttributes(attribute.String("outcome", "idempotency_conflict"))
			return nil, challengegenerated.AppErrorFromOtpIdempotencyConflict(
				"otp idempotency key was reused for another target",
			)
		}
		span.SetAttributes(attribute.String("outcome", "rate_limit_store_failed"))
		return nil, generated.AppErrorFromInternalError("otp rate-limit store failed")
	}
	if !admission.Allowed {
		span.SetAttributes(
			attribute.String("outcome", "rate_limited"),
			attribute.Bool("idempotent_replay", admission.IdempotentReplay),
		)
		return nil, challengegenerated.AppErrorFromOtpRateLimited("otp send throttled").
			WithRecovery("retry", admission.RetryAfterSeconds)
	}
	code, err := s.otpCodeGenerator()
	if err != nil {
		return nil, generated.AppErrorFromInternalError("otp generate")
	}
	challengeID, err := generateToken()
	if err != nil {
		return nil, generated.AppErrorFromInternalError("otp challenge id generate")
	}
	expiresAt := time.Now().UTC().Add(time.Duration(otpCodeExpirySeconds) * time.Second)
	canonicalChallengeID := "otp_ch_" + strings.TrimRight(challengeID, "=")
	requestID := stableOTPRequestID(canonicalChallengeID)
	destinationHash := hashOTPPhone(normalized)
	challengeResult, err := s.authenticationChallenges.CreateChallenge(
		ctx,
		challengeapp.CreateChallengeCommand{
			ID:              canonicalChallengeID,
			Purpose:         purpose,
			Channel:         "sms",
			DestinationHash: destinationHash,
			SecretRef: challengeapp.OTPSecretReference(
				canonicalChallengeID,
				destinationHash,
				[]byte(code),
			),
			BindingTicketRef:  bindingTicketRef,
			DeliveryRequestID: requestID,
			DeliveryStatus:    challengemodel.DeliveryStatusQueued,
			IdempotencyKey:    idempotencyKey,
			ExpiresAt:         expiresAt,
		},
	)
	if err != nil {
		return nil, err
	}
	canonicalChallengeID = challengeResult.Challenge.ID
	requestID = challengeResult.Challenge.DeliveryRequestID
	expiresInSeconds := int(time.Until(challengeResult.Challenge.ExpiresAt).Seconds())
	if expiresInSeconds < 0 {
		expiresInSeconds = 0
	}
	result := &OtpSendResult{
		MaskedPhone:       maskPhoneForDisplay(normalized),
		ExpiresInSeconds:  expiresInSeconds,
		RequestID:         requestID,
		ChallengeID:       canonicalChallengeID,
		DeliveryStatus:    string(challengeResult.Challenge.DeliveryStatus),
		RetryAfterSeconds: admission.RetryAfterSeconds,
	}
	span.SetAttributes(
		attribute.String("delivery_status", result.DeliveryStatus),
		attribute.Bool("idempotent_replay", challengeResult.IdempotentReplay),
	)
	if challengeResult.IdempotentReplay {
		span.SetAttributes(attribute.String("outcome", "idempotent_replay"))
		return result, nil
	}
	if s.externalClient == nil {
		s.markOtpDeliveryFailed(ctx, requestID, "client_unavailable")
		result.DeliveryStatus = string(challengemodel.DeliveryStatusFailed)
		span.SetAttributes(
			attribute.String("outcome", "delivery_failed"),
			attribute.String("delivery_status", result.DeliveryStatus),
		)
		return result, nil
	}
	codeRef, err := s.otpCodeSealer.Seal(
		otpseal.Secret{Phone: normalized, Code: code},
		otpseal.Binding{
			RequestID:   requestID,
			ChallengeID: canonicalChallengeID,
			ExpiresAt:   expiresAt,
		},
	)
	if err != nil {
		s.markOtpDeliveryFailed(ctx, requestID, "seal_failed")
		result.DeliveryStatus = string(challengemodel.DeliveryStatusFailed)
		span.SetAttributes(
			attribute.String("outcome", "delivery_failed"),
			attribute.String("delivery_status", result.DeliveryStatus),
		)
		return result, nil
	}
	if _, err := s.externalClient.SubmitSMSOTP(ctx, SMSOTPDispatchRequest{
		RequestID:      requestID,
		ChallengeID:    canonicalChallengeID,
		PhoneHash:      destinationHash,
		MaskedPhone:    result.MaskedPhone,
		CodeRef:        codeRef,
		IdempotencyKey: idempotencyKey,
		ExpiresAt:      expiresAt,
		Platform:       platform,
		RequestRef:     requestID,
	}); err != nil {
		// Integration 可能已经接受请求但响应在链路中丢失；保持 challenge
		// pending，客户端以同一 Idempotency-Key 重放读取当前权威状态。
		span.SetAttributes(attribute.String("outcome", "delivery_confirming"))
		return nil, challengegenerated.AppErrorFromOtpProviderFailed(
			"otp integration submit failed",
		)
	}
	span.SetAttributes(attribute.String("outcome", "accepted"))
	return result, nil
}

func (s *AuthService) markOtpDeliveryFailed(
	ctx context.Context,
	requestID string,
	failureKind string,
) {
	reportCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), time.Second)
	defer cancel()
	_, _ = s.authenticationChallenges.ReportDeliveryResult(
		reportCtx,
		challengeapp.ReportDeliveryResultCommand{
			EventID:    "otp_local_" + failureKind + "_" + requestID,
			RequestID:  requestID,
			Status:     challengemodel.DeliveryStatusFailed,
			OccurredAt: time.Now().UTC(),
		},
	)
}

func stableOTPRequestID(challengeID string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(challengeID)))
	return "otp_req_" + hex.EncodeToString(sum[:16])
}

func otpChallengePurpose(sourceOperation string) string {
	normalized := strings.ToLower(strings.TrimSpace(sourceOperation))
	switch normalized {
	case "bind_phone":
		return "bind_phone"
	case "account_appeal":
		return "account_appeal"
	default:
		return "phone_login"
	}
}

// OtpSendResult 描述一次发码结果；验证码永不进入 API response。
type OtpSendResult struct {
	MaskedPhone       string `json:"maskedPhone"`
	ExpiresInSeconds  int    `json:"expiresInSeconds"`
	RequestID         string `json:"requestId"`
	ChallengeID       string `json:"challengeId"`
	DeliveryStatus    string `json:"deliveryStatus"`
	RetryAfterSeconds int    `json:"retryAfterSeconds"`
}

func otpSendCommandFingerprint(phone, purpose, bindingTicketRef string) string {
	sum := sha256.Sum256([]byte(strings.Join([]string{
		strings.TrimSpace(phone),
		strings.TrimSpace(purpose),
		strings.TrimSpace(bindingTicketRef),
	}, "\x00")))
	return hex.EncodeToString(sum[:])
}

// verifyOtp 通过 AuthenticationChallenge 对象专属 Facade 校验瞬时凭据；
// 同凭据对 completed challenge 的重放返回原成功语义，不制造新状态。
func (s *AuthService) verifyOtp(
	ctx context.Context,
	phone string,
	code string,
	purpose string,
) error {
	return s.verifyOtpChallenge(ctx, phone, code, purpose, "")
}

func (s *AuthService) verifyOtpChallenge(
	ctx context.Context,
	phone string,
	code string,
	purpose string,
	challengeID string,
) error {
	if s.authenticationChallenges == nil {
		return generated.AppErrorFromInternalError(
			"authentication challenge facade unavailable",
		)
	}
	code = strings.TrimSpace(code)
	if code == "" {
		return generated.AppErrorFromInvalidArgument("otpCode required")
	}
	_, err := s.authenticationChallenges.VerifyChallenge(
		ctx,
		challengeapp.VerifyChallengeCommand{
			ChallengeID:     strings.TrimSpace(challengeID),
			Purpose:         purpose,
			Channel:         "sms",
			DestinationHash: hashOTPPhone(phone),
			Credential:      []byte(code),
		},
	)
	return err
}

// LoginWithPhone 先校验验证码，再走统一的凭证登录链路，并落设备与 consent 留痕。
func (s *AuthService) LoginWithPhone(
	ctx context.Context,
	phone string,
	otpCode string,
	displayLabel string,
	deviceID string,
	platform string,
	appVersion string,
	agreementVersion string,
	privacyVersion string,
) (*sessionapp.AuthSessionGrant, error) {
	normalized, validPhone := canonicalE164Phone(phone)
	if !validPhone {
		return nil, generated.AppErrorFromInvalidArgument(
			"phone must use canonical E.164 format",
		)
	}
	if strings.TrimSpace(agreementVersion) == "" || strings.TrimSpace(privacyVersion) == "" {
		return nil, sessiongenerated.AppErrorFromConsentRequired("agreementVersion and privacyVersion required")
	}
	if err := s.verifyOtp(ctx, normalized, otpCode, "phone_login"); err != nil {
		return nil, err
	}
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = maskPhoneForDisplay(normalized)
	}
	result, err := s.LoginWithCredentialOnDevice(ctx, credentialPhone, normalized, displayLabel, deviceID)
	if err != nil {
		return nil, err
	}
	if err := s.persistLoginDevice(ctx, result.OwnerID, deviceID, platform, appVersion); err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("persist login device: %v", err))
	}
	if err := s.persistConsentRecord(ctx, result.OwnerID, agreementVersion, privacyVersion, deviceID, platform, "LoginWithPhone"); err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("persist consent record: %v", err))
	}
	return result, nil
}

const otpCodeExpirySeconds = 5 * 60

func generateOtpCode() (string, error) {
	const digits = 6
	max := big.NewInt(1000000)
	n, err := rand.Int(rand.Reader, max)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%0*d", digits, n.Int64()), nil
}

// GenerateSecureOTPCode 暴露安全随机验证码生成器供运行时环境装配使用。
func GenerateSecureOTPCode() (string, error) {
	return generateOtpCode()
}

func buildPublicPersonaProfileView(owner *model.UserProfile, persona *model.Persona) map[string]any {
	view := buildPersonaProfileView(owner, persona)
	delete(view, "ownerUserId")
	return view
}

// BuildCreatorRuntimeProfileView projects an imported creator into its
// public-safe account query representation.
func BuildCreatorRuntimeProfileView(creator *userrepo.CreatorRuntimeProfileView) map[string]any {
	if creator == nil {
		return map[string]any{}
	}
	identityTags := append([]string(nil), creator.PublicProfileTagRefs...)
	identityTags = append(identityTags, creator.Roles...)
	identityTags = append(identityTags, creator.Verticals...)
	return map[string]any{
		"subjectType":        "creator",
		"personaId":          creator.PersonaID,
		"userHandle":         creator.Handle,
		"displayName":        creator.DisplayName,
		"headline":           creator.Headline,
		"nicknameCustomized": false,
		"avatarUrl":          creator.AvatarURL,
		"backgroundUrl":      creator.CoverURL,
		"bio":                creator.Bio,
		"identityTags":       identityTags,
		"expertiseClaims":    append([]string(nil), creator.ExpertiseClaims...),
		"disclosure":         creator.Disclosure,
		"followerCount":      int64(0),
		"followingCount":     int64(0),
		"postCount":          int64(len(creator.Works)),
		"circleCount":        int64(0),
		"likeCount":          int64(0),
		"isolationLevel":     defaultIsolationLevel,
		"profileVisibility":  "public",
		"inheritsFromOwner":  false,
		"overriddenFields":   []string{},
		"updatedAt":          creator.UpdatedAt.Format(time.RFC3339),
	}
}

func hasPublicLeakage(view map[string]any) bool {
	for _, key := range []string{"ownerUserId", "ownerAccountId", "ownerId"} {
		if value, ok := view[key]; ok && strings.TrimSpace(fmt.Sprint(value)) != "" && fmt.Sprint(value) != "<nil>" {
			return true
		}
	}
	return false
}

func buildPersonaProfileView(owner *model.UserProfile, persona *model.Persona) map[string]any {
	if owner == nil && persona == nil {
		return map[string]any{}
	}
	if owner == nil {
		owner = &model.UserProfile{UserID: persona.UserID}
	}
	subjectType := "account"
	personaID := ""
	userHandle := strings.TrimSpace(owner.UserID)
	displayName := owner.Nickname
	avatarURL := owner.AvatarURL
	avatarVersion := owner.AvatarVersion
	backgroundURL := owner.BackgroundURL
	bio := owner.Bio
	identityTags := parsePgTextArray(owner.IdentityTags)
	isolationLevel := defaultIsolationLevel
	overriddenFields := []string{}
	updatedAt := owner.UpdatedAt
	nicknameCustomized := owner.NicknameCustomized
	profileVisibility := "public"

	if persona != nil {
		subjectType = "persona"
		personaID = persona.PersonaID
		userHandle = resolvedPersonaUserHandle(persona)
		displayName = strings.TrimSpace(persona.DisplayName)
		avatarURL = strings.TrimSpace(persona.AvatarURL)
		avatarVersion = resolvedPersonaAvatarVersion(persona)
		backgroundURL = strings.TrimSpace(persona.BackgroundURL)
		bio = persona.Bio
		identityTags = append([]string(nil), persona.IdentityTags...)
		nicknameCustomized = persona.NicknameCustomized
		overriddenFields = parseProfileFieldList(persona.OverriddenProfileFields)
		isolationLevel = defaultString(persona.IsolationLevel, defaultIsolationLevel)
		profileVisibility = personaProfileVisibility(persona)
		updatedAt = persona.UpdatedAt
	}
	if displayName == "" && persona == nil {
		displayName = owner.OwnerDisplayName
	}
	if displayName == "" {
		displayName = defaultString(personaID, owner.UserID)
	}
	if updatedAt.IsZero() {
		updatedAt = time.Now().UTC()
	}

	return map[string]any{
		"subjectType":        subjectType,
		"personaId":          personaID,
		"userHandle":         userHandle,
		"displayName":        displayName,
		"nicknameCustomized": nicknameCustomized,
		"avatarUrl":          avatarURLWithVersion(avatarURL, avatarVersion),
		"backgroundUrl":      backgroundURL,
		"bio":                bio,
		"identityTags":       identityTags,
		"followerCount":      owner.FollowerCount,
		"followingCount":     owner.FollowingCount,
		"postCount":          owner.PostCount,
		"circleCount":        owner.CircleCount,
		"likeCount":          owner.LikeCount,
		"isolationLevel":     isolationLevel,
		"profileVisibility":  profileVisibility,
		"inheritsFromOwner":  persona != nil && persona.InheritsProfileFromOwner,
		"overriddenFields":   overriddenFields,
		"updatedAt":          updatedAt.Format(time.RFC3339),
	}
}

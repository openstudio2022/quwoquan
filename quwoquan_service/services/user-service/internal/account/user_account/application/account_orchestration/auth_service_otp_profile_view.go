package application

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"go.opentelemetry.io/otel/attribute"
	"math/big"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/otpseal"
	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	challengegenerated "quwoquan_service/services/user-service/generated/account/authentication_challenge"
	"quwoquan_service/services/user-service/generated/account/user_account"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	"strings"
	"time"
)

// SendOtp 校验号码、限频后创建 OTP challenge，并通过 integration-service 提交短信发送。
func (s *AuthService) SendOtp(ctx context.Context, phone, deviceID, platform, appVersion, sourceOperation string) (_ *OtpSendResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.SendOtp",
		attribute.String("platform", strings.TrimSpace(platform)),
		attribute.String("source.operation", strings.TrimSpace(sourceOperation)))
	defer func() { rtobs.EndSpan(span, err) }()

	normalized := normalizePhoneCredentialKey(phone)
	if len(normalized) < 5 {
		return nil, generated.AppErrorFromInvalidArgument("phone required")
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
	allowed, retryAfter, err := s.otp.AllowSend(ctx, normalized)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("otp allow-send: %v", err))
	}
	if !allowed {
		return nil, challengegenerated.AppErrorFromOtpRateLimited("otp send throttled").
			WithRecovery("retry", retryAfter)
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
	destinationHash := hashOTPPhone(normalized)
	purpose := otpChallengePurpose(sourceOperation)
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
			IdempotencyKey: "otp:" + normalized + ":" +
				expiresAt.Format("200601021504"),
			ExpiresAt: expiresAt,
		},
	)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("otp challenge save: %v", err))
	}
	canonicalChallengeID = challengeResult.Challenge.ID
	requestID := stableOTPRequestID(canonicalChallengeID)
	result := &OtpSendResult{
		MaskedPhone:      maskPhoneForDisplay(normalized),
		ExpiresInSeconds: int(otpCodeExpirySeconds),
		RequestID:        requestID,
		ChallengeID:      canonicalChallengeID,
		DeliveryStatus:   "queued",
	}
	if challengeResult.IdempotentReplay {
		return result, nil
	}
	if s.externalClient == nil {
		_, _ = s.authenticationChallenges.CancelChallenge(
			ctx,
			challengeapp.CancelChallengeCommand{ChallengeID: canonicalChallengeID},
		)
		return nil, challengegenerated.AppErrorFromOtpProviderFailed("otp external interaction client unavailable")
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
		_, _ = s.authenticationChallenges.CancelChallenge(
			ctx,
			challengeapp.CancelChallengeCommand{ChallengeID: canonicalChallengeID},
		)
		return nil, generated.AppErrorFromInternalError("otp code reference sealing failed")
	}
	if _, err := s.externalClient.SubmitSMSOTP(ctx, SMSOTPDispatchRequest{
		RequestID:   requestID,
		ChallengeID: canonicalChallengeID,
		PhoneHash:   destinationHash,
		MaskedPhone: result.MaskedPhone,
		CodeRef:     codeRef,
		IdempotencyKey: "otp:" + normalized + ":" +
			expiresAt.Format("200601021504"),
		ExpiresAt: expiresAt,
	}); err != nil {
		_, _ = s.authenticationChallenges.CancelChallenge(
			ctx,
			challengeapp.CancelChallengeCommand{ChallengeID: canonicalChallengeID},
		)
		return nil, challengegenerated.AppErrorFromOtpProviderFailed(fmt.Sprintf("otp integration submit: %v", err))
	}
	return result, nil
}

func stableOTPRequestID(challengeID string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(challengeID)))
	return "otp_req_" + hex.EncodeToString(sum[:16])
}

func otpChallengePurpose(sourceOperation string) string {
	normalized := strings.ToLower(strings.TrimSpace(sourceOperation))
	if strings.Contains(normalized, "bind_phone") {
		return "bind_phone"
	}
	return "phone_login"
}

// OtpSendResult 描述一次发码结果；验证码永不进入 API response。
type OtpSendResult struct {
	MaskedPhone       string `json:"maskedPhone"`
	ExpiresInSeconds  int    `json:"expiresInSeconds"`
	RequestID         string `json:"requestId,omitempty"`
	ChallengeID       string `json:"challengeId,omitempty"`
	DeliveryStatus    string `json:"deliveryStatus"`
	RetryAfterSeconds int    `json:"retryAfterSeconds,omitempty"`
}

// verifyOtp 通过 AuthenticationChallenge 对象专属 Facade 校验瞬时凭据；
// 同凭据对 completed challenge 的重放返回原成功语义，不制造新状态。
func (s *AuthService) verifyOtp(
	ctx context.Context,
	phone string,
	code string,
	purpose string,
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
) (*LoginResult, error) {
	normalized := normalizePhoneCredentialKey(phone)
	if len(normalized) < 5 {
		return nil, generated.AppErrorFromInvalidArgument("phone required")
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

func (s *AuthService) HandleOtpDeliveryCallback(
	ctx context.Context,
	challengeID string,
	status string,
) error {
	if s.authenticationChallenges == nil {
		return generated.AppErrorFromInternalError(
			"authentication challenge facade unavailable",
		)
	}
	switch strings.TrimSpace(status) {
	case "delivered", "sent_unconfirmed", "active", "queued":
		// delivery 是外部交互事实，Challenge 保持 pending 直到验证/过期。
		return nil
	case "failed", "dead_letter":
		_, err := s.authenticationChallenges.CancelChallenge(
			ctx,
			challengeapp.CancelChallengeCommand{
				ChallengeID: strings.TrimSpace(challengeID),
			},
		)
		return err
	default:
		return generated.AppErrorFromInvalidArgument("otp delivery status unsupported")
	}
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

func buildPublicSubAccountProfileView(owner *model.UserProfile, persona *model.Persona) map[string]any {
	view := buildSubAccountProfileView(owner, persona)
	delete(view, "ownerUserId")
	return view
}

func buildCreatorRuntimeProfileView(creator *model.CreatorRuntimeProfile) map[string]any {
	if creator == nil {
		return map[string]any{}
	}
	identityTags := append([]string(nil), creator.PublicProfileTagRefs...)
	identityTags = append(identityTags, creator.Roles...)
	identityTags = append(identityTags, creator.Verticals...)
	return map[string]any{
		"subjectType":        "creator",
		"subAccountId":       creator.SubAccountID,
		"userId":             creator.CreatorID,
		"userHandle":         creator.Handle,
		"username":           creator.Handle,
		"displayName":        creator.DisplayName,
		"nickname":           creator.DisplayName,
		"headline":           creator.Headline,
		"nicknameCustomized": false,
		"avatarUrl":          creator.AvatarURL,
		"avatarVersion":      creator.AvatarVersion,
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

func buildSubAccountProfileView(owner *model.UserProfile, persona *model.Persona) map[string]any {
	if owner == nil && persona == nil {
		return map[string]any{}
	}
	if owner == nil {
		owner = &model.UserProfile{UserID: persona.UserID}
	}
	subjectType := "user"
	subAccountID := ""
	userHandle := strings.TrimSpace(owner.UserID)
	displayName := owner.Nickname
	avatarURL := owner.AvatarURL
	avatarVersion := owner.AvatarVersion
	backgroundURL := owner.BackgroundURL
	isolationLevel := defaultIsolationLevel
	overriddenFields := []string{}
	updatedAt := owner.UpdatedAt
	// nicknameCustomized 以 owner 基线为真相源；非主分身若自定义过展示名亦视为已定制。
	nicknameCustomized := owner.NicknameCustomized

	if persona != nil {
		subjectType = "persona"
		subAccountID = persona.SubAccountID
		userHandle = resolvedPersonaUserHandle(persona)
		if persona.DisplayName != "" {
			displayName = persona.DisplayName
			overriddenFields = append(overriddenFields, "displayName")
		}
		if persona.AvatarURL != "" {
			avatarURL = persona.AvatarURL
			avatarVersion = resolvedPersonaAvatarVersion(persona)
			overriddenFields = append(overriddenFields, "avatarUrl")
		}
		if persona.BackgroundURL != "" {
			backgroundURL = persona.BackgroundURL
			overriddenFields = append(overriddenFields, "backgroundUrl")
		}
		if !persona.IsPrimary && strings.TrimSpace(persona.DisplayName) != "" {
			nicknameCustomized = true
		}
		isolationLevel = defaultString(persona.IsolationLevel, defaultIsolationLevel)
		updatedAt = persona.UpdatedAt
	}
	if displayName == "" {
		displayName = owner.OwnerDisplayName
	}
	if displayName == "" {
		displayName = owner.UserID
	}
	if updatedAt.IsZero() {
		updatedAt = time.Now().UTC()
	}

	return map[string]any{
		"ownerUserId":        owner.UserID,
		"subjectType":        subjectType,
		"subAccountId":       subAccountID,
		"userId":             defaultString(subAccountID, owner.UserID),
		"userHandle":         userHandle,
		"username":           userHandle,
		"displayName":        displayName,
		"nickname":           displayName,
		"nicknameCustomized": nicknameCustomized,
		"avatarUrl":          avatarURLWithVersion(avatarURL, avatarVersion),
		"avatarVersion":      avatarVersion,
		"backgroundUrl":      backgroundURL,
		"bio":                owner.Bio,
		"identityTags":       parsePgTextArray(owner.IdentityTags),
		"followerCount":      owner.FollowerCount,
		"followingCount":     owner.FollowingCount,
		"postCount":          owner.PostCount,
		"circleCount":        owner.CircleCount,
		"likeCount":          owner.LikeCount,
		"isolationLevel":     isolationLevel,
		"profileVisibility":  profileVisibilityFromIsolation(isolationLevel),
		"inheritsFromOwner":  persona != nil && persona.InheritsProfileFromOwner,
		"overriddenFields":   overriddenFields,
		"updatedAt":          updatedAt.Format(time.RFC3339),
	}
}

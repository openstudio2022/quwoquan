package application

import (
	"context"
	"fmt"
	"go.opentelemetry.io/otel/attribute"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/generated"
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
	if s.otpChallenges == nil {
		return nil, generated.AppErrorFromInternalError("otp challenge store unavailable")
	}
	allowed, retryAfter, err := s.otp.AllowSend(ctx, normalized)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("otp allow-send: %v", err))
	}
	if !allowed {
		return nil, generated.AppErrorFromOtpRateLimited("otp send throttled").
			WithRecovery("retry", retryAfter)
	}
	code, err := generateOtpCode()
	if err != nil {
		return nil, generated.AppErrorFromInternalError("otp generate")
	}
	challengeID, err := generateToken()
	if err != nil {
		return nil, generated.AppErrorFromInternalError("otp challenge id generate")
	}
	requestID, err := generateToken()
	if err != nil {
		return nil, generated.AppErrorFromInternalError("otp request id generate")
	}
	expiresAt := time.Now().UTC().Add(time.Duration(otpCodeExpirySeconds) * time.Second)
	challenge := OtpChallenge{
		ChallengeID:    "otp_ch_" + strings.TrimRight(challengeID, "="),
		RequestID:      "otp_req_" + strings.TrimRight(requestID, "="),
		Phone:          normalized,
		PhoneHash:      hashOTPPhone(normalized),
		CodeHash:       hashOTPCode("otp_ch_"+strings.TrimRight(challengeID, "="), normalized, code),
		Status:         OtpChallengeStatusPendingDispatch,
		IdempotencyKey: "otp:" + normalized + ":" + expiresAt.Format("200601021504"),
		ExpiresAt:      expiresAt,
	}
	challenge, err = s.otpChallenges.CreateChallenge(ctx, challenge)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("otp challenge save: %v", err))
	}
	result := &OtpSendResult{
		MaskedPhone:      maskPhoneForDisplay(normalized),
		ExpiresInSeconds: int(otpCodeExpirySeconds),
		RequestID:        challenge.RequestID,
		ChallengeID:      challenge.ChallengeID,
		DeliveryStatus:   "queued",
	}
	now := time.Now().UTC()
	passThroughAllowed := s.otpPassThrough.Allows(now)
	// 受控放通：gamma 对接真实上游，但命中白名单的测试号跳过真实下发，回填真实验证码（仍可被严格校验）。
	sandboxAllowed := s.otpSandbox.AllowsPhone(normalized, now)
	switch {
	case sandboxAllowed:
		span.SetAttributes(attribute.Bool("otp.sandbox_pass_through", true))
		result.DeliveryStatus = "sandbox"
		_ = s.otpChallenges.MarkChallengeDelivered(ctx, challenge.RequestID, OtpChallengeStatusActive)
	case s.externalClient != nil:
		if _, err := s.externalClient.SubmitSMSOTP(ctx, SMSOTPDispatchRequest{
			RequestID:      challenge.RequestID,
			ChallengeID:    challenge.ChallengeID,
			Phone:          normalized,
			PhoneHash:      challenge.PhoneHash,
			MaskedPhone:    result.MaskedPhone,
			Code:           code,
			IdempotencyKey: challenge.IdempotencyKey,
			ExpiresAt:      expiresAt,
		}); err != nil {
			if !passThroughAllowed {
				_ = s.otpChallenges.MarkChallengeFailed(ctx, challenge.RequestID, err.Error())
				return nil, generated.AppErrorFromOtpProviderFailed(fmt.Sprintf("otp integration submit: %v", err))
			}
			result.DeliveryStatus = "pass_through"
			_ = s.otpChallenges.MarkChallengeDelivered(ctx, challenge.RequestID, OtpChallengeStatusActive)
		} else {
			_ = s.otpChallenges.MarkChallengeDelivered(ctx, challenge.RequestID, OtpChallengeStatusActive)
			result.DeliveryStatus = "queued"
		}
	case passThroughAllowed:
		result.DeliveryStatus = "pass_through"
		_ = s.otpChallenges.MarkChallengeDelivered(ctx, challenge.RequestID, OtpChallengeStatusActive)
	default:
		_ = s.otpChallenges.MarkChallengeFailed(ctx, challenge.RequestID, "external interaction client unavailable")
		return nil, generated.AppErrorFromOtpProviderFailed("otp external interaction client unavailable")
	}
	// 放通(alpha/beta) 与全局 debug reveal 回填明文；受控放通(gamma) 只对白名单回填。
	if passThroughAllowed || sandboxAllowed || s.otpDebugReveal {
		result.DebugCode = code
	}
	return result, nil
}

func buildPublicSubAccountProfileView(owner *model.UserProfile, persona *model.Persona) map[string]any {
	view := buildSubAccountProfileView(owner, persona)
	delete(view, "ownerUserId")
	return view
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

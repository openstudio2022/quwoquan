package application

import (
	"context"
	"fmt"
	"go.opentelemetry.io/otel/attribute"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/otpseal"
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
	if s.otpCodeSealer == nil {
		return nil, generated.AppErrorFromInternalError("otp code reference sealer unavailable")
	}
	allowed, retryAfter, err := s.otp.AllowSend(ctx, normalized)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("otp allow-send: %v", err))
	}
	if !allowed {
		return nil, generated.AppErrorFromOtpRateLimited("otp send throttled").
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
	if s.externalClient == nil {
		_ = s.otpChallenges.MarkChallengeFailed(ctx, challenge.RequestID, "external interaction client unavailable")
		return nil, generated.AppErrorFromOtpProviderFailed("otp external interaction client unavailable")
	}
	codeRef, err := s.otpCodeSealer.Seal(
		otpseal.Secret{Phone: normalized, Code: code},
		otpseal.Binding{
			RequestID:   challenge.RequestID,
			ChallengeID: challenge.ChallengeID,
			ExpiresAt:   expiresAt,
		},
	)
	if err != nil {
		_ = s.otpChallenges.MarkChallengeFailed(ctx, challenge.RequestID, "otp code reference sealing failed")
		return nil, generated.AppErrorFromInternalError("otp code reference sealing failed")
	}
	if _, err := s.externalClient.SubmitSMSOTP(ctx, SMSOTPDispatchRequest{
		RequestID:      challenge.RequestID,
		ChallengeID:    challenge.ChallengeID,
		PhoneHash:      challenge.PhoneHash,
		MaskedPhone:    result.MaskedPhone,
		CodeRef:        codeRef,
		IdempotencyKey: challenge.IdempotencyKey,
		ExpiresAt:      expiresAt,
	}); err != nil {
		_ = s.otpChallenges.MarkChallengeFailed(ctx, challenge.RequestID, err.Error())
		return nil, generated.AppErrorFromOtpProviderFailed(fmt.Sprintf("otp integration submit: %v", err))
	}
	_ = s.otpChallenges.MarkChallengeDelivered(ctx, challenge.RequestID, OtpChallengeStatusActive)
	return result, nil
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
		"avatarVersion":      1,
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

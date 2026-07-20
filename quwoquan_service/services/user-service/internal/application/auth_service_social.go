package application

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	credentialmodel "quwoquan_service/services/user-service/internal/domain/account/credential_binding/model"
	"quwoquan_service/services/user-service/internal/generated"
)

// LoginWithSocialProvider 用社交提供方（微信/支付宝/QQ）的短期授权码登录。
// App 只上传 authCode，服务端置换稳定身份并在首次登录时同步昵称/头像。
func (s *AuthService) CreateSocialAuthorizationRequest(
	ctx context.Context,
	provider string,
) (string, time.Time, error) {
	provider, supported := NormalizeSocialProvider(provider)
	if !supported {
		return "", time.Time{}, generated.AppErrorFromInvalidArgument("unsupported social provider")
	}
	issuer, ok := s.socialProviders.(ExternalAuthAuthorizationIssuer)
	if !ok {
		return "", time.Time{}, generated.AppErrorFromSocialProviderUnavailable(
			provider + " authorization issuer unavailable",
		)
	}
	payload, expiresAt, err := issuer.CreateAuthorizationRequest(ctx, provider)
	if err != nil {
		return "", time.Time{}, generated.AppErrorFromSocialProviderUnavailable(
			provider + " authorization request unavailable",
		)
	}
	return payload, expiresAt, nil
}

func (s *AuthService) LoginWithSocialProvider(
	ctx context.Context,
	provider, authCode, deviceID, platform, appVersion string,
) (_ *LoginResult, err error) {
	provider, supported := NormalizeSocialProvider(provider)
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.LoginWithSocialProvider",
		attribute.String("social.provider", provider))
	defer func() { rtobs.EndSpan(span, err) }()

	if !supported {
		return nil, generated.AppErrorFromInvalidArgument("unsupported social provider")
	}
	if s.socialProviders == nil || !s.socialProviders.Supports(provider) {
		return nil, generated.AppErrorFromSocialProviderUnavailable(fmt.Sprintf("%s provider client unavailable", provider))
	}
	authCode = strings.TrimSpace(authCode)
	if authCode == "" {
		return nil, generated.AppErrorFromInvalidArgument("authCode is required")
	}

	identity, err := s.socialProviders.Exchange(ctx, provider, authCode, platform, appVersion)
	if err != nil {
		return nil, mapSocialProviderError(provider, err)
	}
	if !identity.hasIdentity() {
		return nil, providerAuthFailedError(provider, "provider returned empty identity")
	}
	identity.Provider = provider
	credKey := identity.StableKey()

	existing, found, err := s.credentials.FindByTypeAndKey(
		ctx,
		credentialmodel.CredentialType(provider),
		credKey,
	)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("social credential lookup: %v", err))
	}
	var ownerID string
	if found {
		state := existing.State()
		ownerID = state.OwnerID
		_ = s.credentials.MarkUsed(ctx, state.ID, time.Now().UTC())
	} else {
		ownerID, err = s.createSocialOwnerAccount(ctx, provider, credKey, identity)
		if err != nil {
			return nil, err
		}
	}
	if err := s.persistLoginDevice(ctx, ownerID, deviceID, platform, appVersion); err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("persist social login device: %v", err))
	}
	return s.issueLoginResult(ctx, ownerID, provider, credKey, deviceID)
}

// createSocialOwnerAccount 创建社交首登账号，并以厂商资料初始化昵称/头像。
func (s *AuthService) createSocialOwnerAccount(ctx context.Context, provider, credKey string, identity ExternalIdentity) (string, error) {
	displayLabel := sanitizeProviderDisplayName(identity.DisplayName)
	ownerID, err := s.createOwnerAccount(ctx, provider, credKey, displayLabel)
	if err != nil {
		return "", err
	}
	// 资料首次同步：失败不阻断登录（结构化告警 + 默认资料兜底）。
	if syncErr := s.syncProviderProfileOnFirstLogin(ctx, ownerID, identity); syncErr != nil {
		slog.WarnContext(ctx, "social provider profile first-sync failed",
			"social.provider", provider,
			"owner.id", ownerID,
			"error", syncErr.Error())
	}
	return ownerID, nil
}

// syncProviderProfileOnFirstLogin 用厂商公开资料初始化 owner 与主分身的昵称/头像。
// 注意：头像目前直接引用厂商 URL；转存自有 CDN 留待 media 资产管线（avatarAssetId）后续接入。
func (s *AuthService) syncProviderProfileOnFirstLogin(ctx context.Context, ownerID string, identity ExternalIdentity) error {
	profile, err := s.profiles.FindByID(ctx, ownerID)
	if err != nil || profile == nil {
		return err
	}
	updated := false
	if displayName := sanitizeProviderDisplayName(identity.DisplayName); displayName != "" {
		profile.OwnerDisplayName = displayName
		if nick := sanitizedProviderNickname(displayName); nick != "" {
			profile.Nickname = nick
			// 厂商提供的是真实公开昵称，视为已具备有意义名称：
			// 标记 nicknameCustomized，本人主页不再展示「完善昵称」编辑画笔。
			profile.NicknameCustomized = true
		}
		updated = true
	}
	if avatar := strings.TrimSpace(identity.AvatarURL); avatar != "" && avatar != strings.TrimSpace(profile.AvatarURL) {
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

// sanitizedProviderNickname 直接采用厂商公开昵称作为初始昵称。
// 昵称已不再要求全局唯一，因此不再做占用探测与熵尾后缀拼接。
func sanitizedProviderNickname(desired string) string {
	return sanitizeProviderDisplayName(desired)
}

func sanitizeProviderDisplayName(name string) string {
	trimmed := strings.TrimSpace(name)
	if trimmed == "" {
		return ""
	}
	if len([]rune(trimmed)) > 32 {
		trimmed = string([]rune(trimmed)[:32])
	}
	return trimmed
}

func providerAuthFailedError(provider, message string) error {
	switch provider {
	case SocialProviderWechat:
		return generated.AppErrorFromWechatAuthFailed(message)
	case SocialProviderAlipay:
		return generated.AppErrorFromAlipayAuthFailed(message)
	case SocialProviderQq:
		return generated.AppErrorFromQqAuthFailed(message)
	default:
		return generated.AppErrorFromSocialProviderUnavailable(message)
	}
}

func mapSocialProviderError(provider string, err error) error {
	if err == nil {
		return nil
	}
	text := strings.ToLower(err.Error())
	switch {
	case strings.Contains(text, "cancel"):
		return generated.AppErrorFromSocialProviderCancelled(err.Error())
	case strings.Contains(text, "unavailable"), strings.Contains(text, "timeout"):
		return generated.AppErrorFromSocialProviderUnavailable(err.Error())
	default:
		return providerAuthFailedError(provider, err.Error())
	}
}

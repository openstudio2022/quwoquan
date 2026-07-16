package application

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"log/slog"
	"math/big"
	"net/url"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"go.opentelemetry.io/otel/attribute"

	rtauth "quwoquan_service/runtime/auth"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

const (
	credentialPhone           = "phone"
	credentialCarrierPhone    = "carrier_phone"
	credentialWechat          = "wechat"
	credentialAlipay          = "alipay"
	credentialQq              = "qq"
	credentialApple           = "apple"
	credentialAnonymousDevice = "anonymous_device"

	defaultIsolationLevel = "open"
	personaStatusActive   = "active"
	personaStatusRetired  = "retired"
	maxLoginFailCount     = 5
	maxOTPFailCount       = 5
	lockDurationMinutes   = 30
	refreshTokenTTLHours  = 24 * 30

	anonymousDevicePlatformMaxRunes   = 16
	anonymousDeviceAppVersionMaxRunes = 32

	// defaultNewUserNicknamePrefix 是首次创建用户的系统默认昵称前缀。
	// 云侧可通过 WithDefaultNicknamePrefix 覆盖（USER_DEFAULT_NICKNAME_PREFIX）。
	defaultNewUserNicknamePrefix = "新同学"
)

// AuthService handles OwnerAccount authentication and credential binding.
type AuthService struct {
	profiles         userrepo.UserProfileStore
	personas         PersonaStore
	credentials      userrepo.CredentialBindingStore
	userAuth         userrepo.AccountSessionStore
	userDevices      userrepo.DeviceRegistrationStore
	consents         userrepo.ConsentRecordStore
	anonymousDevices userrepo.AnonymousDeviceBindingStore
	shardDirectory   *ShardDirectory
	oneTapResolver   OneTapPhoneResolver
	otp              OtpCodeStore
	otpChallenges    OtpChallengeStore
	otpCodeSealer    OTPCodeSealer
	otpCodeGenerator func() (string, error)
	externalClient   ExternalInteractionClient
	socialProviders  ExternalAuthProviderClient
	accessSigner     *rtauth.Signer
	nicknamePrefix   string
}

type AuthServiceOption func(*AuthService)

type OTPCodeSealer interface {
	Seal(secret otpseal.Secret, binding otpseal.Binding) (string, error)
}

type OneTapPhoneResolver interface {
	ResolvePhone(ctx context.Context, vendor, carrierToken string) (phone string, displayLabel string, err error)
}

// OtpCodeStore 抽象手机号验证码的存储与限频，实现位于 infrastructure/cache。
// 它只负责发码冷却/配额与读写验证码；是否过期/匹配由 AuthService 判定。
type OtpCodeStore interface {
	AllowSend(ctx context.Context, phone string) (allowed bool, retryAfterSeconds int, err error)
	SaveCode(ctx context.Context, phone, code string) error
	ReadCode(ctx context.Context, phone string) (code string, found bool, err error)
	ClearCode(ctx context.Context, phone string) error
}

func NewAuthService(
	profiles userrepo.UserProfileStore,
	personas PersonaStore,
	credentials userrepo.CredentialBindingStore,
	anonymousDevices userrepo.AnonymousDeviceBindingStore,
	shardDirectory *ShardDirectory,
	opts ...AuthServiceOption,
) *AuthService {
	svc := &AuthService{
		profiles:         profiles,
		personas:         personas,
		credentials:      credentials,
		anonymousDevices: anonymousDevices,
		shardDirectory:   shardDirectory,
		oneTapResolver:   TokenEncodedOneTapPhoneResolver{},
		nicknamePrefix:   defaultNewUserNicknamePrefix,
		otpCodeGenerator: generateOtpCode,
	}
	for _, opt := range opts {
		if opt != nil {
			opt(svc)
		}
	}
	return svc
}

func WithOTPCodeSealer(sealer OTPCodeSealer) AuthServiceOption {
	return func(s *AuthService) {
		if sealer != nil {
			s.otpCodeSealer = sealer
		}
	}
}

func WithOTPCodeGenerator(generator func() (string, error)) AuthServiceOption {
	return func(s *AuthService) {
		if generator != nil {
			s.otpCodeGenerator = generator
		}
	}
}

// WithDefaultNicknamePrefix 注入系统默认昵称前缀（云侧可配置）。
// 首次创建用户时默认昵称为 "{prefix}_{YYMMDD}_{7位尾号}"。
func WithDefaultNicknamePrefix(prefix string) AuthServiceOption {
	return func(s *AuthService) {
		if p := strings.TrimSpace(prefix); p != "" {
			s.nicknamePrefix = p
		}
	}
}

func WithAccountSessionStore(repo userrepo.AccountSessionStore) AuthServiceOption {
	return func(s *AuthService) {
		s.userAuth = repo
	}
}

func WithDeviceRegistrationStore(repo userrepo.DeviceRegistrationStore) AuthServiceOption {
	return func(s *AuthService) {
		s.userDevices = repo
	}
}

func WithConsentRecordStore(repo userrepo.ConsentRecordStore) AuthServiceOption {
	return func(s *AuthService) {
		s.consents = repo
	}
}

func WithOneTapPhoneResolver(resolver OneTapPhoneResolver) AuthServiceOption {
	return func(s *AuthService) {
		if resolver != nil {
			s.oneTapResolver = resolver
		}
	}
}

// WithOtpCodeStore 注入手机号验证码存储。未注入时手机号登录会拒绝（缺少 OTP 校验能力）。
func WithOtpCodeStore(store OtpCodeStore) AuthServiceOption {
	return func(s *AuthService) {
		s.otp = store
	}
}

func WithOtpChallengeStore(store OtpChallengeStore) AuthServiceOption {
	return func(s *AuthService) {
		if store != nil {
			s.otpChallenges = store
		}
	}
}

func WithExternalInteractionClient(client ExternalInteractionClient) AuthServiceOption {
	return func(s *AuthService) {
		s.externalClient = client
	}
}

// WithExternalAuthProviderClient 注入社交登录（微信/支付宝/QQ）票据置换实现。
// 所有 Remote 环境只注入真实 HTTP provider；alpha fixture 不进入服务进程。
func WithExternalAuthProviderClient(client ExternalAuthProviderClient) AuthServiceOption {
	return func(s *AuthService) {
		if client != nil {
			s.socialProviders = client
		}
	}
}

// WithAccessTokenSigner 注入 access token 签发器；注入后 accessToken 为短期 JWT，
// 可被各服务/网关本地验签。未注入时回退到不透明随机串（过渡期回退）。
func WithAccessTokenSigner(signer *rtauth.Signer) AuthServiceOption {
	return func(s *AuthService) {
		s.accessSigner = signer
	}
}

// LoginResult is returned after a successful authentication.
type LoginResult struct {
	AccessToken              string         `json:"accessToken"`
	RefreshToken             string         `json:"refreshToken"`
	OwnerID                  string         `json:"ownerId"`
	ActiveSub                map[string]any `json:"activeSub"`
	SubAccountCount          int            `json:"subAccountCount"`
	AccountState             string         `json:"accountState"`
	IdentityOrigin           string         `json:"identityOrigin"`
	LogicalShard             int            `json:"logicalShard"`
	AnonymousRetentionPolicy string         `json:"anonymousRetentionPolicy"`
	AccountHint              map[string]any `json:"accountHint,omitempty"`
}

type OneTapLoginHint struct {
	State             string         `json:"state"`
	MaskedPhone       string         `json:"maskedPhone"`
	Registered        bool           `json:"registered"`
	AccountHint       map[string]any `json:"accountHint,omitempty"`
	ExpiresInSeconds  int            `json:"expiresInSeconds"`
	ProviderRequestID string         `json:"providerRequestId,omitempty"`
}

// LoginWithCredential authenticates via the given credential type and key.
// It creates a new OwnerAccount + default SubAccount if not found.
func (s *AuthService) LoginWithCredential(ctx context.Context, credType, credKey, displayLabel string) (_ *LoginResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.LoginWithCredential",
		attribute.String("credential.type", credType))
	defer func() { rtobs.EndSpan(span, err) }()

	if strings.TrimSpace(credType) == credentialAnonymousDevice {
		credKey = normalizeAnonymousCredentialKey(credKey)
	}
	existing, err := s.credentials.FindByTypeAndKey(ctx, credType, credKey)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("credential lookup: %v", err))
	}

	var ownerID string
	if existing != nil {
		ownerID = existing.OwnerID
		_ = s.credentials.UpdateLastUsed(ctx, existing.ID)
	} else {
		// New user: create OwnerAccount + default SubAccount
		ownerID, err = s.createOwnerAccount(ctx, credType, credKey, displayLabel)
		if err != nil {
			return nil, generated.AppErrorFromInternalError(fmt.Sprintf("create owner: %v", err))
		}
	}

	return s.issueLoginResult(ctx, ownerID, credType, credKey)
}

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

	existing, err := s.credentials.FindByTypeAndKey(ctx, provider, credKey)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("social credential lookup: %v", err))
	}
	var ownerID string
	if existing != nil {
		ownerID = existing.OwnerID
		_ = s.credentials.UpdateLastUsed(ctx, existing.ID)
	} else {
		ownerID, err = s.createSocialOwnerAccount(ctx, provider, credKey, identity)
		if err != nil {
			return nil, err
		}
	}
	if err := s.persistLoginDevice(ctx, ownerID, deviceID, platform, appVersion); err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("persist social login device: %v", err))
	}
	return s.issueLoginResult(ctx, ownerID, provider, credKey)
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

func (s *AuthService) issueLoginResult(
	ctx context.Context,
	ownerID, credType, credKey string,
) (*LoginResult, error) {
	if _, err := s.resolvePhysicalShard(ownerID); err != nil {
		return nil, err
	}
	profile, err := s.profiles.FindByID(ctx, ownerID)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("load profile: %v", err))
	}
	if profile != nil && strings.TrimSpace(credType) != credentialAnonymousDevice {
		updated := false
		if strings.TrimSpace(profile.AccountState) == accountStateAnonymous {
			promoteRegisteredProfile(profile)
			updated = true
		}
		if strings.TrimSpace(credType) == credentialPhone && strings.TrimSpace(profile.Phone) == "" {
			profile.Phone = credKey
			updated = true
		}
		if updated {
			if err := s.profiles.Update(ctx, profile); err != nil {
				return nil, generated.AppErrorFromInternalError(fmt.Sprintf("promote owner profile: %v", err))
			}
		}
	}

	activeSub, err := s.personas.FindActiveByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}

	subs, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}

	accessToken, err := s.issueAccessToken(ownerID, activeSub)
	if err != nil {
		return nil, err
	}
	refreshToken, err := generateToken()
	if err != nil {
		return nil, err
	}
	if err := s.persistRefreshToken(ctx, ownerID, refreshToken); err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("persist refresh token: %v", err))
	}

	return &LoginResult{
		AccessToken:              accessToken,
		RefreshToken:             refreshToken,
		OwnerID:                  ownerID,
		ActiveSub:                buildActiveSubEnvelope(activeSub),
		SubAccountCount:          len(subs),
		AccountState:             defaultString(profileField(profile, func(p *model.UserProfile) string { return p.AccountState }), accountStateForCredentialType(credType)),
		IdentityOrigin:           defaultString(profileField(profile, func(p *model.UserProfile) string { return p.IdentityOrigin }), identityOriginValue(credType)),
		LogicalShard:             profileIntField(profile, func(p *model.UserProfile) int { return p.LogicalShard }),
		AnonymousRetentionPolicy: defaultString(profileField(profile, func(p *model.UserProfile) string { return p.AnonymousRetentionPolicy }), anonymousRetentionPolicyForCredentialType(credType)),
		AccountHint:              buildLoginAccountHint(profile, ""),
	}, nil
}

func (s *AuthService) persistRefreshToken(ctx context.Context, ownerID, refreshToken string) error {
	if s.userAuth == nil {
		return nil
	}
	return s.userAuth.UpsertRefreshToken(
		ctx,
		strings.TrimSpace(ownerID),
		strings.TrimSpace(refreshToken),
		time.Now().UTC().Add(refreshTokenTTLHours*time.Hour),
	)
}

func (s *AuthService) RefreshToken(ctx context.Context, refreshToken string) (_ *LoginResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.RefreshToken")
	defer func() { rtobs.EndSpan(span, err) }()

	refreshToken = strings.TrimSpace(refreshToken)
	if refreshToken == "" {
		return nil, generated.AppErrorFromInvalidArgument("refreshToken is required")
	}
	if s.userAuth == nil {
		return nil, generated.AppErrorFromInternalError("refresh token store unavailable")
	}
	auth, err := s.userAuth.FindByRefreshToken(ctx, refreshToken)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("lookup refresh token: %v", err))
	}
	if auth == nil || strings.TrimSpace(auth.UserID) == "" {
		return nil, generated.AppErrorFromUnauthorized("refresh token invalid")
	}
	if auth.RefreshTokenExpiresAt == nil || auth.RefreshTokenExpiresAt.Before(time.Now().UTC()) {
		_ = s.userAuth.RevokeRefreshTokenValue(ctx, refreshToken)
		return nil, generated.AppErrorFromTokenExpired("refresh token expired")
	}
	profile, err := s.profiles.FindByID(ctx, auth.UserID)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("load profile: %v", err))
	}
	credType := credentialPhone
	if profile != nil && strings.TrimSpace(profile.IdentityOrigin) != "" {
		credType = strings.TrimSpace(profile.IdentityOrigin)
	}
	return s.issueLoginResult(ctx, auth.UserID, credType, "")
}

func (s *AuthService) Logout(ctx context.Context, ownerID, refreshToken string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.Logout",
		attribute.String("owner.id", strings.TrimSpace(ownerID)))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.userAuth == nil {
		return nil
	}
	refreshToken = strings.TrimSpace(refreshToken)
	if refreshToken != "" {
		return s.userAuth.RevokeRefreshTokenValue(ctx, refreshToken)
	}
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" {
		return nil
	}
	return s.userAuth.RevokeRefreshToken(ctx, ownerID)
}

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
	result, err := s.LoginWithCredential(ctx, credentialCarrierPhone, phone, displayLabel)
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
	existing, err := s.credentials.FindByTypeAndKey(ctx, credentialCarrierPhone, phone)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("one tap credential lookup: %v", err))
	}
	if existing == nil {
		existing, err = s.credentials.FindByTypeAndKey(ctx, credentialPhone, phone)
		if err != nil {
			return nil, generated.AppErrorFromInternalError(fmt.Sprintf("phone credential lookup: %v", err))
		}
	}
	if existing == nil {
		return hint, nil
	}
	profile, err := s.profiles.FindByID(ctx, existing.OwnerID)
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
		existing, err := s.credentials.FindByTypeAndKey(ctx, credentialAnonymousDevice, deviceFingerprintHash)
		if err != nil {
			return nil, generated.AppErrorFromInternalError(fmt.Sprintf("anonymous credential lookup: %v", err))
		}
		if existing != nil {
			ownerID = existing.OwnerID
			_ = s.credentials.UpdateLastUsed(ctx, existing.ID)
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
	return s.issueLoginResult(ctx, ownerID, credentialAnonymousDevice, "")
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

// BindCredential binds a new credential to an existing OwnerAccount.
func (s *AuthService) BindCredential(ctx context.Context, ownerID, credType, credKey, displayLabel string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.BindCredential",
		attribute.String("owner.id", ownerID),
		attribute.String("credential.type", credType))
	defer func() { rtobs.EndSpan(span, err) }()

	// Check global uniqueness: this credential must not be bound to another owner
	existing, err := s.credentials.FindByTypeAndKey(ctx, credType, credKey)
	if err != nil {
		return err
	}
	if existing != nil && existing.OwnerID != ownerID {
		return ErrCredentialConflict
	}
	if existing != nil && existing.OwnerID == ownerID {
		return nil // already bound, idempotent
	}

	// Check per-owner-per-type uniqueness
	ownerCred, err := s.credentials.FindByOwnerAndType(ctx, ownerID, credType)
	if err != nil {
		return err
	}
	if ownerCred != nil {
		return ErrCredentialConflict
	}

	if err := s.credentials.Create(ctx, &model.CredentialBinding{
		ID:             generateCredentialBindingID(),
		OwnerID:        ownerID,
		CredentialType: credType,
		CredentialKey:  credKey,
		DisplayLabel:   displayLabel,
		IsActive:       true,
	}); err != nil {
		return err
	}

	if strings.TrimSpace(credType) == credentialAnonymousDevice {
		return nil
	}
	profile, err := s.profiles.FindByID(ctx, ownerID)
	if err != nil {
		return err
	}
	if profile == nil {
		return nil
	}
	promoteRegisteredProfile(profile)
	if strings.TrimSpace(credType) == credentialPhone && strings.TrimSpace(profile.Phone) == "" {
		profile.Phone = credKey
	}
	return s.profiles.Update(ctx, profile)
}

func (s *AuthService) BindPhoneCredential(ctx context.Context, ownerID, phone, otpCode, displayLabel string) error {
	normalized := normalizePhoneCredentialKey(phone)
	if normalized == "" {
		return generated.AppErrorFromInvalidArgument("phone is required")
	}
	if err := s.verifyOtp(ctx, normalized, otpCode); err != nil {
		return err
	}
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = maskPhoneForDisplay(normalized)
	}
	return s.BindCredential(ctx, ownerID, credentialPhone, normalized, displayLabel)
}

func (s *AuthService) BindCarrierPhoneCredential(ctx context.Context, ownerID, vendor, carrierToken, deviceID, platform, displayLabel string) error {
	resolver := s.oneTapResolver
	if resolver == nil {
		return generated.AppErrorFromCarrierUnavailable("one tap resolver unavailable")
	}
	phone, resolvedLabel, err := resolver.ResolvePhone(ctx, vendor, carrierToken)
	if err != nil {
		return mapCarrierResolverError(err)
	}
	normalized := normalizePhoneCredentialKey(phone)
	if normalized == "" {
		return generated.AppErrorFromCarrierTokenInvalid("one tap phone is empty")
	}
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = strings.TrimSpace(resolvedLabel)
	}
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = maskPhoneForDisplay(normalized)
	}
	if err := s.persistLoginDevice(ctx, ownerID, deviceID, platform, ""); err != nil {
		return generated.AppErrorFromInternalError(fmt.Sprintf("persist carrier bind device: %v", err))
	}
	return s.BindCredential(ctx, ownerID, credentialCarrierPhone, normalized, displayLabel)
}

// UnbindCredential deactivates a credential, but prevents removing the last one.
func (s *AuthService) UnbindCredential(ctx context.Context, ownerID, credType string) (err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.UnbindCredential",
		attribute.String("owner.id", ownerID),
		attribute.String("credential.type", credType))
	defer func() { rtobs.EndSpan(span, err) }()

	count, err := s.credentials.CountActive(ctx, ownerID)
	if err != nil {
		return err
	}
	if count <= 1 {
		return ErrLastCredential
	}
	return s.credentials.Deactivate(ctx, ownerID, credType)
}

// ListCredentials returns the public-facing (masked) credential list for an owner.
func (s *AuthService) ListCredentials(ctx context.Context, ownerID string) (_ []model.CredentialBinding, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.ListCredentials",
		attribute.String("owner.id", ownerID))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.credentials.FindByOwner(ctx, ownerID)
}

// createOwnerAccount creates a new user_profiles row + default persona + initial credential.
func (s *AuthService) createOwnerAccount(ctx context.Context, credType, credKey, displayLabel string) (string, error) {
	identity, err := buildOwnerIdentity(credType)
	if err != nil {
		return "", err
	}
	ownerID := identity.OwnerID
	if _, err := s.resolvePhysicalShard(ownerID); err != nil {
		return "", err
	}
	subAccountID, err := buildSubAccountIdentity(identity.RootPrefix)
	if err != nil {
		return "", err
	}

	profile := &model.UserProfile{
		UserID:                   ownerID,
		Phone:                    "",
		Nickname:                 s.buildDefaultNickname(),
		NicknameCustomized:       false,
		Status:                   "active",
		AccountState:             accountStateForCredentialType(credType),
		IdentityOrigin:           identityOriginValue(credType),
		LogicalShard:             identity.LogicalShard,
		AnonymousRetentionPolicy: anonymousRetentionPolicyForCredentialType(credType),
		IdentityTags:             "{}",
		ProfileVersion:           1,
		SubAccountCount:          1,
	}
	if credType == credentialPhone || credType == credentialCarrierPhone {
		profile.Phone = credKey
	}

	if err := s.profiles.Create(ctx, profile); err != nil {
		return "", generated.AppErrorFromInternalError(fmt.Sprintf("create profile: %v", err))
	}

	persona := &model.Persona{
		UserID:                   ownerID,
		SubAccountID:             subAccountID,
		UserHandle:               systemUserHandleForSubAccount(subAccountID),
		DisplayName:              profile.Nickname,
		Phone:                    profile.Phone,
		IsPrimary:                true,
		IsActive:                 true,
		IsolationLevel:           defaultIsolationLevel,
		InheritsProfileFromOwner: true,
		OverriddenProfileFields:  encodeProfileFieldList(nil),
	}
	normalizePersonaPersistence(persona)
	if err := s.personas.Create(ctx, persona); err != nil {
		return "", generated.AppErrorFromInternalError(fmt.Sprintf("create persona: %v", err))
	}

	cred := &model.CredentialBinding{
		ID:             generateCredentialBindingID(),
		OwnerID:        ownerID,
		CredentialType: credType,
		CredentialKey:  credKey,
		DisplayLabel:   displayLabel,
		IsActive:       true,
	}
	if err := s.credentials.Create(ctx, cred); err != nil {
		return "", generated.AppErrorFromInternalError(fmt.Sprintf("create credential: %v", err))
	}

	return ownerID, nil
}

func (s *AuthService) resolvePhysicalShard(ownerID string) (string, error) {
	if s == nil || s.shardDirectory == nil {
		return "", nil
	}
	physicalShard := strings.TrimSpace(s.shardDirectory.ResolvePhysicalShardForOwnerID(ownerID))
	if physicalShard == "" {
		return "", generated.AppErrorFromInternalError(fmt.Sprintf("resolve physical shard for owner %s", ownerID))
	}
	return physicalShard, nil
}

func buildActiveSubEnvelope(activeSub *model.Persona) map[string]any {
	if activeSub == nil {
		return map[string]any{}
	}
	return map[string]any{
		"subAccountId": activeSub.SubAccountID,
	}
}

func buildLoginAccountHint(profile *model.UserProfile, fallbackMaskedPhone string) map[string]any {
	if profile == nil {
		return nil
	}
	displayName := strings.TrimSpace(profile.OwnerDisplayName)
	if displayName == "" {
		displayName = strings.TrimSpace(profile.Nickname)
	}
	maskedPhone := strings.TrimSpace(fallbackMaskedPhone)
	if maskedPhone == "" {
		maskedPhone = maskPhoneForDisplay(profile.Phone)
	}
	return map[string]any{
		"displayName":        displayName,
		"nicknameCustomized": profile.NicknameCustomized,
		"avatarUrl":          avatarURLWithVersion(profile.AvatarURL, profile.AvatarVersion),
		"avatarAssetId":      strings.TrimSpace(profile.AvatarAssetID),
		"maskedPhone":        maskedPhone,
		"identityOrigin":     strings.TrimSpace(profile.IdentityOrigin),
	}
}

func avatarURLWithVersion(raw string, version int) string {
	value := strings.TrimSpace(raw)
	if value == "" || version <= 0 {
		return value
	}
	parsed, err := url.Parse(value)
	if err != nil {
		return value
	}
	query := parsed.Query()
	query.Set("v", fmt.Sprintf("%d", version))
	parsed.RawQuery = query.Encode()
	return parsed.String()
}

func avatarVersionFromURL(raw string) int {
	value := strings.TrimSpace(raw)
	if value == "" {
		return 0
	}
	parsed, err := url.Parse(value)
	if err != nil {
		return 0
	}
	version, err := strconv.Atoi(strings.TrimSpace(parsed.Query().Get("v")))
	if err != nil || version <= 0 {
		return 0
	}
	return version
}

func resolvedPersonaAvatarVersion(persona *model.Persona) int {
	if persona == nil {
		return 0
	}
	if persona.AvatarVersion > 0 {
		return persona.AvatarVersion
	}
	return avatarVersionFromURL(persona.AvatarURL)
}

func ensureProfileCanLogin(profile *model.UserProfile) error {
	if profile == nil {
		return generated.AppErrorFromUserNotFound("account not found")
	}
	switch strings.TrimSpace(profile.AccountState) {
	case "suspended":
		return generated.AppErrorFromAccountSuspended("account suspended")
	case "deleted":
		return generated.AppErrorFromAccountDeleted("account deleted")
	default:
		return nil
	}
}

func (s *AuthService) persistLoginDevice(ctx context.Context, ownerID, deviceID, platform, appVersion string) error {
	if s.userDevices == nil {
		return nil
	}
	deviceID = strings.TrimSpace(deviceID)
	if strings.TrimSpace(ownerID) == "" || deviceID == "" {
		return nil
	}
	return s.userDevices.UpsertLoginDevice(ctx, &model.UserDevice{
		UserID:       strings.TrimSpace(ownerID),
		DeviceID:     deviceID,
		Platform:     strings.TrimSpace(platform),
		AppVersion:   strings.TrimSpace(appVersion),
		LastActiveAt: time.Now().UTC(),
	})
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

func generateCredentialBindingID() string {
	id, err := generateIdentityEntropyBody()
	if err != nil {
		return "cb_fallback"
	}
	return "cb_" + id
}

// buildDefaultNickname 生成首次创建用户的系统默认昵称：
//
//	{prefix}_{YYMMDD}_{7位尾号}
//
// 前缀云侧可配置（默认「新同学」）；7 位尾号混合时/分/秒/毫秒与随机扰动，
// 在允许重复的前提下尽量降低近时刻碰撞概率。昵称唯一性仍由
// ownerID/subAccountId/userHandle 承担。
func (s *AuthService) buildDefaultNickname() string {
	prefix := strings.TrimSpace(s.nicknamePrefix)
	if prefix == "" {
		prefix = defaultNewUserNicknamePrefix
	}
	now := time.Now()
	yymmdd := now.Format("060102")
	return fmt.Sprintf("%s_%s_%07d", prefix, yymmdd, defaultNicknameSevenDigitSuffix(now))
}

// defaultNicknameSevenDigitSuffix 混合毫秒级时钟与随机熵，返回 [0, 1e7) 的 7 位尾号。
func defaultNicknameSevenDigitSuffix(now time.Time) int64 {
	millisOfDay := int64(now.Hour())*3_600_000 +
		int64(now.Minute())*60_000 +
		int64(now.Second())*1_000 +
		int64(now.Nanosecond()/1_000_000)
	n, err := rand.Int(rand.Reader, big.NewInt(1_000))
	if err != nil {
		return (millisOfDay + now.UnixNano()%1_000) % 10_000_000
	}
	return (millisOfDay + n.Int64()) % 10_000_000
}

func extractOwnerRootPrefix(ownerID string) string {
	parts := strings.Split(strings.TrimSpace(ownerID), "_")
	if len(parts) >= 5 && parts[0] == "uo" {
		return parts[3]
	}
	return "0000"
}

func identityOriginValue(credType string) string {
	origin, _ := identityOriginForCredentialType(credType)
	return origin
}

func profileField(profile *model.UserProfile, getter func(*model.UserProfile) string) string {
	if profile == nil || getter == nil {
		return ""
	}
	return strings.TrimSpace(getter(profile))
}

func profileIntField(profile *model.UserProfile, getter func(*model.UserProfile) int) int {
	if profile == nil || getter == nil {
		return 0
	}
	return getter(profile)
}

// Sentinel errors – returned from AuthService methods.
var (
	ErrCredentialConflict = generated.AppErrorFromCredentialConflict("credential already bound to another account")
	ErrLastCredential     = generated.AppErrorFromLastCredential("cannot unbind the last credential")
)

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

func generateToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.URLEncoding.EncodeToString(b), nil
}

// issueAccessToken 只签发经统一 trust root 配置的短期 JWT。
func (s *AuthService) issueAccessToken(ownerID string, activeSub *model.Persona) (string, error) {
	if s.accessSigner == nil {
		return "", generated.AppErrorFromInternalError("access token signer unavailable")
	}
	persona := ""
	if activeSub != nil {
		persona = activeSub.SubAccountID
	}
	return s.accessSigner.Sign(rtauth.TokenSubject{
		AccountID: ownerID,
		PersonaID: persona,
	})
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

// verifyOtp 校验验证码：只信任持久化 challenge 状态、hash、过期与一次性消费标记。
func (s *AuthService) verifyOtp(ctx context.Context, phone, code string) error {
	if s.otpChallenges == nil {
		return generated.AppErrorFromInternalError("otp challenge store unavailable")
	}
	code = strings.TrimSpace(code)
	if code == "" {
		return generated.AppErrorFromInvalidArgument("otpCode required")
	}
	now := time.Now().UTC()
	challenge, err := s.otpChallenges.FindLatestChallenge(ctx, phone, now)
	if err != nil {
		return generated.AppErrorFromInternalError(fmt.Sprintf("otp challenge read: %v", err))
	}
	if challenge == nil {
		return generated.AppErrorFromOtpExpired("otp expired")
	}
	if challenge.Status != OtpChallengeStatusActive {
		return generated.AppErrorFromOtpExpired("otp not ready")
	}
	if challenge.CodeHash != hashOTPCode(challenge.ChallengeID, phone, code) {
		_, exhausted, recordErr := s.otpChallenges.RecordFailedAttempt(ctx, challenge.ChallengeID, maxOTPFailCount, now)
		if recordErr != nil {
			return generated.AppErrorFromInternalError(fmt.Sprintf("otp failed attempt record: %v", recordErr))
		}
		if exhausted {
			return generated.AppErrorFromOtpAttemptsExceeded("otp attempts exceeded")
		}
		return generated.AppErrorFromOtpMismatch("otp mismatch")
	}
	_ = s.otpChallenges.ConsumeChallenge(ctx, challenge.ChallengeID, now)
	return nil
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
		return nil, generated.AppErrorFromConsentRequired("agreementVersion and privacyVersion required")
	}
	if err := s.verifyOtp(ctx, normalized, otpCode); err != nil {
		return nil, err
	}
	if strings.TrimSpace(displayLabel) == "" {
		displayLabel = maskPhoneForDisplay(normalized)
	}
	result, err := s.LoginWithCredential(ctx, credentialPhone, normalized, displayLabel)
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

func (s *AuthService) HandleOtpDeliveryCallback(ctx context.Context, requestID string, status string, normalizedError string) error {
	if s.otpChallenges == nil {
		return generated.AppErrorFromInternalError("otp challenge store unavailable")
	}
	switch strings.TrimSpace(status) {
	case "delivered", "sent_unconfirmed", "active", "queued":
		return s.otpChallenges.MarkChallengeDelivered(ctx, strings.TrimSpace(requestID), OtpChallengeStatusActive)
	case "failed", "dead_letter":
		return s.otpChallenges.MarkChallengeFailed(ctx, strings.TrimSpace(requestID), normalizedError)
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

// SubAccountService handles SubAccount lifecycle within an OwnerAccount.
func defaultString(value, fallback string) string {
	if value != "" {
		return value
	}
	return fallback
}

func isPersonaHandleConflict(err error) bool {
	return errors.Is(err, userrepo.ErrPersonaHandleConflict)
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

var (
	ErrSubAccountNotFound       = generated.AppErrorFromSubAccountNotFound("sub-account not found")
	ErrPrimarySubAccount        = generated.AppErrorFromPrimarySubAccountGuard("primary persona cannot be deleted or retired")
	ErrLastSubAccount           = generated.AppErrorFromLastSubAccount("cannot retire or delete the last active persona")
	ErrActiveSubAccountAction   = generated.AppErrorFromActiveSubAccountGuard("switch to another persona before deleting or retiring this one")
	ErrRetiredPersonaAction     = generated.AppErrorFromRetiredSubAccountGuard("retired persona cannot accept new actions")
	ErrDeleteEmptyPersonaOnly   = generated.AppErrorFromDeleteEmptySubAccountOnly("empty persona should be deleted directly")
	ErrSubAccountRetireRequired = generated.AppErrorFromSubAccountRetireRequired("persona has history and must be retired instead of deleted")
	ErrSubAccountStrictIso      = generated.AppErrorFromSubAccountStrictIsolation("user not found")
	ErrPersonaHandleTaken       = generated.AppErrorFromSubAccountHandleTaken("persona_handle_taken")
)

func findPersonaBySubAccountID(ctx context.Context, personas userrepo.PersonaReader, subAccountID string) (*model.Persona, error) {
	return personas.FindBySubAccountID(ctx, subAccountID)
}

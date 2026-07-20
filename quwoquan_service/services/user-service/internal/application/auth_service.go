package application

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"math/big"
	"net/url"
	"strconv"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtauth "quwoquan_service/runtime/auth"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/otpseal"
	sessionapp "quwoquan_service/services/user-service/internal/application/account/account_session"
	challengeapp "quwoquan_service/services/user-service/internal/application/account/authentication_challenge"
	credentialapp "quwoquan_service/services/user-service/internal/application/account/credential_binding"
	registrationapp "quwoquan_service/services/user-service/internal/application/account/device_registration"
	credentialmodel "quwoquan_service/services/user-service/internal/domain/account/credential_binding/model"
	credentialports "quwoquan_service/services/user-service/internal/domain/account/credential_binding/ports"
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
	profiles                 userrepo.UserProfileStore
	personas                 PersonaStore
	credentials              credentialports.AggregateStore
	credentialCommands       credentialapp.CommandFacet
	sessions                 sessionapp.CommandFacet
	deviceRegistration       registrationapp.InternalRegisterer
	consents                 userrepo.ConsentRecordStore
	anonymousDevices         userrepo.AnonymousDeviceBindingStore
	shardDirectory           *ShardDirectory
	oneTapResolver           OneTapPhoneResolver
	otp                      OtpCodeStore
	authenticationChallenges *challengeapp.AuthenticationChallengeCommandFacade
	otpCodeSealer            OTPCodeSealer
	otpCodeGenerator         func() (string, error)
	externalClient           ExternalInteractionClient
	socialProviders          ExternalAuthProviderClient
	accessSigner             *rtauth.Signer
	nicknamePrefix           string
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
	credentials credentialports.AggregateStore,
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

func WithCredentialCommands(facet credentialapp.CommandFacet) AuthServiceOption {
	return func(s *AuthService) {
		s.credentialCommands = facet
	}
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

// WithAccountSessionCommands 注入 AccountSession 对象 Facet。登录协调器只传递
// 瞬时 token，哈希、轮换 lineage、吊销与 outbox 均由对象 packet 持有。
func WithAccountSessionCommands(facet sessionapp.CommandFacet) AuthServiceOption {
	return func(s *AuthService) {
		s.sessions = facet
	}
}

func WithDeviceRegistration(
	registrar registrationapp.InternalRegisterer,
) AuthServiceOption {
	return func(s *AuthService) {
		s.deviceRegistration = registrar
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

func WithAuthenticationChallenges(
	facade *challengeapp.AuthenticationChallengeCommandFacade,
) AuthServiceOption {
	return func(s *AuthService) {
		if facade != nil {
			s.authenticationChallenges = facade
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
	AccessToken               string         `json:"accessToken"`
	RefreshToken              string         `json:"refreshToken"`
	OwnerID                   string         `json:"ownerId"`
	ActiveSub                 map[string]any `json:"activeSub"`
	SubAccountCount           int            `json:"subAccountCount"`
	AccountState              string         `json:"accountState"`
	IdentityOrigin            string         `json:"identityOrigin"`
	LogicalShard              int            `json:"logicalShard"`
	AnonymousRetentionPolicy  string         `json:"anonymousRetentionPolicy"`
	AccountHint               map[string]any `json:"accountHint,omitempty"`
	SessionRememberTTLSeconds int            `json:"sessionRememberTtlSeconds"`
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
func (s *AuthService) LoginWithCredential(ctx context.Context, credType, credKey, displayLabel string) (*LoginResult, error) {
	return s.LoginWithCredentialOnDevice(ctx, credType, credKey, displayLabel, "")
}

// LoginWithCredentialOnDevice 同 LoginWithCredential，并把 deviceId 绑定进
// 新签发的 AccountSession（aggregate 规则要求 session 绑定设备）。
func (s *AuthService) LoginWithCredentialOnDevice(
	ctx context.Context,
	credType, credKey, displayLabel, deviceID string,
) (_ *LoginResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.LoginWithCredential",
		attribute.String("credential.type", credType))
	defer func() { rtobs.EndSpan(span, err) }()

	if strings.TrimSpace(credType) == credentialAnonymousDevice {
		credKey = normalizeAnonymousCredentialKey(credKey)
	}
	existing, found, err := s.credentials.FindByTypeAndKey(
		ctx,
		credentialmodel.CredentialType(credType),
		credKey,
	)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(fmt.Sprintf("credential lookup: %v", err))
	}

	var ownerID string
	if found {
		state := existing.State()
		ownerID = state.OwnerID
		_ = s.credentials.MarkUsed(ctx, state.ID, time.Now().UTC())
	} else {
		// New user: create OwnerAccount + default SubAccount
		ownerID, err = s.createOwnerAccount(ctx, credType, credKey, displayLabel)
		if err != nil {
			return nil, generated.AppErrorFromInternalError(fmt.Sprintf("create owner: %v", err))
		}
	}

	return s.issueLoginResult(ctx, ownerID, credType, credKey, deviceID)
}

func (s *AuthService) promoteCredentialOwner(
	ctx context.Context,
	ownerID string,
	credType string,
	credKey string,
) error {
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

// UnbindCredential deactivates a credential, but prevents removing the last one.
func (s *AuthService) UnbindCredential(
	ctx context.Context,
	ownerID, credType string,
) (result credentialapp.CommandResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.UnbindCredential",
		attribute.String("owner.id", ownerID),
		attribute.String("credential.type", credType))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.credentialCommands == nil {
		return credentialapp.CommandResult{}, generated.AppErrorFromInternalError(
			"credential command facet unavailable",
		)
	}
	result, err = s.credentialCommands.UnbindCredential(
		ctx,
		credentialapp.UnbindCredentialCommand{
			CredentialType: credentialmodel.CredentialType(
				strings.TrimSpace(credType),
			),
		},
	)
	return result, err
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

	if s.credentialCommands == nil {
		return "", generated.AppErrorFromInternalError(
			"credential command facet unavailable",
		)
	}
	_, err = s.credentialCommands.BindVerifiedCredential(
		ctx,
		ownerID,
		credentialapp.BindCredentialCommand{
			CredentialType: credentialmodel.CredentialType(credType),
			CredentialKey:  credKey,
			DisplayLabel:   displayLabel,
		},
	)
	if err != nil {
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
	case "closed":
		// aggregate.yaml lifecycle: closed 为注销终态（CloseAccount）。
		return generated.AppErrorFromAccountDeleted("account closed")
	default:
		return nil
	}
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

var (
	ErrSubAccountNotFound     = generated.AppErrorFromSubAccountNotFound("sub-account not found")
	ErrPrimarySubAccount      = generated.AppErrorFromPrimarySubAccountGuard("primary persona cannot be retired")
	ErrLastSubAccount         = generated.AppErrorFromLastSubAccount("cannot retire the last active persona")
	ErrActiveSubAccountAction = generated.AppErrorFromActiveSubAccountGuard("switch to another persona before retiring this one")
	ErrRetiredPersonaAction   = generated.AppErrorFromRetiredSubAccountGuard("retired persona cannot accept new actions")
	ErrSubAccountStrictIso    = generated.AppErrorFromSubAccountStrictIsolation("user not found")
	ErrPersonaHandleTaken     = generated.AppErrorFromSubAccountHandleTaken("persona_handle_taken")
)

func findPersonaBySubAccountID(ctx context.Context, personas userrepo.PersonaReader, subAccountID string) (*model.Persona, error) {
	return personas.FindBySubAccountID(ctx, subAccountID)
}

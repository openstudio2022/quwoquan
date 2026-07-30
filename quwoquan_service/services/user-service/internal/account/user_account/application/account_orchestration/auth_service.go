package application

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
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
	sessiongenerated "quwoquan_service/services/user-service/generated/account/account_session"
	accountgenerated "quwoquan_service/services/user-service/generated/account/user_account"
	personagenerated "quwoquan_service/services/user-service/generated/persona_management/persona"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	credentialports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

const (
	credentialPhone           = "phone"
	credentialCarrierPhone    = "carrier_phone"
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
	personaCommands          personaports.PersonaCommandStore
	personaProfileProjector  userrepo.PersonaProfileProjector
	credentials              credentialports.AggregateStore
	credentialCommands       credentialapp.CommandFacet
	sessions                 sessionapp.CommandFacet
	deviceRegistration       registrationapp.InternalRegisterer
	consents                 userrepo.ConsentRecordStore
	anonymousDevices         userrepo.AnonymousDeviceBindingStore
	federatedBindingTickets  credentialapp.FederatedPhoneBindingStore
	shardDirectory           *ShardDirectory
	carrierPhoneResolver     CarrierPhoneResolver
	otp                      OtpCodeStore
	authenticationChallenges *challengeapp.AuthenticationChallengeCommandFacade
	otpCodeSealer            OTPCodeSealer
	otpCodeGenerator         func() (string, error)
	externalClient           ExternalInteractionClient
	accessSigner             *rtauth.Signer
	accountSecurity          accountports.AccountSecurityReader
	nicknamePrefix           string
}

type AuthServiceOption func(*AuthService)

type OTPCodeSealer interface {
	Seal(secret otpseal.Secret, binding otpseal.Binding) (string, error)
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

// WithPersonaCommandPipeline installs the only Persona bootstrap write path:
// state/receipt/outbox first, followed by the durable public-profile projection.
func WithPersonaCommandPipeline(
	commands personaports.PersonaCommandStore,
	projector userrepo.PersonaProfileProjector,
) AuthServiceOption {
	return func(s *AuthService) {
		s.personaCommands = commands
		s.personaProfileProjector = projector
	}
}

// WithAccountSecurityReader 注入 UserAccount 的权威状态与安全代次 Reader。
// 认证、refresh 与已认证账号请求都必须对 Reader 故障 fail-closed。
func WithAccountSecurityReader(
	reader accountports.AccountSecurityReader,
) AuthServiceOption {
	return func(s *AuthService) {
		s.accountSecurity = reader
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

func WithFederatedPhoneBindingTickets(
	store credentialapp.FederatedPhoneBindingStore,
) AuthServiceOption {
	return func(s *AuthService) {
		if store != nil {
			s.federatedBindingTickets = store
		}
	}
}

func WithCarrierPhoneResolver(resolver CarrierPhoneResolver) AuthServiceOption {
	return func(s *AuthService) {
		if resolver != nil {
			s.carrierPhoneResolver = resolver
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

// WithAccessTokenSigner 注入 access token 签发器；注入后 accessToken 为短期 JWT，
// 可被各服务/网关本地验签。未注入时回退到不透明随机串（过渡期回退）。
func WithAccessTokenSigner(signer *rtauth.Signer) AuthServiceOption {
	return func(s *AuthService) {
		s.accessSigner = signer
	}
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
// It creates a new OwnerAccount + default Persona if not found.
func (s *AuthService) LoginWithCredential(ctx context.Context, credType, credKey, displayLabel string) (*sessionapp.AuthSessionGrant, error) {
	return s.LoginWithCredentialOnDevice(ctx, credType, credKey, displayLabel, "")
}

// LoginWithCredentialOnDevice 同 LoginWithCredential，并把 deviceId 绑定进
// 新签发的 AccountSession（aggregate 规则要求 session 绑定设备）。
func (s *AuthService) LoginWithCredentialOnDevice(
	ctx context.Context,
	credType, credKey, displayLabel, deviceID string,
) (_ *sessionapp.AuthSessionGrant, err error) {
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
		return nil, accountgenerated.AppErrorFromInternalError(fmt.Sprintf("credential lookup: %v", err))
	}

	var ownerID string
	if found {
		state := existing.State()
		ownerID = state.OwnerID
		_ = s.credentials.MarkUsed(ctx, state.ID, time.Now().UTC())
	} else {
		// New user: create OwnerAccount + default Persona
		ownerID, err = s.createOwnerAccount(ctx, credType, credKey, displayLabel)
		if err != nil {
			return nil, accountgenerated.AppErrorFromInternalError(fmt.Sprintf("create owner: %v", err))
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
	phone := ""
	if strings.TrimSpace(credType) == credentialPhone && strings.TrimSpace(profile.Phone) == "" {
		phone = credKey
	}
	return s.profiles.PromoteRegistration(ctx, userrepo.RegistrationPromotion{
		UserID: ownerID,
		Phone:  phone,
	})
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
		return credentialapp.CommandResult{}, accountgenerated.AppErrorFromInternalError(
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
	identityOrigin, originCode := identityOriginForCredentialType(credType)
	return s.createOwnerAccountWithIdentity(
		ctx,
		credentialmodel.CredentialType(credType),
		credKey,
		displayLabel,
		identityOrigin,
		originCode,
	)
}

func (s *AuthService) createOwnerAccountForFederatedIdentity(
	ctx context.Context,
	identity VerifiedFederatedIdentity,
) (string, error) {
	return s.createOwnerAccount(
		ctx,
		string(identity.CredentialType),
		identity.CredentialKey,
		identity.DisplayName,
	)
}

func (s *AuthService) createOwnerAccountWithIdentity(
	ctx context.Context,
	credentialType credentialmodel.CredentialType,
	credentialKey string,
	displayLabel string,
	identityOrigin string,
	originCode string,
) (string, error) {
	identity, err := buildOwnerIdentityForOrigin(identityOrigin, originCode)
	if err != nil {
		return "", err
	}
	ownerID := identity.OwnerID
	if _, err := s.resolvePhysicalShard(ownerID); err != nil {
		return "", err
	}
	personaID, err := buildPersonaIdentity(identity.RootPrefix)
	if err != nil {
		return "", err
	}

	defaultNickname := s.buildDefaultNickname()
	account := userrepo.UserAccountCreate{
		UserID:                   ownerID,
		Phone:                    "",
		AccountState:             accountStateForCredentialType(string(credentialType)),
		IdentityOrigin:           identityOrigin,
		LogicalShard:             identity.LogicalShard,
		AnonymousRetentionPolicy: anonymousRetentionPolicyForCredentialType(string(credentialType)),
		PersonaCount:             1,
	}
	if credentialType == credentialmodel.CredentialType(credentialPhone) ||
		credentialType == credentialmodel.CredentialType(credentialCarrierPhone) {
		account.Phone = credentialKey
	}

	if err := s.profiles.CreateAccount(ctx, account); err != nil {
		return "", accountgenerated.AppErrorFromInternalError(fmt.Sprintf("create account: %v", err))
	}

	persona := &model.Persona{
		UserID:                   ownerID,
		PersonaID:                personaID,
		UserHandle:               systemUserHandleForPersona(personaID),
		DisplayName:              defaultNickname,
		NicknameCustomized:       false,
		IdentityTags:             []string{},
		IsPrimary:                true,
		IsActive:                 true,
		IsolationLevel:           defaultIsolationLevel,
		InheritsProfileFromOwner: false,
		OverriddenProfileFields:  encodeProfileFieldList(nil),
		LastProfileSyncSource:    "initial_inherit",
	}
	normalizePersonaPersistence(persona)
	if s.personaCommands == nil || s.personaProfileProjector == nil {
		return "", accountgenerated.AppErrorFromInternalError(
			"Persona bootstrap command pipeline unavailable",
		)
	}
	bootstrapDigest := sha256.Sum256([]byte(strings.Join([]string{
		ownerID,
		personaID,
		defaultNickname,
		identityOrigin,
	}, "\x00")))
	personaResult, err := s.personaCommands.CommitCreate(
		ctx,
		persona,
		personaports.PersonaCommandMeta{
			IdempotencyKey: "auth-persona-bootstrap:" + personaID,
			CommandDigest:  hex.EncodeToString(bootstrapDigest[:]),
		},
	)
	if err != nil {
		return "", accountgenerated.AppErrorFromInternalError(fmt.Sprintf("create Persona: %v", err))
	}
	if _, err := s.personaProfileProjector.Project(
		ctx,
		personaResult.PersonaID,
		personaResult.Version,
	); err != nil {
		return "", accountgenerated.AppErrorFromInternalError(fmt.Sprintf("project Persona profile: %v", err))
	}

	if s.credentialCommands == nil {
		return "", accountgenerated.AppErrorFromInternalError(
			"credential command facet unavailable",
		)
	}
	_, err = s.credentialCommands.BindVerifiedCredential(
		ctx,
		ownerID,
		credentialapp.BindCredentialCommand{
			CredentialType: credentialType,
			CredentialKey:  credentialKey,
			DisplayLabel:   displayLabel,
		},
	)
	if err != nil {
		return "", accountgenerated.AppErrorFromInternalError(fmt.Sprintf("create credential: %v", err))
	}

	return ownerID, nil
}

func (s *AuthService) resolvePhysicalShard(ownerID string) (string, error) {
	if s == nil || s.shardDirectory == nil {
		return "", nil
	}
	resolved, err := s.shardDirectory.ResolvePhysicalShardForOwnerID(ownerID)
	if err != nil {
		return "", accountgenerated.AppErrorFromInternalError(
			"resolve physical shard for canonical owner identity",
		)
	}
	physicalShard := strings.TrimSpace(resolved)
	if physicalShard == "" {
		return "", accountgenerated.AppErrorFromInternalError(
			"resolve physical shard for canonical owner identity",
		)
	}
	return physicalShard, nil
}

func buildActivePersonaEnvelope(activePersona *model.Persona) map[string]any {
	if activePersona == nil {
		return map[string]any{}
	}
	return map[string]any{
		"personaId": activePersona.PersonaID,
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
		return accountgenerated.AppErrorFromUserNotFound("account not found")
	}
	switch strings.TrimSpace(profile.AccountState) {
	case "suspended":
		return sessiongenerated.AppErrorFromAccountSuspended("account suspended")
	case "closed":
		// object.yaml lifecycle: closed 为注销终态（CloseAccount）。
		return sessiongenerated.AppErrorFromAccountDeleted("account closed")
	default:
		return nil
	}
}

func (s *AuthService) requireActiveAccountSecurity(
	ctx context.Context,
	accountID string,
) (accountports.AccountSecuritySnapshot, error) {
	if s.accountSecurity == nil {
		return accountports.AccountSecuritySnapshot{},
			accountgenerated.AppErrorFromInternalError(
				"UserAccount security reader is unavailable",
			)
	}
	snapshot, err := s.accountSecurity.ReadAccountSecurity(
		ctx,
		strings.TrimSpace(accountID),
	)
	if errors.Is(err, accountports.ErrAccountNotFound) {
		return accountports.AccountSecuritySnapshot{},
			accountgenerated.AppErrorFromUserNotFound("account not found")
	}
	if err != nil {
		return accountports.AccountSecuritySnapshot{},
			accountgenerated.AppErrorFromInternalError(
				"UserAccount security state is unavailable",
			)
	}
	switch strings.TrimSpace(snapshot.AccountState) {
	case "suspended":
		return accountports.AccountSecuritySnapshot{},
			sessiongenerated.AppErrorFromAccountSuspended("account suspended")
	case "closed":
		return accountports.AccountSecuritySnapshot{},
			sessiongenerated.AppErrorFromAccountDeleted("account closed")
	case "active", "anonymous":
		if snapshot.AuthEpoch > 0 {
			return snapshot, nil
		}
	}
	return accountports.AccountSecuritySnapshot{},
		accountgenerated.AppErrorFromInternalError(
			"UserAccount security state is invalid",
		)
}

// buildDefaultNickname 生成首次创建用户的系统默认昵称：
//
//	{prefix}_{YYMMDD}_{7位尾号}
//
// 前缀云侧可配置（默认「新同学」）；7 位尾号混合时/分/秒/毫秒与随机扰动，
// 在允许重复的前提下尽量降低近时刻碰撞概率。昵称唯一性仍由
// ownerID/personaId/userHandle 承担。
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

// PersonaService handles Persona lifecycle within an OwnerAccount.
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
	ErrPersonaNotFound      = personagenerated.AppErrorFromPersonaNotFound("persona not found")
	ErrPrimaryPersona       = personagenerated.AppErrorFromPrimaryPersonaGuard("primary persona cannot be retired")
	ErrLastPersona          = personagenerated.AppErrorFromLastPersona("cannot retire the last active persona")
	ErrActivePersonaAction  = personagenerated.AppErrorFromActivePersonaGuard("switch to another persona before retiring this one")
	ErrRetiredPersonaAction = personagenerated.AppErrorFromRetiredPersonaGuard("retired persona cannot accept new actions")
	ErrPersonaHandleTaken   = personagenerated.AppErrorFromPersonaHandleTaken("persona_handle_taken")
)

func findPersonaByPersonaID(ctx context.Context, personas userrepo.PersonaReader, personaID string) (*model.Persona, error) {
	return personas.FindByPersonaID(ctx, personaID)
}

package application

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	runtimegovernance "quwoquan_service/runtime/governance"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
	usertelemetry "quwoquan_service/services/user-service/internal/domain/user/telemetry"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
)

const (
	credentialPhone           = "phone"
	credentialWechat          = "wechat"
	credentialApple           = "apple"
	credentialAnonymousDevice = "anonymous_device"

	defaultIsolationLevel = "open"
	personaStatusActive   = "active"
	personaStatusRetired  = "retired"
	maxLoginFailCount     = 5
	lockDurationMinutes   = 30
)

// AuthService handles OwnerAccount authentication and credential binding.
type AuthService struct {
	profiles         userrepo.ProfileRepository
	personas         userrepo.PersonaRepository
	credentials      userrepo.CredentialRepository
	anonymousDevices userrepo.AnonymousDeviceBindingRepository
	pcache           *cache.ProfileCache
	shardDirectory   *ShardDirectory
}

func NewAuthService(
	profiles userrepo.ProfileRepository,
	personas userrepo.PersonaRepository,
	credentials userrepo.CredentialRepository,
	anonymousDevices userrepo.AnonymousDeviceBindingRepository,
	pcache *cache.ProfileCache,
	shardDirectory *ShardDirectory,
) *AuthService {
	return &AuthService{
		profiles:         profiles,
		personas:         personas,
		credentials:      credentials,
		anonymousDevices: anonymousDevices,
		pcache:           pcache,
		shardDirectory:   shardDirectory,
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
		return nil, fmt.Errorf("credential lookup: %w", err)
	}

	var ownerID string
	if existing != nil {
		ownerID = existing.OwnerID
		_ = s.credentials.UpdateLastUsed(ctx, existing.ID)
	} else {
		// New user: create OwnerAccount + default SubAccount
		ownerID, err = s.createOwnerAccount(ctx, credType, credKey, displayLabel)
		if err != nil {
			return nil, fmt.Errorf("create owner: %w", err)
		}
	}

	return s.issueLoginResult(ctx, ownerID, credType, credKey)
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
		return nil, fmt.Errorf("load profile: %w", err)
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
				return nil, fmt.Errorf("promote owner profile: %w", err)
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

	accessToken, err := generateToken()
	if err != nil {
		return nil, err
	}
	refreshToken, err := generateToken()
	if err != nil {
		return nil, err
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
	}, nil
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
		return nil, fmt.Errorf("installId is required")
	}
	if deviceFingerprintHash == "" {
		return nil, fmt.Errorf("deviceFingerprintHash is required")
	}

	var ownerID string
	if s.anonymousDevices != nil {
		binding, err := s.anonymousDevices.FindByDeviceFingerprintHash(ctx, deviceFingerprintHash)
		if err != nil {
			return nil, fmt.Errorf("lookup anonymous device binding: %w", err)
		}
		if binding != nil {
			ownerID = strings.TrimSpace(binding.OwnerID)
			_ = s.anonymousDevices.Touch(ctx, binding.ID, installIDHash, platform, appVersion)
		}
	}
	if ownerID == "" {
		existing, err := s.credentials.FindByTypeAndKey(ctx, credentialAnonymousDevice, deviceFingerprintHash)
		if err != nil {
			return nil, fmt.Errorf("anonymous credential lookup: %w", err)
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
			return nil, fmt.Errorf("create anonymous owner account: %w", err)
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
		return nil, fmt.Errorf("persist anonymous device binding: %w", err)
	}
	return s.issueLoginResult(ctx, ownerID, credentialAnonymousDevice, "")
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
		Nickname:                 defaultNickname(ownerID),
		Status:                   "active",
		AccountState:             accountStateForCredentialType(credType),
		IdentityOrigin:           identityOriginValue(credType),
		LogicalShard:             identity.LogicalShard,
		AnonymousRetentionPolicy: anonymousRetentionPolicyForCredentialType(credType),
		ProfileVersion:           1,
		SubAccountCount:          1,
	}
	if credType == credentialPhone {
		profile.Phone = credKey
	}

	if err := s.profiles.Create(ctx, profile); err != nil {
		return "", fmt.Errorf("create profile: %w", err)
	}

	persona := &model.Persona{
		UserID:                   ownerID,
		SubAccountID:             subAccountID,
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
		return "", fmt.Errorf("create persona: %w", err)
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
		return "", fmt.Errorf("create credential: %w", err)
	}

	return ownerID, nil
}

func (s *AuthService) resolvePhysicalShard(ownerID string) (string, error) {
	if s == nil || s.shardDirectory == nil {
		return "", nil
	}
	physicalShard := strings.TrimSpace(s.shardDirectory.ResolvePhysicalShardForOwnerID(ownerID))
	if physicalShard == "" {
		return "", fmt.Errorf("resolve physical shard for owner %s", ownerID)
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

func generateCredentialBindingID() string {
	id, err := generateIdentityEntropyBody()
	if err != nil {
		return "cb_fallback"
	}
	return "cb_" + id
}

func defaultNickname(ownerID string) string {
	trimmed := strings.TrimSpace(ownerID)
	if len(trimmed) > 10 {
		trimmed = trimmed[len(trimmed)-10:]
	}
	trimmed = strings.ReplaceAll(trimmed, "_", "")
	return "user_" + strings.ToLower(trimmed)
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
	ErrCredentialConflict = fmt.Errorf("credential already bound to another account")
	ErrLastCredential     = fmt.Errorf("cannot unbind the last credential")
)

func generateToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.URLEncoding.EncodeToString(b), nil
}

// SubAccountService handles SubAccount lifecycle within an OwnerAccount.
type SubAccountService struct {
	personas userrepo.PersonaRepository
	profiles userrepo.ProfileRepository
	pcache   *cache.ProfileCache
}

func NewSubAccountService(
	personas userrepo.PersonaRepository,
	profiles userrepo.ProfileRepository,
	pcache *cache.ProfileCache,
) *SubAccountService {
	return &SubAccountService{personas: personas, profiles: profiles, pcache: pcache}
}

// ListSubAccounts returns all sub-accounts for an owner.
func (s *SubAccountService) ListSubAccounts(ctx context.Context, ownerID string) ([]model.Persona, error) {
	return s.personas.FindByUserID(ctx, ownerID)
}

// CreateSubAccount creates a new isolated sub-account for the owner.
func (s *SubAccountService) CreateSubAccount(ctx context.Context, ownerID string, data map[string]any) (*model.Persona, error) {
	primary, _ := s.personas.FindActiveByUserID(ctx, ownerID)
	if primary == nil {
		personas, err := s.personas.FindByUserID(ctx, ownerID)
		if err == nil {
			primary = primaryPersona(personas)
		}
	}
	owner, _ := s.profiles.FindByID(ctx, ownerID)
	newSubAccountID, err := buildSubAccountIdentity(extractOwnerRootPrefix(ownerID))
	if err != nil {
		return nil, err
	}
	p := &model.Persona{
		UserID:                   ownerID,
		SubAccountID:             newSubAccountID,
		IsolationLevel:           defaultIsolationLevel,
		InheritsProfileFromOwner: true,
		OverriddenProfileFields:  encodeProfileFieldList(nil),
		LastProfileSyncSource:    "initial_inherit",
	}
	if v, ok := data["displayName"].(string); ok {
		p.DisplayName = strings.TrimSpace(v)
	}
	if v, ok := data["userHandle"].(string); ok {
		p.UserHandle = strings.TrimSpace(v)
	}
	if v, ok := data["avatarUrl"].(string); ok {
		p.AvatarURL = v
	}
	if v, ok := data["isolationLevel"].(string); ok {
		p.IsolationLevel = v
	}
	if v, ok := data["purposeHint"].(string); ok {
		p.PurposeHint = v
	}
	if primary != nil {
		p.Phone = primary.Phone
		p.Email = primary.Email
	} else if owner != nil {
		p.Phone = owner.Phone
	}
	now := time.Now().UTC()
	p.LastProfileSyncAt = &now
	normalizePersonaPersistence(p)
	if err := s.personas.Create(ctx, p); err != nil {
		if strings.Contains(err.Error(), "uq_personas_user_handle") {
			return nil, ErrPersonaHandleTaken
		}
		return nil, err
	}
	// Bump sub_account_count
	_ = s.pcache.Del(ctx, ownerID)
	return p, nil
}

func (s *SubAccountService) UpdatePersona(ctx context.Context, ownerID, personaID string, data map[string]any) (*model.Persona, error) {
	persona, err := s.personas.FindBySubAccountID(ctx, personaID)
	if err != nil {
		return nil, err
	}
	if persona == nil || persona.UserID != ownerID {
		return nil, ErrSubAccountNotFound
	}
	if isRetiredPersona(persona) {
		return nil, ErrRetiredPersonaAction
	}
	personas, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	changedFields := make([]string, 0, 5)
	if v, ok := data["displayName"].(string); ok {
		persona.DisplayName = strings.TrimSpace(v)
		changedFields = append(changedFields, "displayName")
	}
	if v, ok := data["userHandle"].(string); ok {
		persona.UserHandle = strings.TrimSpace(v)
		changedFields = append(changedFields, "userHandle")
	}
	if v, ok := data["phone"].(string); ok {
		persona.Phone = strings.TrimSpace(v)
		changedFields = append(changedFields, "phone")
	}
	if v, ok := data["email"].(string); ok {
		persona.Email = strings.TrimSpace(v)
		changedFields = append(changedFields, "email")
	}
	if v, ok := data["avatarUrl"].(string); ok {
		persona.AvatarURL = v
		changedFields = append(changedFields, "avatarUrl")
	}
	if v, ok := data["isolationLevel"].(string); ok {
		persona.IsolationLevel = v
	}
	if v, ok := data["purposeHint"].(string); ok {
		persona.PurposeHint = v
	}
	if len(changedFields) > 0 {
		persona.InheritsProfileFromOwner = false
		persona.OverriddenProfileFields = encodeProfileFieldList(
			mergeProfileFields(parseProfileFieldList(persona.OverriddenProfileFields), changedFields),
		)
		persona.LastProfileSyncSource = "sub_account_edit"
	}
	normalizePersonaPersistence(persona)
	if err := s.personas.Update(ctx, persona); err != nil {
		if strings.Contains(err.Error(), "uq_personas_user_handle") {
			return nil, ErrPersonaHandleTaken
		}
		return nil, err
	}
	fieldsMask := parseRequestedFieldsMask(data, changedFields)
	if shouldApplyPersonaSync(data) && len(fieldsMask) > 0 {
		if _, err := s.applyPersonaProfileSync(ctx, ownerID, persona, personas, data, fieldsMask); err != nil {
			return nil, err
		}
		usertelemetry.Collector().RecordSyncScopeSubmit()
	}
	_ = s.pcache.Del(ctx, ownerID)
	return persona, nil
}

// ActivateSubAccount atomically switches the active sub-account.
func (s *SubAccountService) ActivateSubAccount(ctx context.Context, ownerID, subAccountID string) error {
	startedAt := time.Now()
	defer func() {
		usertelemetry.RolloutCollector().RecordSwitchLatency(time.Since(startedAt))
	}()
	// Find the persona by subAccountID
	subs, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return err
	}
	var target *model.Persona
	for i := range subs {
		if subs[i].SubAccountID == subAccountID {
			target = &subs[i]
			break
		}
	}
	if target == nil {
		return ErrSubAccountNotFound
	}
	if isRetiredPersona(target) {
		return ErrRetiredPersonaAction
	}
	if err := s.personas.DeactivateAll(ctx, ownerID); err != nil {
		return err
	}
	if err := s.personas.ActivateOne(ctx, target.SubAccountID); err != nil {
		return err
	}
	now := time.Now().UTC()
	target.IsActive = true
	target.LastActivatedAt = &now
	normalizePersonaPersistence(target)
	if err := s.personas.Update(ctx, target); err != nil {
		return err
	}
	_ = s.pcache.Del(ctx, ownerID)
	return nil
}

// DeleteSubAccount only deletes truly empty personas.
func (s *SubAccountService) DeleteSubAccount(ctx context.Context, ownerID, subAccountID string) error {
	subs, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return err
	}
	var target *model.Persona
	for i := range subs {
		if subs[i].SubAccountID == subAccountID {
			target = &subs[i]
			break
		}
	}
	if target == nil {
		return ErrSubAccountNotFound
	}
	if target.IsPrimary {
		return ErrPrimarySubAccount
	}
	if isRetiredPersona(target) {
		return ErrRetiredPersonaAction
	}
	if target.IsActive {
		return ErrActiveSubAccountAction
	}
	if activePersonaCount(subs) <= 1 {
		return ErrLastSubAccount
	}
	hasHistory, err := s.personas.HasAttributedHistory(ctx, target.SubAccountID)
	if err != nil {
		return err
	}
	if hasHistory {
		return ErrSubAccountRetireRequired
	}
	if err := s.personas.Delete(ctx, target.SubAccountID); err != nil {
		return err
	}
	_ = s.pcache.Del(ctx, ownerID)
	return nil
}

func (s *SubAccountService) DeleteEmptyPersona(ctx context.Context, ownerID, personaID string) error {
	return s.DeleteSubAccount(ctx, ownerID, personaID)
}

func (s *SubAccountService) ApplyPersonaProfileSync(ctx context.Context, ownerID, personaID string, data map[string]any) (map[string]any, error) {
	personas, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	source := findPersonaBySubAccount(personas, personaID)
	if source == nil {
		return nil, ErrSubAccountNotFound
	}
	fieldsMask := parseRequestedFieldsMask(data, nil)
	applied, err := s.applyPersonaProfileSync(ctx, ownerID, source, personas, data, fieldsMask)
	if err != nil {
		return nil, err
	}
	if len(fieldsMask) > 0 {
		usertelemetry.Collector().RecordSyncScopeSubmit()
	}
	return map[string]any{
		"status":       "ok",
		"appliedCount": applied,
		"fieldsMask":   fieldsMask,
	}, nil
}

func (s *SubAccountService) GetActivePersonaContextView(ctx context.Context, ownerID string) (map[string]any, error) {
	owner, err := s.profiles.FindByID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	persona, err := s.personas.FindActiveByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	if owner == nil {
		return map[string]any{}, nil
	}
	view := buildSubAccountProfileView(owner, persona)
	return map[string]any{
		"ownerUserId":            ownerID,
		"subAccountId":           view["subAccountId"],
		"displayName":            view["displayName"],
		"avatarUrl":              view["avatarUrl"],
		"subjectType":            "persona",
		"isPrimary":              persona != nil && persona.IsPrimary,
		"personaContextVersion":  "1",
		"personaSnapshotVersion": 1,
		"sourceSurfaceId":        "",
		"explicitOverride":       false,
		"contextVersion":         1,
		"isolationLevel":         defaultString(personaIsolationLevel(persona), defaultIsolationLevel),
		"profileVisibility":      "public",
		"switchedAt":             time.Now().UTC().Format(time.RFC3339),
	}, nil
}

func (s *SubAccountService) GetPersonaManagementSummary(ctx context.Context, ownerID string) (map[string]any, error) {
	personas, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	items := make([]map[string]any, 0, len(personas))
	activeID := ""
	primaryID := ""
	for i := range personas {
		hasHistory, err := s.personas.HasAttributedHistory(ctx, personas[i].SubAccountID)
		if err != nil {
			return nil, err
		}
		item := BuildPersonaManagementItemWithHistory(personas[i], hasHistory)
		items = append(items, item)
		if personas[i].IsActive && !isRetiredPersona(&personas[i]) {
			activeID = personas[i].SubAccountID
		}
		if personas[i].IsPrimary {
			primaryID = personas[i].SubAccountID
		}
	}
	activeContext, err := s.GetActivePersonaContextView(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"items": items,
		"quota": map[string]any{
			"ownerUserId":             ownerID,
			"totalCount":              len(personas),
			"quotaLimit":              5,
			"remainingCount":          remainingPersonaSlots(len(personas), 5),
			"activeProfileSubjectId":  activeID,
			"primaryProfileSubjectId": primaryID,
			"usedSubAccounts":         len(personas),
			"maxSubAccounts":          5,
		},
		"activeContext": activeContext,
	}, nil
}

func (s *SubAccountService) GetPersonaLifecycleGuard(ctx context.Context, ownerID, personaID string) (map[string]any, error) {
	personas, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	var target *model.Persona
	for i := range personas {
		if personas[i].SubAccountID == personaID {
			target = &personas[i]
			break
		}
	}
	if target == nil {
		return nil, ErrSubAccountNotFound
	}
	hasHistory, err := s.personas.HasAttributedHistory(ctx, target.SubAccountID)
	if err != nil {
		return nil, err
	}
	return buildPersonaLifecycleGuardView(target, activePersonaCount(personas), hasHistory), nil
}

func (s *SubAccountService) RetirePersona(ctx context.Context, ownerID, personaID string) (map[string]any, error) {
	personas, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	target := findPersonaBySubAccount(personas, personaID)
	if target == nil {
		return nil, ErrSubAccountNotFound
	}
	if target.IsPrimary {
		return nil, ErrPrimarySubAccount
	}
	if isRetiredPersona(target) {
		return nil, ErrRetiredPersonaAction
	}
	if target.IsActive {
		return nil, ErrActiveSubAccountAction
	}
	if activePersonaCount(personas) <= 1 {
		return nil, ErrLastSubAccount
	}
	hasHistory, err := s.personas.HasAttributedHistory(ctx, target.SubAccountID)
	if err != nil {
		return nil, err
	}
	if !hasHistory {
		return nil, ErrDeleteEmptyPersonaOnly
	}
	now := time.Now().UTC()
	target.Status = personaStatusRetired
	target.IsActive = false
	target.RetiredAt = &now
	normalizePersonaPersistence(target)
	if err := s.personas.Update(ctx, target); err != nil {
		return nil, err
	}
	_ = s.pcache.Del(ctx, ownerID)
	return map[string]any{
		"requestedAction":      "retire",
		"allowed":              true,
		"reason":               "allowed",
		"hasAttributedHistory": true,
		"requiresSuccessor":    false,
		"subAccountId":         target.SubAccountID,
		"canDelete":            false,
		"canRetire":            false,
		"requiredAction":       "",
		"reasonCode":           "allowed",
		"message":              "分身已退役，记录归因已保留",
	}, nil
}

// GetSubAccountProfile returns the raw persona entity for compatibility callers.
func (s *SubAccountService) GetSubAccountProfile(ctx context.Context, subAccountID string) (*model.Persona, error) {
	return s.personas.FindBySubAccountID(ctx, subAccountID)
}

// GetSubAccountProfileView projects a sub-account to the public profile view shape.
func (s *SubAccountService) GetSubAccountProfileView(ctx context.Context, handleOrPersonaID string) (map[string]any, error) {
	startedAt := time.Now()
	defer func() {
		usertelemetry.Collector().RecordPublicRead(time.Since(startedAt))
	}()

	var (
		persona *model.Persona
		err     error
	)
	if runtimegovernance.PersonaPublicProfileEnabled() {
		persona, err = s.resolvePublicPersona(ctx, handleOrPersonaID)
	} else {
		persona, err = s.personas.FindBySubAccountID(ctx, strings.TrimSpace(handleOrPersonaID))
	}
	if err != nil {
		return nil, err
	}
	if persona == nil {
		usertelemetry.Collector().RecordVisibilityNotFound()
		return nil, nil
	}
	if !canExposePublicPersona(persona) {
		usertelemetry.Collector().RecordVisibilityNotFound()
		return nil, nil
	}
	owner, err := s.profiles.FindByID(ctx, persona.UserID)
	if err != nil {
		return nil, err
	}
	view := buildPublicSubAccountProfileView(owner, persona)
	if hasPublicLeakage(view) {
		usertelemetry.RolloutCollector().RecordPublicLeakage()
		delete(view, "ownerUserId")
		delete(view, "ownerAccountId")
		delete(view, "ownerId")
	}
	return view, nil
}

// GetMeProfileView projects the viewer's active owner/sub-account identity.
func (s *SubAccountService) GetMeProfileView(ctx context.Context, userID string) (map[string]any, error) {
	owner, err := s.profiles.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if owner == nil {
		return nil, nil
	}
	persona, err := s.personas.FindActiveByUserID(ctx, userID)
	if err != nil {
		return nil, err
	}
	return buildSubAccountProfileView(owner, persona), nil
}

func (s *SubAccountService) resolvePublicPersona(ctx context.Context, handleOrPersonaID string) (*model.Persona, error) {
	handleOrPersonaID = strings.TrimSpace(handleOrPersonaID)
	if handleOrPersonaID == "" {
		return nil, nil
	}
	persona, err := s.personas.FindByUserHandle(ctx, handleOrPersonaID)
	if err != nil {
		return nil, err
	}
	if persona != nil {
		return persona, nil
	}
	return s.personas.FindBySubAccountID(ctx, handleOrPersonaID)
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
	isolationLevel := defaultIsolationLevel
	overriddenFields := []string{}
	updatedAt := owner.UpdatedAt

	if persona != nil {
		subjectType = "persona"
		subAccountID = persona.SubAccountID
		userHandle = resolvedPersonaUserHandle(persona)
		if persona.DisplayName != "" {
			displayName = persona.DisplayName
			overriddenFields = append(overriddenFields, "displayName")
		}
		if persona.UserHandle != "" {
			overriddenFields = append(overriddenFields, "userHandle")
		}
		if persona.AvatarURL != "" {
			avatarURL = persona.AvatarURL
			overriddenFields = append(overriddenFields, "avatarUrl")
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
		"ownerUserId":       owner.UserID,
		"subjectType":       subjectType,
		"subAccountId":      subAccountID,
		"userId":            defaultString(subAccountID, owner.UserID),
		"userHandle":        userHandle,
		"username":          userHandle,
		"displayName":       displayName,
		"nickname":          displayName,
		"avatarUrl":         avatarURL,
		"backgroundUrl":     "",
		"bio":               owner.Bio,
		"followerCount":     owner.FollowerCount,
		"followingCount":    owner.FollowingCount,
		"postCount":         owner.PostCount,
		"circleCount":       owner.CircleCount,
		"likeCount":         owner.LikeCount,
		"isolationLevel":    isolationLevel,
		"profileVisibility": profileVisibilityFromIsolation(isolationLevel),
		"inheritsFromOwner": persona != nil && persona.InheritsProfileFromOwner,
		"overriddenFields":  overriddenFields,
		"updatedAt":         updatedAt.Format(time.RFC3339),
	}
}

func BuildPersonaManagementItem(persona model.Persona) map[string]any {
	return BuildPersonaManagementItemWithHistory(persona, false)
}

func BuildPersonaManagementItemWithHistory(persona model.Persona, hasAttributedHistory bool) map[string]any {
	var lastProfileSyncAt any
	if persona.LastProfileSyncAt != nil {
		lastProfileSyncAt = persona.LastProfileSyncAt.Format(time.RFC3339)
	}
	var lastActivatedAt any
	if persona.LastActivatedAt != nil {
		lastActivatedAt = persona.LastActivatedAt.Format(time.RFC3339)
	}
	var retiredAt any
	if persona.RetiredAt != nil {
		retiredAt = persona.RetiredAt.Format(time.RFC3339)
	}
	return map[string]any{
		"subAccountId":             persona.SubAccountID,
		"displayName":              persona.DisplayName,
		"userHandle":               resolvedPersonaUserHandle(&persona),
		"phone":                    persona.Phone,
		"email":                    persona.Email,
		"avatarUrl":                persona.AvatarURL,
		"backgroundUrl":            "",
		"bio":                      "",
		"isolationLevel":           defaultString(persona.IsolationLevel, defaultIsolationLevel),
		"profileVisibility":        profileVisibilityFromIsolation(defaultString(persona.IsolationLevel, defaultIsolationLevel)),
		"isPrimary":                persona.IsPrimary,
		"isActive":                 persona.IsActive && !isRetiredPersona(&persona),
		"status":                   personaStatus(persona),
		"retiredAt":                retiredAt,
		"inheritsProfileFromOwner": persona.InheritsProfileFromOwner,
		"inheritsFromOwner":        persona.InheritsProfileFromOwner,
		"overriddenProfileFields":  parseProfileFieldList(persona.OverriddenProfileFields),
		"lastProfileSyncAt":        lastProfileSyncAt,
		"lastProfileSyncSource":    persona.LastProfileSyncSource,
		"lastActivatedAt":          lastActivatedAt,
		"hasAttributedHistory":     hasAttributedHistory,
		"hasPublishedContent":      false,
		"subjectType":              "persona",
		"updatedAt":                persona.UpdatedAt.Format(time.RFC3339),
	}
}

func remainingPersonaSlots(used, limit int) int {
	remaining := limit - used
	if remaining < 0 {
		return 0
	}
	return remaining
}

func personaIsolationLevel(persona *model.Persona) string {
	if persona == nil {
		return defaultIsolationLevel
	}
	return defaultString(persona.IsolationLevel, defaultIsolationLevel)
}

func resolvedPersonaUserHandle(persona *model.Persona) string {
	if persona == nil {
		return ""
	}
	handle := strings.TrimSpace(persona.UserHandle)
	if handle != "" {
		return handle
	}
	return strings.TrimSpace(persona.SubAccountID)
}

func profileVisibilityFromIsolation(isolationLevel string) string {
	switch strings.TrimSpace(isolationLevel) {
	case "strict":
		return "private"
	case "semi":
		return "friends"
	default:
		return "public"
	}
}

func canExposePublicPersona(persona *model.Persona) bool {
	if persona == nil {
		return false
	}
	if isRetiredPersona(persona) {
		return false
	}
	return personaIsolationLevel(persona) != "strict"
}

func lifecycleGuardMessage(reason string) string {
	switch reason {
	case "blocked_primary_persona":
		return "主分身不可删除或退役"
	case "blocked_last_persona":
		return "至少需要保留一个分身"
	case "blocked_active_persona":
		return "请先切换到其他分身后再执行该操作"
	case "blocked_retired_persona":
		return "该分身已退役，记录归因已保留，不可删除或再次退役"
	case "retire_instead_of_delete":
		return "该分身已有记录归因，请使用退役而不是删除"
	default:
		return ""
	}
}

func shouldApplyPersonaSync(data map[string]any) bool {
	scope, _ := data["applyScope"].(string)
	if scope == "" || scope == "current_subject_only" {
		return false
	}
	return true
}

func parseRequestedFieldsMask(data map[string]any, fallback []string) []string {
	raw, ok := data["fieldsMask"]
	if !ok {
		return normalizeProfileFields(fallback)
	}
	list, ok := raw.([]any)
	if !ok {
		return normalizeProfileFields(fallback)
	}
	fields := make([]string, 0, len(list))
	for _, item := range list {
		if text := strings.TrimSpace(fmt.Sprint(item)); text != "" {
			fields = append(fields, text)
		}
	}
	return normalizeProfileFields(fields)
}

func normalizeProfileFields(fields []string) []string {
	seen := make(map[string]struct{})
	result := make([]string, 0, len(fields))
	for _, field := range fields {
		switch strings.TrimSpace(field) {
		case "displayName", "userHandle", "phone", "email", "avatarUrl":
			if _, exists := seen[field]; exists {
				continue
			}
			seen[field] = struct{}{}
			result = append(result, field)
		}
	}
	return result
}

func mergeProfileFields(existing, next []string) []string {
	merged := append([]string{}, existing...)
	merged = append(merged, next...)
	return normalizeProfileFields(merged)
}

func removeProfileFields(existing, toRemove []string) []string {
	removeSet := make(map[string]struct{}, len(toRemove))
	for _, field := range toRemove {
		removeSet[field] = struct{}{}
	}
	result := make([]string, 0, len(existing))
	for _, field := range existing {
		if _, shouldRemove := removeSet[field]; shouldRemove {
			continue
		}
		result = append(result, field)
	}
	return normalizeProfileFields(result)
}

func parseProfileFieldList(raw string) []string {
	text := strings.TrimSpace(raw)
	text = strings.TrimPrefix(text, "{")
	text = strings.TrimSuffix(text, "}")
	if text == "" {
		return nil
	}
	parts := strings.Split(text, ",")
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.Trim(strings.TrimSpace(part), `"`)
		if part != "" {
			result = append(result, part)
		}
	}
	return normalizeProfileFields(result)
}

func encodeProfileFieldList(fields []string) string {
	normalized := normalizeProfileFields(fields)
	if len(normalized) == 0 {
		return "{}"
	}
	return "{" + strings.Join(normalized, ",") + "}"
}

func normalizePersonaPersistence(persona *model.Persona) {
	if persona == nil {
		return
	}
	if strings.TrimSpace(persona.OverriddenProfileFields) == "" {
		persona.OverriddenProfileFields = "{}"
	}
	if strings.TrimSpace(persona.Status) == "" {
		persona.Status = personaStatusActive
	}
	if persona.Status == personaStatusRetired {
		persona.IsActive = false
	}
}

func personaStatus(persona model.Persona) string {
	if strings.TrimSpace(persona.Status) == "" {
		return personaStatusActive
	}
	return strings.TrimSpace(persona.Status)
}

func isRetiredPersona(persona *model.Persona) bool {
	if persona == nil {
		return false
	}
	return personaStatus(*persona) == personaStatusRetired
}

func activePersonaCount(personas []model.Persona) int {
	count := 0
	for i := range personas {
		if !isRetiredPersona(&personas[i]) {
			count++
		}
	}
	return count
}

func buildPersonaLifecycleGuardView(target *model.Persona, activeCount int, hasAttributedHistory bool) map[string]any {
	reason := "allowed"
	canDelete := true
	canRetire := false
	requiredAction := ""
	requiresSuccessor := false
	if target.IsPrimary {
		reason = "blocked_primary_persona"
		canDelete = false
	} else if isRetiredPersona(target) {
		reason = "blocked_retired_persona"
		canDelete = false
	} else if activeCount <= 1 {
		reason = "blocked_last_persona"
		canDelete = false
	} else if target.IsActive {
		reason = "blocked_active_persona"
		canDelete = false
		requiresSuccessor = true
	} else if hasAttributedHistory {
		reason = "retire_instead_of_delete"
		canDelete = false
		canRetire = true
		requiredAction = "retire"
	}
	return map[string]any{
		"requestedAction":      "delete",
		"allowed":              canDelete,
		"reason":               reason,
		"hasAttributedHistory": hasAttributedHistory,
		"requiresSuccessor":    requiresSuccessor,
		"subAccountId":         target.SubAccountID,
		"canDelete":            canDelete,
		"canRetire":            canRetire,
		"requiredAction":       requiredAction,
		"reasonCode":           reason,
		"message":              lifecycleGuardMessage(reason),
	}
}

func primaryPersona(personas []model.Persona) *model.Persona {
	for i := range personas {
		if personas[i].IsPrimary {
			return &personas[i]
		}
	}
	return nil
}

func findPersonaBySubAccount(personas []model.Persona, personaID string) *model.Persona {
	for i := range personas {
		if personas[i].SubAccountID == personaID {
			return &personas[i]
		}
	}
	return nil
}

func resolveSyncTargetPersonas(personas []model.Persona, sourcePersonaID, applyScope string, explicitTargetIDs []string) []*model.Persona {
	explicitSet := make(map[string]struct{}, len(explicitTargetIDs))
	for _, id := range explicitTargetIDs {
		id = strings.TrimSpace(id)
		if id != "" {
			explicitSet[id] = struct{}{}
		}
	}
	targets := make([]*model.Persona, 0, len(personas))
	for i := range personas {
		persona := &personas[i]
		if persona.SubAccountID == sourcePersonaID || isRetiredPersona(persona) {
			continue
		}
		switch applyScope {
		case "all_sub_accounts":
			targets = append(targets, persona)
		case "selected_subjects":
			if _, ok := explicitSet[persona.SubAccountID]; ok {
				targets = append(targets, persona)
			}
		}
	}
	return targets
}

func extractSyncTargetIDs(data map[string]any) []string {
	raw, ok := data["syncTargetIds"]
	if !ok {
		return nil
	}
	list, ok := raw.([]any)
	if !ok {
		return nil
	}
	result := make([]string, 0, len(list))
	for _, item := range list {
		text := strings.TrimSpace(fmt.Sprint(item))
		if text != "" {
			result = append(result, text)
		}
	}
	return result
}

func applyFieldsFromSource(target *model.Persona, source *model.Persona, fields []string) {
	for _, field := range fields {
		switch field {
		case "displayName":
			target.DisplayName = source.DisplayName
		case "userHandle":
			target.UserHandle = source.UserHandle
		case "phone":
			target.Phone = source.Phone
		case "email":
			target.Email = source.Email
		case "avatarUrl":
			target.AvatarURL = source.AvatarURL
		}
	}
}

func (s *SubAccountService) applyPersonaProfileSync(ctx context.Context, ownerID string, source *model.Persona, personas []model.Persona, data map[string]any, fieldsMask []string) (int, error) {
	if source == nil {
		return 0, ErrSubAccountNotFound
	}
	if isRetiredPersona(source) {
		return 0, ErrRetiredPersonaAction
	}
	if len(fieldsMask) == 0 {
		return 0, nil
	}
	applyScope, _ := data["applyScope"].(string)
	targets := resolveSyncTargetPersonas(
		personas,
		source.SubAccountID,
		applyScope,
		extractSyncTargetIDs(data),
	)
	now := time.Now().UTC()
	applied := 0
	for _, target := range targets {
		applyFieldsFromSource(target, source, fieldsMask)
		target.OverriddenProfileFields = encodeProfileFieldList(
			removeProfileFields(parseProfileFieldList(target.OverriddenProfileFields), fieldsMask),
		)
		target.InheritsProfileFromOwner = source.IsPrimary && len(parseProfileFieldList(target.OverriddenProfileFields)) == 0
		target.LastProfileSyncAt = &now
		target.LastProfileSyncSource = "manual_sync"
		normalizePersonaPersistence(target)
		if err := s.personas.Update(ctx, target); err != nil {
			if strings.Contains(err.Error(), "uq_personas_user_handle") {
				return applied, ErrPersonaHandleTaken
			}
			return applied, err
		}
		applied++
	}
	_ = s.pcache.Del(ctx, ownerID)
	return applied, nil
}

func defaultString(value, fallback string) string {
	if value != "" {
		return value
	}
	return fallback
}

func hashInstallID(installID string) string {
	normalized := strings.TrimSpace(strings.ToLower(installID))
	if normalized == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(normalized))
	return hex.EncodeToString(sum[:])
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
	normalizedPlatform := strings.TrimSpace(platform)
	if normalizedPlatform == "" {
		normalizedPlatform = "unknown"
	}
	return s.anonymousDevices.Create(ctx, &model.AnonymousDeviceBinding{
		ID:                    bindingID,
		OwnerID:               strings.TrimSpace(ownerID),
		InstallIDHash:         strings.TrimSpace(installIDHash),
		DeviceFingerprintHash: strings.TrimSpace(deviceFingerprintHash),
		Platform:              normalizedPlatform,
		AppVersion:            strings.TrimSpace(appVersion),
		LastSeenAt:            time.Now().UTC(),
	})
}

var (
	ErrSubAccountNotFound       = fmt.Errorf("sub-account not found")
	ErrPrimarySubAccount        = fmt.Errorf("primary persona cannot be deleted or retired")
	ErrLastSubAccount           = fmt.Errorf("cannot retire or delete the last active persona")
	ErrActiveSubAccountAction   = fmt.Errorf("switch to another persona before deleting or retiring this one")
	ErrRetiredPersonaAction     = fmt.Errorf("retired persona cannot accept new actions")
	ErrDeleteEmptyPersonaOnly   = fmt.Errorf("empty persona should be deleted directly")
	ErrSubAccountRetireRequired = fmt.Errorf("persona has history and must be retired instead of deleted")
	ErrSubAccountStrictIso      = fmt.Errorf("user not found") // intentionally vague
	ErrPersonaHandleTaken       = fmt.Errorf("persona_handle_taken")
)

// PersonaRepository needs FindBySubAccountID – add it to the interface extension.
func findPersonaBySubAccountID(ctx context.Context, personas userrepo.PersonaRepository, subAccountID string) (*model.Persona, error) {
	return personas.FindBySubAccountID(ctx, subAccountID)
}

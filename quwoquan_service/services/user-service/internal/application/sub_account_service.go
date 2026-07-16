package application

import (
	"context"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/ports"
	usertelemetry "quwoquan_service/services/user-service/internal/domain/user/telemetry"
	"quwoquan_service/services/user-service/internal/generated"
)

// SubAccountService owns persona lifecycle and profile synchronization.
type SubAccountService struct {
	personas          PersonaStore
	personaHistory    userrepo.PersonaHistoryReader
	personaActivation userrepo.PersonaActivationStore
	profiles          userrepo.UserProfileStore
	pcache            ProfileCacheInvalidator
	creatorProfiles   userrepo.CreatorRuntimeProfileReader
}

type SubAccountServiceOption func(*SubAccountService)

func WithCreatorRuntimeProfiles(repository userrepo.CreatorRuntimeProfileReader) SubAccountServiceOption {
	return func(service *SubAccountService) {
		service.creatorProfiles = repository
	}
}

func NewSubAccountService(
	personas PersonaStore,
	personaHistory userrepo.PersonaHistoryReader,
	personaActivation userrepo.PersonaActivationStore,
	profiles userrepo.UserProfileStore,
	pcache ProfileCacheInvalidator,
	options ...SubAccountServiceOption,
) *SubAccountService {
	service := &SubAccountService{
		personas:          personas,
		personaHistory:    personaHistory,
		personaActivation: personaActivation,
		profiles:          profiles,
		pcache:            pcache,
	}
	for _, option := range options {
		if option != nil {
			option(service)
		}
	}
	return service
}

// ListSubAccounts returns all sub-accounts for an owner.
func (s *SubAccountService) ListSubAccounts(ctx context.Context, ownerID string) ([]model.Persona, error) {
	return s.personas.FindByUserID(ctx, ownerID)
}

// CreateSubAccount creates a new isolated sub-account for the owner.
func (s *SubAccountService) CreateSubAccount(ctx context.Context, ownerID string, data map[string]any) (*model.Persona, error) {
	if _, ok := data["userHandle"]; ok {
		return nil, generated.AppErrorFromSubAccountHandleReadonly("userHandle is system assigned")
	}
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
		UserHandle:               systemUserHandleForSubAccount(newSubAccountID),
		IsolationLevel:           defaultIsolationLevel,
		InheritsProfileFromOwner: true,
		OverriddenProfileFields:  encodeProfileFieldList(nil),
		LastProfileSyncSource:    "initial_inherit",
	}
	if v, ok := data["displayName"].(string); ok {
		p.DisplayName = strings.TrimSpace(v)
	}
	if v, ok := data["avatarUrl"].(string); ok {
		p.AvatarURL = strings.TrimSpace(v)
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
		if isPersonaHandleConflict(err) {
			return nil, ErrPersonaHandleTaken
		}
		return nil, err
	}
	// Bump sub_account_count
	_ = s.pcache.Del(ctx, ownerID)
	return p, nil
}

func (s *SubAccountService) UpdatePersona(ctx context.Context, ownerID, personaID string, data map[string]any) (*model.Persona, error) {
	if profileMutationRequestsUserHandle(data) {
		return nil, generated.AppErrorFromSubAccountHandleReadonly("userHandle is system assigned")
	}
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
	if v, ok := data["phone"].(string); ok {
		persona.Phone = strings.TrimSpace(v)
		changedFields = append(changedFields, "phone")
	}
	if v, ok := data["email"].(string); ok {
		persona.Email = strings.TrimSpace(v)
		changedFields = append(changedFields, "email")
	}
	if v, ok := data["avatarUrl"].(string); ok {
		nextAvatarURL := strings.TrimSpace(v)
		if nextAvatarURL != strings.TrimSpace(persona.AvatarURL) {
			persona.AvatarURL = nextAvatarURL
			if nextAvatarURL == "" {
				persona.AvatarVersion = 0
			} else {
				persona.AvatarVersion++
				if persona.AvatarVersion <= 0 {
					persona.AvatarVersion = 1
				}
			}
		}
		changedFields = append(changedFields, "avatarUrl")
	}
	if v, ok := data["backgroundUrl"].(string); ok {
		persona.BackgroundURL = strings.TrimSpace(v)
		changedFields = append(changedFields, "backgroundUrl")
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
		if isPersonaHandleConflict(err) {
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
	if err := s.personaActivation.SwitchActive(ctx, ownerID, target.SubAccountID); err != nil {
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
	hasHistory, err := s.personaHistory.HasAttributedHistory(ctx, target.SubAccountID)
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
		"avatarVersion":          view["avatarVersion"],
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
		hasHistory, err := s.personaHistory.HasAttributedHistory(ctx, personas[i].SubAccountID)
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
	hasHistory, err := s.personaHistory.HasAttributedHistory(ctx, target.SubAccountID)
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
	hasHistory, err := s.personaHistory.HasAttributedHistory(ctx, target.SubAccountID)
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

// GetSubAccountProfile returns the raw persona entity to in-context application
// services. Cross-context adapters must use the public typed view.
func (s *SubAccountService) GetSubAccountProfile(ctx context.Context, subAccountID string) (*model.Persona, error) {
	return s.personas.FindBySubAccountID(ctx, subAccountID)
}

// GetSubAccountProfileView projects a sub-account to the public profile view shape.
func (s *SubAccountService) GetSubAccountProfileView(ctx context.Context, handleOrPersonaID string) (map[string]any, error) {
	startedAt := time.Now()
	defer func() {
		usertelemetry.Collector().RecordPublicRead(time.Since(startedAt))
	}()

	persona, err := s.resolvePublicPersona(ctx, handleOrPersonaID)
	if err != nil {
		return nil, err
	}
	if persona == nil {
		if s.creatorProfiles != nil {
			creator, found, creatorErr := s.creatorProfiles.FindActiveByIdentity(ctx, handleOrPersonaID)
			if creatorErr != nil {
				return nil, generated.AppErrorFromInternalError(
					fmt.Sprintf("creator runtime profile read failed: %v", creatorErr),
				)
			}
			if found {
				return buildCreatorRuntimeProfileView(creator), nil
			}
		}
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

func BuildPersonaManagementItem(persona model.Persona) map[string]any {
	return BuildPersonaManagementItemWithHistory(persona, false)
}

func BuildPersonaManagementItemWithHistory(persona model.Persona, hasAttributedHistory bool) map[string]any {
	avatarVersion := resolvedPersonaAvatarVersion(&persona)
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
		"avatarUrl":                avatarURLWithVersion(persona.AvatarURL, avatarVersion),
		"avatarVersion":            avatarVersion,
		"backgroundUrl":            persona.BackgroundURL,
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
		case "displayName", "phone", "email", "avatarUrl":
			if _, exists := seen[field]; exists {
				continue
			}
			seen[field] = struct{}{}
			result = append(result, field)
		}
	}
	return result
}

func profileMutationRequestsUserHandle(data map[string]any) bool {
	if _, ok := data["userHandle"]; ok {
		return true
	}
	raw, ok := data["fieldsMask"]
	if !ok {
		return false
	}
	switch list := raw.(type) {
	case []any:
		for _, item := range list {
			if strings.TrimSpace(fmt.Sprint(item)) == "userHandle" {
				return true
			}
		}
	case []string:
		for _, item := range list {
			if strings.TrimSpace(item) == "userHandle" {
				return true
			}
		}
	}
	return false
}

func systemUserHandleForSubAccount(subAccountID string) string {
	normalized := strings.ToLower(strings.TrimSpace(subAccountID))
	var b strings.Builder
	for _, r := range normalized {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
		}
	}
	value := b.String()
	if value == "" {
		return "qwuser"
	}
	if len(value) > 24 {
		value = value[len(value)-24:]
	}
	return "qw" + value
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

// parsePgTextArray 解析 Postgres TEXT[] 扫描出的 "{a,b}" 字面量为字符串切片（不做字段白名单归一）。
func parsePgTextArray(raw string) []string {
	text := strings.TrimSpace(raw)
	text = strings.TrimPrefix(text, "{")
	text = strings.TrimSuffix(text, "}")
	if text == "" {
		return []string{}
	}
	parts := strings.Split(text, ",")
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.Trim(strings.TrimSpace(part), `"`)
		if part != "" {
			result = append(result, part)
		}
	}
	return result
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
	persona.AvatarURL = strings.TrimSpace(persona.AvatarURL)
	if strings.TrimSpace(persona.OverriddenProfileFields) == "" {
		persona.OverriddenProfileFields = "{}"
	}
	if strings.TrimSpace(persona.Status) == "" {
		persona.Status = personaStatusActive
	}
	if persona.AvatarURL == "" {
		persona.AvatarVersion = 0
	} else if persona.AvatarVersion <= 0 {
		persona.AvatarVersion = resolvedPersonaAvatarVersion(persona)
		if persona.AvatarVersion <= 0 {
			persona.AvatarVersion = 1
		}
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
		case "phone":
			target.Phone = source.Phone
		case "email":
			target.Email = source.Email
		case "avatarUrl":
			target.AvatarURL = source.AvatarURL
			target.AvatarVersion = source.AvatarVersion
		}
	}
}

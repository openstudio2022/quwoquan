package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/user-service/generated/account/user_account"
	personagenerated "quwoquan_service/services/user-service/generated/persona_management/persona"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	usertelemetry "quwoquan_service/services/user-service/internal/account/user_account/domain/user/telemetry"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

// PersonaService owns persona lifecycle and profile synchronization.
// 所有写命令经 PersonaCommandStore 以「服务端内部 CAS + receipt + outbox
// 同事务」提交；本服务只承载业务校验与字段合成。
type PersonaService struct {
	personas        PersonaStore
	commands        personaports.PersonaCommandStore
	projector       userrepo.PersonaProfileProjector
	profiles        userrepo.UserProfileStore
	pcache          ProfileCacheInvalidator
	creatorProfiles userrepo.CreatorRuntimeProfileReader
}

type PersonaServiceOption func(*PersonaService)

func WithCreatorRuntimeProfiles(repository userrepo.CreatorRuntimeProfileReader) PersonaServiceOption {
	return func(service *PersonaService) {
		service.creatorProfiles = repository
	}
}

func NewPersonaService(
	personas PersonaStore,
	commands personaports.PersonaCommandStore,
	projector userrepo.PersonaProfileProjector,
	profiles userrepo.UserProfileStore,
	pcache ProfileCacheInvalidator,
	options ...PersonaServiceOption,
) *PersonaService {
	service := &PersonaService{
		personas:  personas,
		commands:  commands,
		projector: projector,
		profiles:  profiles,
		pcache:    pcache,
	}
	for _, option := range options {
		if option != nil {
			option(service)
		}
	}
	return service
}

// ListPersonas returns all personas for an owner.
func (s *PersonaService) ListPersonas(ctx context.Context, ownerID string) ([]model.Persona, error) {
	return s.personas.FindByUserID(ctx, ownerID)
}

// CreatePersona creates a new isolated persona for the owner.
func (s *PersonaService) CreatePersona(
	ctx context.Context,
	ownerID string,
	command CreatePersonaCommand,
	meta PersonaCommandMeta,
) (*model.Persona, error) {
	rootPrefix, err := extractOwnerRootPrefix(ownerID)
	if err != nil {
		return nil, err
	}
	newPersonaID, err := buildPersonaIdentity(rootPrefix)
	if err != nil {
		return nil, err
	}
	p := &model.Persona{
		UserID:                   ownerID,
		PersonaID:                newPersonaID,
		UserHandle:               systemUserHandleForPersona(newPersonaID),
		DisplayName:              strings.TrimSpace(command.DisplayName),
		NicknameCustomized:       true,
		AvatarURL:                strings.TrimSpace(command.AvatarURL),
		IsolationLevel:           defaultIsolationLevel,
		PurposeHint:              strings.TrimSpace(command.PurposeHint),
		InheritsProfileFromOwner: true,
		OverriddenProfileFields:  encodeProfileFieldList(nil),
		LastProfileSyncSource:    "initial_inherit",
	}
	if isolationLevel := strings.TrimSpace(command.IsolationLevel); isolationLevel != "" {
		p.IsolationLevel = isolationLevel
	}
	now := time.Now().UTC()
	p.LastProfileSyncAt = &now
	normalizePersonaPersistence(p)
	result, err := s.commands.CommitCreate(ctx, p, meta)
	if err != nil {
		if errors.Is(err, personaports.ErrPersonaQuotaReached) {
			return nil, personagenerated.AppErrorFromPersonaQuotaReached(
				"owner reached the Persona quota limit",
			)
		}
		if isPersonaHandleConflict(err) {
			return nil, ErrPersonaHandleTaken
		}
		return nil, err
	}
	if _, err := s.projector.Project(ctx, result.PersonaID, result.Version); err != nil {
		return nil, err
	}
	_ = s.pcache.Del(ctx, ownerID)
	return p, nil
}

func (s *PersonaService) UpdatePersona(
	ctx context.Context,
	ownerID, personaID string,
	command UpdatePersonaCommand,
	meta PersonaCommandMeta,
) (*model.Persona, error) {
	if fieldsMaskRequestsUserHandle(command.Sync.FieldsMask) {
		return nil, personagenerated.AppErrorFromPersonaHandleReadonly("userHandle is system assigned")
	}
	persona, err := s.personas.FindByPersonaID(ctx, personaID)
	if err != nil {
		return nil, err
	}
	if persona == nil || persona.UserID != ownerID {
		return nil, ErrPersonaNotFound
	}
	if isRetiredPersona(persona) {
		return nil, ErrRetiredPersonaAction
	}
	personas, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	changedFields := make([]string, 0, 3)
	if command.DisplayName != nil {
		persona.DisplayName = strings.TrimSpace(*command.DisplayName)
		changedFields = append(changedFields, "displayName")
	}
	if command.AvatarURL != nil {
		nextAvatarURL := strings.TrimSpace(*command.AvatarURL)
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
	if command.BackgroundURL != nil {
		persona.BackgroundURL = strings.TrimSpace(*command.BackgroundURL)
		changedFields = append(changedFields, "backgroundUrl")
	}
	if command.IsolationLevel != nil {
		persona.IsolationLevel = *command.IsolationLevel
	}
	if command.PurposeHint != nil {
		persona.PurposeHint = *command.PurposeHint
	}
	if len(changedFields) > 0 {
		persona.InheritsProfileFromOwner = false
		persona.OverriddenProfileFields = encodeProfileFieldList(
			mergeProfileFields(parseProfileFieldList(persona.OverriddenProfileFields), changedFields),
		)
		persona.LastProfileSyncSource = "persona_edit"
	}
	normalizePersonaPersistence(persona)
	result, err := s.commands.CommitMutation(
		ctx,
		persona,
		personaports.PersonaUpdatedEvent,
		meta,
	)
	if err != nil {
		if isPersonaHandleConflict(err) {
			return nil, ErrPersonaHandleTaken
		}
		return nil, err
	}
	if _, err := s.projector.Project(ctx, result.PersonaID, result.Version); err != nil {
		return nil, err
	}
	fieldsMask := normalizeProfileFieldsWithFallback(command.Sync.FieldsMask, changedFields)
	if shouldApplyPersonaSyncScope(command.Sync) && len(fieldsMask) > 0 {
		if _, err := s.applyPersonaProfileSync(
			ctx, ownerID, persona, personas, command.Sync, fieldsMask, meta,
		); err != nil {
			return nil, err
		}
		usertelemetry.Collector().RecordSyncScopeSubmit()
	}
	_ = s.pcache.Del(ctx, ownerID)
	return persona, nil
}

// ActivatePersona atomically switches the active persona.
func (s *PersonaService) ActivatePersona(
	ctx context.Context,
	ownerID, personaID string,
	meta PersonaCommandMeta,
) error {
	startedAt := time.Now()
	defer func() {
		usertelemetry.RolloutCollector().RecordSwitchLatency(time.Since(startedAt))
	}()
	// Find the persona by personaID
	personas, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return err
	}
	var target *model.Persona
	for i := range personas {
		if personas[i].PersonaID == personaID {
			target = &personas[i]
			break
		}
	}
	if target == nil {
		return ErrPersonaNotFound
	}
	if isRetiredPersona(target) {
		return ErrRetiredPersonaAction
	}
	result, err := s.commands.CommitActivation(ctx, ownerID, target.PersonaID, meta)
	if err != nil {
		return err
	}
	if _, err := s.projector.Project(ctx, result.PersonaID, result.Version); err != nil {
		return err
	}
	_ = s.pcache.Del(ctx, ownerID)
	return nil
}

// ProfileSyncResult 是 ApplyPersonaProfileSync 的强类型回执。
type ProfileSyncResult struct {
	Status       string   `json:"status"`
	AppliedCount int      `json:"appliedCount"`
	FieldsMask   []string `json:"fieldsMask"`
}

func (s *PersonaService) ApplyPersonaProfileSync(
	ctx context.Context,
	ownerID, personaID string,
	options PersonaProfileSyncOptions,
	meta PersonaCommandMeta,
) (*ProfileSyncResult, error) {
	personas, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	source := findPersonaByPersona(personas, personaID)
	if source == nil {
		return nil, ErrPersonaNotFound
	}
	fieldsMask := normalizeProfileFields(options.FieldsMask)
	applied, err := s.applyPersonaProfileSync(
		ctx, ownerID, source, personas, options, fieldsMask, meta,
	)
	if err != nil {
		return nil, err
	}
	if len(fieldsMask) > 0 {
		usertelemetry.Collector().RecordSyncScopeSubmit()
	}
	return &ProfileSyncResult{
		Status:       "ok",
		AppliedCount: applied,
		FieldsMask:   fieldsMask,
	}, nil
}

func (s *PersonaService) GetActivePersonaContextView(ctx context.Context, ownerID string) (map[string]any, error) {
	owner, err := s.profiles.FindByID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	persona, err := s.personas.FindActiveByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	if owner == nil {
		return nil, generated.AppErrorFromInternalError(
			"active Persona owner profile unavailable",
		)
	}
	if persona == nil {
		return nil, generated.AppErrorFromInternalError(
			"active Persona unavailable",
		)
	}
	view := buildPersonaProfileView(owner, persona)
	personaVersion := 1
	if persona.Version > personaVersion {
		personaVersion = persona.Version
	}
	return map[string]any{
		"ownerUserId":            ownerID,
		"personaId":              view["personaId"],
		"displayName":            view["displayName"],
		"avatarUrl":              view["avatarUrl"],
		"avatarVersion":          resolvedPersonaAvatarVersion(persona),
		"subjectType":            "persona",
		"isPrimary":              persona.IsPrimary,
		"personaSnapshotVersion": personaVersion,
		"sourceSurfaceId":        "",
		"explicitOverride":       false,
		"contextVersion":         personaVersion,
		"isolationLevel":         defaultString(personaIsolationLevel(persona), defaultIsolationLevel),
		"profileVisibility":      personaProfileVisibility(persona),
		"switchedAt":             time.Now().UTC().Format(time.RFC3339),
	}, nil
}

func (s *PersonaService) GetPersonaManagementSummary(ctx context.Context, ownerID string) (map[string]any, error) {
	personas, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	items := make([]map[string]any, 0, len(personas))
	activeID := ""
	primaryID := ""
	for i := range personas {
		item := BuildPersonaManagementItem(personas[i])
		items = append(items, item)
		if personas[i].IsActive && !isRetiredPersona(&personas[i]) {
			activeID = personas[i].PersonaID
		}
		if personas[i].IsPrimary {
			primaryID = personas[i].PersonaID
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
			"usedPersonas":            len(personas),
			"maxPersonas":             5,
		},
		"activeContext": activeContext,
	}, nil
}

func (s *PersonaService) GetPersonaLifecycleGuard(ctx context.Context, ownerID, personaID string) (map[string]any, error) {
	personas, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	var target *model.Persona
	for i := range personas {
		if personas[i].PersonaID == personaID {
			target = &personas[i]
			break
		}
	}
	if target == nil {
		return nil, ErrPersonaNotFound
	}
	return buildPersonaLifecycleGuardView(
		target,
		activePersonaCount(personas),
	), nil
}

func (s *PersonaService) RetirePersona(
	ctx context.Context,
	ownerID, personaID string,
	meta PersonaCommandMeta,
) (map[string]any, error) {
	personas, err := s.personas.FindByUserID(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	target := findPersonaByPersona(personas, personaID)
	if target == nil {
		return nil, ErrPersonaNotFound
	}
	if target.IsPrimary {
		return nil, ErrPrimaryPersona
	}
	if isRetiredPersona(target) {
		return nil, ErrRetiredPersonaAction
	}
	if target.IsActive {
		return nil, ErrActivePersonaAction
	}
	if activePersonaCount(personas) <= 1 {
		return nil, ErrLastPersona
	}
	now := time.Now().UTC()
	target.Status = personaStatusRetired
	target.IsActive = false
	target.RetiredAt = &now
	normalizePersonaPersistence(target)
	result, err := s.commands.CommitMutation(
		ctx,
		target,
		personaports.PersonaRetiredEvent,
		meta,
	)
	if err != nil {
		return nil, err
	}
	if _, err := s.projector.Project(ctx, result.PersonaID, result.Version); err != nil {
		return nil, err
	}
	_ = s.pcache.Del(ctx, ownerID)
	return map[string]any{
		"personaId":         target.PersonaID,
		"requestedAction":   "retire",
		"allowed":           true,
		"reason":            "allowed",
		"requiresSuccessor": false,
	}, nil
}

// GetPersonaProfile returns the raw persona entity to in-context application
// services. Cross-context adapters must use the public typed view.
func (s *PersonaService) GetPersonaProfile(ctx context.Context, personaID string) (*model.Persona, error) {
	return s.personas.FindByPersonaID(ctx, personaID)
}

// GetPersonaProfileView projects a persona to the public profile view shape.
func (s *PersonaService) GetPersonaProfileView(ctx context.Context, handleOrPersonaID string) (map[string]any, error) {
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
			creator, found, creatorErr := s.creatorProfiles.FindActiveByPublicIdentity(ctx, handleOrPersonaID)
			if creatorErr != nil {
				return nil, generated.AppErrorFromInternalError(
					fmt.Sprintf("creator runtime profile read failed: %v", creatorErr),
				)
			}
			if found {
				return BuildCreatorRuntimeProfileView(creator), nil
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
	view := buildPublicPersonaProfileView(owner, persona)
	if hasPublicLeakage(view) {
		usertelemetry.RolloutCollector().RecordPublicLeakage()
		delete(view, "ownerUserId")
		delete(view, "ownerAccountId")
		delete(view, "ownerId")
	}
	return view, nil
}

// GetMeProfileView projects the viewer's active owner/persona identity.
func (s *PersonaService) GetMeProfileView(ctx context.Context, userID string) (map[string]any, error) {
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
	return buildPersonaProfileView(owner, persona), nil
}

func (s *PersonaService) resolvePublicPersona(ctx context.Context, handleOrPersonaID string) (*model.Persona, error) {
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
	return s.personas.FindByPersonaID(ctx, handleOrPersonaID)
}

func BuildPersonaManagementItem(persona model.Persona) map[string]any {
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
		"personaId":                persona.PersonaID,
		"displayName":              persona.DisplayName,
		"userHandle":               resolvedPersonaUserHandle(&persona),
		"avatarUrl":                avatarURLWithVersion(persona.AvatarURL, avatarVersion),
		"avatarVersion":            avatarVersion,
		"backgroundUrl":            persona.BackgroundURL,
		"bio":                      persona.Bio,
		"isolationLevel":           defaultString(persona.IsolationLevel, defaultIsolationLevel),
		"profileVisibility":        personaProfileVisibility(&persona),
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
	return strings.TrimSpace(persona.PersonaID)
}

func personaProfileVisibility(persona *model.Persona) string {
	if persona != nil && persona.IsPrivate {
		return "private"
	}
	return "public"
}

func canExposePublicPersona(persona *model.Persona) bool {
	if persona == nil {
		return false
	}
	if isRetiredPersona(persona) {
		return false
	}
	return !persona.IsPrivate && personaIsolationLevel(persona) != "strict"
}

func normalizeProfileFieldsWithFallback(fields, fallback []string) []string {
	if len(fields) == 0 {
		return normalizeProfileFields(fallback)
	}
	return normalizeProfileFields(fields)
}

func normalizeProfileFields(fields []string) []string {
	seen := make(map[string]struct{})
	result := make([]string, 0, len(fields))
	for _, field := range fields {
		switch strings.TrimSpace(field) {
		case "displayName", "avatarUrl":
			if _, exists := seen[field]; exists {
				continue
			}
			seen[field] = struct{}{}
			result = append(result, field)
		}
	}
	return result
}

func fieldsMaskRequestsUserHandle(fieldsMask []string) bool {
	for _, item := range fieldsMask {
		if strings.TrimSpace(item) == "userHandle" {
			return true
		}
	}
	return false
}

func systemUserHandleForPersona(personaID string) string {
	normalized := strings.ToLower(strings.TrimSpace(personaID))
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

func parseProfileFieldList(fields []string) []string {
	return normalizeProfileFields(fields)
}

func encodeProfileFieldList(fields []string) []string {
	return normalizeProfileFields(fields)
}

func normalizePersonaPersistence(persona *model.Persona) {
	if persona == nil {
		return
	}
	persona.AvatarURL = strings.TrimSpace(persona.AvatarURL)
	if persona.IdentityTags == nil {
		persona.IdentityTags = []string{}
	}
	persona.OverriddenProfileFields = normalizeProfileFields(
		persona.OverriddenProfileFields,
	)
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

func buildPersonaLifecycleGuardView(target *model.Persona, activeCount int) map[string]any {
	blockedReason := "allowed"
	allowed := true
	requiresSuccessor := false
	if target.IsPrimary {
		blockedReason = "blocked_primary_persona"
		allowed = false
	} else if isRetiredPersona(target) {
		blockedReason = "blocked_retired_persona"
		allowed = false
	} else if activeCount <= 1 {
		blockedReason = "blocked_last_persona"
		allowed = false
	} else if target.IsActive {
		blockedReason = "blocked_active_persona"
		allowed = false
		requiresSuccessor = true
	}
	return map[string]any{
		"personaId":         target.PersonaID,
		"requestedAction":   "retire",
		"allowed":           allowed,
		"reason":            blockedReason,
		"requiresSuccessor": requiresSuccessor,
	}
}

func findPersonaByPersona(personas []model.Persona, personaID string) *model.Persona {
	for i := range personas {
		if personas[i].PersonaID == personaID {
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
		if persona.PersonaID == sourcePersonaID || isRetiredPersona(persona) {
			continue
		}
		switch applyScope {
		case "all_personas":
			targets = append(targets, persona)
		case "selected_subjects":
			if _, ok := explicitSet[persona.PersonaID]; ok {
				targets = append(targets, persona)
			}
		}
	}
	return targets
}

func applyFieldsFromSource(target *model.Persona, source *model.Persona, fields []string) {
	for _, field := range fields {
		switch field {
		case "displayName":
			target.DisplayName = source.DisplayName
		case "avatarUrl":
			target.AvatarURL = source.AvatarURL
			target.AvatarVersion = source.AvatarVersion
		}
	}
}

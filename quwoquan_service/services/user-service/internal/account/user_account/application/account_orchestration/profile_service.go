package application

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"net/url"
	"os"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	"quwoquan_service/generated/linktemplates"
	rtobs "quwoquan_service/runtime/observability"
	runtimesync "quwoquan_service/runtime/sync"
	"quwoquan_service/services/user-service/generated/account/user_account"
	event "quwoquan_service/services/user-service/internal/account/user_account/domain/user/event"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

type ProfileService struct {
	profiles  userrepo.UserProfileStore
	personas  PersonaStore
	commands  personaports.PersonaCommandStore
	projector userrepo.PersonaProfileProjector
	pcache    ProfileSnapshotCache
	events    UserEventPublisher
	sync      UserSyncStream

	regionTags           RegionTagResolver
	profileTags          ProfileTagValidator
	qrTokens             userrepo.ProfileQrTokenStore
	publicProfileBaseURL string
	qrTokenSecret        []byte
	qrTokenTTL           time.Duration
}

type ProfileServiceOption func(*ProfileService)

func WithProfileQrTokenStore(qrTokens userrepo.ProfileQrTokenStore) ProfileServiceOption {
	return func(s *ProfileService) {
		s.qrTokens = qrTokens
	}
}

func WithProfilePublicBaseURL(baseURL string) ProfileServiceOption {
	return func(s *ProfileService) {
		if normalized := normalizePublicProfileBaseURL(baseURL); normalized != "" {
			s.publicProfileBaseURL = normalized
		}
	}
}

func WithRegionTagResolver(resolver RegionTagResolver) ProfileServiceOption {
	return func(s *ProfileService) {
		if resolver != nil {
			s.regionTags = resolver
		}
	}
}

func WithProfileTagValidator(validator ProfileTagValidator) ProfileServiceOption {
	return func(s *ProfileService) {
		if validator != nil {
			s.profileTags = validator
		}
	}
}

func NewProfileService(
	profiles userrepo.UserProfileStore,
	personas PersonaStore,
	commands personaports.PersonaCommandStore,
	projector userrepo.PersonaProfileProjector,
	pcache ProfileSnapshotCache,
	events UserEventPublisher,
	sync UserSyncStream,
	options ...ProfileServiceOption,
) (*ProfileService, error) {
	if profiles == nil || personas == nil || commands == nil || projector == nil ||
		pcache == nil {
		return nil, errors.New(
			"ProfileService requires account reader, Persona reader/commands/projector and cache",
		)
	}
	events = requireUserEventPublisher(events)
	service := &ProfileService{
		profiles:      profiles,
		personas:      personas,
		commands:      commands,
		projector:     projector,
		pcache:        pcache,
		events:        events,
		sync:          sync,
		regionTags:    PathRegionTagResolver{},
		profileTags:   PathProfileTagValidator{},
		qrTokenSecret: defaultProfileQRTokenSecret(),
		qrTokenTTL:    365 * 24 * time.Hour,
	}
	for _, option := range options {
		if option != nil {
			option(service)
		}
	}
	return service, nil
}

func (s *ProfileService) GetProfile(ctx context.Context, userID string) (snap *model.FullSnapshot, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.GetProfile",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	cached, cacheErr := s.pcache.Get(ctx, userID)
	if cacheErr == nil && cached != nil {
		return cached, nil
	}

	profile, err := s.profiles.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if profile == nil {
		return nil, nil
	}

	activePersona, _ := s.personas.FindActiveByUserID(ctx, userID)

	snap = &model.FullSnapshot{
		Profile:       profile,
		ActivePersona: activePersona,
	}

	_ = s.pcache.Set(ctx, userID, snap)
	return snap, nil
}

func (s *ProfileService) UpdateProfile(
	ctx context.Context,
	userID string,
	command ProfileUpdateCommand,
	meta PersonaCommandMeta,
) (_ *model.UserProfile, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.UpdateProfile",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	profile, err := s.profiles.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if profile == nil {
		return nil, generated.AppErrorFromUserNotFound("user not found: " + userID)
	}
	persona, err := s.personas.FindActiveByUserID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if persona == nil {
		return nil, generated.AppErrorFromInternalError(
			"active Persona is required for public profile mutation",
		)
	}

	// 昵称已不再要求全局唯一（唯一性由 userId/personaId/userHandle 承担）；
	// 用户主动改名后置 nicknameCustomized=true。公开资料只写 active Persona，
	// UserAccount 的同名字段由 durable projector 物化为只读投影。
	// nickname 与 displayName 互为别名：编辑页可能任一字段携带新昵称。
	newNickname := ""
	if command.Nickname != nil && strings.TrimSpace(*command.Nickname) != "" {
		newNickname = strings.TrimSpace(*command.Nickname)
	} else if command.DisplayName != nil && strings.TrimSpace(*command.DisplayName) != "" {
		newNickname = strings.TrimSpace(*command.DisplayName)
	}
	if newNickname != "" && newNickname != strings.TrimSpace(persona.DisplayName) {
		persona.DisplayName = newNickname
		persona.NicknameCustomized = true
	}
	oldAvatarURL := strings.TrimSpace(persona.AvatarURL)
	oldAvatarAssetID := strings.TrimSpace(persona.AvatarMediaAssetID)
	oldAvatarVersion := persona.AvatarVersion
	avatarChanged := false
	if command.AvatarAssetID != nil {
		assetID := strings.TrimSpace(*command.AvatarAssetID)
		if assetID != "" {
			persona.AvatarMediaAssetID = assetID
			persona.AvatarURL = profileMediaURL("profile_avatar", assetID)
		}
	}
	if command.AvatarURL != nil {
		nextAvatarURL := strings.TrimSpace(*command.AvatarURL)
		if isLocalProfileMediaReference(nextAvatarURL) {
			return nil, generated.AppErrorFromProfileInvalidMediaAsset("avatarUrl must be uploaded before PATCH")
		}
		if strings.TrimSpace(persona.AvatarMediaAssetID) == "" && nextAvatarURL != "" {
			return nil, generated.AppErrorFromProfileInvalidMediaAsset("avatarAssetId is required for avatar update")
		}
		if nextAvatarURL != "" {
			persona.AvatarURL = nextAvatarURL
		}
	}
	if strings.TrimSpace(persona.AvatarURL) != oldAvatarURL ||
		strings.TrimSpace(persona.AvatarMediaAssetID) != oldAvatarAssetID {
		avatarChanged = true
		persona.AvatarVersion++
		if persona.AvatarVersion <= 0 {
			persona.AvatarVersion = 1
		}
	}
	if command.BackgroundAssetID != nil {
		assetID := strings.TrimSpace(*command.BackgroundAssetID)
		if assetID != "" {
			persona.BackgroundMediaAssetID = assetID
			persona.BackgroundURL = profileMediaURL("profile_cover", assetID)
		}
	}
	if command.BackgroundURL != nil {
		nb := strings.TrimSpace(*command.BackgroundURL)
		if isLocalProfileMediaReference(nb) {
			return nil, generated.AppErrorFromProfileInvalidMediaAsset("backgroundUrl must be uploaded before PATCH")
		}
		if strings.TrimSpace(persona.BackgroundMediaAssetID) == "" && nb != "" {
			return nil, generated.AppErrorFromProfileInvalidMediaAsset("backgroundAssetId is required for cover update")
		}
		if nb != strings.TrimSpace(persona.BackgroundURL) {
			persona.BackgroundURL = nb
		}
	}
	if command.Bio != nil {
		if len([]rune(*command.Bio)) > 60 {
			return nil, generated.AppErrorFromInvalidArgument("bio exceeds 60 characters")
		}
		persona.Bio = *command.Bio
	}
	if command.Gender != nil {
		gender := strings.TrimSpace(*command.Gender)
		if !isValidProfileGender(gender) {
			return nil, generated.AppErrorFromInvalidArgument("invalid gender")
		}
		persona.Gender = gender
	}
	if command.BirthDate != nil {
		birthDate, err := normalizeProfileBirthDate(*command.BirthDate, time.Now())
		if err != nil {
			return nil, generated.AppErrorFromInvalidArgument(err.Error())
		}
		if birthDate == "" {
			persona.BirthDate = nil
		} else {
			persona.BirthDate = &birthDate
		}
	}
	if command.RegionTagRef != nil {
		regionTagRef := strings.TrimSpace(*command.RegionTagRef)
		resolver := s.regionTags
		if resolver == nil {
			resolver = PathRegionTagResolver{}
		}
		region, err := resolver.ResolveRegionTag(ctx, regionTagRef)
		if err != nil {
			return nil, generated.AppErrorFromProfileInvalidRegion(err.Error())
		}
		persona.RegionTagRef = regionTagRef
		persona.Region = region
	} else if command.Region != nil {
		if strings.TrimSpace(*command.Region) != "" {
			return nil, generated.AppErrorFromProfileInvalidRegion("regionTagRef is required")
		}
		persona.Region = ""
		persona.RegionTagRef = ""
	}
	if nextTags, ok := profileIdentityTagsFromUpdate(command, persona.IdentityTags); ok {
		if err := validateProfileTagRefs(nextTags); err != nil {
			return nil, generated.AppErrorFromProfileInvalidTagRef(err.Error())
		}
		occupationTagRef := firstTagWithPrefix(nextTags, profileOccupationRootTagRef+"/")
		interestRefs := interestTagRefs(nextTags)
		validator := s.profileTags
		if validator == nil {
			return nil, generated.AppErrorFromInternalError(
				"profile tag validator is not configured",
			)
		}
		expectedTaxonomyReleaseID := ""
		if command.ExpectedTaxonomyReleaseID != nil {
			expectedTaxonomyReleaseID = strings.TrimSpace(
				*command.ExpectedTaxonomyReleaseID,
			)
		}
		if err := validator.ValidateProfileTags(
			ctx,
			expectedTaxonomyReleaseID,
			occupationTagRef,
			interestRefs,
		); err != nil {
			if errors.Is(err, ErrProfileTaxonomyReleaseConflict) {
				return nil, generated.AppErrorFromProfileTaxonomyReleaseConflict(
					err.Error(),
				)
			}
			return nil, generated.AppErrorFromProfileInvalidTagRef(err.Error())
		}
		persona.IdentityTags = nextTags
		persona.TaxonomyReleaseID = expectedTaxonomyReleaseID
	}
	if command.ProfileVisibility != nil {
		switch strings.TrimSpace(*command.ProfileVisibility) {
		case "public":
			persona.IsPrivate = false
		case "private":
			persona.IsPrivate = true
		default:
			return nil, generated.AppErrorFromInvalidArgument(
				"profileVisibility must be public or private",
			)
		}
	}
	persona.InheritsProfileFromOwner = false
	persona.LastProfileSyncSource = "persona_edit"
	now := time.Now().UTC()
	persona.LastProfileSyncAt = &now
	normalizePersonaPersistence(persona)
	commandResult, err := s.commands.CommitMutation(
		ctx,
		persona,
		personaports.PersonaUpdatedEvent,
		meta,
	)
	if err != nil {
		return nil, mapPersonaProfileCommandError(err)
	}
	profile, err = s.projector.Project(
		ctx,
		commandResult.PersonaID,
		commandResult.Version,
	)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(
			fmt.Sprintf("project committed Persona profile: %v", err),
		)
	}
	_ = s.pcache.Del(ctx, userID)
	if commandResult.Replayed {
		return profile, nil
	}
	updatedAt := profile.UpdatedAt.UTC().Format("2006-01-02T15:04:05.999999999Z07:00")
	identityTags := append([]string(nil), persona.IdentityTags...)
	occupationTagRef := firstTagWithPrefix(identityTags, profileOccupationRootTagRef+"/")
	interestRefs := interestTagRefs(identityTags)
	if err := s.events.PublishUserEvent(ctx, event.UserProfileUpdated, userID, userID, map[string]any{
		"userId":             profile.UserID,
		"nickname":           profile.Nickname,
		"nicknameCustomized": profile.NicknameCustomized,
		"bio":                profile.Bio,
		"avatarUrl":          avatarURLWithVersion(profile.AvatarURL, profile.AvatarVersion),
		"backgroundUrl":      profile.BackgroundURL,
		"region":             profile.Region,
		"regionTagRef":       profile.RegionCode,
		"identityTags":       identityTags,
		"occupationTagRef":   occupationTagRef,
		"interestTagRefs":    interestRefs,
		"profileVersion":     profile.ProfileVersion,
		"updatedAt":          updatedAt,
	}); err != nil {
		return nil, err
	}
	if avatarChanged && profile.AvatarVersion != oldAvatarVersion {
		avatarPayload := map[string]any{
			"userId":         profile.UserID,
			"avatarAssetId":  profile.AvatarAssetID,
			"avatarVersion":  profile.AvatarVersion,
			"avatarUrl":      avatarURLWithVersion(profile.AvatarURL, profile.AvatarVersion),
			"profileVersion": profile.ProfileVersion,
			"updatedAt":      updatedAt,
		}
		if err := s.events.PublishUserEvent(ctx, event.UserAvatarUpdated, userID, userID, avatarPayload); err != nil {
			return nil, err
		}
		if s.sync != nil {
			if _, err := s.sync.AppendPatch(ctx, userID, "user.avatar.updated", avatarPayload); err != nil {
				return nil, err
			}
		}
	}
	return profile, nil
}

func mapPersonaProfileCommandError(err error) error {
	switch {
	case errors.Is(err, personaports.ErrPersonaVersionConflict):
		return generated.AppErrorFromProfileVersionConflict(err.Error())
	case errors.Is(err, personaports.ErrPersonaIdempotencyConflict):
		return generated.AppErrorFromProfileIdempotencyConflict(err.Error())
	case errors.Is(err, personaports.ErrPersonaCommandMetaRequired):
		return generated.AppErrorFromInvalidArgument(err.Error())
	default:
		return err
	}
}

// ProfileCredentialView 是资料编辑快照所需的最小凭据切片。
// Adapter 从 CredentialBinding 对象的 query view 显式映射，避免 Profile
// application service 依赖另一个对象的 aggregate 或 generated persistence model。
type ProfileCredentialView struct {
	CredentialType string
	DisplayLabel   string
	IsActive       bool
}

func (s *ProfileService) GetEditSnapshot(ctx context.Context, userID string, credentials []ProfileCredentialView) (_ map[string]any, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.GetProfileEditSnapshot",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	profile, err := s.profiles.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if profile == nil {
		return nil, generated.AppErrorFromUserNotFound("user not found: " + userID)
	}
	persona, err := s.personas.FindActiveByUserID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if persona == nil {
		return nil, generated.AppErrorFromInternalError(
			"active Persona is required for profile edit snapshot",
		)
	}
	personaID := strings.TrimSpace(persona.PersonaID)
	displayName := strings.TrimSpace(persona.DisplayName)
	userHandle := resolvedPersonaUserHandle(persona)
	avatarURL := strings.TrimSpace(persona.AvatarURL)
	avatarAssetID := strings.TrimSpace(persona.AvatarMediaAssetID)
	avatarVersion := resolvedPersonaAvatarVersion(persona)
	backgroundURL := strings.TrimSpace(persona.BackgroundURL)
	backgroundAssetID := strings.TrimSpace(persona.BackgroundMediaAssetID)
	if userHandle == "" {
		userHandle = personaID
	}
	tags := append([]string(nil), persona.IdentityTags...)
	birthDate := ""
	if persona.BirthDate != nil {
		birthDate = strings.TrimSpace(*persona.BirthDate)
	}
	versionedAvatarURL := avatarURLWithVersion(avatarURL, avatarVersion)
	qrCard, err := s.buildProfileQRCard(ctx, profile.UserID, personaID, userHandle, versionedAvatarURL, defaultString(displayName, profile.UserID), strings.TrimSpace(persona.Region))
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"ownerUserId":       profile.UserID,
		"personaId":         personaID,
		"avatarUrl":         versionedAvatarURL,
		"avatarAssetId":     avatarAssetID,
		"avatarVersion":     avatarVersion,
		"backgroundUrl":     backgroundURL,
		"backgroundAssetId": backgroundAssetID,
		"nickname":          defaultString(displayName, profile.UserID),
		"displayName":       defaultString(displayName, profile.UserID),
		"gender":            defaultString(persona.Gender, "unspecified"),
		"birthDate":         birthDate,
		"region":            strings.TrimSpace(persona.Region),
		"regionTagRef":      strings.TrimSpace(persona.RegionTagRef),
		"userHandle":        userHandle,
		"bio":               persona.Bio,
		"identityTags":      tags,
		"occupationTagRef":  firstTagWithPrefix(tags, profileOccupationRootTagRef+"/"),
		"interestTagRefs":   interestTagRefs(tags),
		"phoneCredential":   phoneCredentialSummary(credentials),
		"qrCard":            qrCard,
		"updatedAt":         defaultTime(persona.UpdatedAt).Format(time.RFC3339),
	}, nil
}

func (s *ProfileService) GetQRCard(ctx context.Context, userID string) (_ map[string]any, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.GetProfileQRCard",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	profile, err := s.profiles.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if profile == nil {
		return nil, generated.AppErrorFromUserNotFound("user not found: " + userID)
	}
	persona, err := s.personas.FindActiveByUserID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if persona == nil {
		return nil, generated.AppErrorFromInternalError(
			"active Persona is required for profile QR card",
		)
	}
	handle := resolvedPersonaUserHandle(persona)
	displayName := defaultString(persona.DisplayName, profile.UserID)
	avatarURL := persona.AvatarURL
	avatarVersion := resolvedPersonaAvatarVersion(persona)
	if strings.TrimSpace(handle) == "" {
		handle = userID
	}
	personaID := strings.TrimSpace(persona.PersonaID)
	return s.buildProfileQRCard(ctx, profile.UserID, personaID, handle, avatarURLWithVersion(avatarURL, avatarVersion), displayName, strings.TrimSpace(persona.Region))
}

func profileIdentityTagsFromUpdate(command ProfileUpdateCommand, current []string) ([]string, bool) {
	if command.IdentityTags != nil {
		return dedupeStrings(command.IdentityTags), true
	}
	occupationTouched := command.OccupationTagRef != nil
	occupation := ""
	if occupationTouched {
		occupation = *command.OccupationTagRef
	}
	interestsTouched := command.InterestTagRefs != nil
	interests := dedupeStrings(command.InterestTagRefs)
	if !occupationTouched && !interestsTouched {
		return nil, false
	}
	next := make([]string, 0, len(current)+len(interests)+1)
	for _, tag := range current {
		trimmed := strings.TrimSpace(tag)
		if strings.HasPrefix(trimmed, profileOccupationRootTagRef+"/") {
			if occupationTouched {
				continue
			}
			next = append(next, trimmed)
			continue
		}
		if strings.HasPrefix(trimmed, profileInterestRootTagRef+"/") {
			if interestsTouched {
				continue
			}
			next = append(next, trimmed)
			continue
		}
		if strings.HasPrefix(trimmed, "Topic/兴趣/") {
			continue
		}
		next = append(next, tag)
	}
	if strings.TrimSpace(occupation) != "" {
		next = append(next, strings.TrimSpace(occupation))
	}
	for _, tag := range interests {
		if strings.TrimSpace(tag) != "" {
			next = append(next, strings.TrimSpace(tag))
		}
	}
	return dedupeStrings(next), true
}

func stringSliceFromAny(value any) ([]string, bool) {
	switch v := value.(type) {
	case []string:
		return dedupeStrings(v), true
	case []any:
		result := make([]string, 0, len(v))
		for _, item := range v {
			if text := strings.TrimSpace(fmt.Sprint(item)); text != "" {
				result = append(result, text)
			}
		}
		return dedupeStrings(result), true
	default:
		return nil, false
	}
}

func dedupeStrings(values []string) []string {
	seen := map[string]struct{}{}
	result := make([]string, 0, len(values))
	for _, value := range values {
		text := strings.TrimSpace(value)
		if text == "" {
			continue
		}
		if _, ok := seen[text]; ok {
			continue
		}
		seen[text] = struct{}{}
		result = append(result, text)
	}
	return result
}

func firstTagWithPrefix(tags []string, prefix string) string {
	for _, tag := range tags {
		if strings.HasPrefix(strings.TrimSpace(tag), prefix) {
			return strings.TrimSpace(tag)
		}
	}
	return ""
}

func interestTagRefs(tags []string) []string {
	result := make([]string, 0, len(tags))
	for _, tag := range tags {
		trimmed := strings.TrimSpace(tag)
		if strings.HasPrefix(trimmed, profileInterestRootTagRef+"/") {
			result = append(result, trimmed)
		}
	}
	return result
}

func phoneCredentialSummary(credentials []ProfileCredentialView) map[string]any {
	for _, credential := range credentials {
		credType := strings.TrimSpace(credential.CredentialType)
		if credType != credentialPhone && credType != credentialCarrierPhone {
			continue
		}
		return map[string]any{
			"credentialType": credType,
			"displayLabel":   strings.TrimSpace(credential.DisplayLabel),
			"isBound":        credential.IsActive,
		}
	}
	return nil
}

func (s *ProfileService) buildProfileQRCard(ctx context.Context, ownerUserID, personaID, handle, avatarURL, displayName, region string) (map[string]any, error) {
	resolvedHandle := strings.TrimSpace(handle)
	if resolvedHandle == "" {
		resolvedHandle = strings.TrimSpace(personaID)
	}
	if resolvedHandle == "" {
		return nil, generated.AppErrorFromProfileQrTokenInvalid("profile handle is empty")
	}
	rawToken, token, err := s.ensureProfileQRToken(ctx, ownerUserID, personaID, resolvedHandle)
	if err != nil {
		return nil, err
	}
	publicURL := s.profilePublicURL(resolvedHandle)
	qrPayload := publicURL + "?qr=" + url.QueryEscape(rawToken)
	return map[string]any{
		"publicProfileUrl": publicURL,
		"qrPayload":        qrPayload,
		"qrTokenId":        token.TokenID,
		"avatarUrl":        strings.TrimSpace(avatarURL),
		"displayName":      strings.TrimSpace(displayName),
		"region":           strings.TrimSpace(region),
		"shareText":        qrPayload,
		"expiresAt":        formatOptionalTime(token.ExpiresAt),
	}, nil
}

func (s *ProfileService) ResolveProfileQRToken(ctx context.Context, handle, rawToken string) (_ map[string]any, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.ResolveProfileQRToken",
		attribute.String("user.handle", strings.TrimSpace(handle)))
	defer func() { rtobs.EndSpan(span, err) }()
	if s.qrTokens == nil {
		return nil, generated.AppErrorFromProfileQrTokenInvalid("profile qr token store unavailable")
	}
	tokenValue := strings.TrimSpace(rawToken)
	if tokenValue == "" {
		return nil, generated.AppErrorFromProfileQrTokenInvalid("qr token required")
	}
	token, err := s.qrTokens.FindByTokenHash(ctx, profileQRTokenHash(tokenValue))
	if err != nil {
		return nil, err
	}
	if token == nil || strings.TrimSpace(token.Status) != "active" || token.RevokedAt != nil {
		return nil, generated.AppErrorFromProfileQrTokenInvalid("qr token not found")
	}
	if token.ExpiresAt != nil && time.Now().UTC().After(token.ExpiresAt.UTC()) {
		return nil, generated.AppErrorFromProfileQrTokenExpired("qr token expired")
	}
	if expectedHandle := strings.TrimSpace(handle); expectedHandle != "" && expectedHandle != strings.TrimSpace(token.UserHandle) {
		return nil, generated.AppErrorFromProfileQrTokenInvalid("qr token handle mismatch")
	}
	return map[string]any{
		"personaId":        strings.TrimSpace(token.PersonaID),
		"userHandle":       strings.TrimSpace(token.UserHandle),
		"publicProfileUrl": s.profilePublicURL(token.UserHandle),
		"scanStatus":       "accepted",
	}, nil
}

func (s *ProfileService) ensureProfileQRToken(ctx context.Context, ownerUserID, personaID, handle string) (string, *model.ProfileQrToken, error) {
	if s.qrTokens == nil {
		return "", nil, generated.AppErrorFromProfileQrTokenInvalid("profile qr token store unavailable")
	}
	now := time.Now().UTC()
	token, err := s.qrTokens.FindActiveByOwnerAndHandle(ctx, ownerUserID, handle)
	if err != nil {
		return "", nil, err
	}
	expiresAt := now.Add(s.qrTokenTTL)
	if token != nil && token.ExpiresAt != nil {
		expiresAt = token.ExpiresAt.UTC()
	}
	rawToken := s.profileQRRawToken(ownerUserID, personaID, handle, expiresAt)
	tokenHash := profileQRTokenHash(rawToken)
	if token != nil && (token.ExpiresAt == nil || now.Before(token.ExpiresAt.UTC())) {
		changed := false
		if token.TokenHash != tokenHash {
			token.TokenHash = tokenHash
			changed = true
		}
		if strings.TrimSpace(token.PersonaID) != strings.TrimSpace(personaID) {
			token.PersonaID = strings.TrimSpace(personaID)
			changed = true
		}
		if changed {
			if err := s.qrTokens.Update(ctx, token); err != nil {
				return "", nil, err
			}
		}
		return rawToken, token, nil
	}
	token = &model.ProfileQrToken{
		TokenID:     "pqr_" + shortTokenID(tokenHash),
		TokenHash:   tokenHash,
		OwnerUserID: strings.TrimSpace(ownerUserID),
		PersonaID:   strings.TrimSpace(personaID),
		UserHandle:  strings.TrimSpace(handle),
		Status:      "active",
		ExpiresAt:   &expiresAt,
	}
	if err := s.qrTokens.Create(ctx, token); err != nil {
		return "", nil, err
	}
	return rawToken, token, nil
}

func (s *ProfileService) profileQRRawToken(ownerUserID, personaID, handle string, expiresAt time.Time) string {
	payload := strings.Join([]string{
		strings.TrimSpace(ownerUserID),
		strings.TrimSpace(personaID),
		strings.TrimSpace(handle),
		expiresAt.UTC().Format(time.RFC3339),
	}, "|")
	mac := hmac.New(sha256.New, s.qrTokenSecret)
	_, _ = mac.Write([]byte(payload))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func (s *ProfileService) profilePublicURL(handle string) string {
	return strings.TrimRight(s.publicProfileBaseURL, "/") +
		linktemplates.UserWebPath(handle)
}

func profileQRTokenHash(rawToken string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(rawToken)))
	return hex.EncodeToString(sum[:])
}

func shortTokenID(hash string) string {
	if len(hash) <= 24 {
		return hash
	}
	return hash[:24]
}

func normalizePublicProfileBaseURL(baseURL string) string {
	trimmed := strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if trimmed == "" {
		return ""
	}
	return trimmed
}

func defaultProfileQRTokenSecret() []byte {
	if value := strings.TrimSpace(os.Getenv("PROFILE_QR_TOKEN_SECRET")); value != "" {
		return []byte(value)
	}
	return []byte("quwoquan-profile-qr-token-dev-secret")
}

func formatOptionalTime(value *time.Time) string {
	if value == nil || value.IsZero() {
		return ""
	}
	return value.UTC().Format(time.RFC3339)
}

func profileMediaURL(scope, assetID string) string {
	resolvedAssetID := strings.TrimSpace(assetID)
	if resolvedAssetID == "" {
		return ""
	}
	return "media/profile/" + strings.TrimSpace(scope) + "/" + resolvedAssetID
}

func isLocalProfileMediaReference(value string) bool {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return false
	}
	if strings.HasPrefix(trimmed, "file:") || strings.HasPrefix(trimmed, "/") {
		return true
	}
	lower := strings.ToLower(trimmed)
	return strings.Contains(lower, "/tmp/") || strings.Contains(lower, "/var/folders/")
}

func defaultTime(value time.Time) time.Time {
	if value.IsZero() {
		return time.Now().UTC()
	}
	return value.UTC()
}

func (s *ProfileService) GetStats(ctx context.Context, userID string) (_ map[string]any, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.GetStats",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	profile, err := s.profiles.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if profile == nil {
		return nil, nil
	}
	return map[string]any{
		"followerCount":  profile.FollowerCount,
		"followingCount": profile.FollowingCount,
		"postCount":      profile.PostCount,
		"circleCount":    profile.CircleCount,
		"likeCount":      profile.LikeCount,
	}, nil
}

func (s *ProfileService) PullSync(
	ctx context.Context,
	userID string,
	afterSeq int64,
	limit int,
) (_ runtimesync.PullResponse, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "user.PullSync",
		attribute.String("user.id", userID),
		attribute.Int64("sync.after_seq", afterSeq))
	defer func() { rtobs.EndSpan(span, err) }()

	if s.sync == nil {
		return runtimesync.PullResponse{
			Patches:        []runtimesync.Patch{},
			LatestSyncSeq:  0,
			HasMore:        false,
			RequiresResync: false,
		}, nil
	}
	return s.sync.Pull(ctx, userID, afterSeq, limit)
}

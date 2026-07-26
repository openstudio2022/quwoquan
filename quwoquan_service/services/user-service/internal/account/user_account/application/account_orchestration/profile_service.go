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

	rtobs "quwoquan_service/runtime/observability"
	runtimesync "quwoquan_service/runtime/sync"
	"quwoquan_service/services/user-service/generated/account/user_account"
	event "quwoquan_service/services/user-service/internal/account/user_account/domain/user/event"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

type ProfileService struct {
	profiles userrepo.UserProfileStore
	personas PersonaStore
	pcache   ProfileSnapshotCache
	events   UserEventPublisher
	sync     UserSyncStream

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
	pcache ProfileSnapshotCache,
	events UserEventPublisher,
	sync UserSyncStream,
	options ...ProfileServiceOption,
) *ProfileService {
	events = requireUserEventPublisher(events)
	service := &ProfileService{
		profiles:             profiles,
		personas:             personas,
		pcache:               pcache,
		events:               events,
		sync:                 sync,
		regionTags:           PathRegionTagResolver{},
		profileTags:          PathProfileTagValidator{},
		publicProfileBaseURL: defaultPublicProfileBaseURL(),
		qrTokenSecret:        defaultProfileQRTokenSecret(),
		qrTokenTTL:           365 * 24 * time.Hour,
	}
	for _, option := range options {
		if option != nil {
			option(service)
		}
	}
	return service
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

	commandStore, ok := s.profiles.(userrepo.UserProfileCommandStore)
	if !ok {
		return nil, generated.AppErrorFromInternalError(
			"profile command store is not configured",
		)
	}
	profileCommandMeta := userrepo.UserProfileCommandMeta{
		IdempotencyKey: meta.IdempotencyKey,
		CommandDigest:  meta.CommandDigest,
	}
	if _, replayed, replayErr := commandStore.ReplayUserProfileCommand(
		ctx,
		profileCommandMeta,
	); replayErr != nil {
		return nil, mapUserProfileCommandError(replayErr)
	} else if replayed {
		return s.profiles.FindByID(ctx, userID)
	}

	profile, err := s.profiles.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if profile == nil {
		return nil, generated.AppErrorFromUserNotFound("user not found: " + userID)
	}

	// 昵称已不再要求全局唯一（唯一性由 userId/subAccountId/userHandle 承担）；
	// 用户主动改名后置 nicknameCustomized=true，本人主页据此不再展示编辑画笔。
	// nickname 与 displayName 互为别名：编辑页可能任一字段携带新昵称。
	nicknameChanged := false
	newNickname := ""
	if command.Nickname != nil && strings.TrimSpace(*command.Nickname) != "" {
		newNickname = strings.TrimSpace(*command.Nickname)
	} else if command.DisplayName != nil && strings.TrimSpace(*command.DisplayName) != "" {
		newNickname = strings.TrimSpace(*command.DisplayName)
	}
	if newNickname != "" && newNickname != strings.TrimSpace(profile.Nickname) {
		profile.Nickname = newNickname
		profile.NicknameCustomized = true
		nicknameChanged = true
	}
	oldAvatarURL := strings.TrimSpace(profile.AvatarURL)
	oldAvatarAssetID := strings.TrimSpace(profile.AvatarAssetID)
	oldAvatarVersion := profile.AvatarVersion
	avatarChanged := false
	if command.AvatarAssetID != nil {
		assetID := strings.TrimSpace(*command.AvatarAssetID)
		if assetID != "" {
			profile.AvatarAssetID = assetID
			profile.AvatarURL = profileMediaURL("profile_avatar", assetID)
		}
	}
	if command.AvatarURL != nil {
		nextAvatarURL := strings.TrimSpace(*command.AvatarURL)
		if isLocalProfileMediaReference(nextAvatarURL) {
			return nil, generated.AppErrorFromProfileInvalidMediaAsset("avatarUrl must be uploaded before PATCH")
		}
		if strings.TrimSpace(profile.AvatarAssetID) == "" && nextAvatarURL != "" {
			return nil, generated.AppErrorFromProfileInvalidMediaAsset("avatarAssetId is required for avatar update")
		}
		if nextAvatarURL != "" {
			profile.AvatarURL = nextAvatarURL
		}
	}
	if strings.TrimSpace(profile.AvatarURL) != oldAvatarURL || strings.TrimSpace(profile.AvatarAssetID) != oldAvatarAssetID {
		avatarChanged = true
		profile.AvatarVersion++
		if profile.AvatarVersion <= 0 {
			profile.AvatarVersion = 1
		}
	}
	backgroundChanged := false
	if command.BackgroundAssetID != nil {
		assetID := strings.TrimSpace(*command.BackgroundAssetID)
		if assetID != "" {
			profile.BackgroundAssetID = assetID
			profile.BackgroundURL = profileMediaURL("profile_cover", assetID)
		}
	}
	if command.BackgroundURL != nil {
		nb := strings.TrimSpace(*command.BackgroundURL)
		if isLocalProfileMediaReference(nb) {
			return nil, generated.AppErrorFromProfileInvalidMediaAsset("backgroundUrl must be uploaded before PATCH")
		}
		if strings.TrimSpace(profile.BackgroundAssetID) == "" && nb != "" {
			return nil, generated.AppErrorFromProfileInvalidMediaAsset("backgroundAssetId is required for cover update")
		}
		if nb != strings.TrimSpace(profile.BackgroundURL) {
			profile.BackgroundURL = nb
			backgroundChanged = true
		}
	}
	if command.Bio != nil {
		if len([]rune(*command.Bio)) > 60 {
			return nil, generated.AppErrorFromInvalidArgument("bio exceeds 60 characters")
		}
		profile.Bio = *command.Bio
	}
	if command.Gender != nil {
		gender := strings.TrimSpace(*command.Gender)
		if !isValidProfileGender(gender) {
			return nil, generated.AppErrorFromInvalidArgument("invalid gender")
		}
		profile.Gender = gender
	}
	if command.BirthDate != nil {
		birthDate, err := normalizeProfileBirthDate(*command.BirthDate, time.Now())
		if err != nil {
			return nil, generated.AppErrorFromInvalidArgument(err.Error())
		}
		if birthDate == "" {
			profile.BirthDate = nil
		} else {
			profile.BirthDate = &birthDate
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
		profile.RegionCode = regionTagRef
		profile.Region = region
	} else if command.Region != nil {
		if strings.TrimSpace(*command.Region) != "" {
			return nil, generated.AppErrorFromProfileInvalidRegion("regionTagRef is required")
		}
		profile.Region = ""
		profile.RegionCode = ""
	}
	var tagProjection userrepo.UserProfileTagProjection
	tagProjectionRequired := false
	if nextTags, ok := profileIdentityTagsFromUpdate(command, parsePgTextArray(profile.IdentityTags)); ok {
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
		profile.IdentityTags = encodeStringArray(nextTags)
		tagRefs := make([]string, 0, len(interestRefs)+1)
		if occupationTagRef != "" {
			tagRefs = append(tagRefs, occupationTagRef)
		}
		tagRefs = append(tagRefs, interestRefs...)
		tagProjection.TagRefs = tagRefs
		tagProjection.TaxonomyReleaseID = expectedTaxonomyReleaseID
		tagProjectionRequired = true
	}

	// 任一资料字段变更都递增 profileVersion，供端侧增量校验与缓存失效。
	profile.ProfileVersion++
	if profile.ProfileVersion <= 0 {
		profile.ProfileVersion = 1
	}
	profile.UpdatedAt = time.Now().UTC()

	var projection *userrepo.UserProfileTagProjection
	if tagProjectionRequired {
		tagProjection.UserID = profile.UserID
		profileVersion := int64(profile.ProfileVersion)
		tagProjection.ProfileVersion = profileVersion
		tagProjection.OccurredAt = profile.UpdatedAt
		tagProjection.EventID = profileTagProjectionEventID(
			profile.UserID,
			profileVersion,
		)
		projection = &tagProjection
	}
	searchProjections := []userrepo.UserProfileSearchProjection{{
		UserID:         profile.UserID,
		ProfileVersion: int64(profile.ProfileVersion),
		EventType:      event.UserProfileUpdated,
		OccurredAt:     profile.UpdatedAt,
	}}
	if avatarChanged {
		searchProjections = append(
			searchProjections,
			userrepo.UserProfileSearchProjection{
				UserID:         profile.UserID,
				ProfileVersion: int64(profile.ProfileVersion),
				EventType:      event.UserAvatarUpdated,
				OccurredAt:     profile.UpdatedAt,
			},
		)
	}
	commandResult, err := commandStore.CommitUserProfileCommand(
		ctx,
		profile,
		projection,
		searchProjections,
		profileCommandMeta,
	)
	if err != nil {
		return nil, mapUserProfileCommandError(err)
	}
	if commandResult.Replayed {
		return s.profiles.FindByID(ctx, userID)
	}

	// 把继承自 owner 基线的展示字段同步到当前激活分身，
	// 保证本人主页（读取 persona.displayName/avatar/background）保存后立即回显。
	s.propagateOwnerProfileToActivePersona(ctx, userID, profile, nicknameChanged, avatarChanged, backgroundChanged)

	_ = s.pcache.Del(ctx, userID)
	updatedAt := profile.UpdatedAt.UTC().Format("2006-01-02T15:04:05.999999999Z07:00")
	identityTags := parsePgTextArray(profile.IdentityTags)
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
	if profile.AvatarVersion != oldAvatarVersion {
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

func mapUserProfileCommandError(err error) error {
	switch {
	case errors.Is(err, userrepo.ErrUserProfileVersionConflict):
		return generated.AppErrorFromProfileVersionConflict(err.Error())
	case errors.Is(err, userrepo.ErrUserProfileIdempotencyConflict):
		return generated.AppErrorFromProfileIdempotencyConflict(err.Error())
	case errors.Is(err, userrepo.ErrUserProfileCommandMetaRequired):
		return generated.AppErrorFromInvalidArgument(err.Error())
	default:
		return err
	}
}

// ProfileCredentialView 是资料编辑快照所需的最小凭据切片。
// Adapter 从 CredentialBinding 对象的 query view 显式映射，避免 Profile
// application service 依赖另一个对象的 aggregate 或 legacy generated model。
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
	persona, _ := s.personas.FindActiveByUserID(ctx, userID)
	subAccountID := userID
	displayName := strings.TrimSpace(profile.Nickname)
	userHandle := ""
	avatarURL := profile.AvatarURL
	avatarAssetID := profile.AvatarAssetID
	avatarVersion := profile.AvatarVersion
	backgroundURL := profile.BackgroundURL
	backgroundAssetID := profile.BackgroundAssetID
	if persona != nil {
		subAccountID = strings.TrimSpace(persona.SubAccountID)
		userHandle = resolvedPersonaUserHandle(persona)
		if strings.TrimSpace(persona.DisplayName) != "" {
			displayName = strings.TrimSpace(persona.DisplayName)
		}
		if strings.TrimSpace(persona.AvatarURL) != "" {
			avatarURL = persona.AvatarURL
			avatarVersion = resolvedPersonaAvatarVersion(persona)
		}
		if strings.TrimSpace(persona.BackgroundURL) != "" {
			backgroundURL = persona.BackgroundURL
		}
	}
	if userHandle == "" {
		userHandle = subAccountID
	}
	tags := parsePgTextArray(profile.IdentityTags)
	birthDate := ""
	if profile.BirthDate != nil {
		birthDate = strings.TrimSpace(*profile.BirthDate)
	}
	versionedAvatarURL := avatarURLWithVersion(avatarURL, avatarVersion)
	qrCard, err := s.buildProfileQRCard(ctx, profile.UserID, subAccountID, userHandle, versionedAvatarURL, defaultString(displayName, profile.UserID), strings.TrimSpace(profile.Region))
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"ownerUserId":       profile.UserID,
		"subAccountId":      subAccountID,
		"avatarUrl":         versionedAvatarURL,
		"avatarAssetId":     avatarAssetID,
		"avatarVersion":     avatarVersion,
		"backgroundUrl":     backgroundURL,
		"backgroundAssetId": backgroundAssetID,
		"nickname":          defaultString(displayName, profile.UserID),
		"displayName":       defaultString(displayName, profile.UserID),
		"gender":            defaultString(profile.Gender, "unspecified"),
		"birthDate":         birthDate,
		"region":            strings.TrimSpace(profile.Region),
		"regionTagRef":      strings.TrimSpace(profile.RegionCode),
		"userHandle":        userHandle,
		"bio":               profile.Bio,
		"identityTags":      tags,
		"occupationTagRef":  firstTagWithPrefix(tags, profileOccupationRootTagRef+"/"),
		"interestTagRefs":   interestTagRefs(tags),
		"phoneCredential":   phoneCredentialSummary(credentials),
		"qrCard":            qrCard,
		"updatedAt":         defaultTime(profile.UpdatedAt).Format(time.RFC3339),
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
	persona, _ := s.personas.FindActiveByUserID(ctx, userID)
	handle := userID
	displayName := defaultString(profile.Nickname, profile.UserID)
	avatarURL := profile.AvatarURL
	avatarVersion := profile.AvatarVersion
	if persona != nil {
		handle = resolvedPersonaUserHandle(persona)
		if strings.TrimSpace(persona.DisplayName) != "" {
			displayName = strings.TrimSpace(persona.DisplayName)
		}
		if strings.TrimSpace(persona.AvatarURL) != "" {
			avatarURL = persona.AvatarURL
			avatarVersion = resolvedPersonaAvatarVersion(persona)
		}
	}
	if strings.TrimSpace(handle) == "" {
		handle = userID
	}
	subAccountID := userID
	if persona != nil && strings.TrimSpace(persona.SubAccountID) != "" {
		subAccountID = strings.TrimSpace(persona.SubAccountID)
	}
	return s.buildProfileQRCard(ctx, profile.UserID, subAccountID, handle, avatarURLWithVersion(avatarURL, avatarVersion), displayName, strings.TrimSpace(profile.Region))
}

// propagateOwnerProfileToActivePersona 把 owner 基线变更同步到当前激活分身的继承字段。
// 仅在分身仍继承（InheritsProfileFromOwner 或该字段未被 override）时覆盖，避免破坏分身自定义。
func (s *ProfileService) propagateOwnerProfileToActivePersona(
	ctx context.Context,
	userID string,
	profile *model.UserProfile,
	nicknameChanged, avatarChanged, backgroundChanged bool,
) {
	if s.personas == nil || (!nicknameChanged && !avatarChanged && !backgroundChanged) {
		return
	}
	active, err := s.personas.FindActiveByUserID(ctx, userID)
	if err != nil || active == nil {
		return
	}
	overridden := parseProfileFieldList(active.OverriddenProfileFields)
	changed := false
	if nicknameChanged && !containsField(overridden, "displayName") {
		active.DisplayName = profile.Nickname
		changed = true
	}
	if avatarChanged && !containsField(overridden, "avatarUrl") {
		if active.AvatarURL != profile.AvatarURL || active.AvatarVersion != profile.AvatarVersion {
			active.AvatarURL = profile.AvatarURL
			active.AvatarVersion = profile.AvatarVersion
			changed = true
		}
	}
	if backgroundChanged && !containsField(overridden, "backgroundUrl") {
		active.BackgroundURL = profile.BackgroundURL
		changed = true
	}
	if changed {
		_ = s.personas.Update(ctx, active)
	}
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

func profileTagProjectionEventID(userID string, profileVersion int64) string {
	digest := sha256.Sum256(
		[]byte(fmt.Sprintf("%s\x00profile-tags\x00%d", userID, profileVersion)),
	)
	return fmt.Sprintf("profile-tags-%x", digest[:16])
}

func encodeStringArray(values []string) string {
	normalized := dedupeStrings(values)
	if len(normalized) == 0 {
		return "{}"
	}
	for i, value := range normalized {
		normalized[i] = `"` + strings.ReplaceAll(value, `"`, `\"`) + `"`
	}
	return "{" + strings.Join(normalized, ",") + "}"
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

func (s *ProfileService) buildProfileQRCard(ctx context.Context, ownerUserID, subAccountID, handle, avatarURL, displayName, region string) (map[string]any, error) {
	resolvedHandle := strings.TrimSpace(handle)
	if resolvedHandle == "" {
		resolvedHandle = strings.TrimSpace(subAccountID)
	}
	if resolvedHandle == "" {
		return nil, generated.AppErrorFromProfileQrTokenInvalid("profile handle is empty")
	}
	rawToken, token, err := s.ensureProfileQRToken(ctx, ownerUserID, subAccountID, resolvedHandle, "v1")
	if err != nil {
		return nil, err
	}
	publicURL := s.profilePublicURL(resolvedHandle)
	qrPayload := publicURL + "?qr=" + url.QueryEscape(rawToken)
	return map[string]any{
		"publicProfileUrl": publicURL,
		"qrPayload":        qrPayload,
		"qrTokenId":        token.TokenID,
		"styleVersion":     token.StyleVersion,
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
		"subAccountId":     strings.TrimSpace(token.SubAccountID),
		"userHandle":       strings.TrimSpace(token.UserHandle),
		"publicProfileUrl": s.profilePublicURL(token.UserHandle),
		"scanStatus":       "accepted",
	}, nil
}

func (s *ProfileService) ensureProfileQRToken(ctx context.Context, ownerUserID, subAccountID, handle, styleVersion string) (string, *model.ProfileQrToken, error) {
	if s.qrTokens == nil {
		return "", nil, generated.AppErrorFromProfileQrTokenInvalid("profile qr token store unavailable")
	}
	now := time.Now().UTC()
	resolvedStyle := strings.TrimSpace(styleVersion)
	if resolvedStyle == "" {
		resolvedStyle = "v1"
	}
	token, err := s.qrTokens.FindActiveByOwnerAndHandle(ctx, ownerUserID, handle, resolvedStyle)
	if err != nil {
		return "", nil, err
	}
	expiresAt := now.Add(s.qrTokenTTL)
	if token != nil && token.ExpiresAt != nil {
		expiresAt = token.ExpiresAt.UTC()
	}
	rawToken := s.profileQRRawToken(ownerUserID, subAccountID, handle, resolvedStyle, expiresAt)
	tokenHash := profileQRTokenHash(rawToken)
	if token != nil && (token.ExpiresAt == nil || now.Before(token.ExpiresAt.UTC())) {
		changed := false
		if token.TokenHash != tokenHash {
			token.TokenHash = tokenHash
			changed = true
		}
		if strings.TrimSpace(token.SubAccountID) != strings.TrimSpace(subAccountID) {
			token.SubAccountID = strings.TrimSpace(subAccountID)
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
		TokenID:      "pqr_" + shortTokenID(tokenHash),
		TokenHash:    tokenHash,
		OwnerUserID:  strings.TrimSpace(ownerUserID),
		SubAccountID: strings.TrimSpace(subAccountID),
		UserHandle:   strings.TrimSpace(handle),
		StyleVersion: resolvedStyle,
		Status:       "active",
		ExpiresAt:    &expiresAt,
	}
	if err := s.qrTokens.Create(ctx, token); err != nil {
		return "", nil, err
	}
	return rawToken, token, nil
}

func (s *ProfileService) profileQRRawToken(ownerUserID, subAccountID, handle, styleVersion string, expiresAt time.Time) string {
	payload := strings.Join([]string{
		strings.TrimSpace(ownerUserID),
		strings.TrimSpace(subAccountID),
		strings.TrimSpace(handle),
		strings.TrimSpace(styleVersion),
		expiresAt.UTC().Format(time.RFC3339),
	}, "|")
	mac := hmac.New(sha256.New, s.qrTokenSecret)
	_, _ = mac.Write([]byte(payload))
	return base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
}

func (s *ProfileService) profilePublicURL(handle string) string {
	return strings.TrimRight(s.publicProfileBaseURL, "/") + "/u/" + url.PathEscape(strings.TrimSpace(handle))
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

func defaultPublicProfileBaseURL() string {
	if value := normalizePublicProfileBaseURL(os.Getenv("PROFILE_PUBLIC_APP_HOST")); value != "" {
		return value
	}
	return "https://app.quwoquan.com"
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

func containsField(fields []string, target string) bool {
	for _, f := range fields {
		if strings.TrimSpace(f) == target {
			return true
		}
	}
	return false
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

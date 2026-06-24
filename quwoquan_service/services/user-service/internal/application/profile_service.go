package application

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"net/url"
	"os"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	runtimesync "quwoquan_service/runtime/sync"
	event "quwoquan_service/services/user-service/internal/domain/user/event"
	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
	"quwoquan_service/services/user-service/internal/generated"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
)

type ProfileService struct {
	profiles userrepo.ProfileRepository
	personas userrepo.PersonaRepository
	settings userrepo.SettingRepository
	pcache   *cache.ProfileCache
	scache   *cache.SettingCache
	events   UserEventPublisher
	sync     UserSyncStream

	regionTags           RegionTagResolver
	profileTags          ProfileTagValidator
	qrTokens             userrepo.ProfileQrTokenRepository
	publicProfileBaseURL string
	qrTokenSecret        []byte
	qrTokenTTL           time.Duration
}

type ProfileServiceOption func(*ProfileService)

func WithProfileQrTokenRepository(qrTokens userrepo.ProfileQrTokenRepository) ProfileServiceOption {
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
	profiles userrepo.ProfileRepository,
	personas userrepo.PersonaRepository,
	settings userrepo.SettingRepository,
	pcache *cache.ProfileCache,
	scache *cache.SettingCache,
	events UserEventPublisher,
	sync UserSyncStream,
	options ...ProfileServiceOption,
) *ProfileService {
	if events == nil {
		events = NoopUserEventPublisher()
	}
	service := &ProfileService{
		profiles:             profiles,
		personas:             personas,
		settings:             settings,
		pcache:               pcache,
		scache:               scache,
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
	setting, _ := s.settings.FindByUserID(ctx, userID)

	snap = &model.FullSnapshot{
		Profile:       profile,
		ActivePersona: activePersona,
		Settings:      setting,
	}

	_ = s.pcache.Set(ctx, userID, snap)
	return snap, nil
}

func (s *ProfileService) UpdateProfile(ctx context.Context, userID string, data map[string]any) (_ *model.UserProfile, err error) {
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
	if _, ok := data["userHandle"]; ok {
		return nil, generated.AppErrorFromSubAccountHandleReadonly("userHandle is system assigned")
	}

	// 昵称已不再要求全局唯一（唯一性由 userId/subAccountId/userHandle 承担）；
	// 用户主动改名后置 nicknameCustomized=true，本人主页据此不再展示编辑画笔。
	// nickname 与 displayName 互为别名：编辑页可能任一字段携带新昵称。
	nicknameChanged := false
	newNickname := ""
	if v, ok := data["nickname"].(string); ok && strings.TrimSpace(v) != "" {
		newNickname = strings.TrimSpace(v)
	} else if v, ok := data["displayName"].(string); ok && strings.TrimSpace(v) != "" {
		newNickname = strings.TrimSpace(v)
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
	if v, ok := data["avatarAssetId"].(string); ok {
		assetID := strings.TrimSpace(v)
		if assetID != "" {
			profile.AvatarAssetID = assetID
			profile.AvatarURL = profileMediaURL("profile_avatar", assetID)
		}
	}
	if v, ok := data["avatarUrl"].(string); ok {
		nextAvatarURL := strings.TrimSpace(v)
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
	if v, ok := data["backgroundAssetId"].(string); ok {
		assetID := strings.TrimSpace(v)
		if assetID != "" {
			profile.BackgroundAssetID = assetID
			profile.BackgroundURL = profileMediaURL("profile_cover", assetID)
		}
	}
	if v, ok := data["backgroundUrl"].(string); ok {
		nb := strings.TrimSpace(v)
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
	if v, ok := data["bio"].(string); ok {
		if len([]rune(v)) > 60 {
			return nil, generated.AppErrorFromInvalidArgument("bio exceeds 60 characters")
		}
		profile.Bio = v
	}
	if v, ok := data["gender"].(string); ok {
		gender := strings.TrimSpace(v)
		if !isValidProfileGender(gender) {
			return nil, generated.AppErrorFromInvalidArgument("invalid gender")
		}
		profile.Gender = gender
	}
	if v, ok := data["birthDate"].(string); ok {
		birthDate, err := normalizeProfileBirthDate(v, time.Now())
		if err != nil {
			return nil, generated.AppErrorFromInvalidArgument(err.Error())
		}
		if birthDate == "" {
			profile.BirthDate = nil
		} else {
			profile.BirthDate = &birthDate
		}
	}
	if v, ok := data["regionTagRef"].(string); ok {
		regionTagRef := strings.TrimSpace(v)
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
	} else if v, ok := data["region"].(string); ok {
		if strings.TrimSpace(v) != "" {
			return nil, generated.AppErrorFromProfileInvalidRegion("regionTagRef is required")
		}
		profile.Region = ""
		profile.RegionCode = ""
	}
	if nextTags, ok := profileIdentityTagsFromUpdate(data, parsePgTextArray(profile.IdentityTags)); ok {
		if err := validateProfileTagRefs(nextTags); err != nil {
			return nil, generated.AppErrorFromProfileInvalidTagRef(err.Error())
		}
		occupationTagRef := firstTagWithPrefix(nextTags, profileOccupationRootTagRef+"/")
		interestRefs := interestTagRefs(nextTags)
		validator := s.profileTags
		if validator == nil {
			validator = PathProfileTagValidator{}
		}
		if err := validator.ValidateProfileTags(ctx, occupationTagRef, interestRefs); err != nil {
			return nil, generated.AppErrorFromProfileInvalidTagRef(err.Error())
		}
		profile.IdentityTags = encodeStringArray(nextTags)
	}

	// 任一资料字段变更都递增 profileVersion，供端侧增量校验与缓存失效。
	profile.ProfileVersion++
	if profile.ProfileVersion <= 0 {
		profile.ProfileVersion = 1
	}

	if err := s.profiles.Update(ctx, profile); err != nil {
		return nil, err
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

func (s *ProfileService) GetEditSnapshot(ctx context.Context, userID string, credentials []model.CredentialBinding) (_ map[string]any, err error) {
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

func profileIdentityTagsFromUpdate(data map[string]any, current []string) ([]string, bool) {
	if explicit, ok := stringSliceFromAny(data["identityTags"]); ok {
		return explicit, true
	}
	occupation, occupationTouched := data["occupationTagRef"].(string)
	interests, interestsTouched := stringSliceFromAny(data["interestTagRefs"])
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

func phoneCredentialSummary(credentials []model.CredentialBinding) map[string]any {
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

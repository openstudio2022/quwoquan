package application

import (
	"context"
	"fmt"
	"strings"

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
}

func NewProfileService(
	profiles userrepo.ProfileRepository,
	personas userrepo.PersonaRepository,
	settings userrepo.SettingRepository,
	pcache *cache.ProfileCache,
	scache *cache.SettingCache,
	events UserEventPublisher,
	sync UserSyncStream,
) *ProfileService {
	if events == nil {
		events = NoopUserEventPublisher()
	}
	return &ProfileService{
		profiles: profiles,
		personas: personas,
		settings: settings,
		pcache:   pcache,
		scache:   scache,
		events:   events,
		sync:     sync,
	}
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
	oldAvatarVersion := profile.AvatarVersion
	avatarChanged := false
	if v, ok := data["avatarUrl"].(string); ok {
		profile.AvatarURL = strings.TrimSpace(v)
		if strings.TrimSpace(profile.AvatarURL) != oldAvatarURL {
			avatarChanged = true
			profile.AvatarVersion++
			if profile.AvatarVersion <= 0 {
				profile.AvatarVersion = 1
			}
			profile.AvatarAssetID = fmt.Sprintf("ua_%s", userID)
		}
	}
	backgroundChanged := false
	if v, ok := data["backgroundUrl"].(string); ok {
		nb := strings.TrimSpace(v)
		if nb != strings.TrimSpace(profile.BackgroundURL) {
			profile.BackgroundURL = nb
			backgroundChanged = true
		}
	}
	if v, ok := data["bio"].(string); ok {
		profile.Bio = v
	}
	if v, ok := data["gender"].(string); ok {
		profile.Gender = v
	}
	if v, ok := data["birthDate"].(string); ok {
		profile.BirthDate = &v
	}
	if v, ok := data["region"].(string); ok {
		profile.Region = v
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
	if err := s.events.PublishUserEvent(ctx, event.UserProfileUpdated, userID, userID, map[string]any{
		"userId":             profile.UserID,
		"nickname":           profile.Nickname,
		"nicknameCustomized": profile.NicknameCustomized,
		"bio":                profile.Bio,
		"avatarUrl":          avatarURLWithVersion(profile.AvatarURL, profile.AvatarVersion),
		"backgroundUrl":      profile.BackgroundURL,
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

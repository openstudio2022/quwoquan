package application

import (
	"context"
	"strings"

	generated "quwoquan_service/services/user-service/generated/account/user_account"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

type FollowListProfileView struct {
	PersonaID         string
	UserHandle        string
	DisplayName       string
	AvatarURL         string
	ProfileVisibility string
}

// GetFollowListProfileViews 是粉丝/关注行专用的公开资料 reader。所需字段全在
// Persona 公开投影内，因此一页固定一次 PostgreSQL batch，不加载 owner 私有映射。
func (s *PersonaService) GetFollowListProfileViews(
	ctx context.Context,
	personaIDs []string,
) (map[string]FollowListProfileView, error) {
	ordered := uniqueNonBlank(personaIDs)
	views := make(map[string]FollowListProfileView, len(ordered))
	if len(ordered) == 0 {
		return views, nil
	}
	reader, ok := s.personas.(userrepo.PersonaBatchReader)
	if !ok {
		return nil, generated.AppErrorFromInternalError("follow list Persona batch reader unavailable")
	}
	personas, err := reader.FindManyByPersonaID(ctx, ordered)
	if err != nil {
		return nil, err
	}
	for _, personaID := range ordered {
		persona, found := personas[personaID]
		if !found || !canExposePublicPersona(&persona) {
			continue
		}
		views[personaID] = followListProfileView(persona)
	}
	return views, nil
}

func followListProfileView(persona model.Persona) FollowListProfileView {
	displayName := strings.TrimSpace(persona.DisplayName)
	if displayName == "" {
		displayName = persona.PersonaID
	}
	return FollowListProfileView{
		PersonaID:         persona.PersonaID,
		UserHandle:        resolvedPersonaUserHandle(&persona),
		DisplayName:       displayName,
		AvatarURL:         avatarURLWithVersion(strings.TrimSpace(persona.AvatarURL), resolvedPersonaAvatarVersion(&persona)),
		ProfileVisibility: personaProfileVisibility(&persona),
	}
}

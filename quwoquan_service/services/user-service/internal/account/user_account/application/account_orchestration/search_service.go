package application

import (
	"context"
	"strings"

	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

const (
	defaultSearchResultLimit = 20
	maxSearchResultLimit     = 50
)

// SearchService 只承载 user 域的社交关系检索；最近搜索（RecentSearchState）
// 已按 metadata 归属 search 域，由 search-service 对象专属 packet 承载。
type SearchService struct {
	profiles userrepo.UserProfileStore
	personas userrepo.PersonaReader
}

func NewSearchService(
	profiles userrepo.UserProfileStore,
	personas userrepo.PersonaReader,
) *SearchService {
	return &SearchService{
		profiles: profiles,
		personas: personas,
	}
}

func (s *SearchService) SearchSocialRelations(
	ctx context.Context,
	query string,
	limit int,
) ([]map[string]any, error) {
	normalized := strings.TrimSpace(query)
	if normalized == "" {
		return []map[string]any{}, nil
	}
	limit = clampSearchLimit(limit)

	results := make([]map[string]any, 0, limit)
	seen := make(map[string]struct{}, limit)

	appendProfile := func(profile *model.UserProfile, persona *model.Persona) {
		if profile == nil {
			return
		}
		view := buildPersonaProfileView(profile, persona)
		personaID := strings.TrimSpace(asString(view["personaId"]))
		if personaID == "" {
			personaID = strings.TrimSpace(profile.UserID)
		}
		if personaID == "" {
			return
		}
		if _, ok := seen[personaID]; ok {
			return
		}

		displayName := strings.TrimSpace(asString(view["displayName"]))
		if displayName == "" {
			displayName = strings.TrimSpace(profile.OwnerDisplayName)
		}
		if displayName == "" {
			displayName = strings.TrimSpace(profile.Nickname)
		}
		if displayName == "" {
			displayName = personaID
		}
		avatarVersion, _ := view["avatarVersion"].(int)
		userHandle := strings.TrimSpace(asString(view["userHandle"]))
		if userHandle == "" {
			return
		}

		results = append(results, map[string]any{
			"personaId":     personaID,
			"userHandle":    userHandle,
			"displayName":   displayName,
			"avatarUrl":     strings.TrimSpace(asString(view["avatarUrl"])),
			"avatarVersion": avatarVersion,
			"headline":      strings.TrimSpace(asString(view["bio"])),
			"chatAvailable": true,
		})
		seen[personaID] = struct{}{}
	}

	// 趣我圈号(userHandle)精确命中优先：用户输入完整趣我圈号时直接置顶，
	// 隐私 strict 分身不通过搜索暴露（与 GetPersonaProfile strict→404 一致）。
	if handle := normalizeUserHandleQuery(normalized); handle != "" {
		if persona, _ := s.personas.FindByUserHandle(ctx, handle); persona != nil &&
			!strings.EqualFold(strings.TrimSpace(persona.IsolationLevel), "strict") {
			if profile, _ := s.profiles.FindByID(ctx, persona.UserID); profile != nil {
				appendProfile(profile, persona)
			}
		}
	}

	// 昵称/资料模糊匹配补全。
	profiles, err := s.profiles.SearchProfiles(ctx, normalized, limit)
	if err != nil {
		return nil, err
	}
	for i := range profiles {
		if len(results) >= limit {
			break
		}
		persona, _ := s.personas.FindActiveByUserID(ctx, profiles[i].UserID)
		// semi/friends 只允许经完整趣我圈号等“已知路径”访问，不能进入
		// 昵称模糊发现；strict/private 在所有公开搜索路径都不可见。
		if persona != nil && !strings.EqualFold(
			strings.TrimSpace(persona.IsolationLevel),
			"open",
		) {
			continue
		}
		appendProfile(&profiles[i], persona)
	}
	return results, nil
}

// normalizeUserHandleQuery 清洗用户输入的趣我圈号，去掉可选 @ 前缀与空白；
// 不做大小写折叠（user_handle 系统分配，精确匹配）。
func normalizeUserHandleQuery(query string) string {
	handle := strings.TrimSpace(query)
	handle = strings.TrimPrefix(handle, "@")
	return strings.TrimSpace(handle)
}

func clampSearchLimit(limit int) int {
	if limit <= 0 {
		return defaultSearchResultLimit
	}
	if limit > maxSearchResultLimit {
		return maxSearchResultLimit
	}
	return limit
}

func asString(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	default:
		return ""
	}
}

package application

import (
	"context"
	"encoding/json"
	"sort"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
)

const (
	defaultSearchResultLimit = 20
	maxSearchResultLimit     = 50
	maxRecentSearchEntries   = 12
)

type SearchService struct {
	profiles    userrepo.ProfileRepository
	personas    userrepo.PersonaRepository
	recentStore rtredis.Client
}

func NewSearchService(
	profiles userrepo.ProfileRepository,
	personas userrepo.PersonaRepository,
	recentStore rtredis.Client,
) *SearchService {
	return &SearchService{
		profiles:    profiles,
		personas:    personas,
		recentStore: recentStore,
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
		view := buildSubAccountProfileView(profile, persona)
		subAccountID := strings.TrimSpace(asString(view["subAccountId"]))
		if subAccountID == "" {
			subAccountID = strings.TrimSpace(profile.UserID)
		}
		if subAccountID == "" {
			return
		}
		if _, ok := seen[subAccountID]; ok {
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
			displayName = subAccountID
		}
		avatarVersion, _ := view["avatarVersion"].(int)
		userHandle := firstNonEmpty(strings.TrimSpace(asString(view["userHandle"])), strings.TrimSpace(asString(view["username"])), subAccountID)

		results = append(results, map[string]any{
			"subAccountId":  subAccountID,
			"userHandle":    userHandle,
			"username":      firstNonEmpty(strings.TrimSpace(asString(view["username"])), strings.TrimSpace(profile.Nickname), subAccountID),
			"displayName":   displayName,
			"avatarUrl":     strings.TrimSpace(asString(view["avatarUrl"])),
			"avatarVersion": avatarVersion,
			"headline":      strings.TrimSpace(asString(view["bio"])),
			"chatAvailable": true,
		})
		seen[subAccountID] = struct{}{}
	}

	// 趣我圈号(userHandle)精确命中优先：用户输入完整趣我圈号时直接置顶，
	// 隐私 strict 分身不通过搜索暴露（与 GetSubAccountProfile strict→404 一致）。
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

func (s *SearchService) ListRecentSearches(ctx context.Context, userID string) ([]map[string]any, error) {
	return s.loadRecentSearchEntries(ctx, userID)
}

func (s *SearchService) UpsertRecentSearch(
	ctx context.Context,
	userID string,
	entryID string,
	payload map[string]any,
) (map[string]any, bool, error) {
	entry := normalizeRecentSearchEntry(entryID, payload)
	entries, err := s.loadRecentSearchEntries(ctx, userID)
	if err != nil {
		return nil, false, err
	}

	semanticKey := recentSearchSemanticKey(entry)
	created := true
	next := make([]map[string]any, 0, len(entries)+1)
	next = append(next, entry)
	for _, item := range entries {
		if strings.TrimSpace(asString(item["entryId"])) == entry["entryId"] {
			created = false
			continue
		}
		if recentSearchSemanticKey(item) == semanticKey {
			created = false
			continue
		}
		next = append(next, normalizeRecentSearchEntry(asString(item["entryId"]), item))
	}
	next = sortAndTrimRecentSearchEntries(next)
	if err := s.saveRecentSearchEntries(ctx, userID, next); err != nil {
		return nil, false, err
	}
	return entry, created, nil
}

func (s *SearchService) DeleteRecentSearch(ctx context.Context, userID string, entryID string) error {
	entries, err := s.loadRecentSearchEntries(ctx, userID)
	if err != nil {
		return err
	}
	next := make([]map[string]any, 0, len(entries))
	for _, item := range entries {
		if strings.TrimSpace(asString(item["entryId"])) == strings.TrimSpace(entryID) {
			continue
		}
		next = append(next, item)
	}
	return s.saveRecentSearchEntries(ctx, userID, next)
}

func (s *SearchService) ClearRecentSearches(ctx context.Context, userID string) error {
	if strings.TrimSpace(userID) == "" {
		return nil
	}
	return s.recentStore.Del(ctx, recentSearchKey(userID))
}

func (s *SearchService) loadRecentSearchEntries(ctx context.Context, userID string) ([]map[string]any, error) {
	if strings.TrimSpace(userID) == "" {
		return []map[string]any{}, nil
	}
	raw, err := s.recentStore.Get(ctx, recentSearchKey(userID))
	if err != nil || strings.TrimSpace(raw) == "" {
		return []map[string]any{}, nil
	}

	var decoded []map[string]any
	if err := json.Unmarshal([]byte(raw), &decoded); err != nil {
		return []map[string]any{}, nil
	}

	normalized := make([]map[string]any, 0, len(decoded))
	for _, item := range decoded {
		entry := normalizeRecentSearchEntry(asString(item["entryId"]), item)
		if strings.TrimSpace(asString(entry["query"])) == "" {
			continue
		}
		normalized = append(normalized, entry)
	}
	return sortAndTrimRecentSearchEntries(normalized), nil
}

func (s *SearchService) saveRecentSearchEntries(
	ctx context.Context,
	userID string,
	entries []map[string]any,
) error {
	if strings.TrimSpace(userID) == "" {
		return nil
	}
	normalized := sortAndTrimRecentSearchEntries(entries)
	data, err := json.Marshal(normalized)
	if err != nil {
		return err
	}
	return s.recentStore.Set(ctx, recentSearchKey(userID), string(data), 0)
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

func recentSearchKey(userID string) string {
	return "user:search:recent:" + strings.TrimSpace(userID)
}

func normalizeRecentSearchEntry(entryID string, payload map[string]any) map[string]any {
	query := strings.TrimSpace(asString(payload["query"]))
	scope := strings.TrimSpace(asString(payload["scope"]))
	if scope == "" {
		scope = "all"
	}
	facet := strings.TrimSpace(asString(payload["facet"]))
	normalizedID := strings.TrimSpace(entryID)
	if normalizedID == "" {
		normalizedID = "recent:" + recentSearchSemanticKey(map[string]any{
			"query": query,
			"scope": scope,
			"facet": facet,
		})
	}
	updatedAt := parseRecentSearchUpdatedAt(asString(payload["updatedAt"]))
	entry := map[string]any{
		"entryId":   normalizedID,
		"query":     query,
		"scope":     scope,
		"updatedAt": updatedAt.Format(time.RFC3339),
	}
	if facet != "" {
		entry["facet"] = facet
	}
	return entry
}

func sortAndTrimRecentSearchEntries(entries []map[string]any) []map[string]any {
	sort.SliceStable(entries, func(i, j int) bool {
		return parseRecentSearchUpdatedAt(asString(entries[i]["updatedAt"])).After(
			parseRecentSearchUpdatedAt(asString(entries[j]["updatedAt"])),
		)
	})
	if len(entries) > maxRecentSearchEntries {
		entries = entries[:maxRecentSearchEntries]
	}
	return entries
}

func recentSearchSemanticKey(entry map[string]any) string {
	return strings.ToLower(
		strings.TrimSpace(asString(entry["scope"])) + "::" +
			strings.TrimSpace(asString(entry["query"])) + "::" +
			strings.TrimSpace(asString(entry["facet"])),
	)
}

func parseRecentSearchUpdatedAt(raw string) time.Time {
	parsed, err := time.Parse(time.RFC3339, strings.TrimSpace(raw))
	if err == nil {
		return parsed
	}
	return time.Now().UTC()
}

func asString(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	default:
		return ""
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

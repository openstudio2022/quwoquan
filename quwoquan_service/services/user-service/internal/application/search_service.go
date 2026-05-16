package application

import (
	"context"
	"encoding/json"
	"sort"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
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
	profiles, err := s.profiles.SearchProfiles(ctx, normalized, limit)
	if err != nil {
		return nil, err
	}

	results := make([]map[string]any, 0, len(profiles))
	seen := make(map[string]struct{}, len(profiles))
	for _, profile := range profiles {
		persona, _ := s.personas.FindActiveByUserID(ctx, profile.UserID)
		view := buildSubAccountProfileView(&profile, persona)
		subAccountID := strings.TrimSpace(asString(view["subAccountId"]))
		if subAccountID == "" {
			subAccountID = strings.TrimSpace(profile.UserID)
		}
		if subAccountID == "" {
			continue
		}
		if _, ok := seen[subAccountID]; ok {
			continue
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

		results = append(results, map[string]any{
			"subAccountId":  subAccountID,
			"username":      firstNonEmpty(strings.TrimSpace(asString(view["username"])), strings.TrimSpace(profile.Nickname), subAccountID),
			"displayName":   displayName,
			"avatarUrl":     strings.TrimSpace(asString(view["avatarUrl"])),
			"headline":      strings.TrimSpace(asString(view["bio"])),
			"chatAvailable": true,
		})
		seen[subAccountID] = struct{}{}
	}
	return results, nil
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

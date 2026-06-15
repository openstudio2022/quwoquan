package application

import (
	"strings"
	"unicode"
)

func canonicalEntityID(homepageID string, explicit string) string {
	if trimmed := strings.TrimSpace(explicit); trimmed != "" {
		return trimmed
	}
	id := strings.TrimSpace(homepageID)
	if id == "" {
		return ""
	}
	homepageType := homepageTypeFromID(id)
	if homepageType == "" {
		return ""
	}
	trimmedID := strings.TrimSpace(strings.TrimPrefix(id, "homepage_"))
	prefix := homepageType + "_"
	if strings.HasPrefix(trimmedID, prefix) {
		trimmedID = strings.TrimPrefix(trimmedID, prefix)
	}
	trimmedID = strings.Trim(trimmedID, "_")
	if trimmedID == "" {
		return ""
	}
	return "entity:" + homepageType + ":" + trimmedID
}

func canonicalEntityIDFromTypeAndTitle(homepageType string, title string) string {
	normalizedType := strings.TrimSpace(homepageType)
	slug := canonicalSlug(title)
	if normalizedType == "" || slug == "" {
		return ""
	}
	return "entity:" + normalizedType + ":" + slug
}

func canonicalSlug(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}
	var b strings.Builder
	lastUnderscore := false
	for _, r := range trimmed {
		switch {
		case unicode.IsLetter(r) || unicode.IsDigit(r):
			b.WriteRune(unicode.ToLower(r))
			lastUnderscore = false
		case r == '_' || unicode.IsSpace(r) || r == '-' || r == '/':
			if !lastUnderscore {
				b.WriteRune('_')
				lastUnderscore = true
			}
		}
	}
	return strings.Trim(b.String(), "_")
}

func homepageTypeFromID(homepageID string) string {
	id := strings.TrimSpace(homepageID)
	switch {
	case strings.HasPrefix(id, "fixture_homepage_author"):
		return "author"
	case strings.HasPrefix(id, "fixture_homepage_circle"):
		return "circle"
	case strings.HasPrefix(id, "fixture_homepage_poi"):
		return "poi"
	case strings.HasPrefix(id, "fixture_homepage_university_"):
		return "university"
	case strings.HasPrefix(id, "fixture_homepage_travel_photo_"):
		return "travel_photo"
	case strings.HasPrefix(id, "homepage_sight_"):
		return "sight"
	case strings.HasPrefix(id, "homepage_restaurant_"):
		return "restaurant"
	case strings.HasPrefix(id, "homepage_hotel_"):
		return "hotel"
	case strings.HasPrefix(id, "homepage_vehicle_"):
		return "vehicle"
	default:
		return ""
	}
}

func (s *HomepageService) resolveHomepageLocked(rawID string) (*Homepage, bool) {
	if homepage, ok := s.homepages[strings.TrimSpace(rawID)]; ok {
		return homepage, true
	}
	candidates := homepageLookupCandidates(rawID)
	if len(candidates) == 0 {
		return nil, false
	}
	for _, homepage := range s.homepages {
		homepageCandidates := homepageLookupCandidates(homepage.ID)
		homepageCandidates[normalize(homepage.CanonicalEntityID)] = struct{}{}
		homepageCandidates[normalize("entity:homepage:"+homepage.ID)] = struct{}{}
		for _, candidate := range homepageDataEntityRefs(homepage) {
			homepageCandidates[candidate] = struct{}{}
		}
		for candidate := range candidates {
			if _, ok := homepageCandidates[candidate]; ok {
				return homepage, true
			}
		}
	}
	return nil, false
}

func homepageLookupCandidates(rawID string) map[string]struct{} {
	normalized := normalizeHomepageLookupID(rawID)
	if normalized == "" {
		return map[string]struct{}{}
	}
	candidates := map[string]struct{}{normalized: {}}
	parts := strings.FieldsFunc(normalized, func(r rune) bool { return r == '/' })
	if len(parts) > 0 {
		candidates[parts[len(parts)-1]] = struct{}{}
	}
	if strings.HasPrefix(normalized, "entity/homepage/") {
		candidates[strings.TrimPrefix(normalized, "entity/homepage/")] = struct{}{}
	}
	if strings.HasPrefix(normalized, "entity/") {
		candidates[strings.TrimPrefix(normalized, "entity/")] = struct{}{}
	}
	if strings.HasPrefix(normalized, "entities/") {
		candidates[strings.TrimPrefix(normalized, "entities/")] = struct{}{}
	}
	if idx := strings.LastIndex(normalized, ":homepage:"); idx >= 0 {
		candidates[normalized[idx+len(":homepage:"):]] = struct{}{}
	}
	if strings.HasPrefix(normalized, "entity:") {
		if idx := strings.LastIndex(normalized, ":"); idx >= 0 && idx+1 < len(normalized) {
			candidates[normalized[idx+1:]] = struct{}{}
		}
	}
	return candidates
}

func normalizeHomepageLookupID(rawID string) string {
	normalized := strings.TrimSpace(rawID)
	normalized = strings.ReplaceAll(normalized, "\\", "/")
	normalized = strings.TrimLeft(normalized, "/")
	return strings.ToLower(normalized)
}

func homepageDataEntityRefs(homepage *Homepage) []string {
	if homepage == nil {
		return nil
	}
	title := strings.TrimSpace(homepage.Title)
	if title == "" {
		return nil
	}
	entityDomain := "通用"
	entityType := "主页"
	switch strings.TrimSpace(homepage.HomepageType) {
	case "sight":
		entityDomain = "旅行"
		entityType = "景区"
	case "travel_photo":
		entityDomain = "旅行"
		entityType = "机位"
	case "hotel":
		entityDomain = "旅行"
		entityType = "住宿"
	case "restaurant":
		entityDomain = "旅行"
		entityType = "餐饮"
	case "university":
		entityDomain = "校园"
		entityType = "学校"
	}
	return []string{
		normalizeHomepageLookupID("entity/" + entityDomain + "/" + entityType + "/" + title),
		normalizeHomepageLookupID("entities/" + entityDomain + "/" + entityType + "/" + title),
		normalizeHomepageLookupID(entityDomain + "/" + entityType + "/" + title),
		normalizeHomepageLookupID(title),
	}
}

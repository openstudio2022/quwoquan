package recommendation

import "strings"

func normalizedObjectType(objectID, objectType string) string {
	normalized := strings.TrimSpace(objectType)
	if normalized != "" && normalized != "homepage" && normalized != "entity" {
		return normalized
	}
	id := strings.TrimSpace(objectID)
	switch {
	case strings.Contains(id, "_university_"):
		return "university"
	case strings.Contains(id, "_school_"):
		return "school"
	case strings.Contains(id, "_travel_route_"):
		return "route"
	case strings.Contains(id, "_travel_spot_") || strings.Contains(id, "_photo_spot_"):
		return "photo_spot"
	case strings.Contains(id, "_travel_gear_"):
		return "gear"
	case strings.Contains(id, "_travel_place_"), strings.HasPrefix(id, "homepage_sight_"), strings.HasPrefix(id, "fixture_homepage_poi"):
		return "sight"
	default:
		return normalized
	}
}

func objectDimension(objectType string) string {
	switch strings.TrimSpace(objectType) {
	case "university", "school":
		return "identity"
	case "travel_photo", "sight", "place", "route", "photo_spot", "gear", "homepage":
		return "location"
	case "circle":
		return "relationship"
	default:
		return "interest"
	}
}

func objectLabel(objectType string) string {
	switch strings.TrimSpace(objectType) {
	case "university", "school":
		return "同校"
	case "travel_photo", "sight", "place", "route", "photo_spot", "gear", "homepage":
		return "同游"
	case "circle":
		return "同圈"
	default:
		return "同好"
	}
}

func concreteObjectDisplayName(objectID, objectType string) string {
	raw := strings.TrimSpace(objectID)
	if raw == "" {
		return ""
	}
	parts := strings.FieldsFunc(raw, func(r rune) bool {
		return r == '/' || r == ':' || r == '|'
	})
	candidate := raw
	if len(parts) > 0 {
		candidate = strings.TrimSpace(parts[len(parts)-1])
	}
	switch candidate {
	case "", objectLabel(objectType), "这里", "这个对象":
		return ""
	}
	if strings.Contains(candidate, "_") {
		return ""
	}
	return candidate
}

func relationActionType(objectType string) string {
	switch strings.TrimSpace(objectType) {
	case "user", "person":
		return "open_profile"
	default:
		return "view_object"
	}
}

// objectKindForObjectType 将开放 objectType 收口到闭集 objectKind（人/圈/校/地/企角标真相源）。
func objectKindForObjectType(objectType string) string {
	switch strings.TrimSpace(objectType) {
	case "user", "person":
		return "person"
	case "circle":
		return "circle"
	case "university", "school":
		return "school"
	case "route":
		return "route"
	case "photo_spot":
		return "photo_spot"
	case "gear":
		return "gear"
	case "sight", "travel_photo", "place", "entity", "homepage":
		return "place"
	case "brand", "enterprise", "company":
		return "enterprise"
	default:
		return ""
	}
}

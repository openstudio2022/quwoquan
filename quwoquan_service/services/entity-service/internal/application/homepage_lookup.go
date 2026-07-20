package application

import (
	"strings"

	homepagemodel "quwoquan_service/services/entity-service/internal/domain/homepage/model"
)

func canonicalEntityID(homepageID string, explicit string) string {
	if value := strings.TrimSpace(explicit); value != "" {
		return value
	}
	id := strings.TrimSpace(homepageID)
	homepageType := ""
	for _, candidate := range []string{
		"vehicle", "hotel", "restaurant", "sight", "university", "travel_photo",
	} {
		if strings.HasPrefix(id, "homepage_"+candidate+"_") {
			homepageType = candidate
			break
		}
	}
	if homepageType == "" {
		return ""
	}
	slug := strings.TrimPrefix(id, "homepage_"+homepageType+"_")
	if slug == "" {
		return ""
	}
	return "entity:" + homepageType + ":" + slug
}

func canonicalEntityIDFromTypeAndTitle(homepageType string, title string) string {
	return homepagemodel.CanonicalEntityID(homepageType, title)
}

func objectPageTemplate(homepageType string, explicit string) string {
	if value := strings.TrimSpace(explicit); value != "" {
		return value
	}
	switch strings.TrimSpace(homepageType) {
	case "university":
		return "campus"
	case "travel_photo", "sight", "museum", "heritage_site", "ancient_town",
		"religious_site", "check_in_spot", "natural_landscape", "park", "hot_spring", "theme_park":
		return "travel_photo"
	default:
		return "standard"
	}
}

func nonEmpty(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return strings.TrimSpace(value)
}

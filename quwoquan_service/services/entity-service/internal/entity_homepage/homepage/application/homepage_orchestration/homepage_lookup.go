package application

import (
	"strings"

	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
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
	return homepagemodel.ObjectPageTemplate(homepageType, explicit)
}

func nonEmpty(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return strings.TrimSpace(value)
}

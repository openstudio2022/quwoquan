package application

import (
	"strconv"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
)

// circleSearchCategoryID derives the facet/category id used by both the native
// SearchCircles surface and the search-index projection: explicit category, then
// domain, then the "all" bucket. Keeping it in one place stops the index and the
// native facets from disagreeing.
func circleSearchCategoryID(circle model.Circle) string {
	categoryID := strings.TrimSpace(circle.Category)
	if categoryID == "" {
		categoryID = strings.TrimSpace(circle.DomainID)
	}
	if categoryID == "" {
		categoryID = "all"
	}
	return categoryID
}

// CircleSearchEligible mirrors the discoverable set the native circle search
// exposes by default: active + public circles. The ES index must contain exactly
// this set so ES-mode results match the native surface.
func CircleSearchEligible(circle model.Circle) bool {
	return circle.Status == model.CircleStatusActive &&
		circle.Visibility == model.CircleVisibilityPublic
}

// ProjectCircleToSearchDocument projects a circle into the unified search
// Document (objectType circle.circle, target derived as "circle"). It is the
// single source of truth for circle→Document mapping, shared by the native
// SearchCircles surface and the ES search-index projector/backfill so the two
// never diverge.
func ProjectCircleToSearchDocument(circle model.Circle) rtsearch.Document {
	return rtsearch.Document{
		ObjectType:   rtsearch.ObjectTypeCircle,
		ObjectID:     circle.ID,
		Title:        circle.Name,
		Summary:      circle.Description,
		SourceDomain: "circle",
		ContentType:  string(circle.Kind),
		Visibility:   string(circle.Visibility),
		BadgeLabel:   "圈子",
		Tags:         circle.Tags,
		Popularity:   float64(circle.MemberCount + circle.PostCount),
		Freshness:    circle.UpdatedAt,
		Fields: map[string]string{
			"circleId":            circle.ID,
			"circleName":          circle.Name,
			"coverUrl":            circle.CoverUrl,
			"categoryId":          circleSearchCategoryID(circle),
			"subCategory":         circle.SubCategory,
			"domainId":            circle.DomainID,
			"kind":                string(circle.Kind),
			"displaySubjectType":  string(circle.DisplaySubjectType),
			"memberCount":         strconv.FormatInt(circle.MemberCount, 10),
			"postCount":           strconv.FormatInt(circle.PostCount, 10),
			"linkedHomepageId":    circle.LinkedHomepageID,
			"linkedHomepageType":  string(circle.LinkedHomepageType),
			"linkedHomepageTitle": circle.LinkedHomepageTitle,
		},
	}
}

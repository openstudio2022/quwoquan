package post

import (
	"strings"

	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
)

func NormalizeSearchMatchedField(matchedField string, post postmodel.Post) string {
	switch strings.TrimSpace(matchedField) {
	case "tags":
		return "tagRefs"
	case "entities":
		return "entityRefs"
	case "summary":
		if strings.TrimSpace(post.Summary) == "" && strings.TrimSpace(post.Body) != "" {
			return "body"
		}
	}
	return matchedField
}

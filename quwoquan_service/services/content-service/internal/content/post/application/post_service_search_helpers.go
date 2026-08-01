package post

import (
	"strings"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
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
